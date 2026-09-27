"""Deterministic field matching (PRD: "Known ATS... fills them
deterministically"; SPEC.md §3.7). Zero LLM calls — an ordered rule table
over each field's own attributes: HTML `autocomplete` (a real web standard,
WHATWG HTML spec §autofill-field-name) first, then name/id/label patterns.
Checked in map_fields.py::map_form_fields BEFORE the bounded LLM path, not
instead of it — anything this can't resolve falls through unchanged.

Given/family name fill only from the user's own given_name/family_name
basics (migration 0018), never from a split of full_name — a split is a
guess, which the null-over-guess rule forbids for identity data.

Rules match whole tokens (docs/LIVE-FORM-TEST.md #6: `tel` matched
"Telugu", `country` matched a visa question). name/id are split into tokens
(camelCase, `_`, `-`, brackets); labels match whole words, only when short,
and never when they ask about work authorization. A checkbox/radio never
takes a profile value, and a field with options only takes a value that is
one of them (bind_to_options).

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
    "given-name": "given_name",
    "family-name": "family_name",
    "address-level2": "city",
    "address-level1": "region",
    "postal-code": "postal_code",
    "country": "country_code",
    "country-name": "country_code",
    "street-address": "street_address",
    "address-line1": "street_address",
}

# Checked in order over the TOKENIZED name/id ("applicant_phone_number" ->
# "applicant phone number"), so \b is a token boundary. Given/family before
# full_name: "first name" contains "name".
_ID_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:first|given) ?name\b"), "given_name"),
    (re.compile(r"\b(?:last|family) ?name\b|\bsurname\b"), "family_name"),
    (re.compile(r"\be ?mail"), "email"),
    (re.compile(r"\b(?:phone|telephone|mobile)|\btel\b"), "phone"),
    (re.compile(r"^(?:full ?name|name|your ?name)$|\bfull ?name\b"), "full_name"),
    (re.compile(r"\bportfolio|\bpersonal ?(?:site|website)\b|\bwebsite\b"), "website_url"),
    (re.compile(r"\bcity\b|\btown\b"), "city"),
    (re.compile(r"\bstate\b|\bprovince\b|\bregion\b"), "region"),
    (re.compile(r"\bzip|\bpostal"), "postal_code"),
    (re.compile(r"\bcountry\b"), "country_code"),
    (re.compile(r"\bstreet ?address\b|\baddress ?line"), "street_address"),
]

# Labels are prose: whole words only ("Telugu (TEL)" has a word "tel", so no
# bare "tel" here), and only short ones — a question long enough to mention a
# country in passing is not asking for the applicant's country.
_LABEL_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(?:first|given) name\b"), "given_name"),
    (re.compile(r"\b(?:last|family) name\b|\bsurname\b"), "family_name"),
    (re.compile(r"\be-?mail\b"), "email"),
    (re.compile(r"\b(?:phone|mobile|telephone)\b"), "phone"),
    (re.compile(r"^(?:full )?name$|\byour name\b|\bfull name\b"), "full_name"),
    (re.compile(r"\bportfolio\b|\bpersonal (?:site|website)\b|\bwebsite\b"), "website_url"),
    (re.compile(r"\bcity\b|\btown\b"), "city"),
    (re.compile(r"\bstate\b|\bprovince\b|\bregion\b"), "region"),
    (re.compile(r"\bzip\b|\bpostal\b"), "postal_code"),
    (re.compile(r"\bcountry\b"), "country_code"),
    (re.compile(r"\bstreet address\b|\baddress line\b"), "street_address"),
]
_MAX_LABEL_WORDS = 6
# A label about eligibility is a yes/no legal question, whatever noun it uses.
_NOT_A_PROFILE_QUESTION = re.compile(r"sponsor|authori[sz]|visa|eligib|citizen|permit|relocat|willing")

_NO_PROFILE_VALUE_TYPES = {"checkbox", "radio", "hidden", "file", "submit", "button"}

# Checked before the generic rules above — a field naming a specific
# network (LinkedIn/GitHub/...) must resolve to THAT network's URL or fall
# through, never to a generic website_url guess.
_NETWORK_PATTERN = re.compile(r"linkedin|github|gitlab", re.I)

_YES, _NO = {"yes", "y", "true"}, {"no", "n", "false"}


def _tokens(text: str) -> str:
    """"applicantPhone_number[0]" -> "applicant phone number 0"."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return " ".join(re.findall(r"[a-z0-9]+", spaced.lower()))


