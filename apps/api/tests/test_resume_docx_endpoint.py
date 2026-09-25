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


def test_download_resume_docx_returns_a_real_ats_safe_document():
    client = _client()
    client.post("/auth/signup", json={"email": "docx-test@example.com", "password": "correct horse battery staple"})
    token = client.post(
        "/auth/login", data={"username": "docx-test@example.com", "password": "correct horse battery staple"}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    profile = client.post(
        "/profiles", headers=headers, json={"persona": "developer", "headline": "Backend Engineer"}
    ).json()
    client.post(
        "/resume-facts", headers=headers,
        json={"category": "experience", "achievement": "Led a team of 5 engineers"},
    )

    resp = client.get(f"/profiles/{profile['id']}/resume.docx", headers=headers)

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert resp.content[:2] == b"PK"  # DOCX is a real zip archive
