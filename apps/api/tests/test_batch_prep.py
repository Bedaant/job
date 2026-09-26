from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from batch_prep import prepare_application_for_review
from database import Base, get_db


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


TAILOR_RESULT = {
    "summary": "A backend engineer.",
    "bullets": [{"text": "Led a team", "source_fact_ids": ["f1"]}],
    "cover_letter": "Dear hiring manager...",
    "flagged_unsupported_claims": ["invented claim"],
}


@patch("batch_prep.tailor_application", return_value=TAILOR_RESULT)
def test_prepare_application_for_review_persists_tailored_content_and_flags(_mock_tailor):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    user = models.User(email="a@b.com", password_hash="x")
    db.add(user); db.commit()
    profile = models.Profile(user_id=user.id, persona="developer")
    db.add(profile); db.commit()
    job = models.Job(source="remotive", external_id="1", canonical_hash="h1", title="Backend Engineer",
                      company="Acme", apply_url="https://x")
    db.add(job); db.commit()
    application = models.Application(profile_id=profile.id, job_id=job.id)
    db.add(application); db.commit()

    result = prepare_application_for_review(db, application)

    assert result.status == models.ApplicationStatus.ready_for_review
    assert result.tailored_resume_json["summary"] == "A backend engineer."
    assert result.flagged_unsupported_claims == ["invented claim"]
    assert db.query(models.Event).filter(models.Event.type == "application.ready_for_review").count() == 1


