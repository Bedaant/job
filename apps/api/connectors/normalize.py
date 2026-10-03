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

    Accepts: ISO 8601 string (with 'Z', an offset, or naive), epoch seconds,
    epoch milliseconds (as int/float or a numeric string), an existing
    datetime (naive passes through, aware is converted to UTC and stripped),
    None, and "".
    """
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = value / 1000 if abs(value) > 1e12 else value
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc).replace(tzinfo=None)
        except (OverflowError, OSError, ValueError):
            return None

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return coerce_posted_at(float(s))
        except ValueError:
            pass
        try:
            parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    return None


def canonical_hash(company_name: str, title: str, location: str | None) -> str:
    c = _COMPANY_SUFFIXES.sub("", company_name.lower())
    c = re.sub(r"[^a-z0-9]", "", c)

    t = re.sub(r"[^a-z0-9 ]", "", title.lower())
    t = _SENIORITY_SUFFIXES.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()

    loc = normalize_location(location)

    return hashlib.sha256(f"{c}|{t}|{loc}".encode()).hexdigest()
