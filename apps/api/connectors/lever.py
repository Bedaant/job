"""
Lever public postings API — no auth required, per-company token.
Docs: https://github.com/lever/postings-api
"""
import httpx

from providers import guard

from connectors.config import TOKEN_COMPANY_NAMES
from connectors.feeds import _epoch

BASE_URL = "https://api.lever.co/v0/postings/{token}"


def fetch_lever_jobs(company_token: str):
    url = BASE_URL.format(token=company_token)
    resp = guard.call("lever", lambda: httpx.get(url, params={"mode": "json"}, timeout=20))
    if resp.status_code != 200:
        return []
    data = resp.json()

    jobs = []
    for j in data:
        categories = j.get("categories", {})
        location = categories.get("location")

        jobs.append({
            "source": "lever",
            "board_token": company_token,  # COLLECT-D, see greenhouse.py
            "external_id": j.get("id", ""),
            "title": j.get("text", ""),
            "company": TOKEN_COMPANY_NAMES.get(company_token, company_token),
            "location": location,
            "remote": "remote" in (location or "").lower(),
            "salary": None,
            "description": j.get("descriptionPlain", j.get("description", "")),
            "apply_url": j.get("applyUrl") or j.get("hostedUrl", ""),
            "tags": categories.get("tags", []) if isinstance(categories.get("tags"), list) else [],
            "posted_at": _epoch(j["createdAt"] // 1000) if isinstance(j.get("createdAt"), int) else None,  # epoch ms
        })
    return jobs
