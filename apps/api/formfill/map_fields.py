"""F11 bounded form-fill agent (SPEC.md §3.7, ADR-011): one bounded Claude/
nvidia_smoke call maps extracted form fields to profile data. Never invents a
value the profile doesn't have; never fills a demographic/EEO/essay field
regardless of what the model says.
"""
import json

from tailoring.engine import call_llm

CONFIDENCE_THRESHOLD = 0.75

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
    askable_fields = [f for f in fields if f["field_id"] not in forbidden_ids]

    mapping_by_id: dict[str, dict] = {}
    if askable_fields:
        user_prompt = (
            f"FIELDS:\n{json.dumps(askable_fields, indent=2)}\n\n"
            f"PROFILE:\n{json.dumps(profile_summary, indent=2)}"
        )
        for _attempt in range(MAX_ATTEMPTS):
            raw = call_llm(SYSTEM_PROMPT, user_prompt)
            cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            try:
                parsed = json.loads(cleaned)
                mapping_by_id = {m["field_id"]: m for m in parsed}
                break
            except (json.JSONDecodeError, TypeError, KeyError):
                continue

    result = []
    for field in fields:
        field_id = field["field_id"]
        if field_id in forbidden_ids:
            result.append(_flagged(field_id))
            continue
        mapping = mapping_by_id.get(field_id)
        if mapping is None:
            result.append(_flagged(field_id))
            continue
        result.append({
            "field_id": field_id,
            "maps_to": mapping.get("maps_to", "unknown"),
            "confidence": mapping.get("confidence", 0.0),
            "value": mapping.get("value"),
        })
    return result
