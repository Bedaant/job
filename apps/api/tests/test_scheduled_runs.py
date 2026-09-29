"""ADR-015 "approve once, Maggie works for you" — the scheduled campaign sweep.

No request, no user: the sweep runs on the owner DB role, so every query it
makes has to be scoped per campaign/profile by hand. These tests pin that, the
daily cap on the scheduled path, per-campaign failure isolation, and the one
activity event per scheduled run.
"""
from unittest.mock import MagicMock, patch

from rq.job import validate_job_id

import main
import models
from database import get_db
from tests.test_campaigns import _auth, _campaign, _client, _job, _match, _profile, _session

import workers.jobs as jobs
import workers.run_scheduler as run_scheduler

VEC_A = [1.0] + [0.0] * 511


def _wire(db, mock_scope, mock_queue, mock_redis):
    """Point the worker at the test DB; capture enqueues instead of using Redis."""
    mock_scope.return_value.__enter__.return_value = db
    mock_scope.return_value.__exit__.return_value = False
    redis = MagicMock()
    redis.set.return_value = True
    mock_redis.return_value = redis
    return mock_queue.return_value.enqueue


def _drain(enqueue):
    """Run every enqueued job inline, like the worker would."""
    for call in enqueue.call_args_list:
        call.args[0](**call.kwargs["kwargs"])
    enqueue.reset_mock()


def _profile_with_centroid(db, email, centroid):
    profile = _profile(db, email)
    profile.fact_centroid = centroid
    db.commit()
    return profile


@patch("campaigns.prepare_application_for_review")
@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.get_queue")
@patch("workers.jobs.session_scope")
def test_sweep_builds_matches_and_runs_every_active_campaign(mock_scope, mock_queue, mock_redis, _prep):
    db = _session()
    active = _campaign(db, _profile_with_centroid(db, "a@x.com", VEC_A))
    _campaign(db, _profile_with_centroid(db, "p@x.com", VEC_A), status=models.CampaignStatus.paused)
    _campaign(db, _profile_with_centroid(db, "d@x.com", VEC_A), status=models.CampaignStatus.draft)
    _job(db, 1, embedding=VEC_A)
    enqueue = _wire(db, mock_scope, mock_queue, mock_redis)

    result = jobs.sweep_campaigns_task()

    # Matches were built without anyone opening GET /matches...
    assert db.query(models.Match).filter(models.Match.profile_id == active.profile_id).count() == 1
    # ...and only the active campaign was enqueued, with an id rq accepts.
    assert result["enqueued"] == [active.id]
    call = enqueue.call_args
    assert call.args[0] is jobs.run_campaign_task
    assert call.kwargs["unique"] is True
    validate_job_id(call.kwargs["job_id"])
    assert call.kwargs["kwargs"] == {"campaign_id": active.id, "run_id": call.kwargs["job_id"], "scheduled": True}

    _drain(enqueue)
    assert db.query(models.Application).filter(models.Application.campaign_id == active.id).count() == 1


@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.get_queue")
@patch("workers.jobs.session_scope")
def test_sweep_job_id_is_stable_within_a_window(mock_scope, mock_queue, mock_redis):
    """Same window → same id, so unique=True + the Redis claim dedupe a
    re-fired sweep, the same way the manual run's per-minute id does."""
    db = _session()
    _campaign(db, _profile(db))
    enqueue = _wire(db, mock_scope, mock_queue, mock_redis)

    with patch("workers.jobs.time.time", return_value=7200.0):
        jobs.sweep_campaigns_task()
        jobs.sweep_campaigns_task()
    with patch("workers.jobs.time.time", return_value=7200.0 + jobs.CAMPAIGN_SWEEP_INTERVAL_SECONDS):
        jobs.sweep_campaigns_task()

    ids = [c.kwargs["job_id"] for c in enqueue.call_args_list]
    assert ids[0] == ids[1] != ids[2]


@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.get_queue")
@patch("workers.jobs.session_scope")
def test_sweep_skips_matching_gracefully_without_facts_or_embeddings(mock_scope, mock_queue, mock_redis):
    """No fact centroid (no facts) or no job embeddings (no VOYAGE_API_KEY):
    build_matches returns nothing, the sweep still runs the campaign on
    whatever matches already exist, and nothing raises."""
    db = _session()
    no_facts = _campaign(db, _profile(db, "nofacts@x.com"))
    no_embeddings = _campaign(db, _profile_with_centroid(db, "noemb@x.com", VEC_A))
    _job(db, 1)  # embedding=None, as when VOYAGE_API_KEY is absent
    _wire(db, mock_scope, mock_queue, mock_redis)

    result = jobs.sweep_campaigns_task()

    assert sorted(result["enqueued"]) == sorted([no_facts.id, no_embeddings.id])
    assert result["failed"] == []
    assert db.query(models.Match).count() == 0


