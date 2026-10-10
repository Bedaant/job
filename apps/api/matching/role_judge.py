"""The LLM decides whether a job title is the role a campaign asked for; word rules only gather
candidates. Verdicts are stored per (role, title) in `title_verdicts`, so each pair is asked once.

Measured 2026-10-10 on 120 labelled real titles: LLM yes/no F1 0.96 (precision 1.00), JobBERT
0.88, word rules 0.85, Voyage title embeddings 0.74.
"""
import logging
from types import SimpleNamespace

from typing import Literal

from pydantic import BaseModel
from sqlalchemy import func, or_

import models
from campaigns import _in_bounds, _role_variants, _whole_word, role_key
from database import session_scope

logger = logging.getLogger(__name__)

BATCH_SIZE = 25
CANDIDATES_PER_ROLE = 400

SYSTEM = (
    "You screen job titles for a job seeker. For the target role, decide for EACH numbered title "
    "whether someone searching for that role would want to apply. True when it is the same job "
    "function at a comparable level, including specialisations and common variants: for "
    "\"Product Manager\", Technical Product Manager, Senior/Lead/Principal Product Manager and "
    "Product Owner are true. False when the function differs (designer vs brand head, analyst vs "
    "scientist, program or project manager vs product manager) or the level is clearly different. "
    "Answer with a verdict per title: \"match\" = the same role as above; \"similar\" = not the "
    "role, but an adjacent one the person might also consider (a neighbouring function or level, e.g. "
    "Head of Marketing or Brand Manager for Brand Head); \"no\" = unrelated. "
    "Answer every index exactly once."
)


class _Verdict(BaseModel):
    index: int
    verdict: Literal["match", "similar", "no"]


class _Verdicts(BaseModel):
    verdicts: list[_Verdict]


def _ask(role: str, titles: list[str]) -> dict[str, str]:
    """One LLM call for one batch. Titles the model skipped are simply absent."""
    from tailoring.engine import _call_claude_structured

    numbered = "\n".join(f"{i}. {t}" for i, t in enumerate(titles))
    result = _call_claude_structured(SYSTEM, f"Target role: {role}\n\nTitles:\n{numbered}", _Verdicts)
    return {titles[v.index]: v.verdict for v in result.verdicts if 0 <= v.index < len(titles)}


def _any_role_word(role: str):
    words = {w for variant in _role_variants(role) for w in variant}
    return or_(*[_whole_word(w) for w in words]) if words else None


def candidate_titles(db, campaign, role: str, limit: int = CANDIDATES_PER_ROLE) -> list[str]:
    """Distinct live titles inside the campaign's other bounds that share any word with the role:
    a wide net, because the LLM, not the words, decides."""
    loose = _any_role_word(role)
    if loose is None:
        return []
    bounds = SimpleNamespace(**{k: getattr(campaign, k) for k in (
        "remote_only", "sources", "locations", "include_older_postings")}, roles=None)
    rows = (_in_bounds(db.query(models.Job.title), bounds).filter(loose)
            .group_by(models.Job.title).order_by(func.max(models.Job.fetched_at).desc())
            .limit(limit).all())
    return [t for (t,) in rows if t and t.strip()]


def judge_campaign_titles(campaign_id: str, limit: int = CANDIDATES_PER_ROLE, scope=None) -> dict:
    """Ask the LLM about every unjudged candidate title for each of the campaign's roles, then
    store the answers. No transaction is open during an LLM call; a failure leaves those titles
    unjudged, so the word rules keep standing in for them."""
    scope = scope or session_scope
    with scope() as db:
        campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
        if campaign is None:
            return {"judged": 0}
        todo: dict[str, list[str]] = {}
        for role in dict.fromkeys(r.strip() for r in campaign.roles or [] if r and r.strip()):
            titles = candidate_titles(db, campaign, role, limit)
            known = {k for (k,) in db.query(models.TitleVerdict.title_key).filter(
                models.TitleVerdict.role_key == role_key(role),
                models.TitleVerdict.title_key.in_([role_key(t) for t in titles]))} if titles else set()
            seen, fresh = set(known), []
            for t in titles:
                if role_key(t) not in seen:
                    seen.add(role_key(t))
                    fresh.append(t)
            if fresh:
                todo[role] = fresh

    answers: list[tuple[str, str, str]] = []
    for role, titles in todo.items():
        for start in range(0, len(titles), BATCH_SIZE):
            batch = titles[start:start + BATCH_SIZE]
            try:
                verdicts = _ask(role, batch)
            except Exception as exc:
                logger.warning("role judge failed for %r (%s); word rules stand in", role, type(exc).__name__)
                break
            answers += [(role, title, verdict) for title, verdict in verdicts.items()
                        if verdict in ("match", "similar", "no")]

    if answers:
        with scope() as db:
            _save(db, answers)
    return {"judged": len(answers)}


def _save(db, answers: list[tuple[str, str, str]]) -> None:
    """One read and one bulk insert, not a round trip per row (266 ms each to Neon from here).
    A pair another worker stored meanwhile is skipped, not overwritten."""
    pairs = {(role_key(r), role_key(t)): m for r, t, m in answers}
    existing = set(db.query(models.TitleVerdict.role_key, models.TitleVerdict.title_key).filter(
        models.TitleVerdict.role_key.in_({r for r, _ in pairs}),
        models.TitleVerdict.title_key.in_({t for _, t in pairs})).all())
    db.add_all(models.TitleVerdict(role_key=r, title_key=t, match=v == "match", similar=v == "similar")
               for (r, t), v in pairs.items() if (r, t) not in existing)
