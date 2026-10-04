"""Onboarding: facts:bulk is idempotent (Back → Continue must not duplicate facts)
and GET /sources lists what discovery really searches."""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from database import Base, get_db


@pytest.fixture()
def client():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSessionLocal = sessionmaker(bind=engine)

    def override_get_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_get_db
    yield TestClient(main.app), TestSessionLocal
    main.app.dependency_overrides.clear()
    engine.dispose()


def _login(c, email):
    c.post("/auth/signup", json={"email": email, "password": "correct horse battery staple"})
    token = c.post("/auth/login", data={"username": email, "password": "correct horse battery staple"}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    profile = c.post("/profiles", json={"persona": "developer"}, headers=headers).json()
    return headers, profile["id"]


FACT = {"category": "experience", "achievement": "Cut p99 latency 40%", "metric": "40%", "proof": None, "tags": []}


@patch("matching.service.embed_texts", return_value=None)
def test_reposting_the_same_facts_does_not_duplicate_them(_embed, client):
    c, _ = client
    headers, pid = _login(c, "dupe@example.com")

    first = c.post(f"/profiles/{pid}/facts:bulk", json={"facts": [FACT]}, headers=headers)
    assert first.status_code == 200 and len(first.json()) == 1

    # Back then Continue: same fact again, differently spaced/cased, plus one new one.
    again = {**FACT, "achievement": "  cut p99   LATENCY 40% "}
    new = {**FACT, "achievement": "Shipped the billing rewrite"}
    second = c.post(f"/profiles/{pid}/facts:bulk", json={"facts": [again, new]}, headers=headers)
    assert second.status_code == 200
    assert [f["achievement"] for f in second.json()] == ["Shipped the billing rewrite"]
    assert second.headers["X-Skipped-Facts"] == "0"  # payload indices that were already saved

    saved = c.get(f"/resume-facts?profile_id={pid}", headers=headers).json()
    assert sorted(f["achievement"] for f in saved) == ["Cut p99 latency 40%", "Shipped the billing rewrite"]


@patch("matching.service.embed_texts", return_value=None)
def test_duplicates_inside_one_post_are_saved_once(_embed, client):
    c, _ = client
    headers, pid = _login(c, "dupe2@example.com")
    resp = c.post(f"/profiles/{pid}/facts:bulk", json={"facts": [FACT, FACT]}, headers=headers)
    assert len(resp.json()) == 1
    assert resp.headers["X-Skipped-Facts"] == "1"


@patch("matching.service.embed_texts", return_value=None)
def test_same_text_with_a_different_metric_is_a_different_fact(_embed, client):
    c, _ = client
    headers, pid = _login(c, "dupe3@example.com")
    c.post(f"/profiles/{pid}/facts:bulk", json={"facts": [FACT]}, headers=headers)
    resp = c.post(f"/profiles/{pid}/facts:bulk", json={"facts": [{**FACT, "metric": "55%"}]}, headers=headers)
    assert len(resp.json()) == 1
    assert resp.headers["X-Skipped-Facts"] == ""


def test_sources_lists_the_live_feeds_and_marks_dead_ones(client):
    c, SessionLocal = client
    headers, _ = _login(c, "sources@example.com")
    db = SessionLocal()
    db.add(models.Job(source="remoteok", external_id="1", canonical_hash="h1", title="SRE", company="A",
                      apply_url="https://example.com/1"))
    db.commit()
    db.close()

    resp = c.get("/sources", headers=headers)
    assert resp.status_code == 200
    by_id = {s["id"]: s for s in resp.json()}

    for feed in ["remoteok", "himalayas", "workingnomads", "jobicy", "arbeitnow", "weworkremotely", "remotive"]:
        assert by_id[feed]["enabled"] is True, feed
        assert by_id[feed]["label"]
    assert by_id["remoteok"]["job_count"] == 1
    assert by_id["himalayas"]["job_count"] == 0

    # `jobspy_google` used to be listed here with reason "Currently returns no
    # results" — JobSpy was never wired into discover_jobs_task, so the UI was
    # offering a source that could not contribute anything. COLLECT-F removed it;
    # tests/test_source_isolation.py pins that /sources only advertises sources
    # discovery actually fetches.
    assert "jobspy_google" not in by_id

    # Workday is advertised, and reports disabled until a tenant is configured.
    assert by_id["workday"]["label"]


def test_sources_requires_auth(client):
    c, _ = client
    assert c.get("/sources").status_code == 401
