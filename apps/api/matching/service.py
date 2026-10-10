"""F6 matching (SPEC.md §3.2, ARCHITECTURE.md §4.1): score every job with an
embedding against the profile's fact_centroid, upsert into `matches`.

GAPS 2.6: pgvector computes the cosine similarity and the embedding column
never leaves the server. Composite scoring stays in Python, because semantic
similarity is only 0.55 of the score (scoring.py) — vector order is not score
order, so the SQL ordering is a bound on the candidate set, never the ranking.
"""
import logging

from sqlalchemy.orm import Session, defer

import models
from events.outbox import write_event
from matching.embeddings import compute_centroid, cosine_similarity, embed_texts
from matching.filters import passes_hard_filters
from matching.scoring import compute_match_score

# A ceiling on how many jobs reach the Python scorer, NOT a target. It bounds
# the worst case as the corpus grows, and sits deliberately far above the live
# embedded pool (1,967 on 2026-10-06) so nothing is dropped today.
#
# Why it must stay far above that pool: semantic is only 0.55 of the score
# (scoring.py), so coverage (0.30) and recency (0.15) can move a job 45 points
# and vector rank is NOT score rank. This was measured, not assumed — with the
# ceiling at 500 the top-20 lost 1-3 jobs per profile against a full scan
# (overlap 17-19/20). The misses scored 58-69 and sat at vector ranks 513-1025:
# real high scorers that won on recency and coverage despite mediocre
# similarity. A narrow ceiling silently changes which jobs users see, so don't
# lower this to "tune" anything without re-running that comparison.
CANDIDATE_POOL = 5000


def _candidates(query, centroid: list[float], dialect: str, need_description: bool):
    """The candidate jobs plus each one's cosine similarity, as (job, semantic).

    On Postgres the similarity is computed by pgvector and the embedding column
    is left on the server: at 512 floats a row it was the dominant cost of this
    whole function, and nothing downstream reads it once the distance is known.
    `description` is dropped the same way unless the visa filter needs it —
    it is the other large column, and `_passes_visa` is its only reader here.

    Verified against the real database: `1 - (embedding <=> centroid)` matches
    `cosine_similarity()` to 1.4e-07 over 300 real job vectors, which is
    float32 round-trip noise and cannot move a score rounded to 2 decimals.

    `semantic` is None on SQLite (no pgvector in the unit-test engine), which
    tells the caller to compute cosine in Python as before.
    """
    if dialect != "postgresql":
        return [(job, None) for job in query]
    # pgvector's <=> is cosine DISTANCE; cosine_similarity() returns similarity.
    return [
        (job, 1.0 - float(distance))
        for job, distance in _pgvector_query(query, centroid, need_description).all()
    ]


def _pgvector_query(query, centroid: list[float], need_description: bool):
    """Built separately from `_candidates` so a test can compile it without a
    Postgres connection."""
    deferred = [defer(models.Job.embedding)]
    if not need_description:
        deferred.append(defer(models.Job.description))
    distance = models.Job.embedding.cosine_distance(centroid).label("distance")
    return query.options(*deferred).add_columns(distance).order_by(distance).limit(CANDIDATE_POOL)


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
    need_description = bool(prefs.get("visa_sponsorship_required"))
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
    sources = [_in_bounds(embedded, c) for c in active] if active else [embedded]
    # Keyed by id: the same job can be in bounds for two campaigns.
    candidates = {
        job.id: (job, semantic)
        for query in sources
        for job, semantic in _candidates(query, centroid, dialect, need_description)
    }.values()
    scorable = [
        (job, semantic) for job, semantic in candidates
        if passes_hard_filters(prefs, job, profile.country_code)
    ]
    if not scorable:
        return []

    profile_skills = sorted({tag for fact in profile.resume_facts for tag in (fact.tags or [])})

    scored = []
    for job, semantic in scorable:
        if semantic is None:   # SQLite: no pgvector, so cosine in Python as before
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
