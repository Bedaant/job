"""Resume text -> structured Facts KB drafts (SPEC.md §2.1, ADR-009).

Deliberately does NOT repeat tailoring/engine.py's known bug (B5): JSON parsing
is wrapped, malformed output raises a clear ValueError instead of an unhandled
JSONDecodeError, and there's no bare `except: pass`.
"""
import json

import anthropic

from core.config import get_settings

MODEL = "claude-sonnet-5"  # config-driven would be MODEL_STRONG per SPEC.md §6;
                            # single call site for now, revisit when tailoring/engine.py
                            # is fixed in Phase 4 and the two share config

_client = anthropic.Anthropic(api_key=get_settings().anthropic_api_key)

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