@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.get_queue")
@patch("workers.jobs.session_scope")
def test_one_campaign_failing_does_not_stop_the_others(mock_scope, mock_queue, mock_redis):
    db = _session()
    broken = _campaign(db, _profile(db, "broken@x.com"))
    fine = _campaign(db, _profile(db, "fine@x.com"))
    _wire(db, mock_scope, mock_queue, mock_redis)

    real_build = jobs.build_matches

    def build(db_, profile):
        if profile.id == broken.profile_id:
            raise RuntimeError("boom")
        return real_build(db_, profile)

    with patch("workers.jobs.build_matches", side_effect=build):
        result = jobs.sweep_campaigns_task()

    assert result["failed"] == [broken.id]
    assert result["enqueued"] == [fine.id]


@patch("campaigns.prepare_application_for_review")
@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.get_queue")
@patch("workers.jobs.session_scope")
def test_scheduled_sweeps_never_exceed_the_daily_cap(mock_scope, mock_queue, mock_redis, _prep):
    """Many sweeps in one UTC day (distinct windows, so no id dedupe, and the
    Redis claim always succeeds): the cap in run_campaign still holds."""
    db = _session()
    profile = _profile(db)
    campaign = _campaign(db, profile, daily_cap=2)
    for n in range(10):
        _match(db, profile, _job(db, n))
    enqueue = _wire(db, mock_scope, mock_queue, mock_redis)

    for window in range(5):
        with patch("workers.jobs.time.time", return_value=float(window * jobs.CAMPAIGN_SWEEP_INTERVAL_SECONDS)):
            jobs.sweep_campaigns_task()
        _drain(enqueue)

    assert db.query(models.Application).filter(models.Application.campaign_id == campaign.id).count() == 2


@patch("campaigns.prepare_application_for_review")
@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.get_queue")
@patch("workers.jobs.session_scope")
def test_sweep_never_mixes_users_data(mock_scope, mock_queue, mock_redis, _prep):
    """Owner role, no RLS context: each user's matches, applications and events
    must come only from their own profile."""
    db = _session()
    pa = _profile_with_centroid(db, "alice@x.com", VEC_A)
    pb = _profile_with_centroid(db, "bob@x.com", VEC_A)
    ca = _campaign(db, pa, daily_cap=5)
    cb = _campaign(db, pb, daily_cap=5)
    # Both match the same job; Bob already has a match row for it, Alice doesn't.
    shared = _job(db, "shared", embedding=VEC_A)
    _match(db, pb, shared, score=95)
    enqueue = _wire(db, mock_scope, mock_queue, mock_redis)

    jobs.sweep_campaigns_task()
    _drain(enqueue)

    for profile, campaign in ((pa, ca), (pb, cb)):
        apps = db.query(models.Application).filter(models.Application.campaign_id == campaign.id).all()
        assert apps and all(a.profile_id == profile.id for a in apps)
    # One match per profile — Bob's row wasn't reused for Alice or vice versa.
    assert sorted(m.profile_id for m in db.query(models.Match)) == sorted([pa.id, pb.id])
    for event in db.query(models.Event):
        cid = (event.payload or {}).get("campaign_id")
        if cid:
            owner = pa.user_id if cid == ca.id else pb.user_id
            assert event.user_id == owner


@patch("campaigns.prepare_application_for_review")
@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.session_scope")
def test_scheduled_run_writes_one_campaign_event(mock_scope, mock_redis, _prep):
    db = _session()
    profile = _profile(db)
    campaign = _campaign(db, profile, daily_cap=5)
    for n in range(3):
        _match(db, profile, _job(db, n))
    _wire(db, mock_scope, MagicMock(), mock_redis)

    jobs.run_campaign_task(campaign.id, run_id="r1", scheduled=True)
    jobs.run_campaign_task(campaign.id, run_id="r2")  # a manual run: no scheduled event

    events = db.query(models.Event).filter(models.Event.type == "campaign.scheduled_run").all()
    assert len(events) == 1
    assert events[0].user_id == profile.user_id
    assert events[0].payload["campaign_id"] == campaign.id
    assert events[0].payload["created"] == 3


def test_activity_maps_scheduled_run():
    client, SessionLocal = _client()
    headers = _auth(client, "sched@example.com")
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.email == "sched@example.com").one()
    from events.outbox import write_event
    write_event(db, user.id, "campaign.scheduled_run",
                {"campaign_id": "c1", "created": 2, "reason": "Started 2 applications."})
    db.commit()

    items = client.get("/activity", headers=headers).json()
    main.app.dependency_overrides.pop(get_db, None)

    assert items[0]["type"] == "campaign.scheduled_run"
    assert items[0]["title"] == "Ran on schedule"
    assert items[0]["detail"] == "Started 2 applications."


@patch("workers.run_scheduler.get_redis_connection")
@patch("workers.run_scheduler.Scheduler")
def test_scheduler_registers_discovery_and_campaign_sweep(mock_scheduler_cls, _redis):
    scheduler = mock_scheduler_cls.return_value
    scheduler.get_jobs.return_value = []

    run_scheduler.start_scheduler()

    registered = {c.kwargs["func"]: c.kwargs["interval"] for c in scheduler.schedule.call_args_list}
    assert registered == {
        jobs.discover_jobs_task: run_scheduler.DISCOVERY_INTERVAL_SECONDS,
        jobs.sweep_campaigns_task: jobs.CAMPAIGN_SWEEP_INTERVAL_SECONDS,
        jobs.sweep_form_plans_task: 3600,
        jobs.embed_backlog_task: jobs.EMBED_BACKLOG_INTERVAL_SECONDS,
        run_scheduler.daily_digest_task: run_scheduler.DIGEST_INTERVAL_SECONDS,
    }


