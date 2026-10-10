"""
Ashby public job posting API — no auth required, per-org token.
Docs: https://developers.ashbyhq.com/reference/jobpostingapi
"""
import httpx

from providers import guard

from connectors.config import TOKEN_COMPANY_NAMES
from connectors.normalize import coerce_posted_at

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{token}"


def fetch_ashby_jobs(org_token: str):
    url = BASE_URL.format(token=org_token)
    resp = guard.call("ashby", lambda: httpx.get(url, timeout=20))
    if resp.status_code != 200:
        return []
    data = resp.json()

    jobs = []
    for j in data.get("jobs", []):
        jobs.append({
            "source": "ashby",
            "board_token": org_token,  # COLLECT-D, see greenhouse.py
            "external_id": j.get("id", ""),
            "title": j.get("title", ""),
            "company": TOKEN_COMPANY_NAMES.get(org_token, org_token),
            "location": j.get("location"),
            "remote": bool(j.get("isRemote", False)),
            "salary": None,
            "description": j.get("descriptionPlain", ""),
            "apply_url": j.get("applyUrl") or j.get("jobUrl", ""),
            "tags": j.get("department") and [j["department"]] or [],
            "posted_at": coerce_posted_at(j.get("publishedAt")),
        })
    return jobs
