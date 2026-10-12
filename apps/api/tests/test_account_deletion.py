"""P0 #7: DELETE /account removes every row the caller owns and nothing of anyone else's."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import account
import main
import models
from database import Base, get_db

PASSWORD = "correct horse battery staple"

# Global tables: shared by every user and holding no personal data.
GLOBAL_TABLES = {"jobs", "title_verdicts", "connector_runs", "form_plans", "form_plan_versions", "ats_controls",
                 "app_flags"}


@pytest.fixture()
def env():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override
    yield TestClient(main.app), Session
    main.app.dependency_overrides.clear()


def _signup(client, email, consent=True):
    client.post("/auth/signup", json={"email": email, "password": PASSWORD, "privacy_consent": consent})
    token = client.post("/auth/login", data={"username": email, "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _seed(db, email, job):
    """One row in every user-owned table."""
    user = db.query(models.User).filter_by(email=email).one()
    profile = models.Profile(user_id=user.id, full_name="A Person", phone="+91 98765 43210")
    db.add(profile)
    db.flush()
    campaign = models.Campaign(profile_id=profile.id, name="c", roles=["Data Analyst"], sources=["remotive"])
    application = models.Application(profile_id=profile.id, job_id=job.id)
    contact = models.Contact(profile_id=profile.id, company="Acme", full_name="R Person", email=f"r-{email}")
    db.add_all([campaign, application, contact])
    db.flush()
    db.add_all([
        models.ResumeFact(profile_id=profile.id, category="skill", achievement="SQL"),
        models.Match(profile_id=profile.id, job_id=job.id, score=80, breakdown={}),
        models.ResumeUpload(profile_id=profile.id, status="ready"),
        models.AnswerBank(profile_id=profile.id, question_text="Why?", question_normalized="why", answer_text="x"),
        models.FillSnapshot(application_id=application.id, record={}),
        models.Outreach(profile_id=profile.id, application_id=application.id, contact_id=contact.id),
        models.Suppression(profile_id=profile.id, email="no@acme.com", reason="manual"),
        models.Event(user_id=user.id, type="match.new", payload={}),
        models.Notification(user_id=user.id, trigger="weekly_digest", channel="email", template="t"),
        models.GmailCredential(user_id=user.id, refresh_token_encrypted="x", scopes=[]),
        models.SentLog(user_id=user.id, kind="email", recipient="hr@acme.com", application_id=application.id),
    ])
    db.commit()
    return user.id


def _user_owned_tables():
    return sorted(t.name for t in Base.metadata.sorted_tables if t.name not in GLOBAL_TABLES)


def _counts(db, user_id):
    """Rows per user-owned table that belong to user_id."""
    profiles = [p.id for p in db.query(models.Profile.id).filter_by(user_id=user_id)]
    apps = [a.id for a in db.query(models.Application.id).filter(models.Application.profile_id.in_(profiles))]
    counts = {}
    for name in _user_owned_tables():
        table = Base.metadata.tables[name]
        if name == "users":
            q = db.query(table).filter(table.c.id == user_id)
        elif "user_id" in table.c:
            q = db.query(table).filter(table.c.user_id == user_id)
        elif "profile_id" in table.c:
            q = db.query(table).filter(table.c.profile_id.in_(profiles))
        else:
            q = db.query(table).filter(table.c.application_id.in_(apps))
        counts[name] = q.count()
    return counts


def test_every_table_is_either_global_or_covered_by_deletion():
    """A new user-owned table must be added to account.delete_account (or marked global here)."""
    assert set(_user_owned_tables()) == set(account.COVERED_TABLES)


def test_delete_account_removes_every_owned_row_and_leaves_others(env):
    client, Session = env
    headers = _signup(client, "gone@example.com")
    _signup(client, "stays@example.com")
    with Session() as db:
        job = models.Job(source="s", external_id="1", canonical_hash="h", title="t", company="c", apply_url="https://x")
        db.add(job)
        db.add(models.Suppression(profile_id=None, email="global@acme.com", reason="opt_out"))
        db.commit()
        gone = _seed(db, "gone@example.com", job)
        stays = _seed(db, "stays@example.com", job)
        before_other = _counts(db, stays)
    assert all(n >= 1 for n in before_other.values()), before_other

    with patch("account.gmail.revoke", wraps=account.gmail.revoke) as revoke:
        resp = client.delete("/account", headers=headers)
    assert resp.status_code == 204
    revoke.assert_called_once()  # the network guard blocks the real Google call; the row goes anyway

    with Session() as db:
        assert _counts(db, gone) == {name: 0 for name in _user_owned_tables()}
        assert _counts(db, stays) == before_other
        assert db.query(models.Job).count() == 1
        assert db.query(models.Suppression).filter_by(profile_id=None).count() == 1  # recipients' opt-outs stay

    assert client.get("/auth/me", headers=headers).status_code == 401


def test_delete_account_requires_auth(env):
    client, _ = env
    assert client.delete("/account").status_code == 401


def test_signup_records_consent_time(env):
    client, Session = env
    _signup(client, "yes@example.com", consent=True)
    _signup(client, "no@example.com", consent=False)
    with Session() as db:
        assert db.query(models.User).filter_by(email="yes@example.com").one().privacy_consent_at is not None
        assert db.query(models.User).filter_by(email="no@example.com").one().privacy_consent_at is None
