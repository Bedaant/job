"""
Two-pass tailoring:
  Pass 1: Claude tailors a summary + bullets + cover letter using ONLY the
          resume facts provided (never invents new achievements). Every
          bullet must cite the fact id(s) it's backed by (SPEC.md §3.3) —
          enforced by Pydantic validation against the real facts given, via
          `instructor`, not just requested in the prompt and hoped for
          (DEPENDENCIES.md: "Fixes CODE-REVIEW.md B5 — tailoring/engine.py
          currently does an unhandled json.loads on model output").
  Pass 2: A second Claude call acts as a truth-checker — compares the output
          against the facts KB and flags any claim it can't trace back to a
          fact. Flagged claims are surfaced to you, not silently kept.
"""
import hashlib
import os
import json
import logging
import re
from types import SimpleNamespace

import anthropic
import instructor
import openai
from instructor.v2.core.errors import InstructorRetryException
from pydantic import BaseModel, Field, ValidationInfo, field_validator
from core.config import get_settings
from core.grounding import validate_ids_against_known_set
from providers import guard
from matching.keyword_gap import _TOKEN_RE, _match_in_fact, compute_keyword_gap
from matching.skills import skill_occurrences
from langfuse import observe, get_client

MODEL = "claude-sonnet-4-6"

# Was `os.getenv("ANTHROPIC_API_KEY")` — silently None unless the real key
# happened to be exported in the ambient shell (nothing in this project
# loads .env into os.environ globally), which sent a literal `x-api-key:
# None` header and crashed inside httpx's header encoding instead of ever
# reaching Anthropic. Read from Settings, same as everything else here.
_settings = get_settings()
ANTHROPIC_API_KEY = _settings.anthropic_api_key

# Langfuse's client reads LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY/LANGFUSE_HOST
# from os.environ (confirmed against the installed SDK's own source, not
# guessed) — same CWD-relative-.env gap as above, so set them explicitly
# from Settings rather than assume they're exported.
if _settings.langfuse_secret_key:
    os.environ.setdefault("LANGFUSE_SECRET_KEY", _settings.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", _settings.langfuse_public_key or "")
    os.environ.setdefault("LANGFUSE_HOST", _settings.langfuse_base_url)
    _langfuse = get_client()
else:
    _langfuse = None

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=_settings.llm_timeout_seconds)
logger = logging.getLogger(__name__)

# Dev-only smoke-test client. Lazy — only constructed if llm_provider is
# ever actually set to "nvidia_smoke", so a missing nvidia_api_key never
# breaks the default (real Anthropic) path.
_nvidia_client: openai.OpenAI | None = None

# Lazy — only constructed on first real (non-smoke) tailoring call, same
# reasoning as _nvidia_client.
_instructor_client: instructor.Instructor | None = None


def _get_nvidia_client() -> openai.OpenAI:
    global _nvidia_client
    if _nvidia_client is None:
        _nvidia_client = openai.OpenAI(
            api_key=_settings.nvidia_api_key,
            base_url=_settings.nvidia_base_url,
            timeout=_settings.llm_timeout_seconds,
        )
    return _nvidia_client


def _get_instructor_client() -> instructor.Instructor:
    global _instructor_client
    if _instructor_client is None:
        _instructor_client = instructor.from_anthropic(_client)
    return _instructor_client


NVIDIA_STRUCTURED_MAX_TOKENS = 4096
_nvidia_instructor_client: instructor.Instructor | None = None


def _get_nvidia_instructor_client() -> instructor.Instructor:
    # JSON mode, not tool calling: not every NIM model supports tools, and the
    # schema is still enforced by instructor's validation + bounded retry.
    global _nvidia_instructor_client
    if _nvidia_instructor_client is None:
        _nvidia_instructor_client = instructor.from_openai(_get_nvidia_client(), mode=instructor.Mode.JSON)
    return _nvidia_instructor_client


class Bullet(BaseModel):
    """SPEC.md §3.3: 'source_fact_ids is mandatory per bullet. A bullet that
    cites no fact is rejected at validation, before the truth-checker even
    runs.' min_length=1 enforces "mandatory"; the field_validator enforces
    that every id genuinely exists in the KB given for *this* call — a model
    inventing a plausible-looking id is rejected the same as an empty list.
    """
    text: str
    source_fact_ids: list[str] = Field(min_length=1)

    @field_validator("source_fact_ids")
    @classmethod
    def fact_ids_must_exist_in_kb(cls, value: list[str], info: ValidationInfo) -> list[str]:
        known_ids = (info.context or {}).get("known_fact_ids", set())
        return validate_ids_against_known_set(value, known_ids, field_name="source_fact_ids")


