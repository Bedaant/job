"""Lever's createdAt is epoch milliseconds; jobs.posted_at is a timestamp. Postgres
rejects the raw integer (found by the first live Lever upsert, ADR-016 CLI)."""
from datetime import datetime
from unittest.mock import MagicMock, patch

from connectors.lever import fetch_lever_jobs


@patch("connectors.lever.httpx.get")
def test_posted_at_is_a_datetime_not_epoch_ms(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: [
        {"id": "abc", "text": "Engineer", "createdAt": 1771264785944, "categories": {}},
        {"id": "def", "text": "Designer", "categories": {}},
    ])
    jobs = fetch_lever_jobs("acme")
    assert jobs[0]["posted_at"] == datetime(2026, 2, 16, 17, 59, 45)
    assert jobs[1]["posted_at"] is None


@patch("connectors.lever.httpx.get")
def test_company_comes_from_the_token_map_not_the_token(mock_get):
    """Live postings response (api.lever.co/v0/postings/meesho, fetched 2026-10-03)
    has no company name field on the job object at all. The display name has to
    come from an explicit token map."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: [
        {"id": "abc", "text": "Engineer", "categories": {}},
    ])
    jobs = fetch_lever_jobs("meesho")
    assert jobs[0]["company"] == "Meesho"


@patch("connectors.lever.httpx.get")
def test_company_falls_back_to_the_raw_token_when_unmapped(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: [
        {"id": "abc", "text": "Engineer", "categories": {}},
    ])
    jobs = fetch_lever_jobs("some-unmapped-token")
    assert jobs[0]["company"] == "some-unmapped-token"
