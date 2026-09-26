"""ATS board-token discovery (SPEC.md §3.4, F5). Given a company domain,
detect which ATS they use and extract the board token. SSRF-guarded per
ARCHITECTURE.md §6 — this is the one place we fetch arbitrary user/config-
supplied domains, so every request is checked before it goes out.
"""
import ipaddress
import json
import re
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from sqlalchemy.orm import Session

import models
from tailoring.engine import call_llm

CANDIDATE_PATHS = ["/careers", "/jobs", "/join-us", "/work-with-us"]
ALLOWED_SCHEMES = {"http", "https"}
REQUEST_TIMEOUT = 10


@dataclass(frozen=True)
class AtsPattern:
    ats_type: str
    regex: re.Pattern


# The single ATS pattern table. `detect_ats` (company domain -> board token) and
# `apply_target.resolve_apply_target` (aggregator link -> real apply form) both
# read this list; a second competing table is how the two drift apart.
#
# Host shapes adopted from kalil0321/ats-scrapers (MIT, Copyright (c) 2026 Kalil
# Bouzigues) — specifically `src/ats_scrapers/resolve.py`'s `_PATH_HOSTS`,
# `_SUBDOMAIN_SUFFIXES` and `_WORKDAY_HOST_RE`/`_ICIMS_HOST_RE`. See
# DEPENDENCIES.md §3. The regexes themselves are written for this table's
# one-capture-group contract, not copied verbatim.


# Vendor-owned subdomains that are never a tenant slug. Found the hard way: a
# live Arbeitnow page mentioning `app.recruitee.com` (Recruitee's own console)
# was reported as company "app" on Recruitee. ats-scrapers guards the same class
# of bug with per-ATS reserved-segment sets; one shared list is enough here.
_RESERVED_SUBDOMAINS = (
    "www|app|apps|api|jobs|job|careers|career|admin|secure|static|cdn|assets"
    "|help|support|blog|docs|my|hire|hiring|recruiting|resources|status|mail"
)


def _subdomain_tenant(ats_type: str, suffix: str) -> "AtsPattern":
    """`{slug}.{suffix}` tenants. The lookbehind stops a rejected reserved label
    from being salvaged by restarting mid-word (`app.` -> `pp.`), which would
    reintroduce the bug it is there to prevent.
    """
    return AtsPattern(ats_type, re.compile(
        rf"(?<![a-zA-Z0-9_.-])(?!(?:{_RESERVED_SUBDOMAINS})\.)([a-zA-Z0-9_-]+)\.{suffix}"
    ))


ATS_PATTERNS = [
    AtsPattern("greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/([a-zA-Z0-9_-]+)")),
    AtsPattern("lever", re.compile(r"jobs(?:\.eu)?\.lever\.co/([a-zA-Z0-9_-]+)")),
    AtsPattern("ashby", re.compile(r"jobs\.ashbyhq\.com/([a-zA-Z0-9_-]+)")),
    AtsPattern("workable", re.compile(r"apply\.workable\.com/([a-zA-Z0-9_-]+)")),
    AtsPattern("smartrecruiters", re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([a-zA-Z0-9_-]+)")),
    # Workday's tenant lives in the hostname, not the path, and the wdN instance
    # number is load-bearing for any later API call.
    _subdomain_tenant("workday", r"wd\d+\.myworkdayjobs\.com"),
    AtsPattern("jobvite", re.compile(r"jobs\.jobvite\.com/(?:careers/)?([a-zA-Z0-9_-]+)")),
    AtsPattern("icims", re.compile(r"(?:careers-)?([a-zA-Z0-9-]+)\.icims\.com")),
    _subdomain_tenant("recruitee", r"recruitee\.com"),
    _subdomain_tenant("teamtailor", r"teamtailor\.com"),
    _subdomain_tenant("breezy", r"breezy\.hr"),
    _subdomain_tenant("bamboohr", r"bamboohr\.com"),
    _subdomain_tenant("personio", r"jobs\.personio\.(?:com|de)"),
    _subdomain_tenant("pinpoint", r"pinpointhq\.com"),
    _subdomain_tenant("jazzhr", r"applytojob\.com"),
    AtsPattern("gem", re.compile(r"jobs\.gem\.com/([a-zA-Z0-9_-]+)")),
    AtsPattern("rippling", re.compile(r"ats\.rippling\.com/([a-zA-Z0-9_-]+)")),
]