class TailoredDraft(BaseModel):
    summary: str
    bullets: list[Bullet] = Field(min_length=1)
    cover_letter: str
    keywords_targeted: list[str] = []


class TruthCheckResult(BaseModel):
    unsupported_claims: list[str] = []


class ClaimCheck(BaseModel):
    claim: str
    fact_ids: list[str] = []
    unsupported_phrases: list[str] = []


class ClaimAudit(BaseModel):
    """Strict pass 2: every claim of the draft, each tied to fact ids or not."""
    claims: list[ClaimCheck] = []

    def unsupported(self, known_fact_ids: set[str]) -> list[str]:
        out = []
        for c in self.claims:
            if c.unsupported_phrases:
                out.append(f"{c.claim} [not in facts: {'; '.join(c.unsupported_phrases)}]")
            elif not set(c.fact_ids) & known_fact_ids:
                out.append(c.claim)
        return out


CHECK_SYSTEM = (
    "You are a fact-checker. You will be given a candidate's facts KB and a "
    "tailored resume/cover letter draft generated from it. List any specific "
    "claim (achievement, metric, skill, or experience) in the draft that is NOT "
    "clearly supported by the KB."
)

STRICT_CHECK_SYSTEM = (
    "You are a strict fact-checker for a job application. You get a candidate's "
    "facts KB (each fact has an 'id') and a draft written from it. Split the draft "
    "(summary, every bullet, every cover-letter sentence) into its individual claims. "
    "For EACH claim return: the claim text, the id(s) of the fact(s) that state it, "
    "and unsupported_phrases: every word or phrase in the claim that no cited fact "
    "states — added outcomes or purposes ('ensuring on-time delivery', 'improving "
    "reliability'), scope or scale ('across microservices', 'high-throughput', "
    "'enterprise'), domains, tools, numbers, titles, durations and praise adjectives. "
    "Rewording the same meaning is fine; adding meaning is not. If no fact states "
    "the claim, fact_ids is empty. Generic courtesy in the cover letter ('I am "
    "excited to apply') is not a claim; skip it."
)


def _llm_request(primary_model: str, attempt):
    """The single place every provider request passes: `attempt(model)` on the primary, then
    once on `llm_fallback_model` if set. Returns (result, model_used); re-raises the last error."""
    fallback = _settings.llm_fallback_model
    models = [primary_model]
    if isinstance(fallback, str) and fallback and fallback != primary_model:
        models.append(fallback)
    for i, model in enumerate(models):
        try:
            # retries=0: the provider SDKs already retry. ponytail: 0.03 USD/call is a guess for
            # paid providers, so the daily LLM cap is approximate; NIM is free.
            cost = 0.0 if _settings.llm_provider == "nvidia" else 0.03
            return guard.call("llm", lambda: attempt(model), retries=0, cost_usd=cost), model
        except Exception as exc:
            if isinstance(exc, guard.ProviderRefused) or i == len(models) - 1:
                raise
            # TYPE only: provider errors can echo the prompt.
            logger.warning("LLM %s failed (%s); retrying on %s", model, type(exc).__name__, models[i + 1])


def _cache_client():
    from workers.jobs import get_redis_connection
    return get_redis_connection()


def _jsonable(value):
    return sorted(value) if isinstance(value, (set, frozenset)) else str(value)


def _cache_key(system, user, response_model, context, extra_body, max_tokens) -> str:
    provider = _settings.llm_provider
    model = _settings.nvidia_model if provider == "nvidia" else MODEL
    material = json.dumps(
        [provider, model, system, user, response_model.model_json_schema(), context, extra_body, max_tokens],
        sort_keys=True, default=_jsonable,
    )
    return "llmcache:" + hashlib.sha256(material.encode()).hexdigest()


def _cache_get(key, response_model, context):
    # Fail open, and re-validate: a stale hit (e.g. a fact id since deleted) is a miss.
    try:
        raw = _cache_client().get(key)
        return None if raw is None else response_model.model_validate_json(raw, context=context)
    except Exception as exc:
        logger.info("LLM cache read skipped: %s", type(exc).__name__)
        return None


def _cache_set(key, result) -> None:
    try:
        _cache_client().set(key, result.model_dump_json(), ex=int(_settings.llm_cache_ttl_seconds))
    except Exception as exc:
        logger.info("LLM cache write skipped: %s", type(exc).__name__)


