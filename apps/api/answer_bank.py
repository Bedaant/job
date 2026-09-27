"""The answer bank (ADR-015): answer once, reuse forever.

An auto-apply run stops when a form asks something the profile cannot answer
("Why do you want to work here?", "Notice period?", "Years of experience with
X?"). The user is notified, types the answer, and we submit — and until now
that answer was thrown away, so the next employer asking the same question
interrupted them again, forever. This module makes the interruption shrink:
the answer is stored verbatim and served to matching questions afterwards.

Three rails, in the order they matter:

1. **Demographic/EEO questions are never served.** Race, ethnicity, gender,
   veteran status, disability, sexual orientation. Not from the bank, not from
   a model, not ever. `save_answer` refuses to store one and `find_answer`
   refuses to return one, so a row that arrived by any other route (a
   hand-written INSERT, a restored backup, a future code path) still cannot
   reach a form. This is the one outcome that is unacceptable rather than
   merely wrong, so it is checked twice on purpose.

   `DEMOGRAPHIC_LABEL_KEYWORDS` lives here rather than in
   formfill/map_fields.py because map_fields imports tailoring.engine.call_llm
   and this module must not (rail 2) — so the dependency has to point this way.

2. **User-written text only.** Nothing in this module's import graph can reach
   `call_llm`, and `save_answer` is the single function that constructs a row.
   `find_answer` can therefore only ever return something the user typed,
   which is what makes ADR-006/ADR-009 hold for these answers for free: there
   is no generated claim to truth-check.

3. **A wrong answer is worse than asking again.** See `find_answer`.
"""
import re
from datetime import datetime

from fastapi import HTTPException, status
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

import models

# EEO/demographic. Never fillable by anything, under any circumstances.
# SHARED SPEC with apps/extension (fieldDecision.mjs implements the identical
# rule client-side) — change both or neither. All text is normalized first
# (lowercase, punctuation -> space, whitespace collapsed); question keywords
# match as whole words ("Sussex" is not "sex", "embrace" is not "race").
# ponytail: plus an optional plural "s" ("Pronouns", "Races") — server-side only
# unless the extension mirrors it; it can only make the server stricter.
# Live miss that forced the rewrite (docs/LIVE-FORM-TEST.md #2): "Are you
# Hispanic/Latino?" passed the old list and was then served from the bank.
DEMOGRAPHIC_LABEL_KEYWORDS = [
    "race", "ethnicity", "ethnic", "hispanic", "latino", "latina", "latinx",
    "gender", "sexual orientation", "transgender", "pronoun",
    "veteran", "disability", "disabled",
]
_DEMOGRAPHIC_QUESTION = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in [*DEMOGRAPHIC_LABEL_KEYWORDS, "sex"]) + r")s?\b"
)

# Option-only EEO groups (Ashby sends "Man"/"Woman" with no question text). An
# option carries a term only if it EQUALS it or STARTS WITH it plus a space
# ("White (Not Hispanic or Latino)"), and terms count DISTINCT — so a
# university list's "Asian Institute of Technology" and "Texas Woman's
# University" stay one term at most.
DEMOGRAPHIC_OPTION_TERMS = (
    "man", "woman", "male", "female", "non binary", "white", "black or african american",
    "asian", "hispanic or latino", "native hawaiian", "american indian", "two or more races",
    "protected veteran", "i am a veteran", "not a veteran", "i have a disability", "no disability",
)
# Whole words, anywhere in an option (normalized, so "don't" is "don t").
DECLINE_PHRASES = ("decline to self identify", "i don t wish to answer", "prefer not to say")
_NOT_WORD_CHARS = re.compile(r"[^a-z0-9\s]+")


def _normalize_eeo(text: str | None) -> str:
    return _WHITESPACE.sub(" ", _NOT_WORD_CHARS.sub(" ", (text or "").lower())).strip()


# Two gates, both measured against the real pairs below rather than picked
# because they felt right. NEITHER IS SUFFICIENT ALONE, which is the finding
# that shaped this: every single whole-string scorer rapidfuzz offers puts at
# least one semantically-opposite pair above any threshold that still admits a
# real paraphrase. token_set_ratio scores "years of experience with python" vs
# "...with java" at 90.6; fuzz.ratio scores "...with c++" vs "...with c#" at
# 94.5; token_set_ratio scores "do you require visa sponsorship" vs "do you NOT
# require visa sponsorship" at 100.
#
# Gate 1 — token_sort_ratio over the CONTENT words only (stopwords stripped),
# not the whole question. Measured on the whole question the signal drowns in
# shared glue ("why do you...", "years of experience with..."); on content words
# alone the same pairs separate cleanly:
#
#   want work            / leave last job              26.1   rejected
#   willing relocate     / relocate                    66.7   rejected
#   want work            / want work company           69.2   rejected
#   years experience python / years experience java    77.3   rejected
#   years experience c++ / years experience c#         92.3   -> gate 2
#   require visa sponsorship / not require visa sponsorship 92.3 -> gate 2
#   notice period        / notice periods              96.3   accepted
#   notice period        / notice period              100.0   accepted
SIMILARITY_THRESHOLD = 90

