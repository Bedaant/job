"""Greenhouse Job Board API, content=true. Field names verified against a live
board response (boards-api.greenhouse.io/v1/boards/stripe/jobs?content=true,
fetched 2026-10-03): the job object carries both `updated_at` (last edit —
bumped on any edit, not a posting date) and `first_published` (genuine
publish date, ISO 8601 with offset, e.g. "2026-09-09T10:50:29-04:00"). Using
`updated_at` as posted_at (the pre-fix behavior) silently skews every match
score's recency component. posted_at must come from `first_published`, or be
None when that field is absent.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

from connectors.greenhouse import fetch_greenhouse_jobs
from connectors.normalize import canonical_hash


@patch("connectors.greenhouse.httpx.get")
def test_posted_at_comes_from_first_published_not_updated_at(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"jobs": [
        {
            "id": 8172510,
            "title": "Abuse Investigator",
            "location": {"name": "Remote"},
            "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/8172510",
            "content": "<p>Investigate abuse</p>",
            "first_published": "2026-09-09T10:50:29-04:00",
            "updated_at": "2026-09-25T16:45:00-04:00",
        },
    ]})
    jobs = fetch_greenhouse_jobs("acme")
    assert jobs[0]["posted_at"] == datetime(2026, 9, 9, 14, 50, 29)


@patch("connectors.greenhouse.httpx.get")
def test_posted_at_is_none_when_first_published_absent(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"jobs": [
        {
            "id": 1,
            "title": "Engineer",
            "location": None,
            "absolute_url": "https://x",
            "content": "",
            "updated_at": "2026-09-25T16:45:00-04:00",
        },
    ]})
    jobs = fetch_greenhouse_jobs("acme")
    assert jobs[0]["posted_at"] is None


@patch("connectors.greenhouse.httpx.get")
def test_company_comes_from_payload_company_name_when_token_is_unmapped(mock_get):
    """Live board response (boards-api.greenhouse.io/v1/boards/grafanalabs/jobs,
    fetched 2026-10-03) carries `company_name` ("Grafana Labs") on every job
    object, distinct from the board token ("grafanalabs") used in the URL. Using
    a token this map does not cover, to isolate the payload path from the map."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"jobs": [
        {
            "id": 1,
            "title": "Engineer",
            "location": None,
            "absolute_url": "https://x",
            "content": "",
            "company_name": "Grafana Labs",
        },
    ]})
    jobs = fetch_greenhouse_jobs("some-unmapped-token")
    assert jobs[0]["company"] == "Grafana Labs"


@patch("connectors.greenhouse.httpx.get")
def test_company_falls_back_to_token_map_when_company_name_absent(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"jobs": [
        {"id": 1, "title": "Engineer", "location": None, "absolute_url": "https://x", "content": ""},
    ]})
    jobs = fetch_greenhouse_jobs("okta")
    assert jobs[0]["company"] == "Okta"


@patch("connectors.greenhouse.httpx.get")
def test_company_falls_back_to_the_raw_token_when_unmapped(mock_get):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"jobs": [
        {"id": 1, "title": "Engineer", "location": None, "absolute_url": "https://x", "content": ""},
    ]})
    jobs = fetch_greenhouse_jobs("some-unmapped-token")
    assert jobs[0]["company"] == "some-unmapped-token"


@patch("connectors.greenhouse.httpx.get")
def test_mapped_token_s_curated_name_overrides_a_noisy_payload_company_name(mock_get):
    """Fix round 1 (Task 4 review, Critical): rubrik's live payload company_name
    is "Rubrik Job Board" (boards-api.greenhouse.io/v1/boards/rubrik/jobs,
    fetched 2026-10-03), not "Rubrik". _COMPANY_SUFFIXES (normalize.py) only
    strips inc/llc/ltd/gmbh/pvt/private/limited -- "Job Board" survives into the
    hash, so canonical_hash("Rubrik Job Board", ...) != canonical_hash("Rubrik", ...)
    and the same role from a feed source under "Rubrik" could never dedupe
    against this board. The map's clean "Rubrik" must win over that payload
    value. Asserting on the hash, not just the string, because the hash is
    what dedupe actually depends on."""
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"jobs": [
        {
            "id": 1,
            "title": "Engineer",
            "location": {"name": "Remote"},
            "absolute_url": "https://x",
            "content": "",
            "company_name": "Rubrik Job Board",
        },
    ]})
    jobs = fetch_greenhouse_jobs("rubrik")
    assert jobs[0]["company"] == "Rubrik"
    got_hash = canonical_hash(jobs[0]["company"], jobs[0]["title"], jobs[0]["location"])
    assert got_hash == canonical_hash("Rubrik", "Engineer", "Remote")
