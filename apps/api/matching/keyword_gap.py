"""JD <-> resume keyword gap (ATS keyword targeting).

Why this exists. `documents/ats_safety.py` makes the generated DOCX
*mechanically* parseable by an ATS. That is only half of "gets more interview
calls": the other half is whether the resume actually surfaces the vocabulary
the job description screens on. This module answers, per job, three questions:
which JD keywords the user's real facts already evidence, which ones they
genuinely do not have, and which ones are technically present but buried where
no keyword scan will find them.

The rail (ADR-009, and the entire reason the Facts KB exists). A keyword in
`missing` means "the user does not have this." It NEVER produces a suggestion.
Suggestions are built exclusively by walking `matched` — every suggestion
therefore points at a real `ResumeFact` the user owns, and the only actions are
`surface` (move an existing fact's real content where it can be seen) and
`reword` (say the same true thing in the JD's vocabulary). There is no code
path from `missing` to `suggestions`; the final filter in
`_build_suggestions` is a belt-and-braces assertion of that, not the mechanism.
Inventing a credential is how an applicant gets blacklisted, and it is the line
between this product and a fraud generator.

Deterministic and free: pure regex + rapidfuzz, no model call, so it can run on
every match without a budget or a latency conversation. Job descriptions are
untrusted attacker-controllable text (ADR-006) — nothing here feeds them to a
model, which is also why this file is safe to run pre-approval.
"""
import html
import re

from rapidfuzz import fuzz, process

from matching.skills import AMBIGUOUS_TERMS, skill_occurrences, skill_pattern

# ponytail: a hand-written map, not a thesaurus. It only needs to carry the
# abbreviation-vs-expansion pairs where character-level fuzzy matching is
# hopeless because the two forms barely share letters ("K8s"/"Kubernetes"
# scores 25). Everything spelling-shaped ("NodeJS"/"Node.js", "Postgres"/
# "PostgreSQL") is rapidfuzz's job, below. Ceiling: it covers what we have
# seen, nothing more, and it is not per-persona. Upgrade path when this list
# starts needing dozens of entries is a curated alias column alongside the
# skills vocabulary (one source of truth, still no ML), not a synonym model.
SYNONYMS: dict[str, tuple[str, ...]] = {
    "Kubernetes": ("K8s", "kube"),
    "JavaScript": ("JS", "ECMAScript"),
    "TypeScript": ("TS",),
    "Machine Learning": ("ML",),
    "Product Strategy": ("PM", "product manager", "product management"),
    "PostgreSQL": ("Postgres", "psql"),
    "CI/CD": ("continuous integration", "continuous delivery", "continuous deployment"),
    "Google Analytics": ("GA4",),
    "A/B Testing": ("split testing", "experimentation"),
}

# Headings that mark the part of a JD that is actually screened on, and the
# headings that end it. Matched against a line, not the whole document.
_REQUIREMENT_HEADINGS = re.compile(
    r"(requirements?|qualifications?|must[- ]haves?|what (you'?ll need|we'?re looking for)|"
    r"you (will )?(have|bring)|skills? (and|&) experience|minimum|required)",
    re.I,
)
_END_HEADINGS = re.compile(
    r"(nice[- ]to[- ]haves?|bonus|preferred|benefits?|perks?|about (us|the company|our)|"
    r"compensation|salary|equal opportunity|how to apply)",
    re.I,
)

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)
_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9+#./_-]*")

FUZZY_CUTOFF = 90          # ratio, 0-100. 88 lets "Rust"/"trust" through; 90 does not.
FUZZY_MIN_LENGTH = 4       # below this, character noise dominates ("Go"/"got")
_IMPORTANCE_WEIGHT = {"high": 3, "medium": 2, "low": 1}


def strip_html(raw: str | None) -> str:
    """Feeds (remotive, greenhouse, lever, ashby) deliver descriptions as HTML.

    stdlib only: drop script/style bodies, drop tags, unescape entities. No
    parser dependency — we are extracting keywords, not reconstructing a DOM,
    and a malformed feed payload must degrade to "fewer keywords", never raise.
    """
    if not raw:
        return ""
    text = _SCRIPT_RE.sub(" ", raw)
    text = _TAG_RE.sub("\n", text)
    text = html.unescape(text)
    return re.sub(r"[ \t]+", " ", text)


def _requirements_span(text: str) -> str:
    """The slice of the JD between the first requirements-ish heading and the
    first heading that ends it. Empty string when the JD has no such structure.
    """
    start = _REQUIREMENT_HEADINGS.search(text)
    if not start:
        return ""
    tail = text[start.end():]
    end = _END_HEADINGS.search(tail)
    return tail[: end.start()] if end else tail


