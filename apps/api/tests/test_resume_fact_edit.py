"""PATCH/DELETE /resume-facts/{id}: the user keeps their facts true after
onboarding. Owner-scoped, and an edited fact never keeps a vector computed from
its old text (matching would otherwise rank jobs against words that are gone).
"""
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from database import Base, get_db

A = [1.0] + [0.0] * 511
B = [0.0, 1.0] + [0.0] * 510
C = [0.0, 0.0, 1.0] + [0.0] * 509


def _client():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = override_get_db
    return TestClient(main.app), Session


def _user(client, email):
    client.post("/auth/signup", json={"email": email, "password": "correct horse battery staple"})
    token = client.post(
        "/auth/login", data={"username": email, "password": "correct horse battery staple"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    pid = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()["id"]
    return headers, pid


def _seed(client, headers, pid):
    facts = [
        {"category": "experience", "achievement": "Cut deploy time by 40%"},
        {"category": "skill", "achievement": "Python"},
    ]
    with patch("matching.service.embed_texts", return_value=[A, B]):
        return client.post(f"/profiles/{pid}/facts:bulk", headers=headers, json={"facts": facts}).json()


def _row(Session, fact_id):
    with Session() as db:
        return db.get(models.ResumeFact, fact_id)


def _centroid(Session, pid):
    with Session() as db:
        c = db.get(models.Profile, pid).fact_centroid
        return None if c is None else [float(x) for x in c]


def test_patch_updates_fields_and_reembeds_the_new_text():
    client, Session = _client()
    headers, pid = _user(client, "fe-1@example.com")
    fact = _seed(client, headers, pid)[0]

    with patch("matching.service.embed_texts", return_value=[C]) as embed:
        resp = client.patch(
            f"/resume-facts/{fact['id']}", headers=headers,
            json={"achievement": "Cut deploy time by 45%", "metric": "45%"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["achievement"] == "Cut deploy time by 45%"
    assert body["metric"] == "45%"
    assert body["category"] == "experience"  # untouched fields stay
    embed.assert_called_once_with(["Cut deploy time by 45%"], input_type="document")
    assert [float(x) for x in _row(Session, fact["id"]).embedding] == C
    # centroid = mean(C, B), not the stale A
    assert _centroid(Session, pid)[:3] == [0.0, 0.5, 0.5]


def test_patch_when_voyage_fails_clears_the_vector_and_still_saves():
    client, Session = _client()
    headers, pid = _user(client, "fe-2@example.com")
    fact = _seed(client, headers, pid)[0]

    with patch("matching.service.embed_texts", side_effect=RuntimeError("voyage down")):
        resp = client.patch(f"/resume-facts/{fact['id']}", headers=headers, json={"achievement": "New words"})
    assert resp.status_code == 200
    assert _row(Session, fact["id"]).achievement == "New words"
    assert _row(Session, fact["id"]).embedding is None
    assert _centroid(Session, pid)[:2] == [0.0, 1.0]  # only the untouched fact counts


def test_a_fact_left_unembedded_is_embedded_on_the_next_edit():
    client, Session = _client()
    headers, pid = _user(client, "fe-3@example.com")
    first, second = _seed(client, headers, pid)
    with patch("matching.service.embed_texts", return_value=None):  # no key configured
        client.patch(f"/resume-facts/{first['id']}", headers=headers, json={"achievement": "Later"})
    assert _row(Session, first["id"]).embedding is None

    with patch("matching.service.embed_texts", return_value=[C, A]) as embed:
        client.patch(f"/resume-facts/{second['id']}", headers=headers, json={"achievement": "Go"})
    texts = embed.call_args.args[0]
    assert sorted(texts) == ["Go", "Later"]
    assert _row(Session, first["id"]).embedding is not None


def test_patch_without_text_change_does_not_call_voyage():
    client, Session = _client()
    headers, pid = _user(client, "fe-4@example.com")
    fact = _seed(client, headers, pid)[0]
    with patch("matching.service.embed_texts") as embed:
        resp = client.patch(f"/resume-facts/{fact['id']}", headers=headers, json={"proof": "Acme"})
    assert resp.status_code == 200
    embed.assert_not_called()
    assert [float(x) for x in _row(Session, fact["id"]).embedding] == A


def test_patch_rejects_empty_achievement():
    client, _ = _client()
    headers, pid = _user(client, "fe-5@example.com")
    fact = _seed(client, headers, pid)[0]
    resp = client.patch(f"/resume-facts/{fact['id']}", headers=headers, json={"achievement": "  "})
    assert resp.status_code == 422
    resp = client.patch(f"/resume-facts/{fact['id']}", headers=headers, json={"achievement": None})
    assert resp.status_code == 422


def test_delete_removes_the_fact_and_recomputes_the_centroid():
    client, Session = _client()
    headers, pid = _user(client, "fe-6@example.com")
    fact = _seed(client, headers, pid)[0]
    with patch("matching.service.embed_texts") as embed:
        resp = client.delete(f"/resume-facts/{fact['id']}", headers=headers)
    assert resp.status_code == 204
    embed.assert_not_called()
    assert _row(Session, fact["id"]) is None
    assert _centroid(Session, pid)[:2] == [0.0, 1.0]


def test_deleting_the_last_fact_clears_the_centroid():
    client, Session = _client()
    headers, pid = _user(client, "fe-7@example.com")
    for f in _seed(client, headers, pid):
        client.delete(f"/resume-facts/{f['id']}", headers=headers)
    assert _centroid(Session, pid) is None


def test_another_users_fact_is_invisible_to_patch_and_delete():
    client, Session = _client()
    owner, pid = _user(client, "fe-owner@example.com")
    stranger, _ = _user(client, "fe-stranger@example.com")
    fact = _seed(client, owner, pid)[0]

    assert client.patch(f"/resume-facts/{fact['id']}", headers=stranger, json={"achievement": "x"}).status_code == 404
    assert client.delete(f"/resume-facts/{fact['id']}", headers=stranger).status_code == 404
    assert _row(Session, fact["id"]).achievement == "Cut deploy time by 40%"


def test_unauthenticated_is_rejected():
    client, _ = _client()
    assert client.delete("/resume-facts/anything").status_code == 401
