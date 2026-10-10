"""LinkedIn job sourcing via Apify (GAPS 3.1).

**Why this exists despite ADR-002/ADR-015 parking LinkedIn.** The posture is the one
already accepted for `outreach/sources_apify.py`: a paid vendor API call on Apify's own
infrastructure. **No cookie, no session, no user's LinkedIn account, and no
anti-detection layer** — none of that is in this design and none of it should be added.
What this project declined was driving a user's own session or defeating bot detection.
Buying structured data from a vendor is a different thing, and it is already how contact
discovery works.

**Why it was worth doing at all**, measured 2026-10-09 before any code was written:

  * **PhonePe appeared in the first 15 rows** — one of the 19 companies GAPS 3.1 records
    as having no board on greenhouse/lever/ashby *at all*. LinkedIn reaches the market
    this project has spent its whole life unable to reach.
  * **14 of 15 rows were genuinely India-located.** `location="India"` behaves correctly
    here, unlike Glassdoor, where the same string returns **Indianapolis** (see
    `config.JOBSPY_LOCATIONS`).
  * **56% carry a real employer ATS link** (14 EXTERNAL / 11 EASY_APPLY of 25). External
    hosts included careers.google.com, amazon.jobs, and `sustainiam.keka.com`,
    `cashflo-talent.freshteam.com`, `finkraft.zohorecruit.com` — Indian ATSs reachable no
    other way here.
  * **$0.0226 for 15 jobs, ~$0.0015 each** — roughly 5x cheaper per row than the profile
    lookups REACH-E already pays for.

Not swept for delistings: a keyword+location slice is not a complete listing, so absence
from a payload means "not in that search", not "gone" (ADR-017 §2).
"""
import logging
import os

import httpx

from connectors.normalize import coerce_posted_at

logger = logging.getLogger(__name__)

_ACTOR = "bebity~linkedin-jobs-scraper"
_ENDPOINT = f"https://api.apify.com/v2/acts/{_ACTOR}/run-sync-get-dataset-items"
# The actor drives a real browser on Apify's side, so it is slow by nature. Generous but
# bounded: a hung discovery run blocks every other source behind it.
_ACTOR_TIMEOUT = 240
_CLIENT_TIMEOUT = _ACTOR_TIMEOUT + 20


def _token() -> str | None:
    """Settings first, then the environment — same order and reason as
    `ApifyContactSource._resolve_token`: every credential here lives in `apps/api/.env`,
    and `extra="ignore"` silently drops an undeclared key."""
    try:
        from core.config import get_settings

        configured = get_settings().apify_token
    except Exception:
        configured = None
    return configured or os.environ.get("APIFY_TOKEN")


def _first(row: dict, *keys):
    for k in keys:
        v = row.get(k)
        if v:
            return v
    return None


def fetch_linkedin_jobs(title: str, location: str, rows: int = 50) -> list[dict]:
    """One search, one location. Returns normalized dicts for `upsert_jobs`.

    Never raises: discovery runs every source in sequence and one vendor outage must not
    cost the others.
    """
    token = _token()
    if not token:
        # Not configured is not an error — same shape as the Reed connector and the
        # embedding pipeline, which no-op without their keys.
        return []
    if not title or not location or rows <= 0:
        return []

    try:
        r = httpx.post(
            _ENDPOINT,
            params={"timeout": _ACTOR_TIMEOUT},
            headers={"Authorization": f"Bearer {token}"},
            json={
                "title": title,
                "location": location,
                "rows": rows,
                "proxy": {"useApifyProxy": True},
            },
            timeout=_CLIENT_TIMEOUT,
        )
    except Exception as exc:
        # TYPE only: a vendor error body can echo the token.
        logger.warning("linkedin jobs fetch failed for %r in %r: %s",
                       title, location, type(exc).__name__)
        return []

    # 201, not just 200: `run-sync-get-dataset-items` answers **201 Created** on success,
    # because it creates a run. The first version of this checked `!= 200` and discarded
    # a perfectly good payload — found live, one hour after writing the warning below
    # that caught it. The loud-failure design paid for itself immediately: the log said
    # "returned HTTP 201", which is diagnosable, where a silent `[]` would have looked
    # exactly like LinkedIn having no India PM roles.
    if r.status_code not in (200, 201):
        # An empty result must never be indistinguishable from a broken call. That
        # confusion has now cost this project five separate bugs: the Apify token,
        # JobSpy's 403s, the Gmail redirect URI, GitHub's anonymous email field, and this.
        logger.warning("linkedin jobs fetch for %r in %r returned HTTP %s",
                       title, location, r.status_code)
        return []

    try:
        payload = r.json()
    except ValueError:
        logger.warning("linkedin jobs returned unparseable JSON for %r", location)
        return []
    if not isinstance(payload, list):
        logger.warning("linkedin jobs returned %s, not a list, for %r",
                       type(payload).__name__, location)
        return []

    jobs: list[dict] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        apply_url = _first(row, "applyUrl", "jobUrl", "link")
        company = _first(row, "companyName", "company")
        job_title = _first(row, "title", "jobTitle")
        external_id = _first(row, "id", "jobId")
        # apply_url and company are NOT NULL on Job, and company is a third of
        # canonical_hash. A posting nobody can open is not a lead.
        if not (apply_url and company and job_title and external_id):
            continue

        # EASY_APPLY vs EXTERNAL recorded in `source`, the same way jobspy tags per site
        # — so no migration, and a job the extension cannot fill stays VISIBLE instead of
        # being silently dropped. Dropping Easy Apply would discard ~44% of the scarcest
        # supply this product has, and the user can still apply to those by hand.
        kind = str(row.get("applyType") or "unknown").strip().lower()
        jobs.append({
            "source": f"linkedin_{kind}",
            "external_id": str(external_id),
            "title": job_title,
            "company": company,
            "location": _first(row, "location", "formattedLocation"),
            "description": _first(row, "descriptionText", "description"),
            "apply_url": apply_url,
            "posted_at": coerce_posted_at(
                _first(row, "postedAt", "publishedAt", "postedTime", "datePosted")
            ),
        })
    return jobs
