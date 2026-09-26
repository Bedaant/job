"""Applicant identity (JSON Resume `basics`) — the data an application form
actually asks for. Before this existed, formfill could resolve `email` (on
User) and nothing else: no name, no phone, no structured location, no
LinkedIn/GitHub. See WORKLOG.

The validators here exist because a hallucinated name or phone number gets
typed into a real application sent to a real employer — that is direct harm
to the user, so "null rather than a plausible guess" is enforced, not just
requested in the prompt.
"""
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from schemas import ApplicantBasics, NetworkProfile


# ---------- null is always a valid answer ----------

def test_basics_accepts_everything_none():
    """A resume genuinely may not state a phone or a website. Null must always
    be available, or the model is pushed toward inventing something."""
    basics = ApplicantBasics()
    assert basics.full_name is None
    assert basics.phone is None
    assert basics.country_code is None
    assert basics.network_profiles == []


# ---------- country_code: ISO 3166-1 alpha-2 ----------

def test_country_code_rejects_full_country_name():
    with pytest.raises(ValidationError):
        ApplicantBasics(country_code="United States")


def test_country_code_rejects_three_letter_code():
    with pytest.raises(ValidationError):
        ApplicantBasics(country_code="USA")


def test_country_code_normalizes_lowercase():
    """Unambiguous, so normalize instead of burning a retry on it."""
    assert ApplicantBasics(country_code="us").country_code == "US"


def test_country_code_accepts_valid_alpha2():
    assert ApplicantBasics(country_code="IN").country_code == "IN"


# ---------- placeholder names ----------

@pytest.mark.parametrize("placeholder", ["John Doe", "jane doe", "Your Name", "N/A", "FIRST LAST"])
def test_full_name_rejects_known_placeholders(placeholder):
    with pytest.raises(ValidationError):
        ApplicantBasics(full_name=placeholder)


def test_full_name_accepts_a_real_name():
    assert ApplicantBasics(full_name="Bedaant Srivastav").full_name == "Bedaant Srivastav"


# ---------- phone ----------

def test_phone_rejects_reserved_fictional_us_range():
    """555-0100..555-0199 is the reserved fictional range — a model filling a
    gap with a 'realistic looking' number lands here surprisingly often."""
    with pytest.raises(ValidationError):
        ApplicantBasics(phone="(415) 555-0123")


def test_phone_rejects_too_few_digits():
    with pytest.raises(ValidationError):
        ApplicantBasics(phone="123")


def test_phone_accepts_real_international_number():
    assert ApplicantBasics(phone="+91 98765 43210").phone == "+91 98765 43210"


def test_phone_accepts_normal_us_number_not_in_fictional_range():
    assert ApplicantBasics(phone="(415) 555-2671").phone == "(415) 555-2671"


# ---------- urls ----------

def test_website_url_rejects_missing_scheme():
    with pytest.raises(ValidationError):
        ApplicantBasics(website_url="example.com")


def test_website_url_accepts_https():
    assert ApplicantBasics(website_url="https://example.com").website_url == "https://example.com"


def test_network_profile_requires_scheme_on_url():
    with pytest.raises(ValidationError):
        NetworkProfile(network="LinkedIn", username="bedaant", url="linkedin.com/in/bedaant")


def test_network_profile_accepts_valid_entry():
    p = NetworkProfile(network="LinkedIn", username="bedaant", url="https://linkedin.com/in/bedaant")
    assert p.network == "LinkedIn"


# ---------- extract_basics ----------

@patch("parsing.llm_extract._get_instructor_client")
def test_extract_basics_returns_validated_model(mock_get_client):
    from parsing.llm_extract import extract_basics

    expected = ApplicantBasics(full_name="Bedaant Srivastav", phone="+91 98765 43210", city="Bengaluru")
    client = MagicMock()
    client.messages.create.return_value = expected
    mock_get_client.return_value = client

    result = extract_basics("resume text here")

    assert result.full_name == "Bedaant Srivastav"
    assert result.city == "Bengaluru"
    # response_model must be the validated model, not a raw dict
    assert client.messages.create.call_args.kwargs["response_model"] is ApplicantBasics


def test_extract_basics_rejects_empty_text():
    from parsing.llm_extract import extract_basics

    with pytest.raises(ValueError):
        extract_basics("   ")


