"""HTTP layer for the answer bank. The function-layer tenancy test in
test_answer_bank.py proves find_answer scopes by profile_id; this proves the
routes resolve ownership before they ever get there.
"""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
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
    return TestClient(main.app)


def _new_user(client, email):
    client.post("/auth/signup", json={"email": email, "password": "correct horse battery staple"})
    token = client.post(
        "/auth/login", data={"username": email, "password": "correct horse battery staple"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _profile(client, headers):
    return client.post("/profiles", headers=headers, json={"persona": "developer"}).json()["id"]


def test_put_then_get_round_trips_an_answer():
    client = _client()
    headers = _new_user(client, "ab-ep-1@example.com")
    pid = _profile(client, headers)

    resp = client.put(
        f"/profiles/{pid}/answers",
        headers=headers,
        json={"question_text": "What is your notice period?", "answer_text": "30 days"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["question_normalized"] == "what is your notice period"
    assert body["times_used"] == 0

    listed = client.get(f"/profiles/{pid}/answers", headers=headers).json()
    assert len(listed) == 1
    assert listed[0]["answer_text"] == "30 days"


def test_put_twice_updates_in_place_and_does_not_duplicate():
    client = _client()
    headers = _new_user(client, "ab-ep-2@example.com")
    pid = _profile(client, headers)

    first = client.put(
        f"/profiles/{pid}/answers",
        headers=headers,
        json={"question_text": "What is your notice period?", "answer_text": "30 days"},
    ).json()
    second = client.put(
        f"/profiles/{pid}/answers",
        headers=headers,
        json={"question_text": "what is your NOTICE period??", "answer_text": "60 days"},
    ).json()

    assert second["id"] == first["id"]
    listed = client.get(f"/profiles/{pid}/answers", headers=headers).json()
    assert len(listed) == 1
    assert listed[0]["answer_text"] == "60 days"


def test_put_rejects_a_demographic_question():
    client = _client()
    headers = _new_user(client, "ab-ep-3@example.com")
    pid = _profile(client, headers)

    resp = client.put(
        f"/profiles/{pid}/answers",
        headers=headers,
        json={"question_text": "What is your gender?", "answer_text": "Male"},
    )
    assert resp.status_code == 400
    assert client.get(f"/profiles/{pid}/answers", headers=headers).json() == []


def test_delete_removes_the_answer():
    client = _client()
    headers = _new_user(client, "ab-ep-4@example.com")
    pid = _profile(client, headers)
    answer_id = client.put(
        f"/profiles/{pid}/answers",
        headers=headers,
        json={"question_text": "What is your notice period?", "answer_text": "30 days"},
    ).json()["id"]

    assert client.delete(f"/profiles/{pid}/answers/{answer_id}", headers=headers).status_code == 204
    assert client.get(f"/profiles/{pid}/answers", headers=headers).json() == []


def test_delete_404s_for_an_unknown_answer_id():
    client = _client()
    headers = _new_user(client, "ab-ep-5@example.com")
    pid = _profile(client, headers)
    resp = client.delete(
        f"/profiles/{pid}/answers/00000000-0000-0000-0000-000000000000", headers=headers
    )
    assert resp.status_code == 404


def test_every_answer_route_404s_for_a_profile_the_caller_does_not_own():
    client = _client()
    mine = _new_user(client, "ab-ep-mine@example.com")
    theirs = _new_user(client, "ab-ep-theirs@example.com")
    their_pid = _profile(client, theirs)
    their_answer_id = client.put(
        f"/profiles/{their_pid}/answers",
        headers=theirs,
        json={"question_text": "What is your notice period?", "answer_text": "30 days"},
    ).json()["id"]

    assert client.get(f"/profiles/{their_pid}/answers", headers=mine).status_code == 404
    assert client.put(
        f"/profiles/{their_pid}/answers",
        headers=mine,
        json={"question_text": "Anything", "answer_text": "x"},
    ).status_code == 404
    assert client.delete(
        f"/profiles/{their_pid}/answers/{their_answer_id}", headers=mine
    ).status_code == 404

    # and the write attempt left their bank untouched
    still = client.get(f"/profiles/{their_pid}/answers", headers=theirs).json()
    assert len(still) == 1
    assert still[0]["answer_text"] == "30 days"


def test_delete_404s_for_an_answer_belonging_to_another_profile_of_the_same_user():
    """Ownership is per profile, not per user — the answer_id path param must be
    scoped by profile_id too, not looked up globally."""
    client = _client()
    headers = _new_user(client, "ab-ep-two-profiles@example.com")
    # one profile per persona (uq_profile_user_persona), so the second needs a
    # different persona
    pid_a = _profile(client, headers)
    pid_b = client.post(
        "/profiles", headers=headers, json={"persona": "product_manager"}
    ).json()["id"]
    answer_id = client.put(
        f"/profiles/{pid_a}/answers",
        headers=headers,
        json={"question_text": "What is your notice period?", "answer_text": "30 days"},
    ).json()["id"]

    assert client.delete(f"/profiles/{pid_b}/answers/{answer_id}", headers=headers).status_code == 404


def test_map_fields_fills_a_previously_flagged_essay_field_from_the_bank():
    """The integration this whole feature exists for. "Why do you want to work
    here" is flagged unconditionally today; with a stored, user-written answer
    it comes back filled, and the run is not interrupted."""
    client = _client()
    headers = _new_user(client, "ab-ep-integration@example.com")
    pid = _profile(client, headers)
    field = {"field_id": "f1", "label_text": "Why do you want to work here?", "input_type": "textarea"}

    before = client.post(
        "/extension/map-fields",
        headers=headers,
        json={"profile_id": pid, "url": "https://boards.greenhouse.io/acme/jobs/1", "fields": [field]},
    ).json()
    assert before[0]["maps_to"] == "unknown"  # today's behaviour, unchanged with an empty bank

    client.put(
        f"/profiles/{pid}/answers",
        headers=headers,
        json={
            "question_text": "Why do you want to work here?",
            "answer_text": "Your product solves a problem I have shipped against twice.",
        },
    )

    after = client.post(
        "/extension/map-fields",
        headers=headers,
        json={"profile_id": pid, "url": "https://boards.greenhouse.io/acme/jobs/1", "fields": [field]},
    ).json()
    assert after[0]["maps_to"] == "answer_bank"
    assert after[0]["value"] == "Your product solves a problem I have shipped against twice."
    assert after[0]["confidence"] == 1.0

    # and serving it through the real endpoint counted as a use
    listed = client.get(f"/profiles/{pid}/answers", headers=headers).json()
    assert listed[0]["times_used"] == 1


def test_map_fields_never_serves_a_bank_answer_to_a_demographic_field():
    """End-to-end version of the demographic rail: the only way to get a row in
    is PUT, which refuses, and even a field whose label merely contains a
    demographic keyword can never pick up a neighbouring answer."""
    client = _client()
    headers = _new_user(client, "ab-ep-demo@example.com")
    pid = _profile(client, headers)
    client.put(
        f"/profiles/{pid}/answers",
        headers=headers,
        json={"question_text": "Why do you want to work here?", "answer_text": "Because."},
    )

    resp = client.post(
        "/extension/map-fields",
        headers=headers,
        json={
            "profile_id": pid,
            "url": "https://boards.greenhouse.io/acme/jobs/1",
            "fields": [
                {"field_id": "f1", "label_text": "What is your gender?", "input_type": "select"},
                {"field_id": "f2", "label_text": "Veteran status", "input_type": "select"},
                {"field_id": "f3", "label_text": "Disability status", "input_type": "select"},
            ],
        },
    ).json()

    for mapping in resp:
        assert mapping["maps_to"] == "unknown"
        assert mapping["value"] is None
        assert mapping["confidence"] == 0.0
