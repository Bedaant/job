"""Aggregator `apply_url` -> the company's real ATS apply form (ADR-015 Phase 2).

Feed jobs carry an aggregator link — `remoteok.com/l/123`, a Working Nomads
`/job/go/` bounce, a Himalayas tracking URL — not the application form. The
extension driver opens whatever it lands on and tries to fill it, so resolving
the link first is the difference between a form we can fill deterministically
from `deterministic_fields` and a guess.

Two deliberate properties:

* **Patterns live in `discovery.ATS_PATTERNS`, not here.** One table, so
  `detect_ats` (company domain -> board token) gains every host shape this
  resolver learns and the two cannot drift.
* **`is_safe_url` runs on EVERY hop.** Checking only the submitted URL is not a
  guard: a public aggregator that 302s to `169.254.169.254` or `localhost`
  walks straight through it. That is the attack, and it is what
  `httpx`'s own `follow_redirects=True` would do for us, which is why the
  redirect chain is walked by hand here.

Never raises. A dead link, a redirect loop, or an unreachable Redis all return
`resolved: False` and the original URL — the caller proceeds exactly as it did
before this module existed.
"""
import json
from urllib.parse import urljoin, urlparse

import httpx

from connectors.discovery import ATS_PATTERNS, is_safe_url
from connectors.feeds import USER_AGENT

MAX_HOPS = 5
REQUEST_TIMEOUT = 10
CACHE_PREFIX = "apply_target:v1:"
CACHE_TTL = 7 * 24 * 3600  # an ATS URL for a live posting is stable for weeks
_REDIRECT_CODES = {301, 302, 303, 307, 308}


def _detect(haystack: str) -> tuple[str | None, str | None]:
    for pattern in ATS_PATTERNS:
        if m := pattern.regex.search(haystack):
            return pattern.ats_type, m.group(1)
    return None, None


def _cache():
    """Imported lazily: `workers.jobs` imports half of `connectors/`, so a
    module-level import here is a cycle. Returns None when Redis cannot be
    reached — resolution is then just slower, never broken.
    """
    try:
        from workers.jobs import get_redis_connection
        return get_redis_connection()
    except Exception:
        return None


def _unresolved(url: str) -> dict:
    return {"final_url": url, "ats_type": None, "board_token": None, "resolved": False}


def resolve_apply_target(url: str) -> dict:
    """Follow `url` to the real application form and say which ATS serves it.

    Returns `{"final_url", "ats_type", "board_token", "resolved"}`. `resolved`
    means "we reached a real destination", not "we recognised the ATS" — landing
    on the company's own page is still better than handing the driver a
    redirector, so `ats_type` may be None on a resolved result.
    """
    if not url:
        return _unresolved(url)

    # A URL that already names its ATS needs no round trip at all. This is the
    # common case for the greenhouse/lever/ashby connectors' own rows.
    ats_type, token = _detect(url)
    if ats_type:
        return {"final_url": url, "ats_type": ats_type, "board_token": token, "resolved": True}

    redis = _cache()
    key = f"{CACHE_PREFIX}{url}"
    if redis is not None:
        try:
            if (cached := redis.get(key)) is not None:
                return json.loads(cached)
        except Exception:
            redis = None  # down mid-flight; don't try to write either

    result = _follow(url)

    if redis is not None:
        try:
            redis.setex(key, CACHE_TTL, json.dumps(result))
        except Exception:
            pass
    return result


def _follow(url: str) -> dict:
    current = url
    for _ in range(MAX_HOPS):
        # Checked before every single request, including each redirect target.
        if not is_safe_url(current):
            return _unresolved(url)

        try:
            resp = httpx.get(
                current,
                timeout=REQUEST_TIMEOUT,
                follow_redirects=False,
                headers={"User-Agent": USER_AGENT},
            )
        except httpx.HTTPError:
            return _unresolved(url)

        location = resp.headers.get("location")
        if resp.status_code in _REDIRECT_CODES and location:
            nxt = urljoin(current, location)
            if urlparse(nxt).scheme not in {"http", "https"}:
                return _unresolved(url)
            current = nxt
            continue

        ats_type, token = _detect(current)
        if ats_type is None:
            ats_type, token = _detect(resp.text[:200_000])
        return {"final_url": current, "ats_type": ats_type, "board_token": token, "resolved": True}

    # Hop cap hit — a redirect loop or a chain long enough to be one. Hand back
    # the original URL rather than a random point inside the loop.
    return _unresolved(url)