def _fact_fields(fact) -> tuple[str, str]:
    """(prose, metadata) for one fact.

    Split deliberately: prose is what a human and an ATS both read off the
    rendered bullet. Metadata (tags, and the metric/proof fields) is internal —
    a keyword that lives only there is present in our database and invisible on
    the document, which is exactly the `weak` case worth a suggestion.
    """
    if isinstance(fact, str):
        return fact, ""
    prose = " ".join(filter(None, [getattr(fact, "achievement", None) or ""]))
    meta = " ".join(
        filter(None, [
            getattr(fact, "proof", None) or "",
            getattr(fact, "metric", None) or "",
            " ".join(getattr(fact, "tags", None) or []),
        ])
    )
    return prose, meta


def _fact_ref(fact, index: int):
    """The fact's real id when it has one, else its position in the input list."""
    return getattr(fact, "id", None) or index


def _alias_occurrences(text: str) -> dict[str, int]:
    """Canonical-name counts for aliases appearing in `text`.

    The synonym map has to run on the JD side too, not only against the facts:
    a JD that says "K8s" is asking for Kubernetes, and if we only matched the
    vocabulary literally, Kubernetes would never even become a keyword to score.
    """
    counts: dict[str, int] = {}
    if not text:
        return counts
    for canonical, aliases in SYNONYMS.items():
        n = sum(len(skill_pattern(alias).findall(text)) for alias in aliases)
        if n:
            counts[canonical] = n
    return counts


def _jd_keywords(jd_text: str, job_skills: list[str] | None, title: str) -> dict[str, int]:
    counts = skill_occurrences(jd_text)
    for source in (_alias_occurrences(jd_text), skill_occurrences(title), _alias_occurrences(title)):
        for name, n in source.items():
            counts[name] = counts.get(name, 0) + n
    for skill in job_skills or []:
        counts.setdefault(skill, 1)
    return counts


def _importance(keyword: str, count: int, in_title: bool, in_requirements: bool, in_job_skills: bool) -> str:
    """ponytail: additive points, not a learned weighting. Title and the
    requirements section are the two signals that genuinely separate a
    screened-on requirement from boilerplate; repetition and the job's own
    extracted skill list are weaker corroboration. Ceiling: it cannot tell
    "5+ years of Kubernetes" from "we run Kubernetes" — both read as high.
    Upgrade path is parsing the requirement line for a hard/soft qualifier,
    still deterministic, not an LLM pass on a path that must stay free.
    """
    points = (2 if in_title else 0) + (2 if in_requirements else 0)
    points += 1 if count >= 2 else 0
    points += 1 if in_job_skills else 0
    if points >= 2:
        return "high"
    return "medium" if points == 1 else "low"


def _match_in_fact(keyword: str, text: str, tokens: list[str], jd_alias_only: bool = False) -> str | None:
    """"exact" | "synonym" | "fuzzy" | None, in decreasing confidence order."""
    if not text:
        return None
    if skill_pattern(keyword).search(text):
        # `jd_alias_only`: the JD never wrote the canonical term, it wrote an
        # alias ("K8s"). The fact and the JD therefore agree on the skill but
        # not on the word — that is a synonym bridge from the user's point of
        # view, and the honest label for the report, even though the fact side
        # matched literally.
        return "synonym" if jd_alias_only else "exact"
    for alias in SYNONYMS.get(keyword, ()):
        if skill_pattern(alias).search(text):
            return "synonym"
    # Fuzzy only for single-word keywords long enough that character overlap
    # means something. Multi-word phrases ("Machine Learning") would need token
    # -set scoring against every n-gram of the fact — cost and false-positive
    # risk for a case the synonym map already covers where it matters.
    # Never fuzzy-match a term that is also an ordinary English word: the fuzzy
    # scan lowercases both sides, which throws away exactly the casing signal
    # skills.AMBIGUOUS_TERMS relies on, so "rest of the team" would score 100
    # against "REST" and be reported as an API skill the user does not have.
    if (
        keyword not in AMBIGUOUS_TERMS
        and len(keyword) >= FUZZY_MIN_LENGTH
        and " " not in keyword
        and tokens
    ):
        hit = process.extractOne(
            keyword.lower(), tokens, scorer=fuzz.ratio, score_cutoff=FUZZY_CUTOFF
        )
        if hit:
            return "fuzzy"
    return None