# Gate 2 — every content word on each side must have a near-identical partner on
# the other. This is what catches the two pairs gate 1 lets through: "not"
# (negation, no partner at all) and "c++"/"c#" (40). 90 admits plurals
# ("period"/"periods" = 92.3) and rejects the near-miss technology names that
# defeat every whole-string scorer ("python"/"pytorch" = 61.5,
# "python"/"java" = 0).
TOKEN_THRESHOLD = 90

# Question glue, removed before gate 2 so that phrasing differences don't count
# as distinguishing content. Deliberately excludes "not"/"no"/"never": negation
# flips the answer, so it must stay a content word — "do you require visa
# sponsorship" and "do you NOT require visa sponsorship" score 100 on
# token_set_ratio, and only gate 2 keeps them apart.
_STOPWORDS = frozenset(
    """a about an and any are as at be been briefly by can could describe did do does
    for from had has have here how if in is it me much of on or our please tell that
    the there this to us was we what when where which who why will with would you
    your yours""".split()
)

# Punctuation is collapsed to whitespace EXCEPT `+` and `#`: they are the only
# thing distinguishing "c++" from "c#", and collapsing those into a shared "c"
# would serve a C# answer to a C++ question. Everything else (?, ., commas,
# parens, quotes) is noise a form varies freely.
_NOT_QUESTION_CHARS = re.compile(r"[^a-z0-9+#\s]+")
_WHITESPACE = re.compile(r"\s+")


def normalize_question(text: str | None) -> str:
    """The matching key: lowercased, punctuation collapsed, whitespace squeezed."""
    if not text:
        return ""
    return _WHITESPACE.sub(" ", _NOT_QUESTION_CHARS.sub(" ", text.lower())).strip()


def is_demographic_field(label_text: str | None, options: list[str] | None = None) -> bool:
    """Rail 1, the one place the EEO rule lives. True means unfillable, full
    stop — not "flag for review". Demographic if (a) the label/question names
    one, or (b) the options are an EEO answer set: a decline phrase alongside
    any demographic option, or at least two demographic options.
    """
    if _DEMOGRAPHIC_QUESTION.search(_normalize_eeo(label_text)):
        return True

    normalized = [_normalize_eeo(o) for o in options or []]
    terms = {t for o in normalized for t in DEMOGRAPHIC_OPTION_TERMS if o == t or o.startswith(t + " ")}
    declines = any(f" {p} " in f" {o} " for o in normalized for p in DECLINE_PHRASES)
    return len(terms) >= 2 or (declines and bool(terms))


# Legal consent is the user's own act — the same "never automated" class as the
# demographic rail. Found live: the model accepted Greenhouse's "Agreement to
# Arbitrate" (its only option: "I understand and agree to the terms…") and the
# extension clicked it. Also never stored: agreeing once is not agreeing for
# every later employer. Matched on the question AND its options.
_CONSENT = re.compile(
    r"\barbitrat\w*|\bterms (?:and|&) conditions\b|\bterms of (?:service|use)\b|\bprivacy (?:policy|notice)\b"
    r"|\bi (?:understand and )?agree\b|\bi accept\b|\bconsent\w*|\bcertif(?:y|ies|ication)\b|\battest\w*"
    r"|\backnowledg\w*|\b(?:electronic |e )?signature\b"
)


def is_consent_field(label_text: str | None, options: list[str] | None = None) -> bool:
    texts = [label_text or "", *(options or [])]
    return any(_CONSENT.search(_normalize_eeo(t)) for t in texts)


def is_demographic_label(label_text: str | None) -> bool:
    """The label half of is_demographic_field — for callers holding only a question."""
    return is_demographic_field(label_text)


def _content_tokens(normalized: str) -> list[str]:
    return [token for token in normalized.split() if token not in _STOPWORDS]


def _tokens_all_covered(needles: list[str], haystack: list[str]) -> bool:
    return all(
        any(fuzz.ratio(needle, other) >= TOKEN_THRESHOLD for other in haystack)
        for needle in needles
    )