# ---------- build_profile_summary ----------

class _FakeProfile:
    """Minimal stand-in — build_profile_summary only reads attributes."""

    def __init__(self, **kwargs):
        defaults = {
            "full_name": None, "phone": None, "website_url": None, "street_address": None,
            "city": None, "region": None, "country_code": None, "postal_code": None,
            "network_profiles": [], "work_auth": [], "headline": None, "resume_facts": [],
        }
        for key, value in {**defaults, **kwargs}.items():
            setattr(self, key, value)


def test_profile_summary_omits_empty_fields_entirely():
    """A null must not appear as a key at all — sending "phone": null invites the
    model to map a field to a value that doesn't exist."""
    from formfill.map_fields import build_profile_summary

    summary = build_profile_summary(_FakeProfile(), "a@b.com")

    assert summary == {"email": "a@b.com"}
    assert "phone" not in summary
    assert "full_name" not in summary


def test_profile_summary_includes_the_fields_that_make_a_form_fillable():
    from formfill.map_fields import build_profile_summary

    profile = _FakeProfile(
        full_name="Bedaant Srivastav",
        phone="+91 98765 43210",
        city="Bengaluru",
        country_code="IN",
        network_profiles=[{"network": "LinkedIn", "username": "bedaant", "url": "https://linkedin.com/in/bedaant"}],
        work_auth=["IN-citizen"],
    )

    summary = build_profile_summary(profile, "a@b.com")

    assert summary["full_name"] == "Bedaant Srivastav"
    assert summary["phone"] == "+91 98765 43210"
    assert summary["city"] == "Bengaluru"
    assert summary["country_code"] == "IN"
    assert summary["network_profiles"][0]["network"] == "LinkedIn"
    assert summary["work_auth"] == ["IN-citizen"]


# ---------- endpoints ----------

def _client():
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import main
    from database import Base, get_db

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
    return TestClient(main.app)


def _auth(client, email):
    client.post("/auth/signup", json={"email": email, "password": "correct horse battery staple"})
    token = client.post(
        "/auth/login", data={"username": email, "password": "correct horse battery staple"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_basics_returns_empty_shape_before_anything_is_set():
    client = _client()
    headers = _auth(client, "bedaant-basics@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()

    resp = client.get(f"/profiles/{profile['id']}/basics", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["full_name"] is None
    assert body["network_profiles"] == []
    assert body["work_auth"] == []


def test_put_then_get_basics_round_trips():
    client = _client()
    headers = _auth(client, "bedaant-roundtrip@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()

    payload = {
        "full_name": "Bedaant Srivastav",
        "phone": "+91 98765 43210",
        "city": "Bengaluru",
        "country_code": "in",  # normalized to IN on the way in
        "network_profiles": [
            {"network": "GitHub", "username": "bedaant", "url": "https://github.com/bedaant"}
        ],
        "work_auth": ["IN-citizen"],
    }
    put = client.put(f"/profiles/{profile['id']}/basics", headers=headers, json=payload)
    assert put.status_code == 200

    got = client.get(f"/profiles/{profile['id']}/basics", headers=headers).json()
    assert got["full_name"] == "Bedaant Srivastav"
    assert got["country_code"] == "IN"
    assert got["network_profiles"][0]["url"] == "https://github.com/bedaant"
    assert got["work_auth"] == ["IN-citizen"]


def test_put_basics_rejects_placeholder_name_with_422():
    """The validation that protects a real application form is enforced at the
    API boundary too, not only during extraction."""
    client = _client()
    headers = _auth(client, "bedaant-placeholder@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()

    resp = client.put(
        f"/profiles/{profile['id']}/basics", headers=headers, json={"full_name": "John Doe"}
    )
    assert resp.status_code == 422


def test_basics_endpoints_are_tenant_scoped():
    client = _client()
    mine = _auth(client, "bedaant-mine@example.com")
    theirs = _auth(client, "bedaant-theirs@example.com")
    their_profile = client.post("/profiles", headers=theirs, json={"persona": "developer"}).json()

    assert client.get(f"/profiles/{their_profile['id']}/basics", headers=mine).status_code == 404
    assert client.put(
        f"/profiles/{their_profile['id']}/basics", headers=mine, json={"full_name": "Someone Else"}
    ).status_code == 404