def _build_suggestions(matched: list[dict], weak: list[dict], missing_keywords: set[str]) -> list[dict]:
    """Built from `matched`/`weak` only — there is no `missing` input to read
    from, by construction. The trailing filter is a second lock on the same
    door: if a future edit ever wires a missing keyword in here, it is dropped
    rather than shipped to a user's resume.
    """
    weak_by_keyword = {w["keyword"]: w for w in weak}
    suggestions = []

    for entry in matched:
        keyword = entry["keyword"]
        weak_entry = weak_by_keyword.get(keyword)
        if weak_entry and weak_entry["reason"] == "metadata_only":
            suggestions.append({
                "action": "surface",
                "fact_id_or_index": entry["evidence_fact_id_or_index"],
                "keyword": keyword,
                "rationale": (
                    f"'{keyword}' is recorded on this fact but only in its tags/metric, so it never "
                    f"reaches the bullet text an ATS reads. Say it in the achievement itself."
                ),
            })
        elif entry["match_type"] in ("fuzzy", "synonym"):
            suggestions.append({
                "action": "reword",
                "fact_id_or_index": entry["evidence_fact_id_or_index"],
                "keyword": keyword,
                "rationale": (
                    f"This fact already describes '{keyword}', but not in the job's wording. "
                    f"Reword it to use '{keyword}' verbatim — same claim, the screener's vocabulary."
                ),
            })
        elif weak_entry and weak_entry["reason"] == "single_mention":
            suggestions.append({
                "action": "surface",
                "fact_id_or_index": entry["evidence_fact_id_or_index"],
                "keyword": keyword,
                "rationale": (
                    f"'{keyword}' appears once across your facts while the job leans on it. "
                    f"Order this fact earlier so it is the first thing read."
                ),
            })

    return [s for s in suggestions if s["keyword"] not in missing_keywords]


def compute_keyword_gap(
    job_description: str,
    facts: list,
    job_skills: list[str] | None = None,
    job_title: str | None = None,
) -> dict:
    """Keyword coverage of one JD against one user's real facts.

    `facts` accepts `ResumeFact` rows or plain strings (the string form is for
    callers that only have text, e.g. tests and the eval harness). Evidence is
    reported as the fact's id when it has one, otherwise its list index.
    """
    jd_text = strip_html(job_description)
    title = strip_html(job_title)
    requirements = _requirements_span(jd_text)

    keyword_counts = _jd_keywords(jd_text, job_skills, title)
    literal_jd_keywords = set(skill_occurrences(jd_text)) | set(skill_occurrences(title)) | {
        s for s in (job_skills or [])
    }
    if not keyword_counts:
        return {"coverage": 0.0, "matched": [], "missing": [], "weak": [], "suggestions": []}

    job_skills_set = {s.lower() for s in (job_skills or [])}
    title_keywords = set(skill_occurrences(title)) | set(_alias_occurrences(title))
    requirement_keywords = set(skill_occurrences(requirements)) | set(_alias_occurrences(requirements))

    # Pre-tokenize each fact once — the fuzzy scan is O(keywords * tokens).
    prepared = []
    for index, fact in enumerate(facts or []):
        prose, meta = _fact_fields(fact)
        prepared.append({
            "ref": _fact_ref(fact, index),
            "prose": prose,
            "meta": meta,
            "prose_tokens": [t.lower() for t in _TOKEN_RE.findall(prose)],
            "meta_tokens": [t.lower() for t in _TOKEN_RE.findall(meta)],
        })

    matched: list[dict] = []
    missing: list[dict] = []
    weak: list[dict] = []

    for keyword in sorted(keyword_counts):
        importance = _importance(
            keyword,
            keyword_counts[keyword],
            keyword in title_keywords,
            keyword in requirement_keywords,
            keyword.lower() in job_skills_set,
        )

        prose_hits, meta_hits = [], []
        for entry in prepared:
            alias_only = keyword not in literal_jd_keywords
            hit = _match_in_fact(keyword, entry["prose"], entry["prose_tokens"], alias_only)
            if hit:
                prose_hits.append((entry["ref"], hit))
                continue
            hit = _match_in_fact(keyword, entry["meta"], entry["meta_tokens"], alias_only)
            if hit:
                meta_hits.append((entry["ref"], hit))

        if not prose_hits and not meta_hits:
            missing.append({"keyword": keyword, "importance": importance})
            continue

        ref, match_type = (prose_hits or meta_hits)[0]
        matched.append({
            "keyword": keyword,
            "evidence_fact_id_or_index": ref,
            "match_type": match_type,
            "importance": importance,
        })

        # Buried, two ways: nowhere in any bullet's prose, or in exactly one.
        if not prose_hits:
            weak.append({"keyword": keyword, "evidence_fact_id_or_index": ref, "reason": "metadata_only"})
        elif len(prose_hits) == 1:
            weak.append({"keyword": keyword, "evidence_fact_id_or_index": ref, "reason": "single_mention"})

    # Importance-weighted, so failing one "high" keyword costs more than failing
    # one mentioned once in the perks section.
    total_weight = sum(_IMPORTANCE_WEIGHT[e["importance"]] for e in matched + missing)
    matched_weight = sum(_IMPORTANCE_WEIGHT[m["importance"]] for m in matched)
    coverage = round(matched_weight / total_weight, 4) if total_weight else 0.0

    return {
        "coverage": coverage,
        "matched": matched,
        "missing": missing,
        "weak": weak,
        "suggestions": _build_suggestions(matched, weak, {m["keyword"] for m in missing}),
    }