def _is_same_question(asked: str, stored: str) -> bool:
    """Gate 1 then gate 2, bidirectionally.

    Bidirectional coverage is the deliberately strict choice: it means a
    paraphrase that *adds* a content word ("why do you want to work here" ->
    "why do you want to work at our company", token_set_ratio 90.2) will NOT
    match and the user gets asked again. That is the right trade — this is the
    module that decides what text goes into a real job application, and a
    plausible-but-wrong answer is worse than one more interruption.

    # ponytail: lexical ceiling. Genuine paraphrases with different vocabulary
    # ("what draws you to this role") can't be recognised at all. The upgrade
    # path is embeddings — Profile.fact_centroid already proves voyage-3-lite
    # is wired up — but that costs a network call per field on a path that is
    # currently free and instant, so it waits for evidence that the misses
    # actually annoy a real user.
    """
    asked_tokens = _content_tokens(asked)
    stored_tokens = _content_tokens(stored)
    if not asked_tokens or not stored_tokens:
        # No content words means no signal to match on; an all-glue question
        # ("Why do you?") would otherwise fuzzy-match every stored entry.
        # Exact match already handled that case before we got here.
        return False

    # Gate 1: content-word similarity, order-insensitive.
    if fuzz.token_sort_ratio(" ".join(asked_tokens), " ".join(stored_tokens)) < SIMILARITY_THRESHOLD:
        return False

    # Gate 2: no unpartnered content word on either side.
    return _tokens_all_covered(asked_tokens, stored_tokens) and _tokens_all_covered(
        stored_tokens, asked_tokens
    )


def find_answer(db: Session, profile_id: str, question: str) -> models.AnswerBank | None:
    """Exact normalized match first, then the two-gate fuzzy match. Read-only —
    it never increments the usage counters, because a lookup is not a use.
    Returns None for a demographic question regardless of what is stored.
    """
    if is_demographic_field(question) or is_consent_field(question):
        return None

    normalized = normalize_question(question)
    if not normalized:
        return None

    # ponytail: linear scan of one profile's bank per lookup. A bank is tens of
    # rows (one per distinct question a human has been asked), so this is
    # cheaper than the round trips a smarter plan would need. If it ever grows
    # into the thousands, the ix_answer_bank_question_normalized index plus a
    # trigram/prefix prefilter is the upgrade path — not an in-process cache.
    rows = db.query(models.AnswerBank).filter(models.AnswerBank.profile_id == profile_id).all()
    # Also the cleanup for rows saved before the rule grew (the live
    # "Are you Hispanic/Latino?" row): they stay in the table, never served.
    rows = [row for row in rows
            if not is_demographic_field(row.question_text) and not is_consent_field(row.question_text)]

    for row in rows:
        if row.question_normalized == normalized:
            return row

    best, best_score = None, 0.0
    for row in rows:
        if _is_same_question(normalized, row.question_normalized):
            score = fuzz.token_sort_ratio(normalized, row.question_normalized)
            if score > best_score:
                best, best_score = row, score
    return best


def save_answer(db: Session, profile_id: str, question: str, answer: str) -> models.AnswerBank:
    """The only write path into the bank — upsert on (profile_id,
    question_normalized), so re-answering updates and never duplicates.

    Refuses demographic questions with a 400 rather than storing-and-ignoring:
    a row that exists but can never be served is a trap for the next reader.
    """
    if is_demographic_field(question):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Demographic/EEO questions are never stored or auto-filled.",
        )
    if is_consent_field(question):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Legal agreements and consents are never stored or auto-filled — each employer's is yours to accept.",
        )

    normalized = normalize_question(question)
    if not normalized:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "question_text is empty after normalization")

    row = (
        db.query(models.AnswerBank)
        .filter(
            models.AnswerBank.profile_id == profile_id,
            models.AnswerBank.question_normalized == normalized,
        )
        .first()
    )
    if row is None:
        row = models.AnswerBank(
            profile_id=profile_id,
            question_text=question,
            question_normalized=normalized,
            answer_text=answer,
        )
        db.add(row)
    else:
        # Refresh the verbatim text too: it should read as the form most
        # recently asked it, which is the phrasing the user was looking at.
        row.question_text = question
        row.answer_text = answer

    db.commit()
    db.refresh(row)
    return row


def serve_answer(db: Session, profile_id: str, question: str) -> str | None:
    """find_answer plus the usage counters. This is what the form-fill path
    calls: `times_used`/`last_used_at` are how the product can later show that
    the interruptions really are shrinking.
    """
    row = find_answer(db, profile_id, question)
    if row is None:
        return None

    row.times_used = (row.times_used or 0) + 1
    row.last_used_at = datetime.utcnow()
    db.commit()
    return row.answer_text
