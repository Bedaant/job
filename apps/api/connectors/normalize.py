"""Dedupe normalization (SPEC.md §3.1). Fixes CODE-REVIEW.md H3: dedupe was
(source, external_id) only, so the same role from two sources landed twice.
canonical_hash collapses them across sources.
"""
import hashlib
import re

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


def canonical_hash(company_name: str, title: str, location: str | None) -> str:
    c = _COMPANY_SUFFIXES.sub("", company_name.lower())
    c = re.sub(r"[^a-z0-9]", "", c)

    t = re.sub(r"[^a-z0-9 ]", "", title.lower())
    t = _SENIORITY_SUFFIXES.sub("", t)
    t = re.sub(r"\s+", " ", t).strip()

    loc = normalize_location(location)

    return hashlib.sha256(f"{c}|{t}|{loc}".encode()).hexdigest()
