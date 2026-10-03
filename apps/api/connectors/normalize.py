"""Dedupe normalization (SPEC.md §3.1). Fixes CODE-REVIEW.md H3: dedupe was
(source, external_id) only, so the same role from two sources landed twice.
canonical_hash collapses them across sources.
"""
import hashlib
import re
from datetime import datetime, timezone

_COMPANY_SUFFIXES = re.compile(r"\b(inc|llc|ltd|gmbh|pvt|private|limited)\b")
_SENIORITY_SUFFIXES = re.compile(r"\b(sr|jr|i{1,3}|iv|v)\b")


def normalize_location(location: str | None) -> str:
    if not location:
        return ""
    loc = location.lower().strip()
    if "remote" in loc:
        return "remote"
    loc = re.sub(r"\s+", " ", loc)
    loc = re.sub(r",\s*", ",", loc)
    return loc.strip(",")


def coerce_posted_at(value) -> datetime | None:
    """Coerce whatever a connector gives for a posting date into a naive UTC
    datetime, or None. Never raises — an unparseable value returns None.

    Accepts: ISO 8601 string (with 'Z', an offset, or naive), the ISO 8601
    compact basic date form ("20260909"), None, and "". Anything else is None.

    Strings only, on purpose. Every wired caller passes a str or None
    (greenhouse.py `first_published`, ashby.py `publishedAt`,
    jobspy_connector.py `date_posted`, which comes back through JSON). The
    number-epoch and datetime-passthrough branches this used to carry had no
    caller in the codebase — lever.py and feeds.py each decode their own
    epochs locally — so they were dead flexibility (YAGNI). Add one back with
    its caller if a connector ever needs it.

    Deliberately NOT accepted: an epoch value given as a string (e.g.
    "1790265606"). No wired connector sends one — Greenhouse/Ashby send ISO
    strings, JobSpy sends a date string, Lever sends epoch milliseconds as a
    number (connectors/lever.py). Three rounds of trying to tell a genuine
    numeric-epoch string apart from an invalid or compact date string (by
    input magnitude, then by decoded-date plausibility window) each produced
    a different wrong-but-plausible datetime for some input instead of None.
    Dropping string-epoch support entirely closes that class by construction:
    a str is parsed as a date or it's None, full stop.
    """
    if value is None or value == "":
        return None

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed

    return None


def canonical_hash(company_name: str, title: str, location: str | None) -> str:
    c = _COMPANY_SUFFIXES.sub("", company_name.lower())
    c = re.sub(r"[^a-z0-9]", "", c)

    t = re.sub(r"[^a-z0-9 ]", "", title.lower())
    t = _SENIORITY_SUFFIXES.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()

    loc = normalize_location(location)

    return hashlib.sha256(f"{c}|{t}|{loc}".encode()).hexdigest()
