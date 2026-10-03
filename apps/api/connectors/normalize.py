"""Dedupe normalization (SPEC.md §3.1). Fixes CODE-REVIEW.md H3: dedupe was
(source, external_id) only, so the same role from two sources landed twice.
canonical_hash collapses them across sources.
"""
import hashlib
import re
from datetime import datetime, timezone

_COMPANY_SUFFIXES = re.compile(r"\b(inc|llc|ltd|gmbh|pvt|private|limited)\b")
_SENIORITY_SUFFIXES = re.compile(r"\b(sr|jr|i{1,3}|iv|v)\b")

# Sane calendar bounds for an epoch-derived posting date. No real job was
# posted before Unix epoch 0, and none is posted ~500 years from now --
# a numeric string that decodes outside this window is not a timestamp
# that was ever meant as one, it's a misread (see coerce_posted_at).
_EPOCH_DATE_MIN = datetime(1970, 1, 1)
_EPOCH_DATE_MAX = datetime(2100, 1, 1)


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

        # Try it as a date/datetime string FIRST. A compact numeric string
        # like "20260909" is a valid ISO 8601 basic-format date and must be
        # read as one. A magnitude floor on the numeric interpretation (the
        # previous fix) only moves the boundary where a compact form gets
        # misread as an epoch value instead of closing it -- a longer
        # compact form like "20260909120000" (14 digits) clears any such
        # floor and still gets misread as epoch milliseconds, landing on a
        # wrong-but-plausible-looking date (year 2612). Trying the date
        # parse first means a real date string is never handed to the
        # numeric path at all.
        try:
            parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
        except ValueError:
            pass

        # Not a recognizable date string -- consider it a numeric epoch
        # value, but only accept the result if it lands within a sane
        # calendar window. This is what actually closes the bug class: any
        # numeric string whose epoch-seconds-or-ms interpretation decodes to
        # an implausible date (year 2612, say) is rejected as None rather
        # than returned as a wrong date that merely looks plausible.
        try:
            numeric = float(s)
        except ValueError:
            return None
        candidate = coerce_posted_at(numeric)
        if candidate is not None and _EPOCH_DATE_MIN <= candidate < _EPOCH_DATE_MAX:
            return candidate
        return None

    return None


def canonical_hash(company_name: str, title: str, location: str | None) -> str:
    c = _COMPANY_SUFFIXES.sub("", company_name.lower())
    c = re.sub(r"[^a-z0-9]", "", c)

    t = re.sub(r"[^a-z0-9 ]", "", title.lower())
    t = _SENIORITY_SUFFIXES.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()

    loc = normalize_location(location)

    return hashlib.sha256(f"{c}|{t}|{loc}".encode()).hexdigest()
