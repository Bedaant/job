"""GET /matches/{match_id}/keyword-gap — tenant scoping (ADR-007) and shape."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
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


def _seed_match(session, email):
    user = session.query(models.User).filter(models.User.email == email).one()
    profile = models.Profile(user_id=user.id, persona=models.Persona.developer)
    session.add(profile)
    session.flush()
    session.add(models.ResumeFact(
        profile_id=profile.id, category="experience",
        achievement="Built a Python service backed by PostgreSQL",
    ))
    job = models.Job(
        source="remotive", external_id="1", canonical_hash=f"h-{email}",
        title="Backend Engineer", company="Acme", apply_url="https://x",
        description="<p>Requirements: Python, PostgreSQL, Kubernetes.</p>",
        skills=["Python", "PostgreSQL", "Kubernetes"],
    )
    session.add(job)
    session.flush()
    match = models.Match(profile_id=profile.id, job_id=job.id, score=50, breakdown={}, state="new")
    session.add(match)
    session.commit()
    return match.id


def test_owner_gets_keyword_gap():
    client, SessionLocal = _client()
    headers = _auth(client, "owner-kg@example.com")
    session = SessionLocal()
    match_id = _seed_match(session, "owner-kg@example.com")
    session.close()

    resp = client.get(f"/matches/{match_id}/keyword-gap", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert 0.0 <= body["coverage"] <= 1.0
    assert {m["keyword"] for m in body["matched"]} >= {"Python", "PostgreSQL"}
    assert "Kubernetes" in {m["keyword"] for m in body["missing"]}
    missing = {m["keyword"] for m in body["missing"]}
    assert all(s["keyword"] not in missing for s in body["suggestions"])


def test_other_user_gets_404():
    client, SessionLocal = _client()
    _auth(client, "owner2-kg@example.com")
    intruder = _auth(client, "intruder-kg@example.com")
    session = SessionLocal()
    match_id = _seed_match(session, "owner2-kg@example.com")
    session.close()

    assert client.get(f"/matches/{match_id}/keyword-gap", headers=intruder).status_code == 404


def test_unknown_match_is_404():
    client, _ = _client()
    headers = _auth(client, "nobody-kg@example.com")
    resp = client.get("/matches/00000000-0000-0000-0000-000000000000/keyword-gap", headers=headers)
    assert resp.status_code == 404
