"""F11 bounded form-fill agent (SPEC.md §3.7, ADR-011): one bounded Claude/
nvidia_smoke call maps extracted form fields to profile data. Never invents a
value the profile doesn't have; never fills a demographic/EEO/essay field
regardless of what the model says.
"""
import json

from core.grounding import validate_ids_against_known_set
from formfill.deterministic import match_field_deterministic
from tailoring.engine import call_llm

CONFIDENCE_THRESHOLD = 0.75

# Applicant-identity fields handed to the mapping model, mirroring
# schemas.ApplicantBasics — these are the columns that actually make a form
# fillable (added 2026-09-26; before that only `email` resolved, so name,
# phone, location and links always came back `unknown`).
_BASICS_FIELDS = (
    "full_name",
    "phone",
    "website_url",
    "street_address",
    "city",
    "region",
    "country_code",
    "postal_code",
)


def build_profile_summary(profile, email: str) -> dict:
    """The profile view handed to the mapping model.

    Only non-empty values are included, deliberately: sending `"phone": null`
    invites the model to "map" a field to a value that doesn't exist, whereas an
    absent key makes the gap unambiguous. Same reasoning as the null-over-guess
    rule in parsing/llm_extract.py's extraction prompt.
    """
    summary: dict = {"email": email}

    for name in _BASICS_FIELDS:
        value = getattr(profile, name, None)
        if value:
            summary[name] = value

    if getattr(profile, "network_profiles", None):
        summary["network_profiles"] = profile.network_profiles
    if getattr(profile, "work_auth", None):
        summary["work_auth"] = profile.work_auth
    if getattr(profile, "headline", None):
        summary["headline"] = profile.headline
    if getattr(profile, "resume_facts", None):
        summary["resume_fact_categories"] = sorted({f.category for f in profile.resume_facts})

    return summary

FORBIDDEN_LABEL_KEYWORDS = [
    "race", "ethnicity", "gender", "veteran status", "disability status",
    "sexual orientation", "why do you want to work", "why are you interested",
]

MAX_ATTEMPTS = 2  # ADR-011: bounded retry on a malformed response, not a reasoning loop

SYSTEM_PROMPT = (
    "You map extracted job-application form fields to a candidate's profile data. "
    "You will be given a JSON list of form fields (field_id, label_text, input_type, "
    "options) and a JSON summary of the candidate's profile. For each field, decide "
    "what it maps to using ONLY the profile data given — never invent a value. "
    'maps_to must be one of: "profile.<attr>" (attr present in the profile summary), '
    '"resume_fact:<category>", "literal:<short string derived only from given data>", '
    'or "unknown" if nothing in the profile answers it. confidence is 0.0-1.0 — use '
    "low confidence rather than a guess when the label is ambiguous. Respond ONLY "
    'with a valid JSON array: [{"field_id": "...", "maps_to": "...", '
    '"confidence": 0.0, "value": "... or null"}]'
)


def is_forbidden_label(label_text: str | None) -> bool:
    if not label_text:
        return False
    lower = label_text.lower()
    return any(keyword in lower for keyword in FORBIDDEN_LABEL_KEYWORDS)


def _flagged(field_id: str) -> dict:
    return {"field_id": field_id, "maps_to": "unknown", "confidence": 0.0, "value": None}


def map_form_fields(fields: list[dict], profile_summary: dict) -> list[dict]:
    forbidden_ids = {f["field_id"] for f in fields if is_forbidden_label(f.get("label_text"))}

    # Deterministic pass first (SPEC.md §3.7 / PRD "Known ATS... fills them
    # deterministically") — zero LLM calls for anything structurally
    # unambiguous (autocomplete attribute, name/id/label patterns). Only
    # fields it can't resolve go on to the bounded LLM path at all.
    deterministic_results: dict[str, dict] = {}
    remaining_fields = []
    for field in fields:
        if field["field_id"] in forbidden_ids:
            continue
        match = match_field_deterministic(field, profile_summary)
        if match is not None:
            deterministic_results[field["field_id"]] = match
        else:
            remaining_fields.append(field)

    mapping_by_id: dict[str, dict] = {}
    if remaining_fields:
        known_field_ids = {f["field_id"] for f in remaining_fields}
        user_prompt = (
            f"FIELDS:\n{json.dumps(remaining_fields, indent=2)}\n\n"
            f"PROFILE:\n{json.dumps(profile_summary, indent=2)}"
        )
        for _attempt in range(MAX_ATTEMPTS):
            raw = call_llm(SYSTEM_PROMPT, user_prompt)
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            try:
                parsed = json.loads(cleaned)
                candidate = {m["field_id"]: m for m in parsed}
                # Same grounding check as tailoring/engine.py's Bullet
                # validator, applied explicitly here rather than left to the
                # implicit effect of `mapping_by_id.get()` below returning
                # None for an id we never supplied. Unlike tailoring (which
                # lets `instructor` retry on ValueError), this raises into
                # the *same* bounded MAX_ATTEMPTS loop already used for
                # malformed JSON — an invented field_id is just another kind
                # of malformed response. If attempts run out, the loop falls
                # through with `mapping_by_id` still {}, and every field
                # lands in the existing `_flagged()` "unknown, human review"
                # path below — consistent with this module's own "never
                # invent, flag for a human" philosophy, not a hard failure.
                validate_ids_against_known_set(
                    list(candidate.keys()), known_field_ids, field_name="field_id"
                )
                mapping_by_id = candidate
                break
            except (json.JSONDecodeError, TypeError, KeyError, ValueError):
                continue

    result = []
    for field in fields:
        field_id = field["field_id"]
        if field_id in forbidden_ids:
            result.append(_flagged(field_id))
        elif field_id in deterministic_results:
            result.append(deterministic_results[field_id])
        else:
            mapping = mapping_by_id.get(field_id)
            if mapping is None:
                result.append(_flagged(field_id))
            else:
                result.append({
                    "field_id": field_id,
                    "maps_to": mapping.get("maps_to", "unknown"),
                    "confidence": mapping.get("confidence", 0.0),
                    "value": mapping.get("value"),
                })
    return result
