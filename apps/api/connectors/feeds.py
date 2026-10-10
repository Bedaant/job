"""Tier-A public remote-job feeds (ADR-015 section 1): Remote OK, Himalayas,
Working Nomads, Jobicy, Arbeitnow, We Work Remotely.

All six are free, keyless, public endpoints. Every field name used below was
read off a live response on 2026-09-26 (fetched, keys printed) -- none guessed
from docs. Fetch and parse are split so the parsers are testable without
network; tests/test_feeds.py covers the parsers.

Most of these feeds return their whole board rather than accepting a search
term, so filtering is client-side via filter_by_keywords against
connectors.config. Attribution: Remote OK's and Jobicy's terms require a link
back to the source -- apply_url always points at the original posting.
"""
import email.utils
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import httpx

from providers import guard

USER_AGENT = "ApplyScout/0.1 (+https://applyscout.in)"
TIMEOUT = 25

# Pacing between pages of ONE feed -- same host, back to back. Separate from
# workers.jobs.HOST_PACING_SECONDS, which paces that module's per-token loops;
# these are different loops over different hosts and share nothing but the idea.
PAGE_PACING_SECONDS = 1.0
# Safety stop for any cursor loop: a feed that always claims `hasMore` must not
# spin a worker forever. Jobicy exhausted in 7 pages (measured 2026-10-03), so
# 30 is ~4x headroom.
MAX_PAGES = 30


