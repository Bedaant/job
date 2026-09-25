import json
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
        "posted_at": "2026-08-16",
    }]


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
