"""F11 bounded form-fill agent (SPEC.md §3.7, ADR-011): one bounded Claude/
nvidia_smoke call maps extracted form fields to profile data. Never invents a
value the profile doesn't have; never fills a demographic/EEO/essay field
regardless of what the model says.
"""
import json

from answer_bank import DEMOGRAPHIC_LABEL_KEYWORDS, is_demographic_label
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

# These two lists used to be one, and lumping them together was wrong: they are
# unfillable for completely different reasons and only one of them is permanent.
#
# DEMOGRAPHIC (imported from answer_bank, where it is enforced on both the read
# and write path): race, ethnicity, gender, veteran/disability status, sexual
# orientation. NEVER fillable — not from the profile, not from the answer bank,
# not from a model, not ever. No feature may change this.
#
# ESSAY: "why do you want to work here", "why are you interested". Unfillable
# only because we had no user-written answer to fill them with. Now that the
# answer bank exists, filling these from something the user actually typed is
# the entire point — a model must still never write one (ADR-006/ADR-009), which
# is why the essay path checks the bank and then stops, rather than falling
# through to the LLM like an ordinary unresolved field.
ESSAY_LABEL_KEYWORDS = [
    "why do you want to work", "why are you interested",
]

# Kept as the union so existing callers (and the extension's mirrored list) keep
# their meaning: "nothing here is fillable without a user-written answer".
FORBIDDEN_LABEL_KEYWORDS = DEMOGRAPHIC_LABEL_KEYWORDS + ESSAY_LABEL_KEYWORDS

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
    """Demographic OR essay. Still the right question for a caller asking "can
    this be filled from profile data alone?" — but no longer the right question
    for "can this be filled at all", which is why the essay half is now checked
    separately in map_form_fields.
    """
    if not label_text:
        return False
    lower = label_text.lower()
    return any(keyword in lower for keyword in FORBIDDEN_LABEL_KEYWORDS)


def is_essay_label(label_text: str | None) -> bool:
    """Motivation/essay question — fillable only from a user-written answer."""
    if not label_text:
        return False
    lower = label_text.lower()
    return any(keyword in lower for keyword in ESSAY_LABEL_KEYWORDS)


def _flagged(field_id: str) -> dict:
    return {"field_id": field_id, "maps_to": "unknown", "confidence": 0.0, "value": None}


def _from_answer_bank(field_id: str, value: str) -> dict:
    # confidence 1.0 because the text is the user's own, and the match that
    # produced it already had to clear answer_bank's two gates — there is no
    # model judgement in this value to discount.
    return {"field_id": field_id, "maps_to": "answer_bank", "confidence": 1.0, "value": value}


def map_form_fields(fields: list[dict], profile_summary: dict, answer_lookup=None) -> list[dict]:
    """`answer_lookup(question_text) -> str | None` is the answer bank, injected
    rather than imported so this module stays free of a DB session and its tests
    stay free of a database. main.py passes
    `answer_bank.serve_answer`-bound-to-this-profile; None means "no bank", which
    reproduces the pre-bank behaviour exactly.
    """
    # Demographic first and unconditionally: these fields are excluded before
    # the deterministic matcher, before the bank, and before the model. Nothing
    # downstream gets the chance to resolve one.
    demographic_ids = {
        f["field_id"] for f in fields if is_demographic_label(f.get("label_text"))
    }

    # Deterministic pass next (SPEC.md §3.7 / PRD "Known ATS... fills them
    # deterministically") — zero LLM calls for anything structurally
    # unambiguous (autocomplete attribute, name/id/label patterns). Then the
    # answer bank, for anything the profile itself can't answer. Only what
    # neither resolves goes on to the bounded LLM path at all.
    deterministic_results: dict[str, dict] = {}
    bank_results: dict[str, dict] = {}
    remaining_fields = []
    for field in fields:
        field_id = field["field_id"]
        if field_id in demographic_ids:
            continue

        if is_essay_label(field.get("label_text")):
            # An essay question has no deterministic answer and must never be
            # written by a model. The bank or nothing.
            answer = answer_lookup(field["label_text"]) if answer_lookup else None
            if answer:
                bank_results[field_id] = _from_answer_bank(field_id, answer)
            continue

        match = match_field_deterministic(field, profile_summary)
        if match is not None:
            deterministic_results[field_id] = match
            continue

        answer = answer_lookup(field.get("label_text")) if answer_lookup else None
        if answer:
            bank_results[field_id] = _from_answer_bank(field_id, answer)
            continue

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
        if field_id in demographic_ids:
            result.append(_flagged(field_id))
        elif field_id in deterministic_results:
            result.append(deterministic_results[field_id])
        elif field_id in bank_results:
            result.append(bank_results[field_id])
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