def _get(url: str, params: dict | None = None) -> httpx.Response:
    def once():
        resp = httpx.get(url, params=params, timeout=TIMEOUT,
                         headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        resp.raise_for_status()
        return resp
    # Breaker per feed host: one dead feed must not open the circuit for the others.
    return guard.call(f"feed:{httpx.URL(url).host}", once)


def _epoch(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def _iso(value) -> datetime | None:
    if not value:
        return None
    for parse in (
        lambda v: datetime.fromisoformat(str(v).replace("Z", "+00:00")),
        lambda v: datetime.strptime(str(v), "%Y-%m-%d %H:%M:%S"),
    ):
        try:
            parsed = parse(value)
            return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            continue
    return None


def _rfc2822(value) -> datetime | None:
    if not value:
        return None
    try:
        return email.utils.parsedate_to_datetime(value).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _salary(minimum, maximum) -> str | None:
    """Feeds disagree on whether "unknown" is 0, None or an absent key. Render
    only what is actually present -- never a misleading "0-160000".
    """
    lo, hi = minimum or None, maximum or None
    if lo and hi:
        return f"{lo}-{hi}"
    return str(lo or hi) if (lo or hi) else None


def filter_by_keywords(jobs: list[dict], keywords: list[str]) -> list[dict]:
    """No keywords configured means "keep everything" -- an empty config must
    not silently discard a whole feed.
    """
    if not keywords:
        return jobs
    lowered = [k.lower() for k in keywords]
    return [j for j in jobs if any(k in j["title"].lower() for k in lowered)]


# --- Remote OK -- https://remoteok.com/api (row 0 is a legal/ToS notice) ------

def parse_remoteok(raw: list[dict]) -> list[dict]:
    return [{
        "source": "remoteok",
        "external_id": str(j.get("id") or j.get("slug")),
        "title": j.get("position", ""),
        "company": j.get("company", ""),
        "location": j.get("location") or None,
        "remote": True,
        "salary": _salary(j.get("salary_min"), j.get("salary_max")),
        "description": j.get("description", ""),
        "apply_url": j.get("apply_url") or j.get("url", ""),
        "tags": j.get("tags") or [],
        "posted_at": _iso(j.get("date")) or _epoch(j.get("epoch")),
    } for j in raw if j.get("position")]


def fetch_remoteok_jobs() -> list[dict]:
    return parse_remoteok(_get("https://remoteok.com/api").json())


# --- Himalayas -- https://himalayas.app/jobs/api -----------------------------

def parse_himalayas(raw: dict) -> list[dict]:
    return [{
        "source": "himalayas",
        "external_id": str(j.get("guid") or j.get("applicationLink")),
        "title": j.get("title", ""),
        "company": j.get("companyName", ""),
        "location": ", ".join(j.get("locationRestrictions") or []) or None,
        "remote": True,
        "salary": _salary(j.get("minSalary"), j.get("maxSalary")),
        "description": j.get("description", ""),
        "apply_url": j.get("applicationLink") or j.get("guid", ""),
        "tags": (j.get("categories") or []) + ([j["employmentType"]] if j.get("employmentType") else []),
        "posted_at": _epoch(j.get("pubDate")) or _iso(j.get("pubDate")),
    } for j in raw.get("jobs", []) if j.get("title")]


def fetch_himalayas_jobs(limit: int = 100) -> list[dict]:
    return parse_himalayas(_get("https://himalayas.app/jobs/api", {"limit": limit}).json())


# --- Working Nomads -- /api/exposed_jobs/ (no id field; it is in the URL) -----

def parse_workingnomads(raw: list[dict]) -> list[dict]:
    jobs = []
    for j in raw:
        url = j.get("url", "")
        if not j.get("title") or not url:
            continue
        tags = j.get("tags")
        jobs.append({
            "source": "workingnomads",
            "external_id": url.rstrip("/").rsplit("/", 1)[-1],
            "title": j.get("title", ""),
            "company": j.get("company_name") or "",
            "location": j.get("location") or None,
            "remote": True,
            "salary": None,
            "description": j.get("description", ""),
            "apply_url": url,
            "tags": tags.split(",") if isinstance(tags, str) else (tags or []),
            "posted_at": _iso(j.get("pub_date")),
        })
    return jobs


def fetch_workingnomads_jobs() -> list[dict]:
    return parse_workingnomads(_get("https://www.workingnomads.com/api/exposed_jobs/").json())


# --- Jobicy -- https://jobicy.com/api/v2/remote-jobs -------------------------

def parse_jobicy(raw: dict) -> list[dict]:
    return [{
        "source": "jobicy",
        "external_id": str(j.get("id")),
        "title": j.get("jobTitle", ""),
        "company": j.get("companyName", ""),
        "location": j.get("jobGeo") or None,
        "remote": True,
        "salary": _salary(j.get("salaryMin"), j.get("salaryMax")),
        "description": j.get("jobDescription") or j.get("jobExcerpt", ""),
        "apply_url": j.get("url", ""),
        "tags": (j.get("jobIndustry") or []) + (j.get("jobType") or []),
        "posted_at": _iso(j.get("pubDate")),
    } for j in raw.get("jobs", []) if j.get("jobTitle")]


def fetch_jobicy_jobs(count: int = 100) -> list[dict]:
    """Paginated to exhaustion through the cursor Jobicy's own envelope returns
    (`nextCursor` + `hasMore`, both read off a live response 2026-10-03). This
    is what makes jobicy a COMPLETE listing, and therefore the only one of the
    six keyless feeds that may be swept for delistings (ADR-017 §2 — absence
    from a truncated window is age, not a delisting). Measured: 7 requests,
    633 jobs, `count` honoured at 100.

    A mid-pagination failure raises, discarding the pages already collected,
    and that is deliberate: `fetch_enabled_feeds` turns it into a per-source
    error and the sweep gets nothing. Returning a partial listing would make
    every job on the pages that never arrived look absent from the board.

    `hasMore` alone is not trusted — without a cursor there is nothing to
    advance, and re-requesting page 1 would loop until MAX_PAGES.
    """
    jobs: list[dict] = []
    cursor = None
    for page in range(MAX_PAGES):
        if page:
            time.sleep(PAGE_PACING_SECONDS)
        params = {"count": count}
        if cursor:
            params["cursor"] = cursor
        raw = _get("https://jobicy.com/api/v2/remote-jobs", params).json()
        jobs.extend(parse_jobicy(raw))
        cursor = raw.get("nextCursor")
        if not raw.get("hasMore") or not cursor:
            break
    return jobs


# --- Arbeitnow -- /api/job-board-api (mixed remote/on-site, EU-heavy) --------

def parse_arbeitnow(raw: dict) -> list[dict]:
    return [{
        "source": "arbeitnow",
        "external_id": j.get("slug", ""),
        "title": j.get("title", ""),
        "company": j.get("company_name", ""),
        "location": j.get("location") or None,
        "remote": bool(j.get("remote")),
        "salary": None,
        "description": j.get("description", ""),
        "apply_url": j.get("url", ""),
        "tags": (j.get("tags") or []) + (j.get("job_types") or []),
        "posted_at": _epoch(j.get("created_at")),
    } for j in raw.get("data", []) if j.get("title")]


def fetch_arbeitnow_jobs() -> list[dict]:
    return parse_arbeitnow(_get("https://www.arbeitnow.com/api/job-board-api").json())


# --- We Work Remotely -- RSS (no JSON API). stdlib ElementTree, no new dep ---

def parse_wwr(xml: str) -> list[dict]:
    jobs = []
    for item in ET.fromstring(xml).findall("./channel/item"):
        def text(tag: str) -> str:
            node = item.find(tag)
            return (node.text or "").strip() if node is not None else ""

        raw_title = text("title")
        if not raw_title:
            continue
        # WWR encodes the employer in the title as "Company: Role".
        company, _, title = raw_title.partition(": ")
        if not title:
            company, title = "", raw_title
        link = text("link") or text("guid")
        jobs.append({
            "source": "weworkremotely",
            "external_id": link.rstrip("/").rsplit("/", 1)[-1],
            "title": title,
            "company": company,
            "location": text("region") or None,
            "remote": True,
            "salary": None,
            "description": text("description"),
            "apply_url": link,
            "tags": [t for t in (text("category"), text("type")) if t],
            "posted_at": _rfc2822(text("pubDate")),
        })
    return jobs


def fetch_wwr_jobs() -> list[dict]:
    return parse_wwr(_get("https://weworkremotely.com/remote-jobs.rss").text)


# Every keyless feed, in one place. discover_jobs_task iterates this, so adding
# a source is one line here rather than a new branch in the worker.
FEED_FETCHERS = {
    "remoteok": fetch_remoteok_jobs,
    "himalayas": fetch_himalayas_jobs,
    "workingnomads": fetch_workingnomads_jobs,
    "jobicy": fetch_jobicy_jobs,
    "arbeitnow": fetch_arbeitnow_jobs,
    "weworkremotely": fetch_wwr_jobs,
}


def fetch_enabled_feeds(enabled: list[str], keywords: list[str]) -> tuple[list[dict], dict]:
    """Fetch every enabled feed. Returns (jobs, report) where report maps each
    source to its kept-job count, or to an error string if that source failed.

    One broken board must not abort a six-source run, and must not vanish
    silently either (ADR-015: "per-source adapters that fail visibly") — the
    report is what the caller logs to connector_runs.
    """
    all_jobs: list[dict] = []
    report: dict[str, int | str] = {}

    for name in enabled:
        fetcher = FEED_FETCHERS.get(name)
        if fetcher is None:
            report[name] = "unknown feed name (check ENABLED_FEEDS)"
            continue
        try:
            kept = filter_by_keywords(fetcher(), keywords)
        except Exception as exc:  # network, JSON shape drift, XML drift
            report[name] = f"{type(exc).__name__}: {exc}"
            continue
        all_jobs.extend(kept)
        report[name] = len(kept)

    return all_jobs, report
