"""F11 bounded form-fill agent (SPEC.md §3.7, ADR-011): one bounded Claude/
nvidia_smoke call maps extracted form fields to profile data. Never invents a
value the profile doesn't have; never fills a demographic/EEO/essay field
regardless of what the model says.
"""
import json
import re

from answer_bank import DEMOGRAPHIC_LABEL_KEYWORDS, is_consent_field, is_demographic_field, is_demographic_label  # noqa: F401
from core.grounding import validate_ids_against_known_set
from formfill.deterministic import (
    _NO_PROFILE_VALUE_TYPES, _NOT_A_PROFILE_QUESTION, _country_option, _find_network_url,
    bind_to_options, match_field_deterministic, recognised_profile_key,
)
from tailoring.engine import call_llm

CONFIDENCE_THRESHOLD = 0.75

# docs/LIVE-FORM-TEST.md #15: one 3,302-option university <select> put 122 KB
# into the prompt. The model sees the first N; binding still checks the full list.
MAX_PROMPT_OPTIONS = 50

# Fields nothing can answer (#10): anti-bot tokens, hidden inputs, search boxes
# (intl-tel-input's country "Search"), fields with no label, name or options,
# and option-less radios/checkboxes (see _unanswerable).
_UNANSWERABLE_TYPES = {"hidden", "search", "file", "submit", "button"}
_ANTI_BOT = re.compile(r"g-recaptcha|h-captcha|cf-turnstile", re.I)
_CHOICE_TYPES = {"radio", "checkbox"}