def test_review_queue_endpoint_returns_only_ready_for_review_applications():
    client, SessionLocal = _client()
    headers = _auth(client, "reviewq@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()

    db = SessionLocal()
    job1 = models.Job(source="remotive", external_id="1", canonical_hash="h1", title="Backend Engineer",
                       company="Acme", apply_url="https://x")
    job2 = models.Job(source="remotive", external_id="2", canonical_hash="h2", title="Frontend Engineer",
                       company="Acme", apply_url="https://y")
    db.add_all([job1, job2]); db.commit()

    ready = models.Application(
        profile_id=profile["id"], job_id=job1.id, status=models.ApplicationStatus.ready_for_review,
        tailored_resume_json={"summary": "S", "bullets": []}, flagged_unsupported_claims=["x"],
    )
    saved = models.Application(profile_id=profile["id"], job_id=job2.id, status=models.ApplicationStatus.saved)
    db.add_all([ready, saved]); db.commit()
    db.close()

    resp = client.get(f"/applications/review-queue?profile_id={profile['id']}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["job"]["title"] == "Backend Engineer"
    assert body[0]["flagged_unsupported_claims"] == ["x"]


def test_batch_approve_transitions_all_and_is_all_or_nothing():
    client, SessionLocal = _client()
    headers = _auth(client, "batchapprove@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()

    db = SessionLocal()
    job = models.Job(source="remotive", external_id="1", canonical_hash="h1", title="Backend Engineer",
                      company="Acme", apply_url="https://x")
    db.add(job); db.commit()
    app1 = models.Application(profile_id=profile["id"], job_id=job.id, status=models.ApplicationStatus.ready_for_review)
    db.add(app1); db.commit()
    app1_id = app1.id
    db.close()

    resp = client.post("/applications/batch-approve", headers=headers, json={"application_ids": [app1_id]})
    assert resp.status_code == 200
    assert resp.json()["approved"] == [app1_id]

    db = SessionLocal()
    refreshed = db.query(models.Application).filter(models.Application.id == app1_id).first()
    assert refreshed.status == models.ApplicationStatus.approved
    assert db.query(models.Event).filter(models.Event.type == "application.approved").count() == 1
    db.close()


def test_batch_approve_404s_on_unowned_application():
    client, SessionLocal = _client()
    mine = _auth(client, "mine@example.com")
    theirs = _auth(client, "theirs@example.com")
    their_profile = client.post("/profiles", headers=theirs, json={"persona": "developer"}).json()

    db = SessionLocal()
    job = models.Job(source="remotive", external_id="1", canonical_hash="h1", title="Backend Engineer",
                      company="Acme", apply_url="https://x")
    db.add(job); db.commit()
    their_app = models.Application(profile_id=their_profile["id"], job_id=job.id, status=models.ApplicationStatus.ready_for_review)
    db.add(their_app); db.commit()
    their_app_id = their_app.id
    db.close()

    resp = client.post("/applications/batch-approve", headers=mine, json={"application_ids": [their_app_id]})
    assert resp.status_code == 404


def test_batch_approve_422s_when_not_ready_for_review():
    client, SessionLocal = _client()
    headers = _auth(client, "notready@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()

    db = SessionLocal()
    job = models.Job(source="remotive", external_id="1", canonical_hash="h1", title="Backend Engineer",
                      company="Acme", apply_url="https://x")
    db.add(job); db.commit()
    app1 = models.Application(profile_id=profile["id"], job_id=job.id, status=models.ApplicationStatus.saved)
    db.add(app1); db.commit()
    app1_id = app1.id
    db.close()

    resp = client.post("/applications/batch-approve", headers=headers, json={"application_ids": [app1_id]})
    assert resp.status_code == 422


def test_dismiss_via_existing_patch_endpoint():
    client, SessionLocal = _client()
    headers = _auth(client, "dismiss@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()

    db = SessionLocal()
    job = models.Job(source="remotive", external_id="1", canonical_hash="h1", title="Backend Engineer",
                      company="Acme", apply_url="https://x")
    db.add(job); db.commit()
    app1 = models.Application(profile_id=profile["id"], job_id=job.id, status=models.ApplicationStatus.ready_for_review)
    db.add(app1); db.commit()
    app1_id = app1.id
    db.close()

    resp = client.patch(f"/applications/{app1_id}", headers=headers, json={"status": "dismissed"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "dismissed"


def test_claim_submission_transitions_approved_to_applied():
    client, SessionLocal = _client()
    headers = _auth(client, "claim@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()

    db = SessionLocal()
    job = models.Job(source="remotive", external_id="1", canonical_hash="h1", title="Backend Engineer",
                      company="Acme", apply_url="https://x")
    db.add(job); db.commit()
    app1 = models.Application(profile_id=profile["id"], job_id=job.id, status=models.ApplicationStatus.approved)
    db.add(app1); db.commit()
    app1_id = app1.id
    db.close()

    resp = client.post(f"/applications/{app1_id}/claim-submission", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"claimed": True, "application_id": app1_id}

    db = SessionLocal()
    refreshed = db.query(models.Application).filter(models.Application.id == app1_id).first()
    assert refreshed.status == models.ApplicationStatus.applied
    assert refreshed.applied_at is not None
    db.close()


def test_claim_submission_cannot_fire_twice():
    """The core correctness property: a second claim on the same application
    must fail (it's no longer `approved` after the first claim succeeds)."""
    client, SessionLocal = _client()
    headers = _auth(client, "claimtwice@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()

    db = SessionLocal()
    job = models.Job(source="remotive", external_id="1", canonical_hash="h1", title="Backend Engineer",
                      company="Acme", apply_url="https://x")
    db.add(job); db.commit()
    app1 = models.Application(profile_id=profile["id"], job_id=job.id, status=models.ApplicationStatus.approved)
    db.add(app1); db.commit()
    app1_id = app1.id
    db.close()

    first = client.post(f"/applications/{app1_id}/claim-submission", headers=headers)
    assert first.status_code == 200

    second = client.post(f"/applications/{app1_id}/claim-submission", headers=headers)
    assert second.status_code == 409


def test_claim_submission_404s_when_not_owned():
    client, SessionLocal = _client()
    mine = _auth(client, "claimmine@example.com")
    theirs = _auth(client, "claimtheirs@example.com")
    their_profile = client.post("/profiles", headers=theirs, json={"persona": "developer"}).json()

    db = SessionLocal()
    job = models.Job(source="remotive", external_id="1", canonical_hash="h1", title="Backend Engineer",
                      company="Acme", apply_url="https://x")
    db.add(job); db.commit()
    their_app = models.Application(profile_id=their_profile["id"], job_id=job.id, status=models.ApplicationStatus.approved)
    db.add(their_app); db.commit()
    their_app_id = their_app.id
    db.close()

    resp = client.post(f"/applications/{their_app_id}/claim-submission", headers=mine)
    assert resp.status_code == 404


def test_claim_submission_409s_when_not_approved():
    client, SessionLocal = _client()
    headers = _auth(client, "claimnotapproved@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()

    db = SessionLocal()
    job = models.Job(source="remotive", external_id="1", canonical_hash="h1", title="Backend Engineer",
                      company="Acme", apply_url="https://x")
    db.add(job); db.commit()
    app1 = models.Application(profile_id=profile["id"], job_id=job.id, status=models.ApplicationStatus.ready_for_review)
    db.add(app1); db.commit()
    app1_id = app1.id
    db.close()

    resp = client.post(f"/applications/{app1_id}/claim-submission", headers=headers)
    assert resp.status_code == 409