@observe(as_type="generation", name="claude-call")
def call_llm(system: str, user: str) -> str:
    provider = _settings.llm_provider

    if provider in ("nvidia", "nvidia_smoke"):
        nvidia_model = _settings.nvidia_model if provider == "nvidia" else _settings.nvidia_smoke_model
        response, model_used = _llm_request(nvidia_model, lambda model: _get_nvidia_client().chat.completions.create(
            model=model,
            extra_body=_settings.nvidia_extra_body(),
            max_tokens=1500,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        ))
        text = response.choices[0].message.content or ""
        usage_details = (
            {
                "input": response.usage.prompt_tokens,
                "output": response.usage.completion_tokens,
            }
            if response.usage
            else None
        )
    else:
        message, model_used = _llm_request(MODEL, lambda model: _client.messages.create(
            model=model,
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user}],
        ))
        text = "".join(block.text for block in message.content if block.type == "text")
        usage_details = {
            "input": message.usage.input_tokens,
            "output": message.usage.output_tokens,
        }

    if _langfuse is not None:
        get_client().update_current_generation(
            input=user,
            output=text,
            model=model_used,
            usage_details=usage_details,
        )

    return text


@observe(as_type="generation", name="claude-call-structured")
def _call_claude_structured(
    system: str, user: str, response_model: type, context: dict | None = None,
    extra_body: dict | None = None, max_tokens: int = NVIDIA_STRUCTURED_MAX_TOKENS,
):
    """The default (real Anthropic) provider's structured path — validates
    the response against response_model, retrying (bounded — ADR-011's same
    "bounded, not an open loop" philosophy) on a schema violation instead of
    trusting an unhandled json.loads. Not used by the nvidia_smoke path (see
    tailor_application) — the free smoke model isn't asked to honor this
    contract, so it must never be credited with having validated against it.
    """
    key = _cache_key(system, user, response_model, context, extra_body, max_tokens)
    cached = _cache_get(key, response_model, context)
    if cached is not None:
        return cached
    if _settings.llm_provider == "nvidia":
        # OpenAI shape: the system prompt is a message, there is no `system=` kwarg.
        result, model_used = _llm_request(_settings.nvidia_model, lambda model: _get_nvidia_instructor_client().chat.completions.create(
            model=model,
            # Open models spend tokens before the JSON; 1500 truncated the draft live.
            max_tokens=max_tokens,
            extra_body=_settings.nvidia_extra_body() if extra_body is None else extra_body,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_model=response_model,
            max_retries=2,
            context=context,
        ))
    else:
        result, model_used = _llm_request(MODEL, lambda model: _get_instructor_client().messages.create(
            model=model,
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user}],
            response_model=response_model,
            max_retries=2,
            context=context,
        ))
    if _langfuse is not None:
        get_client().update_current_generation(input=user, output=result.model_dump_json(), model=model_used)
    _cache_set(key, result)
    return result


JD_TERMS_HEADER = "JD TERMS YOUR FACTS SUPPORT:"

# Found live on NVIDIA (WORKLOG latest+34): bullets gained "ensuring on-time
# delivery", "across microservices" — padding no fact states.
NO_PADDING_RULE = (
    "Say only what the cited fact says: do not add outcomes, purposes, benefits, "
    "qualities, scope, scale, domains, team sizes, durations or numbers it does not "
    "state — never add why it mattered unless the fact says so."
)


def _jd_terms_section(gap: dict) -> str:
    """The prompt's "use these terms" block. Built from `matched` only — the
    scorer's `missing` list is never read here, so a keyword the user's facts
    don't back has no path into the bullets (ADR-006/009). `missing` is
    returned to the user as a gap instead, see tailor_application."""
    actions = {s["keyword"]: s["action"] for s in gap["suggestions"]}
    lines = [
        f"- {m['keyword']} (fact {m['evidence_fact_id_or_index']}"
        + (f"; {actions[m['keyword']]}" if m["keyword"] in actions else "")
        + ")"
        for m in gap["matched"]
    ]
    return JD_TERMS_HEADER + "\n" + ("\n".join(lines) or "- (none)") + "\n\n"


_NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*")
# From two: "one"/"zero" are ordinary prose ("one of the roles I want most"), not claims.
_NUMBER_WORDS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split()) if i >= 2}


def _numbers(text: str) -> set[str]:
    found = {n.replace(",", "") for n in _NUMBER_RE.findall(text)}
    return found | {_NUMBER_WORDS[w] for w in re.findall(r"[a-z]+", text.lower()) if w in _NUMBER_WORDS}


