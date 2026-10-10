"""On-demand search per campaign, and pool freshness.

Measured 2026-10-10: the pre-collected pool had 2 live brand-head roles and 0 marketing heads
in India, because the search sources (LinkedIn jobs, hiring posts, JobSpy) only ran a fixed
keyword list. A campaign's own titles and locations now drive a search the moment it starts,
and daily after. Separately, 1,332 "live" rows had not been seen for over a week (feeds that
never return a full listing, so nothing could delist them) and 26% were posted 90+ days ago.
"""
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import models
import workers.jobs as wj
from campaigns import MAX_POSTING_AGE_DAYS, _in_bounds
from tests.test_campaigns import _auth, _campaign, _client, _job, _profile


def _li_job(n, title="Brand Head", location="Mumbai, India", source="linkedin_external"):
    return {"source": source, "external_id": f"li-{n}", "company": f"Co{n}", "title": title,
            "location": location, "apply_url": f"https://co{n}.example/apply", "description": "d",
            "remote": False}


@contextmanager
def _offline(db, **overrides):
    stubs = {
        "fetch_linkedin_jobs": MagicMock(return_value=[]),
        "fetch_linkedin_posts": MagicMock(return_value=[]),
        "fetch_jobspy_jobs": MagicMock(return_value=[]),
        "backfill_job_embeddings": MagicMock(return_value=0),
        "build_matches": MagicMock(return_value=[]),
        "get_queue": MagicMock(),
        "judge_campaign_titles": MagicMock(return_value={"judged": 0}),
        **overrides,
    }
    scope = MagicMock()
    scope.return_value.__enter__.return_value = db
    scope.return_value.__exit__.return_value = False
    patches = [patch(f"workers.jobs.{n}", s) for n, s in stubs.items()]
    patches += [patch("workers.jobs.session_scope", scope), patch("workers.jobs.time.sleep")]
    for p in patches:
        p.start()
    try:
        yield stubs
    finally:
        for p in patches:
            p.stop()


# --- the plan: what one campaign searches for ------------------------------------------

def test_plan_caps_titles_and_locations_and_drops_blanks(db_session):
    c = _campaign(db_session, _profile(db_session), roles=["Brand Head", " ", "brand head", "CMO",
                                                          "Marketing Director", "VP Marketing"],
                  locations=["Mumbai", "Bengaluru", "Delhi"], remote_only=False)
    roles, locations = wj.campaign_search_plan(c)
    assert roles == ["Brand Head", "CMO", "Marketing Director"]
    assert locations == ["Mumbai", "Bengaluru"]


def test_plan_without_locations_uses_the_default_market(db_session):
    c = _campaign(db_session, _profile(db_session), roles=["Designer"], locations=[])
    assert wj.campaign_search_plan(c)[1] == list(wj.conn_config.LINKEDIN_JOB_LOCATIONS)


# --- the task ---------------------------------------------------------------------------

def test_search_saves_what_it_finds_then_runs_the_campaign(db_session):
    c = _campaign(db_session, _profile(db_session), roles=["Brand Head"], locations=["Mumbai"],
                  remote_only=False)
    with _offline(db_session, fetch_linkedin_jobs=MagicMock(return_value=[_li_job(1)])) as s:
        result = wj.campaign_search_task(c.id)
    assert result["inserted"] == 1
    s["fetch_linkedin_jobs"].assert_called_once_with("Brand Head", "Mumbai",
                                                     rows=wj.CAMPAIGN_SEARCH_ROWS)
    assert db_session.query(models.Job).filter_by(external_id="li-1").one().title == "Brand Head"
    # The new in-bounds job is embedded so it can match now, not after the backlog gets to it.
    assert s["backfill_job_embeddings"].call_args.kwargs["only_ids"]
    enqueued = s["get_queue"].return_value.enqueue.call_args
    assert enqueued.args[0] is wj.run_campaign_task
    assert enqueued.kwargs["kwargs"]["campaign_id"] == c.id
    run = db_session.query(models.ConnectorRun).filter_by(source="linkedin").one()
    assert run.token == f"campaign-{c.id}" and run.fetched == 1


def test_one_failing_source_does_not_cost_the_others(db_session):
    c = _campaign(db_session, _profile(db_session), roles=["Designer"], locations=["Pune"],
                  remote_only=False)
    with _offline(db_session,
                  fetch_linkedin_jobs=MagicMock(side_effect=RuntimeError("apify down")),
                  fetch_jobspy_jobs=MagicMock(return_value=[_li_job(2, "Product Designer", "Pune",
                                                                    "jobspy_glassdoor")])):
        result = wj.campaign_search_task(c.id)
    assert result["inserted"] == 1


