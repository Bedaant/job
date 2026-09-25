from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from connectors.discovery import (
    ATS_PATTERNS, classify_unknown_ats, detect_ats, discover_ats_for_domain, is_safe_url,
)


# ---------- SSRF guard (ARCHITECTURE.md §6) ----------

def test_is_safe_url_rejects_non_http_scheme():
    assert is_safe_url("ftp://example.com") is False
    assert is_safe_url("file:///etc/passwd") is False


@patch("connectors.discovery.socket.gethostbyname")
def test_is_safe_url_rejects_loopback(mock_resolve):
    mock_resolve.return_value = "127.0.0.1"
    assert is_safe_url("https://localhost/careers") is False


@patch("connectors.discovery.socket.gethostbyname")
def test_is_safe_url_rejects_private_ip(mock_resolve):
    mock_resolve.return_value = "10.0.0.5"
    assert is_safe_url("https://internal.example.com/careers") is False


@patch("connectors.discovery.socket.gethostbyname")
def test_is_safe_url_rejects_link_local_metadata_endpoint(mock_resolve):
    mock_resolve.return_value = "169.254.169.254"  # cloud metadata service — classic SSRF target
    assert is_safe_url("https://metadata.internal/careers") is False


@patch("connectors.discovery.socket.gethostbyname")
def test_is_safe_url_accepts_public_ip(mock_resolve):
    mock_resolve.return_value = "93.184.216.34"  # a public IP
    assert is_safe_url("https://example.com/careers") is True


@patch("connectors.discovery.socket.gethostbyname")
def test_is_safe_url_rejects_unresolvable_host(mock_resolve):
    mock_resolve.side_effect = OSError("name resolution failed")
    assert is_safe_url("https://does-not-exist.invalid/careers") is False


# ---------- ATS pattern detection ----------

def test_ats_patterns_cover_known_boards():
    types = {p.ats_type for p in ATS_PATTERNS}
    assert {"greenhouse", "lever", "ashby", "workable", "smartrecruiters"} <= types


@patch("connectors.discovery.is_safe_url", return_value=True)
@patch("connectors.discovery.httpx.get")
def test_detect_ats_finds_greenhouse_board(mock_get, _safe):
    resp = MagicMock()
    resp.url = "https://acme.com/careers"
    resp.text = '<a href="https://boards.greenhouse.io/acmecorp">Careers</a>'
    mock_get.return_value = resp

    result = detect_ats("acme.com")
    assert result == ("greenhouse", "acmecorp")


@patch("connectors.discovery.is_safe_url", return_value=True)
@patch("connectors.discovery.httpx.get")
def test_detect_ats_finds_lever_board(mock_get, _safe):
    resp = MagicMock()
    resp.url = "https://acme.com/careers"
    resp.text = 'apply at <a href="https://jobs.lever.co/acmecorp/abc123">this role</a>'
    mock_get.return_value = resp

    result = detect_ats("acme.com")
    assert result == ("lever", "acmecorp")


@patch("connectors.discovery.is_safe_url", return_value=True)
@patch("connectors.discovery.httpx.get")
def test_detect_ats_returns_none_when_no_pattern_matches(mock_get, _safe):
    resp = MagicMock()
    resp.url = "https://acme.com/careers"
    resp.text = "<p>We are not hiring right now.</p>"
    mock_get.return_value = resp

    assert detect_ats("acme.com") is None


@patch("connectors.discovery.is_safe_url", return_value=True)
@patch("connectors.discovery.httpx.get")
def test_detect_ats_tries_multiple_paths(mock_get, _safe):
    """First path (/careers) has nothing, second path (/jobs) has the board link."""
    empty = MagicMock(url="https://acme.com/careers", text="<p>nothing here</p>")
    found = MagicMock(url="https://acme.com/jobs", text='<a href="https://jobs.ashbyhq.com/acmecorp">Jobs</a>')
    mock_get.side_effect = [empty, found]

    result = detect_ats("acme.com")
    assert result == ("ashby", "acmecorp")
    assert mock_get.call_count == 2


@patch("connectors.discovery.is_safe_url", return_value=False)
def test_detect_ats_skips_unsafe_urls_without_fetching(mock_safe):
    with patch("connectors.discovery.httpx.get") as mock_get:
        result = detect_ats("internal.example.com")
    mock_get.assert_not_called()
    assert result is None


# ---------- F5: unknown-ATS Claude classification ----------

def _db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


@patch("connectors.discovery.call_llm")
@patch("connectors.discovery.is_safe_url", return_value=True)
@patch("connectors.discovery.httpx.get")
def test_classify_unknown_ats_returns_parsed_proposal(mock_get, _safe, mock_call_llm):
    resp = MagicMock(status_code=200, text="<script src='workday-bundle.js'></script>")
    resp.url = "https://acme.com/careers"
    mock_get.return_value = resp
    mock_call_llm.return_value = (
        '{"ats_type": "workday", "proposed_regex": "acme\\\\.wd1\\\\.myworkdayjobs\\\\.com/([a-zA-Z0-9_-]+)", '
        '"confidence": "medium", "evidence": "workday-bundle.js script tag"}'
    )

    result = classify_unknown_ats("acme.com")

    assert result["ats_type"] == "workday"
    assert result["confidence"] == "medium"
    mock_call_llm.assert_called_once()


@patch("connectors.discovery.is_safe_url", return_value=False)
def test_classify_unknown_ats_returns_none_when_no_page_reachable(mock_safe):
    with patch("connectors.discovery.httpx.get") as mock_get:
        result = classify_unknown_ats("internal.example.com")
    mock_get.assert_not_called()
    assert result is None


@patch("connectors.discovery.classify_unknown_ats")
@patch("connectors.discovery.detect_ats")
def test_discover_ats_for_domain_returns_known_pattern_without_classifying(mock_detect, mock_classify):
    mock_detect.return_value = ("greenhouse", "acmecorp")
    db = _db()

    result = discover_ats_for_domain(db, "acme.com")

    assert result == ("greenhouse", "acmecorp")
    mock_classify.assert_not_called()
    assert db.query(models.ConnectorRun).count() == 0


@patch("connectors.discovery.classify_unknown_ats")
@patch("connectors.discovery.detect_ats", return_value=None)
def test_discover_ats_for_domain_logs_proposal_for_human_review(_mock_detect, mock_classify):
    mock_classify.return_value = {"ats_type": "workday", "proposed_regex": "x", "confidence": "low", "evidence": "y"}
    db = _db()

    result = discover_ats_for_domain(db, "acme.com")

    assert result is None  # never auto-promotes into ATS_PATTERNS
    run = db.query(models.ConnectorRun).one()
    assert run.source == "ats_discovery_classify"
    assert run.token == "acme.com"
    assert run.failed == 0
    assert run.notes["ats_type"] == "workday"


@patch("connectors.discovery.classify_unknown_ats", return_value=None)
@patch("connectors.discovery.detect_ats", return_value=None)
def test_discover_ats_for_domain_logs_failure_when_classification_finds_nothing(_mock_detect, _mock_classify):
    db = _db()

    result = discover_ats_for_domain(db, "acme.com")

    assert result is None
    run = db.query(models.ConnectorRun).one()
    assert run.failed == 1
    assert run.notes is None