def is_safe_url(url: str) -> bool:
    """Deny-private-IP, allowlist-scheme fetcher guard. A misconfigured or
    malicious domain must not be able to make our server hit localhost,
    a private network, or a cloud metadata endpoint (169.254.169.254).
    """
    parsed = urlparse(url)
    if parsed.scheme not in ALLOWED_SCHEMES or not parsed.hostname:
        return False

    try:
        ip = ipaddress.ip_address(socket.gethostbyname(parsed.hostname))
    except (OSError, ValueError):
        return False

    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)


def detect_ats(domain: str) -> tuple[str, str] | None:
    for path in CANDIDATE_PATHS:
        url = f"https://{domain}{path}"
        if not is_safe_url(url):
            continue

        try:
            resp = httpx.get(url, timeout=REQUEST_TIMEOUT, follow_redirects=True)
        except httpx.HTTPError:
            continue

        haystack = f"{resp.url}\n{resp.text[:200_000]}"
        for pattern in ATS_PATTERNS:
            if m := pattern.regex.search(haystack):
                return pattern.ats_type, m.group(1)

    return None


CLASSIFY_SYSTEM_PROMPT = (
    "You are an ATS (applicant tracking system) detector. You will be given a "
    "company careers page's final URL and truncated HTML. The page did not match "
    "any of our known ATS URL regex patterns (Greenhouse, Lever, Ashby, Workable, "
    "SmartRecruiters). Look for evidence of which ATS the page is actually using — "
    "JS bundle URLs, iframe src, API calls, or vendor branding (Workday, iCIMS, "
    "Taleo, BambooHR, JazzHR, or any other). If you can identify one, propose a "
    "Python-regex pattern with exactly one capture group that would extract the "
    "company's board token/slug from a job-listing URL on that ATS, grounded in "
    "concrete evidence from the page — never invent a pattern with no supporting "
    "evidence. Respond ONLY with valid JSON: "
    '{"ats_type": "string or null", "proposed_regex": "string or null", '
    '"confidence": "high|medium|low", "evidence": "string, what in the page led to this"}'
)


def classify_unknown_ats(domain: str) -> dict | None:
    """SPEC.md §3.4 addendum: when detect_ats() finds no known pattern, make
    one bounded Claude/nvidia_smoke call (ADR-011: single pass, not F11's
    multi-pass budget) proposing what ATS the page might be using. Never
    auto-updates ATS_PATTERNS — the owner reviews and manually promotes a
    proposal (discover_ats_for_domain logs it to connector_runs for that).
    Reuses the same is_safe_url() SSRF guard as detect_ats — no new fetch
    surface.
    """
    for path in CANDIDATE_PATHS:
        url = f"https://{domain}{path}"
        if not is_safe_url(url):
            continue

        try:
            resp = httpx.get(url, timeout=REQUEST_TIMEOUT, follow_redirects=True)
        except httpx.HTTPError:
            continue

        if resp.status_code == 200 and resp.text.strip():
            user_prompt = f"DOMAIN: {domain}\nFINAL URL: {resp.url}\nHTML (truncated):\n{resp.text[:20_000]}"
            raw = call_llm(CLASSIFY_SYSTEM_PROMPT, user_prompt)
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(cleaned)

    return None


def discover_ats_for_domain(db: Session, domain: str) -> tuple[str, str] | None:
    """The real F5 entrypoint: try the known-pattern detector first; only pay
    for a Claude call when that fails. Every classification attempt (whether
    it found a candidate or not) is logged to connector_runs — the review
    surface the owner promotes proposals from, decided as "no new table/admin
    UI" (plan item 3).
    """
    known = detect_ats(domain)
    if known is not None:
        return known

    proposal = classify_unknown_ats(domain)
    db.add(models.ConnectorRun(
        source="ats_discovery_classify",
        token=domain,
        fetched=1,
        inserted=0,
        failed=0 if proposal else 1,
        notes=proposal,
    ))
    db.commit()
    return None