def deterministic_unsupported(facts: list[dict], draft_texts: list[str]) -> list[str]:
    """Pass 2's model-free half: a tool/technology or a number the draft names
    that no fact contains is flagged, whatever the model checker says. Same
    vocabulary and matching (synonym + fuzzy) as the keyword-gap scorer, so
    "K8s" in a fact backs "Kubernetes" in the draft.

    ponytail: only names in matching/skills.py's vocabulary and digits are seen;
    an invented domain or outcome in plain words ("financial transactions") is
    left to the model checker."""
    facts_text = " ".join(
        " ".join(v) if isinstance(v, list) else str(v)
        for f in facts for k, v in f.items() if k != "id" and v
    )
    tokens = [t.lower() for t in _TOKEN_RE.findall(facts_text)]
    fact_numbers = _numbers(facts_text)
    flags = []
    for text in draft_texts:
        # Vocabulary names only: the alias map has loose entries ("product
        # manager" -> Product Strategy) that turn a job title into a false flag.
        for name in sorted(skill_occurrences(text)):
            if not _match_in_fact(name, facts_text, tokens):
                flags.append(f"{text} [not in facts: {name}]")
        for n in sorted(_numbers(text) - fact_numbers):
            flags.append(f"{text} [not in facts: {n}]")
    return flags


def split_sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text or "") if s.strip()]


def truth_check(facts: list[dict], summary: str, bullet_texts: list[str], cover_letter: str) -> list[str]:
    """Pass 2 (ADR-006: facts + draft only, never the JD)."""
    known_fact_ids = {f["id"] for f in facts if f.get("id")}
    draft = {"summary": summary, "bullets": bullet_texts, "cover_letter": cover_letter}
    check_user = (
        f"CANDIDATE FACTS KB:\n{json.dumps(facts, indent=2)}\n\n"
        f"DRAFT:\n{json.dumps(draft, indent=2)}"
    )
    try:
        audit = _call_claude_structured(STRICT_CHECK_SYSTEM, check_user, ClaimAudit)
    except InstructorRetryException as exc:
        raise RuntimeError(f"Truth-check pass could not produce a valid response: {exc}") from exc
    sentences = split_sentences(summary) + list(bullet_texts) + split_sentences(cover_letter)
    # Returned SEPARATELY, not concatenated (GAPS 6.7, owner ruling 2026-10-05).
    # Concatenating them is what made the gate un-splittable at the call site:
    # the model checker's findings blocked 29 of 30 golden rows while the
    # deterministic half flagged nothing. See split_gate_findings.
    return audit.unsupported(known_fact_ids), deterministic_unsupported(facts, sentences)


def split_gate_findings(model_findings: list[str],
                        deterministic_findings: list[str]) -> tuple[list[str], list[str]]:
    """Which pass-2 findings BLOCK an application, and which are advisory.

    Owner ruling 2026-10-05 (GAPS 6.7), on measured evidence: the model
    checker's findings are **framing, not fabrication**, and must not block.

    What forced it: on the 30-row golden set the bullets were 107/107 correctly
    grounded and pass 2 still flagged 29 of 30 rows — every flag from the model
    checker, none from `deterministic_unsupported`. `main.py` drops any
    application with `flagged_unsupported_claims` from the ready queue, so ~97%
    of applications could never be sent. The checker was obeying its own
    instructions: `STRICT_CHECK_SYSTEM` tells it to flag "scope or scale" and
    "titles, durations and praise adjectives", so it flagged "Senior Backend
    Engineer with expertise in…" and "Proven ability to…".

    hard gate -> deterministic only: a tool/technology name or a number the
                 draft states that no fact contains. Precise, and it had zero
                 false positives across the measured rows.
    advisory  -> the model checker's audit. Surfaced to a human, never blocking.

    **The accepted cost, stated so it is not forgotten:**
    `deterministic_unsupported` only sees names in `matching/skills.py`'s
    vocabulary plus digits — its own docstring says an invented domain or
    outcome in plain words is "left to the model checker". Making that advisory
    means such a claim can reach an employer unless a human reads the advisory
    list. That is the trade the owner took, not an oversight: ADR-006's
    no-fabrication rail now binds on concrete claims and advises on prose.
    """
    hard = list(deterministic_findings)
    seen = set(hard)
    advisory = [f for f in model_findings if f not in seen]
    return hard, advisory


