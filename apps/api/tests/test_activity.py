"""GET /activity (what Maggie did, from the events outbox) and GET /today
(the three home-screen counters)."""
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from database import Base, get_db

PASSWORD = "correct horse battery staple"


def _client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_get_db
    return TestClient(main.app), SessionLocal


def _user(client, email):
    client.post("/auth/signup", json={"email": email, "password": PASSWORD})
    token = client.post("/auth/login", data={"username": email, "password": PASSWORD}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    return headers, profile["id"]


def _world():
    """User A with one job + application and a spread of events; user B with one
    event that must never leak to A."""
    client, SessionLocal = _client()
    headers_a, profile_a = _user(client, "a@example.com")
    headers_b, profile_b = _user(client, "b@example.com")

    db = SessionLocal()
    user_a = db.query(models.User).filter(models.User.email == "a@example.com").one()
    user_b = db.query(models.User).filter(models.User.email == "b@example.com").one()
    job = models.Job(source="remotive", external_id="1", canonical_hash="h1", title="Backend Engineer",
                     company="Acme", apply_url="https://x")
    db.add(job)
    db.flush()
    app_row = models.Application(profile_id=profile_a, job_id=job.id, status=models.ApplicationStatus.applied)
    db.add(app_row)
    db.flush()

    base = datetime.utcnow().replace(microsecond=0) - timedelta(hours=1)
    rows = [
        ("match.new", {"job_id": job.id, "job_title": job.title, "score": 82.4}),
        ("application.ready_for_review", {"application_id": app_row.id, "job_title": job.title}),
        ("application.approved", {"application_id": app_row.id}),
        ("application.status_changed", {"application_id": app_row.id, "status": "submitting"}),
        ("application.needs_human", {"application_id": app_row.id, "status": "ready_for_review",
                                     "reason": "Asked for a portfolio link"}),
        ("application.failed", {"application_id": app_row.id, "status": "approved", "reason": None}),
        ("application.submitted", {"application_id": app_row.id, "status": "applied", "reason": None}),
    ]
    for i, (type_, payload) in enumerate(rows):
        db.add(models.Event(user_id=user_a.id, type=type_, payload=payload,
                            created_at=base + timedelta(minutes=i)))
    db.add(models.Event(user_id=user_b.id, type="match.new",
                        payload={"job_id": job.id, "job_title": "LEAK", "score": 99}, created_at=base))
    db.commit()
    ids = {"job": job.id, "application": app_row.id, "profile_a": profile_a, "profile_b": profile_b}
    db.close()
    return client, SessionLocal, headers_a, headers_b, ids, base


def test_activity_requires_auth():
    client, *_ = _world()
    assert client.get("/activity").status_code == 401


def test_activity_is_newest_first_scoped_and_mapped():
    client, _, headers_a, _, ids, base = _world()
    resp = client.get("/activity", headers=headers_a)
    assert resp.status_code == 200
    items = resp.json()

    # status_changed is plumbing (the claim), not something the user did or needs.
    assert [i["type"] for i in items] == [
        "application.submitted", "application.failed", "application.needs_human",
        "application.approved", "application.ready_for_review", "match.new",
    ]
    assert all(i["job"] == {"title": "Backend Engineer", "company": "Acme"} for i in items)
    assert "LEAK" not in resp.text

    submitted = items[0]
    assert submitted["title"] == "Applied"
    assert submitted["application_id"] == ids["application"]
    # UTC made explicit so a browser never reads it as local time.
    assert submitted["at"].endswith("Z") or submitted["at"].endswith("+00:00")

    by_type = {i["type"]: i for i in items}
    assert by_type["application.needs_human"]["detail"] == "Asked for a portfolio link"
    assert by_type["application.failed"]["detail"]  # a reason-less failure still says something
    assert by_type["match.new"]["detail"] == "82% match"
    assert by_type["match.new"]["application_id"] is None


def test_activity_limit_and_since():
    client, _, headers_a, _, _, base = _world()
    assert len(client.get("/activity?limit=2", headers=headers_a).json()) == 2
    assert client.get("/activity?limit=0", headers=headers_a).status_code == 422
    assert client.get("/activity?limit=201", headers=headers_a).status_code == 422

    since = (base + timedelta(minutes=5)).isoformat()
    types = [i["type"] for i in client.get("/activity", params={"since": since}, headers=headers_a).json()]
    assert types == ["application.submitted", "application.failed"]


def test_activity_other_user_sees_only_their_own():
    client, _, _, headers_b, _, _ = _world()
    items = client.get("/activity", headers=headers_b).json()
    assert [i["detail"] for i in items] == ["99% match"]


def test_today_counts():
    client, SessionLocal, headers_a, headers_b, ids, _ = _world()
    db = SessionLocal()
    now = datetime.utcnow()
    jobs = [models.Job(source="remotive", external_id=str(n), canonical_hash=f"h{n}", title="SRE",
                       company="Beta", apply_url="https://y") for n in range(2, 6)]
    db.add_all(jobs)
    db.flush()
    j2, j3, j4, j5 = (j.id for j in jobs)
    # The _world application is `applied` but has no applied_at: not sent today.
    db.add_all([
        models.Application(profile_id=ids["profile_a"], job_id=j2,
                           status=models.ApplicationStatus.applied, applied_at=now),
        models.Application(profile_id=ids["profile_a"], job_id=j3,
                           status=models.ApplicationStatus.applied, applied_at=now - timedelta(days=2)),
        models.Application(profile_id=ids["profile_a"], job_id=j4,
                           status=models.ApplicationStatus.ready_for_review),
        models.Application(profile_id=ids["profile_b"], job_id=j5,
                           status=models.ApplicationStatus.ready_for_review),
        models.Match(profile_id=ids["profile_a"], job_id=j2, score=80, breakdown={}, created_at=now),
        models.Match(profile_id=ids["profile_a"], job_id=ids["job"], score=70, breakdown={},
                     created_at=now - timedelta(days=3)),
    ])
    db.commit()
    db.close()

    assert client.get("/today").status_code == 401
    assert client.get("/today", headers=headers_a).json() == {"sent_today": 1, "unconfirmed_today": 0, "needs_you": 1, "new_matches_today": 1}
    assert client.get("/today", headers=headers_b).json() == {"sent_today": 0, "unconfirmed_today": 0, "needs_you": 1, "new_matches_today": 0}


def test_activity_maps_campaign_skips():
    client, SessionLocal, headers_a, _, ids, base = _world()
    db = SessionLocal()
    user_a = db.query(models.User).filter(models.User.email == "a@example.com").one()
    later = base + timedelta(minutes=30)
    rows = [
        {"campaign_id": "c", "job_id": ids["job"], "reason_code": "below_score",
         "reason": "Score 61%, below your 70% minimum"},
        {"campaign_id": "c", "reason_code": "checked", "reason": "Checked 214 new jobs; 12 fit your campaign."},
        {"campaign_id": "c", "reason_code": "daily_cap", "reason": "Daily limit of 10 reached."},
        {"campaign_id": "c", "reason_code": "not_active", "reason": "Your campaign is paused, so nothing was sent."},
    ]
    for i, payload in enumerate(rows):
        db.add(models.Event(user_id=user_a.id, type="campaign.skipped", payload=payload,
                            created_at=later + timedelta(minutes=i)))
    db.commit()
    db.close()

    items = client.get("/activity?limit=4", headers=headers_a).json()
    assert [(i["title"], i["detail"]) for i in items] == [
        ("Didn't run", "Your campaign is paused, so nothing was sent."),
        ("Daily limit reached", "Daily limit of 10 reached."),
        ("Checked new jobs", "Checked 214 new jobs; 12 fit your campaign."),
        ("Skipped", "Score 61%, below your 70% minimum"),
    ]
    assert items[-1]["job"] == {"title": "Backend Engineer", "company": "Acme"}
    assert items[0]["job"] is None


def test_today_counts_over_the_callers_local_day():
    """/today?tz= counts from the viewer's local midnight; invalid tz falls back to UTC."""
    import campaigns
    from zoneinfo import ZoneInfo

    kolkata = campaigns.local_day_start("Asia/Kolkata")
    local_now = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
    assert timedelta(hours=5, minutes=30) <= local_now - kolkata < timedelta(days=1, hours=5, minutes=30)
    assert campaigns.local_day_start("Not/AZone") == campaigns.utc_day_start()
    assert campaigns.local_day_start(None) == campaigns.utc_day_start()

    client, SessionLocal, headers_a, _, ids, _ = _world()
    db = SessionLocal()
    jobs = [models.Job(source="remotive", external_id=str(n), canonical_hash=f"k{n}", title="SRE",
                       company="Beta", apply_url="https://y") for n in range(2, 4)]
    db.add_all(jobs)
    db.flush()
    stamps = [kolkata + timedelta(minutes=1), kolkata - timedelta(minutes=1)]
    for job, at in zip(jobs, stamps):
        db.add(models.Application(profile_id=ids["profile_a"], job_id=job.id,
                                  status=models.ApplicationStatus.applied, applied_at=at))
        db.add(models.Match(profile_id=ids["profile_a"], job_id=job.id, score=80, breakdown={}, created_at=at))
    db.commit()
    db.close()

    utc_expected = sum(at >= campaigns.utc_day_start() for at in stamps)
    local = client.get("/today", params={"tz": "Asia/Kolkata"}, headers=headers_a).json()
    assert local["sent_today"] == 1 and local["new_matches_today"] == 1
    for tz in ("UTC", "Not/AZone", "../../etc/passwd"):
        assert client.get("/today", params={"tz": tz}, headers=headers_a).json()["sent_today"] == utc_expected