# Applicant-identity fields handed to the mapping model, mirroring
# schemas.ApplicantBasics — these are the columns that actually make a form
# fillable (added 2026-09-26; before that only `email` resolved, so name,
# phone, location and links always came back `unknown`).
_BASICS_FIELDS = (
    "full_name",
    "given_name",   # user-entered (migration 0018); else split from full_name below
    "family_name",
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

    # Missing name parts come from the user's own full_name, mapping-time only
    # (never written back), and only for an unambiguous two-word name. "Mary Jane
    # Watson" or "Cher" has no one right split: those stay missing and are flagged.
    tokens = (summary.get("full_name") or "").split()
    if len(tokens) == 2:
        summary.setdefault("given_name", tokens[0])
        summary.setdefault("family_name", tokens[1])

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
    "low confidence rather than a guess when the label is ambiguous. "
    "If a field lists options, value MUST be exactly one of those options, copied "
    'verbatim (a Yes/No question gets "Yes" or "No", never a city or other profile '
    'attribute) — otherwise maps_to "unknown" and value null. A select, radio, '
    'checkbox or combobox with no options listed: "unknown". Respond ONLY '
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


def _unanswerable(field: dict) -> bool:
    ids = f"{field.get('name') or ''} {field.get('dom_id') or ''}"
    return (
        (field.get("input_type") or "").lower() in _UNANSWERABLE_TYPES
        or bool(_ANTI_BOT.search(ids))
        or not (field.get("label_text") or ids.strip() or field.get("options"))
        # A lone radio/checkbox's label is an option ("White", "Telugu (TEL)"),
        # not a question; a group arrives with its options.
        or ((field.get("input_type") or "").lower() in _CHOICE_TYPES and not field.get("options"))
    )


def _prompt_field(field: dict) -> dict:
    """What the model needs, nothing more: no autocomplete/dom_id noise, and
    options capped at MAX_PROMPT_OPTIONS with the true count alongside."""
    out = {k: field.get(k) for k in ("field_id", "label_text", "input_type")}
    if not field.get("label_text") and field.get("name"):
        out["name"] = field["name"]
    options = field.get("options") or []
    if options:
        out["options"] = options[:MAX_PROMPT_OPTIONS]
        if len(options) > MAX_PROMPT_OPTIONS:
            out["options_total"] = len(options)
    return out


def _flagged(field_id: str) -> dict:
    return {"field_id": field_id, "maps_to": "unknown", "confidence": 0.0, "value": None}


def _from_answer_bank(field_id: str, value: str) -> dict:
    # confidence 1.0 because the text is the user's own, and the match that
    # produced it already had to clear answer_bank's two gates — there is no
    # model judgement in this value to discount.
    return {"field_id": field_id, "maps_to": "answer_bank", "confidence": 1.0, "value": value}


# ADR-016 plan `fill_from` -> profile_summary key (or network). Anything else
# (resume, cover_letter, location, current_*, unknown, and "never": the plan's
# consent/EEO tagging is untrusted, the rail decides) takes today's path.
_PLAN_PROFILE_KEYS = {
    **{k: k for k in ("full_name", "given_name", "family_name", "email", "phone", "city", "region", "country_code")},
    "website": "website_url", "linkedin": "network:linkedin", "github": "network:github",
}


def _plan_mapping(field: dict, fill_from: str, profile_summary: dict, answer_lookup) -> dict | None:
    """ADR-016: the plan routes a field, it never supplies a value. A value comes
    only from the profile or the bank, bound to the live options; a routed field
    with no value is flagged, never sent to the model (except an answer-bank miss).
    None = not routed."""
    field_id = field["field_id"]
    if fill_from == "answer_bank_question":
        answer = answer_lookup(field.get("label_text")) if answer_lookup else None
        bound = bind_to_options(answer, field.get("options")) if answer else None
        # A miss takes today's path: the measured planner tags most fields this way (even Name/Email).
        return {"field_id": field_id, "maps_to": "plan:answer_bank", "confidence": 1.0, "value": bound} if bound else None
    key = _PLAN_PROFILE_KEYS.get(fill_from)
    if (
        key is None
        or (field.get("input_type") or "").lower() in _NO_PROFILE_VALUE_TYPES
        or _NOT_A_PROFILE_QUESTION.search((field.get("label_text") or "").lower())
    ):
        return None  # deterministic.py's guards: a choice or yes/no field never takes a profile string
    if key.startswith("network:"):
        name = key.split(":", 1)[1]
        value = bind_to_options(_find_network_url(profile_summary, name), field.get("options"))
        maps_to = f"plan:network_profile:{name}"
    else:
        value = bind_to_options(profile_summary.get(key) or None, field.get("options"))
        if not value and key == "country_code":
            value = _country_option(profile_summary.get(key), field.get("options"))
        maps_to = f"plan:profile.{key}"
    return {"field_id": field_id, "maps_to": maps_to, "confidence": 1.0, "value": value} if value else _flagged(field_id)


def map_form_fields(
    fields: list[dict], profile_summary: dict, answer_lookup=None, ats_type: str | None = None, plan: dict | None = None
) -> list[dict]:
    """`answer_lookup(question_text) -> str | None` is the answer bank, injected
    rather than imported so this module stays free of a DB session and its tests
    stay free of a database. main.py passes
    `answer_bank.serve_answer`-bound-to-this-profile; None means "no bank", which
    reproduces the pre-bank behaviour exactly.

    `plan` is the job's stored Stagehand plan (ADR-016). If any plan key is not
    on the live form, the form changed since planning: the whole plan is dropped.
    """
    live = ({f.get("name") for f in fields} | {f.get("dom_id") for f in fields}) - {None, ""}
    plan_fields = (plan or {}).get("fields") or []
    route = (
        {p.get("key"): p.get("fill_from") for p in plan_fields}
        if all(p.get("key") in live for p in plan_fields) else {}
    )
    # Demographic first and unconditionally: these fields are excluded before
    # the deterministic matcher, before the bank, and before the model. Nothing
    # downstream gets the chance to resolve one. Today's extension sends one
    # descriptor per radio/checkbox ("Man", "Woman"), so same-name siblings'
    # labels count as the group's options for this check. Unanswerable fields
    # (captcha, hidden, no context) are dropped here too, flagged, never prompted.
    group_labels: dict[str, list[str]] = {}
    for f in fields:
        if f.get("input_type") in _CHOICE_TYPES and f.get("name") and f.get("label_text"):
            group_labels.setdefault(f["name"], []).append(f["label_text"])
    demographic_ids = {
        f["field_id"] for f in fields
        if is_demographic_field(f.get("label_text"), (f.get("options") or []) + group_labels.get(f.get("name") or "", []))
        or is_consent_field(f.get("label_text"), (f.get("options") or []) + group_labels.get(f.get("name") or "", []))
        or _unanswerable(f)
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

        match = match_field_deterministic(field, profile_summary, ats_type)
        if match is not None:
            deterministic_results[field_id] = match
            continue
        fill_from = route.get(field.get("name")) or route.get(field.get("dom_id"))
        planned = _plan_mapping(field, fill_from, profile_summary, answer_lookup) if fill_from else None
        if planned is not None:
            deterministic_results[field_id] = planned
            continue
        if recognised_profile_key(field, ats_type) is not None:
            # A known profile field whose data the profile lacks (e.g. First Name
            # with no given_name): flag it. Found live — the model filled the FULL
            # name into both First and Last Name when this fell through.
            deterministic_results[field_id] = _flagged(field_id)
            continue

        answer = answer_lookup(field.get("label_text")) if answer_lookup else None
        if answer:
            # Bound to the options or flagged — never falls through to the model.
            bound = bind_to_options(answer, field.get("options"))
            if bound:
                bank_results[field_id] = _from_answer_bank(field_id, bound)
            continue

        remaining_fields.append(field)

    mapping_by_id: dict[str, dict] = {}
    if remaining_fields:
        # ONE call for every field no rule or bank answered.
        known_field_ids = {f["field_id"] for f in remaining_fields}
        user_prompt = (
            f"FIELDS:\n{json.dumps([_prompt_field(f) for f in remaining_fields])}\n\n"
            f"PROFILE:\n{json.dumps(profile_summary)}"
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
            value = mapping.get("value") if mapping else None
            bound = bind_to_options(value, field.get("options"))
            if mapping is None or (value is not None and bound is None):
                # Live: "San Francisco" into a Yes/No relocation combobox at 0.8.
                result.append(_flagged(field_id))
            else:
                result.append({
                    "field_id": field_id,
                    "maps_to": mapping.get("maps_to", "unknown"),
                    "confidence": mapping.get("confidence", 0.0),
                    "value": bound,
                })
    return result
