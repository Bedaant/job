"""Resume text -> structured Facts KB drafts (SPEC.md §2.1, ADR-009).

Deliberately does NOT repeat tailoring/engine.py's known bug (B5): JSON parsing
is wrapped, malformed output raises a clear ValueError instead of an unhandled
JSONDecodeError, and there's no bare `except: pass`.
"""
import json

import anthropic
import instructor
import openai

from core.config import get_settings
from schemas import ApplicantBasics

MODEL = "claude-sonnet-5"  # config-driven would be MODEL_STRONG per SPEC.md §6;
                            # single call site for now, revisit when tailoring/engine.py
                            # is fixed in Phase 4 and the two share config

_client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)

# Dev-only smoke-test client (same nvidia_smoke provider as tailoring/engine.py
# - this module never had that branch until now, a real gap: with no real
# ANTHROPIC_API_KEY, resume upload's fact/identity extraction was dead code).
# Lazy - only built if llm_provider is ever actually "nvidia_smoke", so a
# missing nvidia_api_key never breaks the default (real Anthropic) path.
_nvidia_client: openai.OpenAI | None = None


def _get_nvidia_client() -> openai.OpenAI:
    global _nvidia_client
    if _nvidia_client is None:
        settings = get_settings()
        _nvidia_client = openai.OpenAI(api_key=settings.nvidia_api_key, base_url=settings.nvidia_base_url)
    return _nvidia_client


SYSTEM_PROMPT = (
    "You extract atomic, verifiable facts from a resume's raw text for a candidate's "
    "Facts KB. Each fact must be a single claim traceable to something the resume "
    "actually says — never infer or invent achievements, metrics, or experience not "
    "present in the text. For each fact, extract: category (one of experience, "
    "project, skill, certification, education), achievement (the claim, in plain "
    "language), proof (what it's backed by — role/project/employer name, or null), "
    "metric (a quantified result if the resume states one, or null), and tags (a short "
    "list of relevant keywords). Respond ONLY with valid JSON: "
    '{"facts": [{"category": "...", "achievement": "...", "proof": "...", '
    '"metric": "...", "tags": ["..."]}]}'
)


def extract_facts_from_text(resume_text: str) -> list[dict]:
    if not resume_text or not resume_text.strip():
        raise ValueError("resume text is empty — nothing to extract facts from")

    settings = get_settings()
    if settings.llm_provider == "nvidia_smoke":
        # Mechanical smoke path - NIM serves open models, not Claude, so this
        # does NOT validate real fact-extraction quality.
        response = _get_nvidia_client().chat.completions.create(
            model=settings.nvidia_smoke_model,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": resume_text[:20_000]},
            ],
        )
        raw = response.choices[0].message.content or ""
    else:
        response = _client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": resume_text[:20_000]}],
        )
        raw = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")

    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON from fact-extraction model: {exc}") from exc

    facts = parsed.get("facts")
    if not isinstance(facts, list):
        raise ValueError("malformed response: expected a 'facts' list")

    return facts


# ---------- Applicant identity (JSON Resume `basics`) ----------

# Lazy, same reasoning as tailoring/engine.py's clients — only built on first
# real call, so nothing here breaks at import time.
_instructor_client: instructor.Instructor | None = None
_nvidia_instructor_client: instructor.Instructor | None = None


def _get_instructor_client() -> instructor.Instructor:
    global _instructor_client
    if _instructor_client is None:
        _instructor_client = instructor.from_anthropic(_client)
    return _instructor_client


def _get_nvidia_instructor_client() -> instructor.Instructor:
    global _nvidia_instructor_client
    if _nvidia_instructor_client is None:
        _nvidia_instructor_client = instructor.from_openai(_get_nvidia_client())
    return _nvidia_instructor_client


