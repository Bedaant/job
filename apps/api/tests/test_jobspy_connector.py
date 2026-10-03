import json
from datetime import datetime
from unittest.mock import MagicMock, patch


@patch("connectors.jobspy_connector.subprocess.run")
def test_fetch_jobspy_jobs_parses_subprocess_json(mock_run):
    payload = [{"title": "Backend Engineer", "company": "Acme", "site": "google", "job_url": "https://x", "location": "Remote", "date_posted": "2026-08-16"}]
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(payload))

    from connectors.jobspy_connector import fetch_jobspy_jobs
    jobs = fetch_jobspy_jobs("backend engineer", results_wanted=5)

    assert jobs == [{
        "source": "jobspy_google",
        "external_id": "https://x",
        "title": "Backend Engineer",
        "company": "Acme",
        "location": "Remote",
        "apply_url": "https://x",
        "posted_at": datetime(2026, 8, 16),
    }]


@patch("connectors.jobspy_connector.subprocess.run")
def test_fetch_jobspy_jobs_posted_at_none_when_date_posted_missing(mock_run):
    payload = [{"title": "PM", "company": "Acme", "site": "google", "job_url": "https://y", "location": "Remote", "date_posted": None}]
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(payload))

    from connectors.jobspy_connector import fetch_jobspy_jobs
    jobs = fetch_jobspy_jobs("pm", results_wanted=5)
    assert jobs[0]["posted_at"] is None


@patch("connectors.jobspy_connector.subprocess.run")
def test_fetch_jobspy_jobs_returns_empty_on_subprocess_failure(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

    from connectors.jobspy_connector import fetch_jobspy_jobs
    assert fetch_jobspy_jobs("backend engineer") == []


@patch("connectors.jobspy_connector.subprocess.run")
def test_fetch_jobspy_jobs_returns_empty_on_no_results(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="[]")

    from connectors.jobspy_connector import fetch_jobspy_jobs
    assert fetch_jobspy_jobs("backend engineer") == []


@patch("connectors.jobspy_connector.subprocess.run")
def test_fetch_jobspy_jobs_tags_source_per_site_not_always_google(mock_run):
    """ADR-015 lifted the Google-only restriction. A row scraped from
    ZipRecruiter must not be recorded as coming from Google."""
    payload = [{"title": "PM", "company": "Acme", "site": "zip_recruiter",
                "job_url": "https://z", "location": "Remote", "date_posted": "2026-09-26"}]
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(payload))

    from connectors.jobspy_connector import fetch_jobspy_jobs
    assert fetch_jobspy_jobs("pm")[0]["source"] == "jobspy_zip_recruiter"


def test_jobspy_never_scrapes_linkedin_or_indeed():
    """ADR-015 parks LinkedIn (special case) and defers Indeed to Tier C.
    Neither may appear in the default site list."""
    from connectors import config
    assert "linkedin" not in config.JOBSPY_SITES
    assert "indeed" not in config.JOBSPY_SITES
    assert config.JOBSPY_SITES, "at least one JobSpy site must be enabled"
