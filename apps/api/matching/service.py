"""F6 matching (SPEC.md §3.2, ARCHITECTURE.md §4.1): score every job with an
embedding against the profile's fact_centroid, upsert into `matches`.

Candidate selection happens in Postgres (`ORDER BY embedding <=> centroid`,
GAPS 2.6); composite scoring stays in Python, because semantic similarity is
only 0.55 of the score (scoring.py) — vector order is not score order, so the
SQL is a prefilter and never the ranking.
"""
import logging

from sqlalchemy.orm import Session

import models
from events.outbox import write_event
from matching.embeddings import compute_centroid, cosine_similarity, embed_texts
from matching.filters import passes_hard_filters
from matching.scoring import compute_match_score

# How many of the nearest jobs are handed to the Python scorer. Wide on
# purpose: coverage (0.30) and recency (0.15) can move a job 45 points, so the
# nearest-K is only safe as a prefilter while K is far larger than `limit`.
#
# Measured against the real database (1,865 live embedded jobs): fetching every
# embedding to score in Python took a median of 63.5s, almost all of it
# transferring 1,865 x 512 floats from Neon. Returning the nearest 500 ids
# instead takes 376ms, of which 7.7ms is Postgres (the rest is round-trip).
#
# Two separate approximations, don't conflate them:
#  1. The prefilter itself. A job outside the nearest K can no longer reach the
#     top `limit` on coverage/recency alone. Always present; that is the trade.
#  2. Which K rows come back. Postgres currently answers with a seq scan +
#     top-N heapsort and IGNORES ix_jobs_embedding, so the K it returns is the
#     true nearest K (verified: 500/500 against a forced seq scan). The ivfflat
#     index only takes over once the scan gets expensive, and then recall
#     becomes a function of `ivfflat.probes` (default 1 over lists=100) — set
#     probes and re-check this constant when EXPLAIN shows an index scan here.
CANDIDATE_POOL = 500


def _narrow(query, centroid: list[float], limit: int, dialect: str):
    """Restrict `query` to the jobs nearest `centroid`, in SQL where possible.

    SQLite (the unit-test engine) has no pgvector, so there the query is
    returned untouched and the caller scans everything — which is what every
    matching test exercises.
    """
    if dialect != "postgresql":
        return query
    return query.order_by(models.Job.embedding.cosine_distance(centroid)).limit(
        max(CANDIDATE_POOL, limit)
    )


def refresh_fact_vectors(db: Session, profile: models.Profile) -> None:
    """Embed every fact still missing a vector (an edit, or an earlier Voyage
    outage), then recompute the centroid from the facts that have one. Voyage
    failing never blocks the edit: the fact stays unembedded until next time."""
    facts = db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == profile.id).all()
    pending = [f for f in facts if f.embedding is None]
    if pending:
        try:
            vectors = embed_texts([f.achievement for f in pending], input_type="document")
        except Exception:
            logging.getLogger(__name__).exception("re-embedding %d facts failed", len(pending))
            vectors = None
        for fact, vector in zip(pending, vectors or []):
            fact.embedding = vector
    embedded = [[float(x) for x in f.embedding] for f in facts if f.embedding is not None]
    profile.fact_centroid = compute_centroid(embedded) if embedded else None


def build_matches(db: Session, profile: models.Profile, limit: int = 20) -> list[models.Match]:
    if profile.fact_centroid is None or any(f.embedding is None for f in profile.resume_facts):
        # Facts a Voyage outage left unembedded (the free tier's 429 at resume confirm).
        refresh_fact_vectors(db, profile)
        db.commit()
    if profile.fact_centroid is None:
        return []

    prefs = profile.prefs or {}
    # pgvector returns numpy.float32 arrays on a real Postgres connection (not
    # on the SQLite unit-test engine, where it round-trips plain lists) — cast
    # to native floats here so json.dumps on the `breakdown` column downstream
    # doesn't choke on a numpy scalar buried in the dict. Needed before the
    # candidate query now, which binds it as the <=> operand.
    centroid = [float(x) for x in profile.fact_centroid]
    dialect = db.get_bind().dialect.name
    # delisted_at excluded here too (Task 5) — cheaper in SQL than relying
    # solely on passes_hard_filters below to drop it in Python.
    embedded = db.query(models.Job).filter(
        models.Job.embedding.isnot(None), models.Job.delisted_at.is_(None)
    )
    # The top N is taken inside what the user's active campaigns ask for (roles, places,
    # sources); filtering after would let better-scoring out-of-bounds jobs starve them.
    from campaigns import _in_bounds  # campaigns imports this module's callers
    active = db.query(models.Campaign).filter(
        models.Campaign.profile_id == profile.id, models.Campaign.status == models.CampaignStatus.active
    ).all()
    if active:
        # Narrowed per campaign, not once over the union: each campaign has to
        # get its own nearest pool, or a broad campaign would eat the budget.
        candidates = {
            j.id: j for c in active for j in _narrow(_in_bounds(embedded, c), centroid, limit, dialect)
        }.values()
    else:
        candidates = _narrow(embedded, centroid, limit, dialect).all()
    jobs = [job for job in candidates if passes_hard_filters(prefs, job, profile.country_code)]
    if not jobs:
        return []

    profile_skills = sorted({tag for fact in profile.resume_facts for tag in (fact.tags or [])})

    scored = []
    for job in jobs:
        semantic = cosine_similarity(centroid, [float(x) for x in job.embedding])
        breakdown = compute_match_score(semantic, job.skills or [], profile_skills, job.posted_at)
        scored.append((job, breakdown))
    scored.sort(key=lambda pair: pair[1]["score"], reverse=True)
    scored = scored[:limit]

    existing = {
        m.job_id: m
        for m in db.query(models.Match).filter(models.Match.profile_id == profile.id).all()
    }

    result = []
    for job, breakdown in scored:
        match = existing.get(job.id)
        if match is None:
            match = models.Match(profile_id=profile.id, job_id=job.id, state="new")
            db.add(match)
            # ADR-012 outbox: only a genuinely new match is announced — a
            # re-score of an already-seen match (test_build_matches_upserts_
            # not_duplicates) must not re-fire match.new on every rebuild.
            write_event(
                db, profile.user_id, "match.new",
                {"job_id": job.id, "job_title": job.title, "score": breakdown["score"]},
            )
        match.score = breakdown["score"]
        match.breakdown = breakdown
        match.job = job
        result.append(match)

    db.commit()
    return result
