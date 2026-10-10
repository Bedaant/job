"""
Remotive public API — no auth required.
Docs: https://remotive.com/api-documentation
"""
import httpx

from providers import guard
from datetime import datetime

BASE_URL = "https://remotive.com/api/remote-jobs"


def fetch_remotive_jobs(search: str, limit: int = 50):
    """Returns a list of normalized job dicts."""
    resp = guard.call("remotive", lambda: httpx.get(BASE_URL, params={"search": search, "limit": limit}, timeout=20))
    resp.raise_for_status()
    data = resp.json()

    jobs = []
    for j in data.get("jobs", []):
        jobs.append({
            "source": "remotive",
            "external_id": str(j["id"]),
            "title": j.get("title", ""),
            "company": j.get("company_name", ""),
            "location": j.get("candidate_required_location"),
            "remote": True,
            "salary": j.get("salary") or None,
            "description": j.get("description", ""),
            "apply_url": j.get("url", ""),
            "tags": j.get("tags", []),
            "posted_at": _parse_date(j.get("publication_date")),
        })
    return jobs


def _parse_date(raw):
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
