"""Ashby Job Posting API. `publishedAt` is ISO 8601 with a Z suffix; must be
parsed to a real datetime rather than stored as the raw string (the pre-fix
behavior that zeroed the recency score component)."""
from datetime import datetime
from unittest.mock import MagicMock, patch

from connectors.ashby import fetch_ashby_jobs


@patch("connectors.ashby.httpx.get")
def test_posted_at_parsed_from_published_at(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"jobs": [
        {
            "id": "abc",
            "title": "Engineer",
            "location": "Remote",
            "isRemote": True,
            "descriptionPlain": "Build things",
            "applyUrl": "https://jobs.ashbyhq.com/acme/abc",
            "department": "Engineering",
            "publishedAt": "2026-09-09T10:50:29.000Z",
        },
    ]})
    jobs = fetch_ashby_jobs("acme")
    assert jobs[0]["posted_at"] == datetime(2026, 9, 9, 10, 50, 29)


@patch("connectors.ashby.httpx.get")
def test_posted_at_is_none_when_published_at_missing(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"jobs": [
        {"id": "x", "title": "Designer"},
    ]})
    jobs = fetch_ashby_jobs("acme")
    assert jobs[0]["posted_at"] is None


@patch("connectors.ashby.httpx.get")
def test_company_comes_from_the_token_map_not_the_token(mock_get):
    """Live board response (api.ashbyhq.com/posting-api/job-board/sarvam, fetched
    2026-10-03) has no company name field on the job object at all — just id,
    title, department, team, location, etc. The display name has to come from
    an explicit token map."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"jobs": [
        {"id": "x", "title": "Engineer"},
    ]})
    jobs = fetch_ashby_jobs("sarvam")
    assert jobs[0]["company"] == "Sarvam"


@patch("connectors.ashby.httpx.get")
def test_company_falls_back_to_the_raw_token_when_unmapped(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"jobs": [
        {"id": "x", "title": "Engineer"},
    ]})
    jobs = fetch_ashby_jobs("some-unmapped-token")
    assert jobs[0]["company"] == "some-unmapped-token"
