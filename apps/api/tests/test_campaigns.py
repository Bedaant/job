"""ADR-015 §2 — campaign model tests.

The daily cap is the one rail ADR-015 calls non-negotiable, so most of this
file is about it: the boundary (cap-1 / cap / cap+1), and — the property that
actually matters — that a retried or duplicated worker run cannot push past
it, because the cap is derived from `applications` itself and recomputed
inside the run, not from a counter that could drift.
"""
import itertools
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import campaigns as campaigns_mod
import main
import models
from database import Base, get_db


# ---------- fixtures / helpers ----------

def _session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_get_db
    return TestClient(main.app), TestSessionLocal


def _auth(client, email):
    client.post("/auth/signup", json={"email": email, "password": "correct horse battery staple"})
    token = client.post(
        "/auth/login", data={"username": email, "password": "correct horse battery staple"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _profile(db, email="a@b.com"):
    user = models.User(email=email, password_hash="x")
    db.add(user)
    db.flush()
    profile = models.Profile(user_id=user.id, persona=models.Persona.developer)
    db.add(profile)
    db.commit()
    return profile


def _campaign(db, profile, **kwargs):
    kwargs.setdefault("name", "Backend roles")
    kwargs.setdefault("status", models.CampaignStatus.active)
    kwargs.setdefault("daily_cap", 3)
    campaign = models.Campaign(profile_id=profile.id, **kwargs)
    db.add(campaign)
    db.commit()
    return campaign


def _job(db, n, **kwargs):
    kwargs.setdefault("source", "remotive")
    kwargs.setdefault("title", "Backend Engineer")
    kwargs.setdefault("company", f"Acme{n}")
    kwargs.setdefault("apply_url", "https://x")
    kwargs.setdefault("remote", True)
    job = models.Job(external_id=str(n), canonical_hash=f"h{n}", **kwargs)
    db.add(job)
    db.commit()
    return job


def _match(db, profile, job, score=90):
    match = models.Match(profile_id=profile.id, job_id=job.id, score=score, breakdown={}, state="new")
    db.add(match)
    db.commit()
    return match


_job_seq = itertools.count()


def _applications(db, campaign, count, created_at=None):
    for _ in range(count):
        job = _job(db, f"cap{next(_job_seq)}")
        db.add(models.Application(
            profile_id=campaign.profile_id, job_id=job.id, campaign_id=campaign.id,
            created_at=created_at or datetime.utcnow(),
        ))
    db.commit()


TAILOR_RESULT = {
    "summary": "A backend engineer.",
    "bullets": [{"text": "Led a team", "source_fact_ids": ["f1"]}],
    "cover_letter": "Dear hiring manager...",
    "flagged_unsupported_claims": [],
}


# ---------- daily cap: the boundary ----------

@pytest.mark.parametrize("already_applied,expected_remaining", [(2, 1), (3, 0), (4, 0)])
def test_remaining_quota_at_cap_boundary(already_applied, expected_remaining):
    """cap-1 leaves one slot, cap leaves none, cap+1 (only reachable by a bug
    or a lowered cap) clamps to zero rather than going negative."""
    db = _session()
    campaign = _campaign(db, _profile(db), daily_cap=3)
    _applications(db, campaign, already_applied)

    assert campaigns_mod.remaining_quota(db, campaign) == expected_remaining


def test_remaining_quota_ignores_yesterdays_applications():
    db = _session()
    campaign = _campaign(db, _profile(db), daily_cap=3)
    _applications(db, campaign, 3, created_at=datetime.utcnow() - timedelta(days=1))

    assert campaigns_mod.remaining_quota(db, campaign) == 3


def test_remaining_quota_ignores_other_campaigns_applications():
    db = _session()
    profile = _profile(db)
    mine = _campaign(db, profile, daily_cap=3)
    theirs = _campaign(db, profile, name="Other", daily_cap=3)
    _applications(db, theirs, 3)

    assert campaigns_mod.remaining_quota(db, mine) == 3


# ---------- the worker ----------

@patch("campaigns.prepare_application_for_review")
def test_run_campaign_creates_applications_up_to_remaining_cap(mock_prepare):
    db = _session()
    profile = _profile(db)
    campaign = _campaign(db, profile, daily_cap=2)
    for n in range(5):
        _match(db, profile, _job(db, n))

    result = campaigns_mod.run_campaign(db, campaign)

    assert result["created"] == 2
    assert db.query(models.Application).filter(models.Application.campaign_id == campaign.id).count() == 2
    assert mock_prepare.call_count == 2
    assert campaign.last_run_at is not None


@patch("campaigns.prepare_application_for_review")
def test_run_campaign_skips_matches_below_min_match_score(mock_prepare):
    db = _session()
    profile = _profile(db)
    campaign = _campaign(db, profile, daily_cap=10, min_match_score=0.8)
    _match(db, profile, _job(db, 1), score=85)   # 0.85 -> in
    _match(db, profile, _job(db, 2), score=70)   # 0.70 -> out

    result = campaigns_mod.run_campaign(db, campaign)

    assert result["created"] == 1


@patch("campaigns.prepare_application_for_review")
def test_run_campaign_filters_by_roles_locations_and_sources(mock_prepare):
    db = _session()
    profile = _profile(db)
    campaign = _campaign(
        db, profile, daily_cap=10, roles=["backend"], locations=["berlin"], sources=["remotive"],
    )
    _job(db, 1, title="Backend Engineer", location="Berlin, DE", source="remotive")
    _job(db, 2, title="Frontend Engineer", location="Berlin, DE", source="remotive")  # wrong role
    _job(db, 3, title="Backend Engineer", location="Lisbon, PT", source="remotive")   # wrong location
    _job(db, 4, title="Backend Engineer", location="Berlin, DE", source="lever")      # wrong source
    for job in db.query(models.Job).all():
        _match(db, profile, job)

    result = campaigns_mod.run_campaign(db, campaign)

    assert result["created"] == 1
    created = db.query(models.Application).filter(models.Application.campaign_id == campaign.id).one()
    assert created.job.company == "Acme1"


@patch("campaigns.prepare_application_for_review")
def test_run_campaign_skips_jobs_already_applied_to(mock_prepare):
    db = _session()
    profile = _profile(db)
    campaign = _campaign(db, profile, daily_cap=10)
    job = _job(db, 1)
    _match(db, profile, job)
    db.add(models.Application(profile_id=profile.id, job_id=job.id,
                              created_at=datetime.utcnow() - timedelta(days=2)))
    db.commit()

    result = campaigns_mod.run_campaign(db, campaign)

    assert result["created"] == 0


@patch("campaigns.prepare_application_for_review")
def test_run_campaign_on_paused_campaign_is_a_noop(mock_prepare):
    db = _session()
    profile = _profile(db)
    campaign = _campaign(db, profile, status=models.CampaignStatus.paused, daily_cap=10)
    _match(db, profile, _job(db, 1))

    result = campaigns_mod.run_campaign(db, campaign)

    assert result["skipped"] is True
    assert result["created"] == 0
    assert db.query(models.Application).count() == 0
    assert mock_prepare.call_count == 0
    assert campaign.last_run_at is None


# ---------- skip events: "Skipped X — reason" in What Maggie did ----------

def _skips(db):
    return db.query(models.Event).filter(models.Event.type == "campaign.skipped").order_by(models.Event.id).all()


@patch("campaigns.prepare_application_for_review")
def test_run_campaign_records_why_each_considered_job_was_skipped(mock_prepare):
    db = _session()
    profile = _profile(db)
    campaign = _campaign(db, profile, daily_cap=1, min_match_score=0.8, roles=["backend"])
    picked, capped, low, applied = (_job(db, n) for n in range(1, 5))
    off_role = _job(db, 5, title="Frontend Engineer")
    _match(db, profile, picked, score=95)
    _match(db, profile, capped, score=90)
    _match(db, profile, low, score=61)
    _match(db, profile, applied, score=92)
    _match(db, profile, off_role, score=99)
    db.add(models.Application(profile_id=profile.id, job_id=applied.id))
    db.commit()

    campaigns_mod.run_campaign(db, campaign)

    events = _skips(db)
    assert all(e.user_id == profile.user_id and e.payload["campaign_id"] == campaign.id for e in events)
    per_job = {e.payload["job_id"]: e.payload for e in events if e.payload.get("job_id")}
    # Off-role jobs are never listed one by one — only counted in the summary.
    assert set(per_job) == {capped.id, low.id, applied.id}
    assert per_job[capped.id]["reason_code"] == "daily_cap"
    assert per_job[low.id]["reason_code"] == "below_score"
    assert per_job[low.id]["reason"] == "Score 61%, below your 80% minimum"
    assert per_job[applied.id]["reason_code"] == "already_applied"
    [summary] = [e.payload for e in events if not e.payload.get("job_id")]
    assert summary["reason_code"] == "checked"
    assert summary["reason"] == "Checked 5 new jobs; 4 fit your campaign."


@patch("campaigns.prepare_application_for_review")
def test_run_campaign_does_not_rereport_jobs_it_already_looked_at(mock_prepare):
    db = _session()
    profile = _profile(db)
    campaign = _campaign(db, profile, daily_cap=1)
    _match(db, profile, _job(db, 1))
    _match(db, profile, _job(db, 2))

    campaigns_mod.run_campaign(db, campaign)
    before = len(_skips(db))
    campaigns_mod.run_campaign(db, campaign)

    new = _skips(db)[before:]
    # Nothing new to look at and the cap is used: one run-level note, no per-job rows.
    assert [e.payload["reason_code"] for e in new] == ["daily_cap"]
    assert "job_id" not in new[0].payload


@patch("campaigns.prepare_application_for_review")
def test_run_campaign_caps_per_job_skip_events_and_summarizes_the_rest(mock_prepare):
    db = _session()
    profile = _profile(db)
    campaign = _campaign(db, profile, daily_cap=1, min_match_score=0.9)
    for n in range(25):
        _match(db, profile, _job(db, n), score=50)

    campaigns_mod.run_campaign(db, campaign)

    events = _skips(db)
    assert len([e for e in events if e.payload.get("job_id")]) == campaigns_mod.SKIP_EVENT_LIMIT == 20
    [summary] = [e.payload for e in events if not e.payload.get("job_id")]
    assert summary["reason"] == "Checked 25 new jobs; 25 fit your campaign. 5 more skipped, not listed."


@patch("campaigns.prepare_application_for_review")
def test_run_campaign_on_paused_campaign_records_one_skip(mock_prepare):
    db = _session()
    profile = _profile(db)
    campaign = _campaign(db, profile, status=models.CampaignStatus.paused)
    _match(db, profile, _job(db, 1))

    campaigns_mod.run_campaign(db, campaign)

    [event] = _skips(db)
    assert event.payload == {"campaign_id": campaign.id, "reason_code": "not_active",
                             "reason": "Your campaign is paused, so nothing was sent."}


@patch("campaigns.prepare_application_for_review")
def test_run_campaign_leaves_applications_ready_for_review_when_auto_submit_false(mock_prepare):
    """auto_submit False keeps the optional review step: prepared, not approved."""
    def fake_prepare(db, application):
        application.status = models.ApplicationStatus.ready_for_review
        db.commit()
        return application

    mock_prepare.side_effect = fake_prepare
    db = _session()
    profile = _profile(db)
    campaign = _campaign(db, profile, daily_cap=1, auto_submit=False)
    _match(db, profile, _job(db, 1))

    campaigns_mod.run_campaign(db, campaign)

    row = db.query(models.Application).one()
    assert row.status == models.ApplicationStatus.ready_for_review


@patch("campaigns.prepare_application_for_review")
def test_run_campaign_marks_approved_when_auto_submit_true(mock_prepare):
    def fake_prepare(db, application):
        application.status = models.ApplicationStatus.ready_for_review
        db.commit()
        return application

    mock_prepare.side_effect = fake_prepare
    db = _session()
    profile = _profile(db)
    campaign = _campaign(db, profile, daily_cap=1, auto_submit=True)
    _match(db, profile, _job(db, 1))

    campaigns_mod.run_campaign(db, campaign)

    row = db.query(models.Application).one()
    assert row.status == models.ApplicationStatus.approved


@patch("campaigns.prepare_application_for_review")
@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.session_scope")
def test_run_campaign_task_double_run_never_exceeds_cap(mock_scope, mock_redis, mock_prepare):
    """The claim is deliberately made to succeed BOTH times here, so this
    proves the cap holds on the database-derived count alone — not because
    the Redis idempotency claim happened to catch the duplicate."""
    from workers.jobs import run_campaign_task

    db = _session()
    profile = _profile(db)
    campaign = _campaign(db, profile, daily_cap=2)
    for n in range(5):
        _match(db, profile, _job(db, n))

    mock_scope.return_value.__enter__.return_value = db
    mock_scope.return_value.__exit__.return_value = False
    redis = MagicMock()
    redis.set.return_value = True
    mock_redis.return_value = redis

    first = run_campaign_task(campaign.id, run_id="r1")
    second = run_campaign_task(campaign.id, run_id="r2")

    assert first["created"] == 2
    assert second["created"] == 0
    assert db.query(models.Application).filter(models.Application.campaign_id == campaign.id).count() == 2


@patch("workers.jobs.get_redis_connection")
def test_run_campaign_task_skips_when_claim_already_held(mock_redis):
    from workers.jobs import run_campaign_task

    redis = MagicMock()
    redis.set.return_value = False
    mock_redis.return_value = redis

    result = run_campaign_task("some-campaign-id", run_id="r1")

    assert result == {"skipped": True, "reason": "already claimed"}


# ---------- tenancy ----------

def test_campaign_is_not_readable_across_profiles():
    db = _session()
    owner_profile = _profile(db, "owner@example.com")
    intruder_profile = _profile(db, "intruder@example.com")
    campaign = _campaign(db, owner_profile)

    intruder = db.query(models.User).filter(models.User.id == intruder_profile.user_id).one()
    with pytest.raises(HTTPException) as exc_info:
        campaigns_mod.resolve_campaign_ownership(db, intruder, campaign.id)
    assert exc_info.value.status_code == 404

    owner = db.query(models.User).filter(models.User.id == owner_profile.user_id).one()
    assert campaigns_mod.resolve_campaign_ownership(db, owner, campaign.id).id == campaign.id


def test_campaign_endpoints_are_not_reachable_across_tenants():
    client, _ = _client()
    owner_headers = _auth(client, "campowner@example.com")
    intruder_headers = _auth(client, "campintruder@example.com")
    profile = client.post("/profiles", headers=owner_headers, json={"persona": "developer"}).json()
    created = client.post("/campaigns", headers=owner_headers, json={
        "profile_id": profile["id"], "name": "Backend roles",
    })
    assert created.status_code == 200, created.text
    campaign_id = created.json()["id"]

    assert client.get(f"/campaigns/{campaign_id}", headers=intruder_headers).status_code == 404
    assert client.patch(f"/campaigns/{campaign_id}", headers=intruder_headers,
                        json={"name": "hijacked"}).status_code == 404
    assert client.delete(f"/campaigns/{campaign_id}", headers=intruder_headers).status_code == 404
    assert client.get(f"/campaigns/{campaign_id}/stats", headers=intruder_headers).status_code == 404
    assert client.get("/campaigns", headers=intruder_headers).json() == []
    # and the owner still sees exactly their own
    assert [c["id"] for c in client.get("/campaigns", headers=owner_headers).json()] == [campaign_id]


def test_cannot_create_campaign_on_someone_elses_profile():
    client, _ = _client()
    owner_headers = _auth(client, "cprofowner@example.com")
    intruder_headers = _auth(client, "cprofintruder@example.com")
    profile = client.post("/profiles", headers=owner_headers, json={"persona": "developer"}).json()

    response = client.post("/campaigns", headers=intruder_headers, json={
        "profile_id": profile["id"], "name": "Backend roles",
    })
    assert response.status_code == 404


# ---------- endpoints ----------

def test_create_campaign_defaults_match_adr015_rails():
    client, _ = _client()
    headers = _auth(client, "campdefaults@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()

    body = client.post("/campaigns", headers=headers,
                       json={"profile_id": profile["id"], "name": "Backend roles"}).json()

    assert body["status"] == "draft"
    assert body["daily_cap"] == 10
    assert body["min_match_score"] == 0.7
    assert body["auto_submit"] is False
    assert body["remote_only"] is True
    assert body["roles"] == [] and body["locations"] == [] and body["sources"] == []


def test_delete_campaign_archives_instead_of_deleting():
    client, SessionLocal = _client()
    headers = _auth(client, "camparchive@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    campaign_id = client.post("/campaigns", headers=headers,
                              json={"profile_id": profile["id"], "name": "Backend roles"}).json()["id"]

    response = client.delete(f"/campaigns/{campaign_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["status"] == "archived"
    db = SessionLocal()
    row = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).one()
    assert row.status == models.CampaignStatus.archived
    # still fetchable — archived, not gone
    assert client.get(f"/campaigns/{campaign_id}", headers=headers).status_code == 200


@pytest.mark.parametrize("from_status,to_status,expected", [
    ("draft", "active", 200),
    ("active", "paused", 200),
    ("paused", "active", 200),
    ("active", "archived", 200),
    ("archived", "active", 422),
    ("draft", "paused", 422),
])
def test_campaign_status_transitions(from_status, to_status, expected):
    client, SessionLocal = _client()
    headers = _auth(client, f"campstatus{from_status}{to_status}@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    campaign_id = client.post("/campaigns", headers=headers,
                              json={"profile_id": profile["id"], "name": "Backend roles"}).json()["id"]
    db = SessionLocal()
    row = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).one()
    row.status = models.CampaignStatus(from_status)
    db.commit()

    response = client.patch(f"/campaigns/{campaign_id}", headers=headers, json={"status": to_status})

    assert response.status_code == expected
    if expected == 200:
        assert response.json()["status"] == to_status


def test_patch_campaign_updates_bounds():
    client, _ = _client()
    headers = _auth(client, "campedit@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    campaign_id = client.post("/campaigns", headers=headers,
                              json={"profile_id": profile["id"], "name": "Backend roles"}).json()["id"]

    body = client.patch(f"/campaigns/{campaign_id}", headers=headers, json={
        "name": "Senior backend only", "roles": ["staff engineer"], "daily_cap": 5,
        "min_match_score": 0.85, "auto_submit": True, "tailoring_notes": "lead with the fintech work",
    }).json()

    assert body["name"] == "Senior backend only"
    assert body["roles"] == ["staff engineer"]
    assert body["daily_cap"] == 5
    assert body["min_match_score"] == 0.85
    assert body["auto_submit"] is True
    assert body["tailoring_notes"] == "lead with the fintech work"


def test_create_campaign_rejects_out_of_range_bounds():
    client, _ = _client()
    headers = _auth(client, "campbounds@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()

    assert client.post("/campaigns", headers=headers, json={
        "profile_id": profile["id"], "name": "x", "daily_cap": 0,
    }).status_code == 422
    assert client.post("/campaigns", headers=headers, json={
        "profile_id": profile["id"], "name": "x", "min_match_score": 1.5,
    }).status_code == 422


def test_campaign_stats_uses_the_same_quota_function_as_the_worker():
    client, SessionLocal = _client()
    headers = _auth(client, "campstats@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    campaign_id = client.post("/campaigns", headers=headers, json={
        "profile_id": profile["id"], "name": "Backend roles", "daily_cap": 3,
    }).json()["id"]

    db = SessionLocal()
    campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).one()
    _applications(db, campaign, 2)
    _applications(db, campaign, 1, created_at=datetime.utcnow() - timedelta(days=1))

    body = client.get(f"/campaigns/{campaign_id}/stats", headers=headers).json()

    assert body == {
        "applied_today": 2,
        "daily_cap": 3,
        "remaining_today": campaigns_mod.remaining_quota(db, campaign),
        "total_applied": 3,
        "last_run_at": None,
    }
    assert body["remaining_today"] == 1


def test_run_campaign_endpoint_enqueues_and_returns_a_job_id():
    client, _ = _client()
    headers = _auth(client, "camprun@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    campaign_id = client.post("/campaigns", headers=headers,
                              json={"profile_id": profile["id"], "name": "Backend roles"}).json()["id"]

    fake_job = MagicMock()
    fake_job.id = "rq-job-1"
    fake_job.get_status.return_value = "queued"
    with patch("main.get_queue") as mock_queue, patch("main._workers_online", return_value=True):
        mock_queue.return_value.enqueue.return_value = fake_job
        response = client.post(f"/campaigns/{campaign_id}/run", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"task_id": "rq-job-1", "status": "queued"}


def test_application_campaign_fk_is_set_null_not_cascade():
    """A hard-deleted campaign row must not take the user's real application
    history with it. Asserted at the schema level: SQLite (the unit-test
    engine) doesn't enforce foreign keys by default, so deleting a row here
    would "pass" regardless of what the constraint actually says.
    """
    fk = next(iter(models.Application.__table__.c.campaign_id.foreign_keys))
    assert fk.ondelete == "SET NULL"
    assert models.Application.__table__.c.campaign_id.nullable is True
    # campaigns themselves cascade from their profile, like every other tenant table
    profile_fk = next(iter(models.Campaign.__table__.c.profile_id.foreign_keys))
    assert profile_fk.ondelete == "CASCADE"


def test_enqueued_job_ids_are_valid_rq_ids():
    """Found live: rq 2.x rejects ':' in job ids, so POST /campaigns/{id}/run and
    POST /discover/run 500'd on every call. The mocked-queue tests above can't
    see it — this runs rq's own validator on the ids the endpoints build."""
    from rq.job import validate_job_id

    client, _ = _client()
    headers = _auth(client, "rqid@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    campaign_id = client.post("/campaigns", headers=headers,
                              json={"profile_id": profile["id"], "name": "Backend roles"}).json()["id"]

    fake_job = MagicMock()
    fake_job.id = "x"
    fake_job.get_status.return_value = "queued"
    with patch("main.get_queue") as mock_queue, patch("main._workers_online", return_value=True):
        mock_queue.return_value.enqueue.return_value = fake_job
        client.post(f"/campaigns/{campaign_id}/run", headers=headers)
        client.post("/discover/run", headers=headers)

    job_ids = [c.kwargs["job_id"] for c in mock_queue.return_value.enqueue.call_args_list]
    assert len(job_ids) == 2
    for job_id in job_ids:
        validate_job_id(job_id)  # raises ValueError on an id rq would refuse


def test_run_says_so_when_no_worker_is_listening():
    """Live (2026-09-29): no worker was running; Run returned 200 and the job sat in
    Redis for hours. The user is told instead, and nothing is enqueued."""
    client, _ = _client()
    headers = _auth(client, "noworker@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    campaign_id = client.post("/campaigns", headers=headers,
                              json={"profile_id": profile["id"], "name": "PM"}).json()["id"]
    with patch("main.get_queue") as mock_queue, patch("main._workers_online", return_value=False):
        for path in (f"/campaigns/{campaign_id}/run", "/discover/run"):
            response = client.post(path, headers=headers)
            assert response.status_code == 503
            assert "background worker" in response.json()["detail"]
    mock_queue.return_value.enqueue.assert_not_called()


@patch("campaigns.prepare_application_for_review")
def test_run_campaign_retries_its_applications_a_failed_prep_left_at_saved(mock_prepare):
    """Live (2026-09-29): NIM 503'd during tailoring, the application stayed `saved`,
    and every later run skipped the job as "already applied". It is retried, even when
    the day's cap is spent (it was counted when created)."""
    db = _session()
    profile = _profile(db)
    campaign = _campaign(db, profile, daily_cap=1)
    job = _job(db, 1)
    _match(db, profile, job)
    mock_prepare.side_effect = RuntimeError("503 Service temporarily overloaded")
    assert campaigns_mod.run_campaign(db, campaign)["failed"]
    stuck = db.query(models.Application).one()
    assert stuck.status == models.ApplicationStatus.saved

    mock_prepare.side_effect = None
    result = campaigns_mod.run_campaign(db, campaign)
    assert result["prepared"] == 1
    assert mock_prepare.call_args.args[1].id == stuck.id


@patch("campaigns.prepare_application_for_review")
def test_run_campaign_skips_remote_roles_restricted_to_another_country(mock_prepare):
    """Live: a user in India was offered "Remote - US" roles. Stored matches from
    before the filter existed must not be picked either."""
    db = _session()
    profile = _profile(db)
    profile.country_code = "IN"
    db.commit()
    campaign = _campaign(db, profile, remote_only=True)
    _match(db, profile, _job(db, 1, location="Remote - US"), score=95)
    _match(db, profile, _job(db, 2, location="Anywhere in the World"), score=90)

    campaigns_mod.run_campaign(db, campaign)

    assert [a.job.location for a in db.query(models.Application).all()] == ["Anywhere in the World"]
