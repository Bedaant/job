"""Aggregator `apply_url` -> real ATS apply target (ADR-015 Phase 2).

Feed jobs carry an aggregator link (`remoteok.com/l/123`, a Working Nomads
`/job/go/` bounce) rather than the company's application form. The driver opens
whatever it lands on, so the difference between a deterministically fillable
Greenhouse form and a guess is made here.

Every test in this file is offline — `httpx` is mocked. The SSRF tests are the
exception that matters: they mock DNS, not the guard, so the *real*
`discovery.is_safe_url` runs on every hop. Mocking the guard itself would make
the per-hop check untestable, which is precisely the bug being guarded against.
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import main
import models
from connectors.apply_target import MAX_HOPS, resolve_apply_target
from database import Base, get_db


def _resp(status, url, location=None, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.url = url
    resp.headers = {"location": location} if location else {}
    resp.text = text
    return resp


@pytest.fixture(autouse=True)
def _no_cache():
    """Redis must never be consulted by accident in these tests — the cache
    tests opt in explicitly. An unavailable Redis is also the production
    fallback path, so this doubles as coverage of it.
    """
    with patch("connectors.apply_target._cache", return_value=None):
        yield


# ---------- direct ATS URLs: no network at all ----------

def test_a_direct_greenhouse_url_resolves_without_any_network_call():
    with patch("connectors.apply_target.httpx.get") as mock_get:
        result = resolve_apply_target("https://boards.greenhouse.io/acmecorp/jobs/4001")

    mock_get.assert_not_called()
    assert result == {
        "final_url": "https://boards.greenhouse.io/acmecorp/jobs/4001",
        "ats_type": "greenhouse",
        "board_token": "acmecorp",
        "resolved": True,
    }


@pytest.mark.parametrize("url,ats,token", [
    ("https://jobs.lever.co/netlify/abc-123", "lever", "netlify"),
    ("https://jobs.ashbyhq.com/openai/xyz", "ashby", "openai"),
    ("https://job-boards.greenhouse.io/stripe/jobs/7", "greenhouse", "stripe"),
    ("https://boards.eu.greenhouse.io/gitlab/jobs/7", "greenhouse", "gitlab"),
    ("https://acme.wd5.myworkdayjobs.com/en-US/External/job/1", "workday", "acme"),
    ("https://apply.workable.com/vercel/j/ABC/", "workable", "vercel"),
    ("https://jobs.smartrecruiters.com/Bosch/74409", "smartrecruiters", "Bosch"),
])
def test_known_ats_url_shapes_are_recognised_offline(url, ats, token):
    with patch("connectors.apply_target.httpx.get") as mock_get:
        result = resolve_apply_target(url)

    mock_get.assert_not_called()
    assert (result["ats_type"], result["board_token"], result["resolved"]) == (ats, token, True)


@pytest.mark.parametrize("vendor_url", [
    "https://app.recruitee.com/",          # Recruitee's own console
    "https://www.teamtailor.com/pricing",  # the vendor's marketing site
    "https://jobs.breezy.hr/",
    "https://api.bamboohr.com/v1/",
])
def test_a_vendor_owned_subdomain_is_not_mistaken_for_a_tenant(vendor_url):
    """Found live on a real Arbeitnow page: a body mentioning `app.recruitee.com`
    was reported as company "app" on Recruitee, which would send the driver to a
    login screen and burn a submission attempt.
    """
    with patch("connectors.apply_target.httpx.get") as mock_get:
        mock_get.side_effect = [_resp(200, "https://agg.example/j/1", text=vendor_url)]
        with patch("connectors.discovery.socket.gethostbyname", return_value="93.184.216.34"):
            result = resolve_apply_target("https://agg.example/j/1")

    assert result["ats_type"] is None, f"{vendor_url} leaked a fake tenant"
    assert result["board_token"] is None


def test_a_real_tenant_subdomain_still_resolves():
    with patch("connectors.apply_target.httpx.get") as mock_get:
        mock_get.side_effect = [
            _resp(200, "https://agg.example/j/2",
                  text='<a href="https://myapp.recruitee.com/o/backend-engineer">Apply</a>'),
        ]
        with patch("connectors.discovery.socket.gethostbyname", return_value="93.184.216.34"):
            result = resolve_apply_target("https://agg.example/j/2")

    assert (result["ats_type"], result["board_token"]) == ("recruitee", "myapp")


# ---------- redirect chains ----------

@patch("connectors.discovery.socket.gethostbyname", return_value="93.184.216.34")
@patch("connectors.apply_target.httpx.get")
def test_a_redirect_chain_resolves_to_the_real_ats(mock_get, _dns):
    mock_get.side_effect = [
        _resp(302, "https://remoteok.com/l/123", location="https://www.workingnomads.com/job/go/9"),
        _resp(301, "https://www.workingnomads.com/job/go/9",
              location="https://boards.greenhouse.io/acmecorp/jobs/4001"),
        _resp(200, "https://boards.greenhouse.io/acmecorp/jobs/4001", text="<html>Apply</html>"),
    ]

    result = resolve_apply_target("https://remoteok.com/l/123")

    assert result["final_url"] == "https://boards.greenhouse.io/acmecorp/jobs/4001"
    assert result["ats_type"] == "greenhouse"
    assert result["board_token"] == "acmecorp"
    assert result["resolved"] is True
    assert mock_get.call_count == 3


@patch("connectors.discovery.socket.gethostbyname", return_value="93.184.216.34")
@patch("connectors.apply_target.httpx.get")
def test_the_page_body_is_used_when_the_final_url_says_nothing(mock_get, _dns):
    """An aggregator that renders an embedded ATS iframe instead of redirecting
    still tells us which ATS it is — in the markup.
    """
    mock_get.side_effect = [
        _resp(200, "https://someboard.example/job/42",
              text='<iframe src="https://jobs.lever.co/acme/1111/apply"></iframe>'),
    ]

    result = resolve_apply_target("https://someboard.example/job/42")

    assert result["final_url"] == "https://someboard.example/job/42"
    assert (result["ats_type"], result["board_token"]) == ("lever", "acme")


@patch("connectors.discovery.socket.gethostbyname", return_value="93.184.216.34")
@patch("connectors.apply_target.httpx.get")
def test_a_relative_location_header_is_resolved_against_the_current_hop(mock_get, _dns):
    mock_get.side_effect = [
        _resp(302, "https://agg.example/l/1", location="/out/greenhouse"),
        _resp(200, "https://agg.example/out/greenhouse", text="nothing useful"),
    ]

    result = resolve_apply_target("https://agg.example/l/1")

    assert result["final_url"] == "https://agg.example/out/greenhouse"
    assert result["ats_type"] is None
    assert result["resolved"] is True


# ---------- SSRF: every hop, not just the first ----------

@patch("connectors.apply_target.httpx.get")
def test_ssrf_guard_rejects_the_first_url_when_it_is_private(mock_get):
    with patch("connectors.discovery.socket.gethostbyname", return_value="127.0.0.1"):
        result = resolve_apply_target("https://localhost-alias.example/apply")

    mock_get.assert_not_called()
    assert result == {
        "final_url": "https://localhost-alias.example/apply",
        "ats_type": None,
        "board_token": None,
        "resolved": False,
    }


@patch("connectors.apply_target.httpx.get")
def test_ssrf_guard_rejects_a_chain_that_redirects_to_cloud_metadata(mock_get):
    """The whole point of checking every hop. The first host is a perfectly
    ordinary public aggregator; the *redirect target* is the AWS metadata
    endpoint. A guard applied only to the initial URL follows this happily.
    """
    mock_get.side_effect = [
        _resp(302, "https://agg.example/l/1", location="http://169.254.169.254/latest/meta-data/"),
        _resp(200, "http://169.254.169.254/latest/meta-data/", text="iam/security-credentials"),
    ]

    def fake_dns(host):
        return {"agg.example": "93.184.216.34", "169.254.169.254": "169.254.169.254"}[host]

    with patch("connectors.discovery.socket.gethostbyname", side_effect=fake_dns):
        result = resolve_apply_target("https://agg.example/l/1")

    # One fetch — the aggregator. The metadata hop was refused before any request.
    assert mock_get.call_count == 1
    assert result["final_url"] == "https://agg.example/l/1"
    assert result["resolved"] is False


@patch("connectors.apply_target.httpx.get")
def test_ssrf_guard_rejects_a_chain_that_redirects_to_loopback(mock_get):
    mock_get.side_effect = [
        _resp(302, "https://agg.example/l/1", location="http://localhost:6379/"),
        _resp(200, "http://localhost:6379/", text="redis"),
    ]

    def fake_dns(host):
        return {"agg.example": "93.184.216.34", "localhost": "127.0.0.1"}[host]

    with patch("connectors.discovery.socket.gethostbyname", side_effect=fake_dns):
        result = resolve_apply_target("https://agg.example/l/1")

    assert mock_get.call_count == 1
    assert result["resolved"] is False


@patch("connectors.apply_target.httpx.get")
def test_ssrf_guard_rejects_a_chain_that_redirects_to_a_private_network(mock_get):
    mock_get.side_effect = [
        _resp(302, "https://agg.example/l/1", location="http://10.0.0.5/admin"),
        _resp(200, "http://10.0.0.5/admin", text="internal"),
    ]

    def fake_dns(host):
        return {"agg.example": "93.184.216.34", "10.0.0.5": "10.0.0.5"}[host]

    with patch("connectors.discovery.socket.gethostbyname", side_effect=fake_dns):
        result = resolve_apply_target("https://agg.example/l/1")

    assert mock_get.call_count == 1
    assert result["resolved"] is False


def test_a_non_http_scheme_is_refused_without_dns_or_fetch():
    with patch("connectors.apply_target.httpx.get") as mock_get:
        result = resolve_apply_target("file:///C:/Windows/win.ini")

    mock_get.assert_not_called()
    assert result["resolved"] is False


# ---------- failure modes ----------

@patch("connectors.discovery.socket.gethostbyname", return_value="93.184.216.34")
@patch("connectors.apply_target.httpx.get")
def test_a_dead_link_returns_unresolved_rather_than_raising(mock_get, _dns):
    import httpx
    mock_get.side_effect = httpx.ConnectError("no route to host")

    result = resolve_apply_target("https://gone.example/l/1")

    assert result == {
        "final_url": "https://gone.example/l/1",
        "ats_type": None,
        "board_token": None,
        "resolved": False,
    }


@patch("connectors.discovery.socket.gethostbyname", return_value="93.184.216.34")
@patch("connectors.apply_target.httpx.get")
def test_the_hop_cap_terminates_a_redirect_loop(mock_get, _dns):
    mock_get.side_effect = lambda url, **kw: _resp(302, url, location="https://loop.example/b"
                                                   if url.endswith("/a") else "https://loop.example/a")

    result = resolve_apply_target("https://loop.example/a")

    assert mock_get.call_count == MAX_HOPS
    assert result["resolved"] is False
    assert result["final_url"] == "https://loop.example/a"


# ---------- cache ----------

def test_a_cache_hit_avoids_a_second_fetch():
    store = {}
    fake_redis = MagicMock()
    fake_redis.get.side_effect = lambda k: store.get(k)
    fake_redis.setex.side_effect = lambda k, ttl, v: store.__setitem__(k, v)

    with patch("connectors.apply_target._cache", return_value=fake_redis), \
         patch("connectors.discovery.socket.gethostbyname", return_value="93.184.216.34"), \
         patch("connectors.apply_target.httpx.get") as mock_get:
        mock_get.side_effect = [
            _resp(302, "https://agg.example/l/7", location="https://jobs.lever.co/acme/1"),
            _resp(200, "https://jobs.lever.co/acme/1", text=""),
        ]
        first = resolve_apply_target("https://agg.example/l/7")
        fetches_after_first = mock_get.call_count
        second = resolve_apply_target("https://agg.example/l/7")

    assert first == second
    assert first["ats_type"] == "lever"
    assert mock_get.call_count == fetches_after_first  # no extra round trip


def test_resolution_still_works_when_redis_is_down():
    fake_redis = MagicMock()
    fake_redis.get.side_effect = ConnectionError("redis unreachable")
    fake_redis.setex.side_effect = ConnectionError("redis unreachable")

    with patch("connectors.apply_target._cache", return_value=fake_redis), \
         patch("connectors.apply_target.httpx.get") as mock_get:
        result = resolve_apply_target("https://jobs.lever.co/acme/1")

    mock_get.assert_not_called()
    assert result["ats_type"] == "lever"


# ---------- work-queue integration ----------

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


def _seed(client, SessionLocal, headers, apply_url):
    profile_id = client.post(
        "/profiles", headers=headers, json={"persona": "developer"}
    ).json()["id"]
    session = SessionLocal()
    job = models.Job(
        source="remoteok", external_id=apply_url, title="Backend Engineer", company="Acme",
        canonical_hash=f"h-{apply_url}", apply_url=apply_url,
    )
    session.add(job)
    session.commit()
    app_row = models.Application(
        profile_id=profile_id, job_id=job.id, status=models.ApplicationStatus.approved
    )
    session.add(app_row)
    session.commit()
    app_id = app_row.id
    session.close()
    return app_id


def test_work_queue_serves_the_resolved_url_and_the_detected_ats():
    client, SessionLocal = _client()
    headers = _auth(client, "resolver@example.com")
    _seed(client, SessionLocal, headers, "https://remoteok.com/l/123")

    with patch("main.resolve_apply_target", return_value={
        "final_url": "https://boards.greenhouse.io/acmecorp/jobs/4001",
        "ats_type": "greenhouse", "board_token": "acmecorp", "resolved": True,
    }):
        item = client.get("/extension/work-queue", headers=headers).json()[0]

    assert item["apply_url"] == "https://boards.greenhouse.io/acmecorp/jobs/4001"
    assert item["original_apply_url"] == "https://remoteok.com/l/123"
    assert item["ats_type"] == "greenhouse"
    assert item["board_token"] == "acmecorp"


def test_work_queue_falls_back_to_the_original_url_when_resolution_fails():
    client, SessionLocal = _client()
    headers = _auth(client, "fallback@example.com")
    _seed(client, SessionLocal, headers, "https://remoteok.com/l/456")

    with patch("main.resolve_apply_target", return_value={
        "final_url": "https://remoteok.com/l/456",
        "ats_type": None, "board_token": None, "resolved": False,
    }):
        item = client.get("/extension/work-queue", headers=headers).json()[0]

    assert item["apply_url"] == "https://remoteok.com/l/456"
    assert item["ats_type"] is None


def test_work_queue_stays_backward_compatible_for_the_existing_driver():
    """The driver reads exactly these five keys. New fields are additive; if any
    of these disappears or changes shape the shipped extension breaks.
    """
    client, SessionLocal = _client()
    headers = _auth(client, "compat@example.com")
    app_id = _seed(client, SessionLocal, headers, "https://remoteok.com/l/789")

    with patch("main.resolve_apply_target", return_value={
        "final_url": "https://jobs.lever.co/acme/1",
        "ats_type": "lever", "board_token": "acme", "resolved": True,
    }):
        item = client.get("/extension/work-queue", headers=headers).json()[0]

    assert item["application_id"] == app_id
    assert item["profile_id"]
    assert item["company"] == "Acme"
    assert item["title"] == "Backend Engineer"
    assert isinstance(item["apply_url"], str) and item["apply_url"]


def test_work_queue_survives_a_resolver_that_blows_up():
    """Resolution is an optimisation. A resolver exception must not take out the
    whole queue — the original URL is still actionable.
    """
    client, SessionLocal = _client()
    headers = _auth(client, "boom@example.com")
    _seed(client, SessionLocal, headers, "https://remoteok.com/l/999")

    with patch("main.resolve_apply_target", side_effect=RuntimeError("resolver exploded")):
        resp = client.get("/extension/work-queue", headers=headers)

    assert resp.status_code == 200
    assert resp.json()[0]["apply_url"] == "https://remoteok.com/l/999"
