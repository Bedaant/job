from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from database import Base, get_db


def _client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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


def _signed_up_client():
    client, SessionLocal = _client()
    client.post("/auth/signup", json={"email": "events-test@example.com", "password": "correct horse battery staple"})
    token = client.post(
        "/auth/login", data={"username": "events-test@example.com", "password": "correct horse battery staple"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    return client, SessionLocal, headers


def test_update_application_status_writes_outbox_event():
    client, SessionLocal, headers = _signed_up_client()

    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()

    db = SessionLocal()
    job = models.Job(
        source="remotive", external_id="1", canonical_hash="h1", title="Backend Engineer",
        company="Acme", apply_url="https://x",
    )
    db.add(job)
    db.commit()
    job_id = job.id
    db.close()

    application = client.post(
        "/applications", headers=headers, json={"job_id": job_id, "profile_id": profile["id"]}
    ).json()

    resp = client.patch(
        f"/applications/{application['id']}", headers=headers, json={"status": "applied"}
    )
    assert resp.status_code == 200

    db = SessionLocal()
    events = db.query(models.Event).filter(models.Event.type == "application.status_changed").all()
    assert len(events) == 1
    assert events[0].payload == {"application_id": application["id"], "status": "applied"}
    db.close()


def test_list_and_patch_notifications():
    client, SessionLocal, headers = _signed_up_client()
    me = client.get("/profiles", headers=headers)  # just to confirm auth works
    assert me.status_code == 200

    db = SessionLocal()
    user = db.query(models.User).filter(models.User.email == "events-test@example.com").first()
    notif = models.Notification(
        user_id=user.id, trigger="weekly_digest", channel="in_app", template="digest_v1", payload={},
    )
    db.add(notif)
    db.commit()
    notif_id = notif.id
    db.close()

    resp = client.get("/notifications", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["status"] == "pending"

    resp = client.patch(f"/notifications/{notif_id}", headers=headers, json={"status": "seen"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "seen"


def test_patch_notification_not_owned_returns_404():
    client, SessionLocal, headers = _signed_up_client()
    client.get("/profiles", headers=headers)

    db = SessionLocal()
    other_user = models.User(email="other@example.com", password_hash="x")
    db.add(other_user)
    db.commit()
    notif = models.Notification(
        user_id=other_user.id, trigger="weekly_digest", channel="in_app", template="digest_v1", payload={},
    )
    db.add(notif)
    db.commit()
    notif_id = notif.id
    db.close()

    resp = client.patch(f"/notifications/{notif_id}", headers=headers, json={"status": "seen"})
    assert resp.status_code == 404
