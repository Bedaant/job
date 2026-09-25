"""Reed API — UK job board, official (PRD.md §6 Tier 2). Auth: HTTP Basic,
API key as username, empty password. No-ops if no key is configured.
Docs: https://www.reed.co.uk/developers/jobseeker
"""
from datetime import datetime

import httpx

from core.config import get_settings

BASE_URL = "https://www.reed.co.uk/api/1.0/search"


def fetch_reed_jobs(keywords: str, limit: int = 50):
    """Returns a list of normalized job dicts. No-ops (returns []) if
    REED_API_KEY isn't configured — matches the pattern of connectors that
    depend on optional per-user config (board tokens), not a hard failure.
    """
    api_key = get_settings().reed_api_key
    if not api_key:
        return []

    resp = httpx.get(
        BASE_URL,
        params={"keywords": keywords, "resultsToTake": limit},
        auth=(api_key, ""),
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()

    jobs = []
    for j in data.get("results", []):
        jobs.append({
            "source": "reed",
            "external_id": str(j["jobId"]),
            "title": j.get("jobTitle", ""),
            "company": j.get("employerName", ""),
            "location": j.get("locationName"),
            "remote": "remote" in (j.get("locationName") or "").lower(),
            "salary": _format_salary(j),
            "description": j.get("jobDescription", ""),
            "apply_url": j.get("jobUrl", ""),
            "tags": [],
            "posted_at": _parse_date(j.get("date")),
        })
    return jobs


def _format_salary(j: dict) -> str | None:
    lo, hi, currency = j.get("minimumSalary"), j.get("maximumSalary"), j.get("currency")
    if not lo and not hi:
        return None
    if lo and hi and lo != hi:
        return f"{lo:.0f}-{hi:.0f} {currency}".strip()
    return f"{lo or hi:.0f} {currency}".strip()


def _parse_date(raw: str | None):
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%d/%m/%Y")
    except ValueError:
        return None
