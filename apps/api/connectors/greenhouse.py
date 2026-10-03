"""
Greenhouse public job board API — no auth required, per-company board token.
Docs: https://developers.greenhouse.io/job-board.html
"""
import httpx

from connectors.config import TOKEN_COMPANY_NAMES
from connectors.normalize import coerce_posted_at

BASE_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"


def fetch_greenhouse_jobs(board_token: str):
    url = BASE_URL.format(token=board_token)
    resp = httpx.get(url, params={"content": "true"}, timeout=20)
    if resp.status_code != 200:
        return []
    data = resp.json()

    jobs = []
    for j in data.get("jobs", []):
        location = None
        if j.get("location"):
            location = j["location"].get("name")

        jobs.append({
            "source": "greenhouse",
            "external_id": str(j["id"]),
            "title": j.get("title", ""),
            # The curated map wins over the payload where both exist: Greenhouse's
            # own company_name sometimes carries board-page cruft canonical_hash's
            # suffix-strip doesn't cover (e.g. rubrik -> "Rubrik Job Board"), which
            # would defeat cross-source dedupe against a feed's plain "Rubrik".
            # The map is reviewed, clean text; the payload is Greenhouse's own
            # copy and is only a fallback for a token the map doesn't cover
            # (Fix round 1, Task 4 review).
            "company": TOKEN_COMPANY_NAMES.get(board_token) or j.get("company_name") or board_token,
            "location": location,
            "remote": "remote" in (location or "").lower(),
            "salary": None,
            "description": j.get("content", ""),
            "apply_url": j.get("absolute_url", ""),
            "tags": [],
            # first_published is the genuine publish date; updated_at is a
            # modification date bumped on any edit (see tests/test_greenhouse.py).
            "posted_at": coerce_posted_at(j.get("first_published")),
        })
    return jobs
