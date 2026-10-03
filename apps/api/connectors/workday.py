"""Workday CXS public job endpoint — no auth, one tenant+site per employer.

COLLECT-C (ADR-018). Every constant and field name below was measured off live
responses on 2026-10-03/04; the full measurement is in
`docs/harness-reports/collect-c-platforms.md`.

Two steps per board, and the split is the whole design:

1. **LIST** `POST /wday/cxs/{tenant}/{site}/jobs` with
   `{"appliedFacets":{}, "limit":20, "offset":N, "searchText":""}`.
   `limit` is capped at 20 — 50 and above return HTTP 400 — so a 527-job board
   is 27 requests. `searchText` cannot carry the keyword filter: it filters a
   single word ("engineer" cut adobe 527→343) but returns everything ranked for
   a phrase ("product manager" → all 527), so filtering stays client-side like
   greenhouse/lever/ashby.
   The list payload's `locationsText` is frequently a COUNT, not a place
   ("5 Locations", "3 Locations"). It is never stored: it would poison
   `canonical_hash` and silently defeat the India location filter.

2. **DETAIL** `GET /wday/cxs/{tenant}/{site}{externalPath}`, only for titles that
   survive the keyword filter — a handful per board, not all 527. It carries the
   real `location`, `additionalLocations`, `country`, and `startDate`.

`startDate` is the posting date. Checked against six jobs with six different
`postedOn` values: "Posted Yesterday" → 2026-10-02, "Posted 3 Days Ago" →
2026-09-30, … "Posted 12 Days Ago" → 2026-09-21 — an exact, constant one-day
offset throughout. A role start date would not track `postedOn` at all, let
alone with a fixed offset; the offset is a timezone artifact of Workday's prose.
Used as-is. `postedOn` itself is never parsed: "Posted 30+ Days Ago" is
unbounded, and Phase 1 established that a wrong-but-plausible date is worse
than NULL (see `normalize.coerce_posted_at`).
"""
import time

import httpx

from connectors.config import FEED_KEYWORDS as KEYWORDS
from connectors.config import TOKEN_COMPANY_NAMES, WORKDAY_BOARDS
from connectors.normalize import coerce_posted_at

USER_AGENT = "ApplyScout/0.1 (+https://applyscout.in)"
TIMEOUT = 30
# Measured: the endpoint rejects limit > 20 with HTTP 400.
PAGE = 20
# Safety stop, not a throttle. Boards measured 2026-10-04: shell 132, paypal 291,
# adobe 526, cisco 1341, target 2000, micron 3080 — so 100 pages (2000 jobs) is
# too tight to be a safety net, it would reject real boards. 150 leaves cisco
# (68 pages) room to grow. Hitting it RAISES rather than truncating; see
# _list_board for why a short listing is unusable.
MAX_PAGES = 150
# Between requests to one board — same host, back to back. Separate from
# feeds.PAGE_PACING_SECONDS and workers.jobs.HOST_PACING_SECONDS; different
# loops, different hosts, shared only in spirit.
#
# 0.5s rather than 1s because this is the most request-hungry source wired: a
# board costs ceil(jobs/20) list requests plus one detail fetch per keyword
# match, and adobe measured 67 requests. At 1s the two configured boards would
# add ~2.6 min of sleeping to every hourly discovery run. No 429 and no
# throttling was seen across ~600 requests at 0.35s during the COLLECT-C
# measurement, so 0.5s keeps real headroom. Lower it no further without
# re-measuring.
PAGE_PACING_SECONDS = 0.5


def _post(base: str, offset: int) -> dict:
    resp = httpx.post(
        f"{base}/jobs",
        json={"appliedFacets": {}, "limit": PAGE, "offset": offset, "searchText": ""},
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


def _get(base: str, external_path: str) -> dict:
    resp = httpx.get(f"{base}{external_path}", headers={"User-Agent": USER_AGENT},
                     timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def _matches(title: str | None) -> bool:
    t = (title or "").lower()
    return not KEYWORDS or any(k.lower() in t for k in KEYWORDS)


def _list_board(base: str) -> list[dict]:
    """Every posting on the board, paginated to exhaustion.

    Exhaustion is what makes absence from this payload real delisting signal
    (ADR-017 §2), so a truncated read is unusable: every job on the pages that
    were never fetched would look absent and be tombstoned while still live.
    Hitting MAX_PAGES therefore raises instead of returning what it has.
    """
    rows: list[dict] = []
    total = 0
    for page in range(MAX_PAGES):
        if page:
            time.sleep(PAGE_PACING_SECONDS)
        payload = _post(base, page * PAGE)
        batch = payload.get("jobPostings") or []
        if page == 0:
            # ONLY the first page reports the board size. Measured on adobe:
            # offset 0 -> total 526, offset 20 -> total 0 WITH 20 rows. Trusting
            # the per-page value made "len(rows) >= total" true at 40 >= 0, so
            # the board returned 40 of 526 rows — and a short listing still goes
            # to the delisting sweep, which would have tombstoned 486 live jobs.
            total = payload.get("total") or 0
        rows.extend(batch)
        if total and len(rows) >= total:
            return rows
        if not batch:
            if total and len(rows) < total:
                # Empty before the end is indistinguishable from a failed fetch
                # (ADR-017 §3's empty-fetch trap), so it is never "end of board".
                raise RuntimeError(
                    f"{base}: listing incomplete — {len(rows)} of {total} rows, then an "
                    "empty page; refusing to return a short listing (it would tombstone "
                    "live jobs)"
                )
            return rows  # genuinely empty board, or no total reported at all
    raise RuntimeError(
        f"{base}: hit the {MAX_PAGES}-page cap with more to fetch; refusing to "
        "return a truncated listing (it would tombstone live jobs)"
    )


def fetch_workday_jobs(tenant: str) -> list[dict]:
    """Normalized job dicts for one Workday employer. `tenant` is the key in
    `config.WORKDAY_BOARDS`, whose value is "wd<N>/<site>".

    Raises on any HTTP failure, including a single detail fetch. That is
    deliberate: a job missing from the returned list is indistinguishable from a
    job that left the board, so a partial payload would tombstone live roles.
    `workers.jobs._isolate` turns the raise into a `connector_runs` error and the
    sweep gets nothing — the same rule jobicy's pagination follows.
    """
    board = WORKDAY_BOARDS.get(tenant)
    if not board:
        return []
    wd, _, site = board.partition("/")
    base = f"https://{tenant}.{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}"
    company = TOKEN_COMPANY_NAMES.get(tenant, tenant)

    jobs = []
    for listed in _list_board(base):
        if not _matches(listed.get("title")):
            continue
        time.sleep(PAGE_PACING_SECONDS)
        info = (_get(base, listed["externalPath"]) or {}).get("jobPostingInfo") or {}
        locations = [info.get("location") or ""] + list(info.get("additionalLocations") or [])
        location = "; ".join(l for l in locations if l) or None
        req_id = info.get("jobReqId") or (listed.get("bulletFields") or [None])[0]
        jobs.append({
            "source": "workday",
            # Req ids are unique per tenant, not per source, and
            # uq_job_source_external_id spans the whole source.
            "external_id": f"{tenant}:{req_id}",
            "title": info.get("title") or listed.get("title") or "",
            "company": company,
            "location": location,
            "remote": "remote" in (location or "").lower(),
            "salary": None,
            "description": info.get("jobDescription") or "",
            "apply_url": info.get("externalUrl") or f"{base}{listed['externalPath']}",
            "tags": [t for t in (info.get("timeType"),) if t],
            "posted_at": coerce_posted_at(info.get("startDate")),
        })
    return jobs