def test_a_paused_or_missing_campaign_searches_nothing(db_session):
    c = _campaign(db_session, _profile(db_session), roles=["Designer"],
                  status=models.CampaignStatus.paused)
    with _offline(db_session) as s:
        assert wj.campaign_search_task(c.id)["skipped"] is True
        assert wj.campaign_search_task(str(uuid.uuid4()))["skipped"] is True
    s["fetch_linkedin_jobs"].assert_not_called()


def test_sources_the_campaign_excluded_are_not_searched(db_session):
    c = _campaign(db_session, _profile(db_session), roles=["Designer"], locations=["Pune"],
                  sources=["greenhouse"], remote_only=False)
    with _offline(db_session) as s:
        wj.campaign_search_task(c.id)
    s["fetch_linkedin_jobs"].assert_not_called()
    s["fetch_linkedin_posts"].assert_not_called()
    s["fetch_jobspy_jobs"].assert_not_called()


# --- triggers -----------------------------------------------------------------------------

def _start(client, headers, **body):
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    created = client.post("/campaigns", headers=headers, json={
        "profile_id": profile["id"], "name": "Brand", "roles": ["Brand Head"],
        "locations": ["Mumbai"], **body}).json()
    return created["id"]


def test_starting_a_campaign_queues_its_search():
    client, _ = _client()
    headers = _auth(client, "brand@example.com")
    cid = _start(client, headers)
    queue = MagicMock()
    with patch("main.get_queue", return_value=queue) as get_queue:
        assert client.patch(f"/campaigns/{cid}", headers=headers,
                            json={"status": "active"}).status_code == 200
    get_queue.assert_called_with(wj.BACKGROUND_QUEUE)
    call = queue.enqueue.call_args
    assert call.args[0] is wj.campaign_search_task and call.kwargs["kwargs"] == {"campaign_id": cid}


def test_changing_titles_on_an_active_campaign_searches_again_but_pausing_does_not():
    client, _ = _client()
    headers = _auth(client, "brand2@example.com")
    cid = _start(client, headers)
    queue = MagicMock()
    with patch("main.get_queue", return_value=queue):
        client.patch(f"/campaigns/{cid}", headers=headers, json={"status": "active"})
        client.patch(f"/campaigns/{cid}", headers=headers, json={"roles": ["CMO"]})
        client.patch(f"/campaigns/{cid}", headers=headers, json={"status": "paused"})
        client.patch(f"/campaigns/{cid}", headers=headers, json={"daily_cap": 4})
    assert queue.enqueue.call_count == 2


def test_a_queue_outage_never_fails_starting_the_campaign():
    client, _ = _client()
    headers = _auth(client, "brand3@example.com")
    cid = _start(client, headers)
    with patch("main.get_queue", side_effect=ConnectionError("redis down")):
        r = client.patch(f"/campaigns/{cid}", headers=headers, json={"status": "active"})
    assert r.status_code == 200 and r.json()["status"] == "active"


def test_the_daily_refresh_is_one_union_search_deduplicated_across_users(db_session):
    me, you = _profile(db_session, "me@x.com"), _profile(db_session, "you@x.com")
    _campaign(db_session, me, roles=["Brand Head"], locations=["Mumbai"], remote_only=False)
    _campaign(db_session, you, roles=["brand head", "CMO"], locations=["Mumbai"], remote_only=False)
    _campaign(db_session, you, name="paused", roles=["Designer"], locations=["Pune"],
              status=models.CampaignStatus.paused)
    with _offline(db_session) as s:
        result = wj.refresh_campaign_searches_task()
    pairs = [c.args for c in s["fetch_linkedin_jobs"].call_args_list]
    assert pairs == [("Brand Head", "Mumbai"), ("CMO", "Mumbai")]
    assert sorted(s["fetch_linkedin_posts"].call_args.args[0]) == ["hiring Brand Head Mumbai",
                                                                  "hiring CMO Mumbai"]
    assert result["pairs"] == 2


