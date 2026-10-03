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