def bind_to_options(value: str | None, options: list[str] | None) -> str | None:
    """The option a value selects, or None. No options = any value stands.

    Case-insensitive, trimmed, exact. The one normalization: a yes/no value
    (yes/y/true, no/n/false) picks the single option starting with that word
    ("Yes" -> "Yes, I will relocate"); two such options = ambiguous = None.
    """
    if not options:
        return value
    if value is None:
        return None
    wanted = value.strip().lower()
    for option in options:
        if option.strip().lower() == wanted:
            return option
    for words, word in ((_YES, "yes"), (_NO, "no")):
        if wanted in words:
            hits = [o for o in options if re.match(rf"{word}\b", o.strip().lower())]
            return hits[0] if len(hits) == 1 else None
    return None


def _country_option(code: str | None, options: list[str] | None) -> str | None:
    """ISO code -> the option naming that country ("US" -> "United States +1").
    phonenumbers is already installed; _region_display_name is private, so any
    failure just means "not filled", never a wrong value."""
    if not code or not options:
        return None
    try:
        from phonenumbers.geocoder import _region_display_name
        name = _region_display_name(code.upper(), "en")
    except Exception:
        return None
    if not name:
        return None
    wanted = name.lower()
    hits = [o for o in options if o.strip().lower() == wanted or o.strip().lower().startswith(wanted + " ")]
    return hits[0] if len(hits) == 1 else None


def _find_network_url(profile_summary: dict, network_name: str) -> str | None:
    for entry in profile_summary.get("network_profiles", []):
        if entry.get("network", "").lower() == network_name.lower():
            return entry.get("url")
    return None


def _mapping(field_id: str, maps_to: str, value: str) -> dict:
    return {"field_id": field_id, "maps_to": maps_to, "confidence": 1.0, "value": value}


def recognised_profile_key(field: dict, ats_type: str | None = None) -> str | None:
    """Which profile value this field structurally asks for (a profile_summary
    key, or "network:<name>"), independent of whether the profile has it. None =
    not a field these rules recognise."""
    if (field.get("input_type") or "").lower() in _NO_PROFILE_VALUE_TYPES:
        return None  # a profile string never belongs here (live: phone -> "Telugu" checkbox)

    name_attr = field.get("name") or ""
    dom_id = field.get("dom_id") or ""
    ids = [_tokens(name_attr), _tokens(dom_id)]
    label = (field.get("label_text") or "").strip().lower().rstrip("*✱: ")
    label_usable = len(label.split()) <= _MAX_LABEL_WORDS and not _NOT_A_PROFILE_QUESTION.search(label)

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
            return f"network:{network_match.group(0).lower()}"

        # The last token names the field; earlier ones are section/hint tokens.
        tokens = (field.get("autocomplete") or "").lower().split()
        key = next((_AUTOCOMPLETE_MAP[t] for t in reversed(tokens) if t in _AUTOCOMPLETE_MAP), None)
    if key is None:
        key = next((k for pattern, k in _ID_RULES if any(pattern.search(i) for i in ids)), None)
    if key is None and label_usable:
        key = next((k for pattern, k in _LABEL_RULES if pattern.search(label)), None)

    return key


def match_field_deterministic(field: dict, profile_summary: dict, ats_type: str | None = None) -> dict | None:
    """Returns a FieldMapping dict at confidence 1.0 if this field can be
    resolved without any model call, else None — the caller (map_fields.py)
    sends None results on, EXCEPT when recognised_profile_key() says the field
    is a known profile field whose data is simply missing: that is flagged, never
    handed to the model to guess.
    """
    key = recognised_profile_key(field, ats_type)
    if key is None:
        return None
    if key.startswith("network:"):
        network_name = key.split(":", 1)[1]
        url = _find_network_url(profile_summary, network_name)
        return _mapping(field["field_id"], f"network_profile:{network_name}", url) if url else None

    # Rule matched structurally, but the data isn't there (or isn't one of the
    # field's options) — flag, don't guess.
    value = bind_to_options(profile_summary.get(key) or None, field.get("options"))
    if not value and key == "country_code":
        value = _country_option(profile_summary.get(key), field.get("options"))
    if not value:
        return None

    return _mapping(field["field_id"], f"profile.{key}", value)