@patch("workers.run_scheduler.get_redis_connection")
@patch("workers.run_scheduler.Scheduler")
def test_scheduler_restart_cancels_both_recurring_jobs(mock_scheduler_cls, _redis):
    scheduler = mock_scheduler_cls.return_value
    old = [MagicMock(func_name="workers.jobs.discover_jobs_task"),
           MagicMock(func_name="workers.jobs.sweep_campaigns_task"),
           MagicMock(func_name="something.else")]
    scheduler.get_jobs.return_value = old

    run_scheduler.start_scheduler()

    assert [c.args[0] for c in scheduler.cancel.call_args_list] == old[:2]


@patch("campaigns.prepare_application_for_review")
@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.session_scope")
def test_a_scheduled_run_with_nothing_new_stays_out_of_the_activity_list(mock_scope, mock_redis, _prep):
    """Hourly sweeps would otherwise add up to 24 "Nothing new" rows a day per
    campaign and bury what Maggie actually did."""
    db = _session()
    profile = _profile(db)
    campaign = _campaign(db, profile, daily_cap=5)
    _wire(db, mock_scope, MagicMock(), mock_redis)

    jobs.run_campaign_task(campaign.id, run_id="r1", scheduled=True)

    assert db.query(models.Event).filter(models.Event.type == "campaign.scheduled_run").count() == 0


def test_redis_connection_is_one_shared_client_per_process():
    # A new client (and pool) per call leaked sockets in the long-lived worker
    # until Redis Cloud's 30-client cap refused every connection.
    from workers.jobs import get_queue, get_redis_connection

    assert get_redis_connection() is get_redis_connection()
    assert get_queue().connection is get_redis_connection()


def test_scheduler_survives_a_redis_blip():
    # Live: a DNS blip (getaddrinfo failed) killed the scheduler for good; nothing
    # was scheduled again until someone restarted it by hand.
    from redis.exceptions import ConnectionError as RedisConnectionError

    runs = MagicMock(side_effect=[RedisConnectionError("getaddrinfo failed"),
                                  RedisConnectionError("getaddrinfo failed"), KeyboardInterrupt])
    start = MagicMock(return_value=MagicMock(run=runs))
    sleep = MagicMock()
    try:
        run_scheduler.run_forever(start=start, sleep=sleep)
    except KeyboardInterrupt:
        pass
    assert start.call_count == 3  # re-registered after each blip
    assert [c.args[0] for c in sleep.call_args_list] == [5, 10]


@patch("workers.jobs.backfill_job_embeddings", return_value=6)
@patch("workers.jobs.session_scope")
def test_embed_backlog_task_runs_one_backfill_pass(mock_scope, mock_backfill):
    """Live (2026-09-29): on Voyage's free tier one pass embeds ~6 jobs before the
    minute's cap, and discovery ran it once an hour while adding ~100 jobs. A pass
    every couple of minutes clears the backlog (~180/hour, inside 3 RPM)."""
    assert jobs.embed_backlog_task() == {"embedded": 6}
    mock_backfill.assert_called_once()
    assert 60 <= jobs.EMBED_BACKLOG_INTERVAL_SECONDS <= 300


@patch("workers.jobs.session_scope")
def test_embed_backlog_task_embeds_jobs_the_active_campaigns_want_first(mock_scope, db_session):
    """Live: 1,556 jobs waited and newest-first spent the free tier on roles nobody's
    campaign asks for (PM backlog 96 -> 92 in four passes)."""
    mock_scope.return_value.__enter__.return_value = db_session
    mock_scope.return_value.__exit__.return_value = False
    user = models.User(email="emb@x.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    profile = models.Profile(user_id=user.id, persona=models.Persona.developer)
    db_session.add(profile)
    db_session.commit()
    for n, title in enumerate(["Product Manager", "Staff Engineer"]):
        db_session.add(models.Job(source="lever", external_id=str(n), canonical_hash=f"e{n}", title=title,
                                  company="Acme", apply_url="https://x", location="Bengaluru"))
    db_session.add(models.Campaign(profile_id=profile.id, name="PM", roles=["product manager"], locations=[],
                                   remote_only=False, sources=[], status=models.CampaignStatus.active))
    db_session.commit()

    with patch("connectors.pipeline.embed_texts", side_effect=lambda texts, input_type: [[0.1] * 512 for _ in texts]):
        assert jobs.embed_backlog_task() == {"embedded": 1}
        assert db_session.query(models.Job).filter(models.Job.embedding.isnot(None)).one().title == "Product Manager"
        assert jobs.embed_backlog_task() == {"embedded": 1}  # nothing wanted left: the rest of the backlog
