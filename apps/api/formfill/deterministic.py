"""Deterministic field matching (PRD: "Known ATS... fills them
deterministically"; SPEC.md §3.7). Zero LLM calls — an ordered rule table
over each field's own attributes: HTML `autocomplete` (a real web standard,
WHATWG HTML spec §autofill-field-name) first, then name/id/label regex
patterns. Checked in map_fields.py::map_form_fields BEFORE the bounded LLM
path, not instead of it — anything this can't resolve falls through
unchanged, same confidence-threshold/forbidden-label behavior as before.

Deliberately does not attempt given-name/family-name fields: Profile has no
structured name-parts column, only a single `full_name` string, and
guessing a split (first token = given, rest = family) would be exactly the
kind of invention the null-over-guess rule already forbids for identity
data (schemas.ApplicantBasics's validators). Those fields fall through to
the LLM path, same as any other field this module doesn't recognize.

When the caller passes an `ats_type`, formfill/ats_schemas.py's verified
per-ATS system field names are consulted first (ADR-015 Phase 2).
"""
import re

from formfill.ats_schemas import ATS_FIELD_SCHEMAS

# autocomplete token -> profile_summary key. WHATWG HTML living standard,
# https://html.spec.whatwg.org/multipage/form-control-infrastructure.html#autofill-field-name
# — not guessed, a real published enumeration.
_AUTOCOMPLETE_MAP = {
    "email": "email",
    "tel": "phone",
    "tel-national": "phone",
    "name": "full_name",
    "address-level2": "city",
    "address-level1": "region",
    "postal-code": "postal_code",
    "country": "country_code",
    "country-name": "country_code",
    "street-address": "street_address",
    "address-line1": "street_address",
}

# name/id/label regex -> profile_summary key, checked in this order (email
# and phone first — the most unambiguous signals — down to the vaguer
# address fields). No given-name/family-name entry: see module docstring.
_PATTERN_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"e[-_]?mail", re.I), "email"),
    (re.compile(r"phone|mobile|tel(?:ephone)?", re.I), "phone"),
    (re.compile(r"^\s*full[-_ ]?name\s*$|^\s*name\s*$|your[-_ ]?name", re.I), "full_name"),
    (re.compile(r"portfolio|personal[-_ ]?(?:site|website)|\bwebsite\b", re.I), "website_url"),
    (re.compile(r"\bcity\b|\btown\b", re.I), "city"),
    (re.compile(r"\bstate\b|\bprovince\b|\bregion\b", re.I), "region"),
    (re.compile(r"zip|postal", re.I), "postal_code"),
    (re.compile(r"\bcountry\b", re.I), "country_code"),
    (re.compile(r"street[-_ ]?address|address[-_ ]?line", re.I), "street_address"),
]

# Checked before the generic rules above — a field naming a specific
# network (LinkedIn/GitHub/...) must resolve to THAT network's URL or fall
# through, never to a generic website_url guess.
_NETWORK_PATTERN = re.compile(r"linkedin|github|gitlab", re.I)


def _find_network_url(profile_summary: dict, network_name: str) -> str | None:
    for entry in profile_summary.get("network_profiles", []):
        if entry.get("network", "").lower() == network_name.lower():
            return entry.get("url")
    return None


def _mapping(field_id: str, maps_to: str, value: str) -> dict:
    return {"field_id": field_id, "maps_to": maps_to, "confidence": 1.0, "value": value}


def match_field_deterministic(field: dict, profile_summary: dict, ats_type: str | None = None) -> dict | None:
    """Returns a FieldMapping dict at confidence 1.0 if this field can be
    resolved without any model call, else None — the caller (map_fields.py)
    sends None results to the bounded LLM path unchanged.
    """
    autocomplete = (field.get("autocomplete") or "").lower()
    name_attr = field.get("name") or ""
    dom_id = field.get("dom_id") or ""
    label = field.get("label_text") or ""

    # A verified system field on a known ATS wins over every generic rule.
    schema = ATS_FIELD_SCHEMAS.get(ats_type, {})
    key = schema.get(name_attr) or schema.get(dom_id)

    if key is None:
        network_match = (
            _NETWORK_PATTERN.search(name_attr)
            or _NETWORK_PATTERN.search(dom_id)
            or _NETWORK_PATTERN.search(label)
        )
        if network_match:
            network_name = network_match.group(0)
            url = _find_network_url(profile_summary, network_name)
            if url:
                return _mapping(field["field_id"], f"network_profile:{network_name.lower()}", url)
            return None  # a real network field, but we don't have that one — flag, don't guess

        key = _AUTOCOMPLETE_MAP.get(autocomplete)
    if key is None:
        for pattern, candidate_key in _PATTERN_RULES:
            if pattern.search(name_attr) or pattern.search(dom_id) or pattern.search(label):
                key = candidate_key
                break

    if key is None:
        return None

    value = profile_summary.get(key)
    if not value:
        return None  # rule matched structurally, but the data isn't there — flag, don't guess

    return _mapping(field["field_id"], f"profile.{key}", value)
