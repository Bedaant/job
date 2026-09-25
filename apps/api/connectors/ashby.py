"""
Ashby public job posting API — no auth required, per-org token.
Docs: https://developers.ashbyhq.com/reference/jobpostingapi
"""
import httpx

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board/{token}"


def fetch_ashby_jobs(org_token: str):
    url = BASE_URL.format(token=org_token)
    resp = httpx.get(url, timeout=20)
    if resp.status_code != 200:
        return []
    data = resp.json()

    jobs = []
    for j in data.get("jobs", []):
        jobs.append({
            "source": "ashby",
            "external_id": j.get("id", ""),
            "title": j.get("title", ""),
            "company": org_token,
            "location": j.get("location"),
            "remote": bool(j.get("isRemote", False)),
            "salary": None,
            "description": j.get("descriptionPlain", ""),
            "apply_url": j.get("applyUrl") or j.get("jobUrl", ""),
            "tags": j.get("department") and [j["department"]] or [],
            "posted_at": j.get("publishedAt"),
        })
    return jobs