def tailor_application(job: dict, facts: list[dict]) -> dict:
    facts_json = json.dumps(facts, indent=2)
    known_fact_ids = {f["id"] for f in facts if f.get("id")}
    description = job.get("description") or ""
    gap = compute_keyword_gap(
        description, [SimpleNamespace(**f) for f in facts], job.get("skills"), job.get("title")
    )

    tailor_system = (
        "You are a resume-tailoring assistant. You will be given a candidate's "
        "resume-facts knowledge base (KB), where each fact has a unique 'id' field, "
        "and a job description. Using ONLY facts present in the KB, produce: a "
        "2-sentence professional summary, 4-6 tailored bullet points ranked by "
        "relevance to this job, and a short (150-200 word) cover letter. Every bullet "
        "must cite the id(s) of the fact(s) it is directly backed by. Never invent "
        "achievements, metrics, or experience not present in the KB. " + NO_PADDING_RULE + " Reorder and "
        "rewrite for relevance and ATS keyword match only. The '"
        + JD_TERMS_HEADER
        + "' list names the job's own keywords that a KB fact already backs, with "
        "that fact's id (reword = the fact says it in other words; surface = it is "
        "buried): use each term verbatim, only in a bullet citing that fact. Do not "
        "add any other skill, tool, or keyword from the job description."
    )
    tailor_user = (
        f"CANDIDATE FACTS KB:\n{facts_json}\n\n"
        + _jd_terms_section(gap)
        + f"JOB TITLE: {job.get('title')}\n"
        f"COMPANY: {job.get('company')}\n"
        f"JOB DESCRIPTION:\n{description[:4000]}"
    )

    if _settings.llm_provider == "nvidia_smoke" or not known_fact_ids:
        # Dev-only smoke path (and the legacy case of facts with no "id" at
        # all): keeps the original unvalidated raw-JSON contract rather than
        # claiming a source_fact_ids link the model was never constrained to
        # produce. bullets still come back as {text, source_fact_ids: []} —
        # a real, honest shape, just never carrying an unverified id.
        smoke_system = tailor_system + (
            ' Respond ONLY with valid JSON: {"summary": "...", '
            '"bullets": ["...", "..."], "cover_letter": "..."}'
        )
        raw = call_llm(smoke_system, tailor_user)
        cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(cleaned)
        summary = parsed.get("summary", "")
        bullets = [{"text": b, "source_fact_ids": []} for b in parsed.get("bullets", [])]
        cover_letter = parsed.get("cover_letter", "")
    else:
        try:
            draft = _call_claude_structured(
                tailor_system, tailor_user, TailoredDraft,
                context={"known_fact_ids": known_fact_ids},
            )
        except InstructorRetryException as exc:
            raise RuntimeError(
                f"Tailoring pass 1 could not produce a valid, fact-grounded draft "
                f"after retrying: {exc}"
            ) from exc
        summary = draft.summary
        bullets = [{"text": b.text, "source_fact_ids": b.source_fact_ids} for b in draft.bullets]
        cover_letter = draft.cover_letter

    # Pass 2: truth-check
    if _settings.llm_provider == "nvidia_smoke" or not known_fact_ids:
        check_user = (
            f"CANDIDATE FACTS KB:\n{facts_json}\n\n"
            f"DRAFT:\n{json.dumps({'summary': summary, 'bullets': [b['text'] for b in bullets], 'cover_letter': cover_letter}, indent=2)}"
        )
        smoke_check_system = CHECK_SYSTEM + (
            ' Respond ONLY with valid JSON: {"unsupported_claims": ["...", "..."]} '
            "(empty array if none)."
        )
        raw_check = call_llm(smoke_check_system, check_user)
        cleaned_check = raw_check.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        # Smoke path: one unstructured model call, no deterministic half at all,
        # so by the same ruling nothing here is a hard gate.
        advisory_claims = json.loads(cleaned_check).get("unsupported_claims", [])
        unsupported_claims = []
    else:
        model_findings, det_findings = truth_check(
            facts, summary, [b["text"] for b in bullets], cover_letter
        )
        unsupported_claims, advisory_claims = split_gate_findings(model_findings, det_findings)

    return {
        "summary": summary,
        "bullets": bullets,
        "cover_letter": cover_letter,
        # Hard gate: deterministic findings only (GAPS 6.7). main.py keys the
        # ready/work queue off this, so anything in here stops the send.
        "flagged_unsupported_claims": unsupported_claims,
        # Advisory: the model checker's claim audit. Shown to a human, never
        # blocking — see split_gate_findings for the measurement behind this.
        "advisory_claims": advisory_claims,
        # Advisory only: `missing` is what the job wants and the facts don't
        # show — for the user to see, never written into the resume.
        "keyword_gap": {
            "coverage_before": gap["coverage"],
            "coverage_after": compute_keyword_gap(
                description, [b["text"] for b in bullets], job.get("skills"), job.get("title")
            )["coverage"],
            "missing": [m["keyword"] for m in gap["missing"]],
        },
    }