def test_one_user_cannot_take_more_than_their_share_of_the_union(db_session):
    p = _profile(db_session)
    _campaign(db_session, p, name="a", roles=["A1", "A2", "A3"], locations=["X", "Y"], remote_only=False)
    _campaign(db_session, p, name="b", roles=["B1", "B2", "B3"], locations=["X", "Y"], remote_only=False)
    with _offline(db_session) as s:
        wj.refresh_campaign_searches_task()
    assert s["fetch_linkedin_jobs"].call_count == wj.CAMPAIGN_SEARCH_PAIRS_PER_USER


# --- freshness --------------------------------------------------------------------------

def test_live_rows_not_seen_for_a_week_expire_and_search_rows_get_two(db_session):
    now = datetime.utcnow()
    feed_old = _job(db_session, 1, source="arbeitnow", last_seen_at=now - timedelta(days=8))
    feed_new = _job(db_session, 2, source="arbeitnow", last_seen_at=now - timedelta(days=2))
    search_9d = _job(db_session, 3, source="linkedin_external", last_seen_at=now - timedelta(days=9))
    search_15d = _job(db_session, 4, source="jobspy_glassdoor", last_seen_at=now - timedelta(days=15))
    assert wj._expire_unseen(db_session) == 2
    db_session.commit()
    live = {j.id for j in db_session.query(models.Job).filter(models.Job.delisted_at.is_(None))}
    assert live == {feed_new.id, search_9d.id}
    assert feed_old.id not in live and search_15d.id not in live


def test_the_discovery_coordinator_expires_stale_rows(db_session):
    _job(db_session, 1, source="arbeitnow", last_seen_at=datetime.utcnow() - timedelta(days=30))
    with _offline(db_session), patch("workers.jobs._discovery_units", return_value=[]):
        wj.discover_jobs_task()
    assert db_session.query(models.Job).one().delisted_at is not None


def test_campaigns_skip_postings_older_than_the_age_limit(db_session):
    c = _campaign(db_session, _profile(db_session), roles=["Backend"])
    now = datetime.utcnow()
    fresh = _job(db_session, 1, posted_at=now - timedelta(days=5))
    old = _job(db_session, 2, posted_at=now - timedelta(days=MAX_POSTING_AGE_DAYS + 1))
    unknown = _job(db_session, 3, posted_at=None)
    ids = {j.id for j in _in_bounds(db_session.query(models.Job), c)}
    assert ids == {fresh.id, unknown.id}
    assert old.id not in ids


def test_a_campaign_can_opt_back_in_to_older_postings(db_session):
    c = _campaign(db_session, _profile(db_session), roles=["Backend"], include_older_postings=True)
    old = _job(db_session, 1, posted_at=datetime.utcnow() - timedelta(days=MAX_POSTING_AGE_DAYS + 30))
    assert [j.id for j in _in_bounds(db_session.query(models.Job), c)] == [old.id]


def test_the_older_postings_switch_is_editable_and_off_by_default():
    client, _ = _client()
    headers = _auth(client, "older@example.com")
    cid = _start(client, headers)
    assert client.get(f"/campaigns/{cid}", headers=headers).json()["include_older_postings"] is False
    r = client.patch(f"/campaigns/{cid}", headers=headers, json={"include_older_postings": True})
    assert r.status_code == 200 and r.json()["include_older_postings"] is True


def test_the_llm_judges_titles_before_embedding_so_accepted_jobs_get_embedded(db_session):
    c = _campaign(db_session, _profile(db_session), roles=["Brand Head"], locations=["Mumbai"],
                  remote_only=False)
    order = []
    judge = MagicMock(side_effect=lambda cid, **kw: order.append("judge") or {"judged": 1})
    embed = MagicMock(side_effect=lambda *a, **k: order.append("embed") or 0)
    with _offline(db_session, judge_campaign_titles=judge, backfill_job_embeddings=embed,
                  fetch_linkedin_jobs=MagicMock(return_value=[_li_job(9)])):
        wj.campaign_search_task(c.id)
    assert judge.call_args.args == (c.id,)
    assert order[0] == "judge"


def test_the_daily_refresh_judges_every_active_campaign(db_session):
    p = _profile(db_session)
    a = _campaign(db_session, p, roles=["Designer"], locations=["Pune"], remote_only=False)
    _campaign(db_session, p, name="paused", roles=["CMO"], status=models.CampaignStatus.paused)
    with _offline(db_session) as s:
        wj.refresh_campaign_searches_task()
    assert [c.args[0] for c in s["judge_campaign_titles"].call_args_list] == [a.id]
