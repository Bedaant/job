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


def test_create_and_list_profile():
    client = _client()
    client.post("/auth/signup", json={"email": "profiles-test@example.com", "password": "correct horse battery staple"})
    token = client.post(
        "/auth/login", data={"username": "profiles-test@example.com", "password": "correct horse battery staple"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    resp = client.post("/profiles", headers=headers, json={"persona": "developer", "headline": "Backend Engineer"})
    assert resp.status_code == 200
    assert resp.json()["persona"] == "developer"
    assert resp.json()["headline"] == "Backend Engineer"

    resp = client.get("/profiles", headers=headers)
    assert len(resp.json()) == 1

    main.app.dependency_overrides.clear()


def test_profiles_are_not_visible_across_users():
    client = _client()
    client.post("/auth/signup", json={"email": "owner3@example.com", "password": "correct horse battery staple"})
    owner_token = client.post(
        "/auth/login", data={"username": "owner3@example.com", "password": "correct horse battery staple"}
    ).json()["access_token"]
    client.post("/profiles", headers={"Authorization": f"Bearer {owner_token}"}, json={"persona": "developer"})

    client.post("/auth/signup", json={"email": "other3@example.com", "password": "correct horse battery staple"})
    other_token = client.post(
        "/auth/login", data={"username": "other3@example.com", "password": "correct horse battery staple"}
    ).json()["access_token"]

    resp = client.get("/profiles", headers={"Authorization": f"Bearer {other_token}"})
    assert resp.json() == []

    main.app.dependency_overrides.clear()
