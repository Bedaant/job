from unittest.mock import patch

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


@patch("main.map_form_fields")
def test_map_fields_endpoint_returns_mappings_for_owned_profile(mock_map):
    mock_map.return_value = [
        {"field_id": "f1", "maps_to": "profile.email", "confidence": 0.9, "value": "formfill-test@example.com"},
    ]
    client = _client()
    headers = _new_user(client, "formfill-test@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()

    resp = client.post(
        "/extension/map-fields",
        headers=headers,
        json={
            "profile_id": profile["id"],
            "url": "https://boards.greenhouse.io/acme/jobs/1",
            "fields": [{"field_id": "f1", "label_text": "Email", "input_type": "email"}],
        },
    )

    assert resp.status_code == 200
    assert resp.json() == [
        {"field_id": "f1", "maps_to": "profile.email", "confidence": 0.9, "value": "formfill-test@example.com"}
    ]
    mock_map.assert_called_once()


def test_map_fields_endpoint_404s_for_profile_not_owned_by_caller():
    client = _client()
    headers = _new_user(client, "formfill-a@example.com")
    other_headers = _new_user(client, "formfill-b@example.com")
    other_profile = client.post("/profiles", headers=other_headers, json={"persona": "developer"}).json()

    resp = client.post(
        "/extension/map-fields",
        headers=headers,
        json={"profile_id": other_profile["id"], "url": "https://x", "fields": []},
    )
    assert resp.status_code == 404