# Prompt-engineering notes, because the failure mode here is specific and
# expensive: this output is typed into real application forms sent to real
# employers, so a *plausible* wrong value is worse than a missing one. The
# prompt therefore (1) states the stakes so the model knows why precision
# matters, (2) makes null the explicitly-preferred answer rather than a
# fallback, (3) names the exact placeholder patterns models reach for when
# filling gaps, (4) forbids expansion/normalisation of partial data, and
# (5) gives per-field formats that schemas.ApplicantBasics also *enforces*
# — so a violation is caught and retried by instructor, not shipped.
BASICS_SYSTEM_PROMPT = (
    "You extract a job applicant's contact and identity details from the raw text of their "
    "resume. This data is typed directly into real job application forms submitted to real "
    "employers. An invented or 'filled-in' value therefore causes real harm to the applicant — "
    "a wrong phone number or misspelled name can silently cost them the role.\n\n"
    "ABSOLUTE RULE: extract ONLY what the resume text literally states. If a field is not "
    "present in the text, return null for it. Null is always an acceptable answer and is "
    "strongly preferred over a plausible guess. An incomplete-but-correct result is a success; "
    "a complete-but-invented one is a failure.\n\n"
    "Never emit placeholder values. Specifically never: 'John Doe', 'Jane Doe', 'Your Name', "
    "'Full Name', 'N/A', 'Unknown', or any phone number in the reserved 555-0100..555-0199 "
    "range. If you are tempted to write one of those, return null instead.\n\n"
    "Never complete, expand, or normalise partial data. If the resume says only 'SF', return "
    "city='SF' and leave region and country_code null — do NOT expand it to 'San Francisco', "
    "'California', or 'US'. If it gives a city with no country, leave country_code null.\n\n"
    "Field formats:\n"
    "- full_name: exactly as written on the resume, no reformatting.\n"
    "- phone: keep the resume's own formatting, including country code if present.\n"
    "- website_url and every network profile url: must include an http(s):// scheme. If the "
    "resume shows a bare path or handle, prefix 'https://' ONLY when the platform is "
    "unambiguous from the text (e.g. a linkedin.com/in/... path); otherwise return null.\n"
    "- country_code: ISO 3166-1 alpha-2 — exactly two letters (US, IN, GB). Never a full "
    "country name, never a 3-letter code.\n"
    "- network_profiles: one entry per professional link found (LinkedIn, GitHub, portfolio, "
    "etc.) with the platform name as `network`.\n"
    "- work_auth: populate only if the resume explicitly states work authorization or visa "
    "status; otherwise leave it empty."
)


def extract_basics(resume_text: str) -> ApplicantBasics:
    """Resume text -> validated applicant identity.

    Uses instructor so schemas.ApplicantBasics' validators (placeholder names,
    fictional phone ranges, ISO country codes, url schemes) are *enforced* on
    the model's output with a bounded retry, rather than parsed hopefully.

    Provider note: mirrors tailoring/engine.py's nvidia_smoke dev branch -
    instructor wraps whichever raw client is active, so validation (placeholder
    names, fictional phone ranges, ISO country codes, url schemes) is enforced
    the same way on both providers. The free smoke model is asked to honor the
    same contract as Claude; it is not graded any more leniently.
    """
    if not resume_text or not resume_text.strip():
        raise ValueError("resume text is empty — nothing to extract identity from")

    settings = get_settings()
    user_content = resume_text[:20_000]

    if settings.llm_provider == "nvidia_smoke":
        # OpenAI-shaped APIs (NIM included) have no separate `system` param —
        # the system prompt is a role in the messages list, unlike Anthropic's
        # native shape below. Found live: Anthropic's `system=` kwarg passed
        # straight through raised "Completions.create() got an unexpected
        # keyword argument 'system'" against the real NVIDIA endpoint.
        return _get_nvidia_instructor_client().messages.create(
            model=settings.nvidia_smoke_model,
            max_tokens=1024,
            messages=[
                {"role": "system", "content": BASICS_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_model=ApplicantBasics,
            max_retries=2,
        )

    return _get_instructor_client().messages.create(
        model=MODEL,
        max_tokens=1024,
        system=BASICS_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        response_model=ApplicantBasics,
        max_retries=2,
    )
