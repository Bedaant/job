"""F6 matching (SPEC.md §3.2, ARCHITECTURE.md §4.1): score every job with an
embedding against the profile's fact_centroid, upsert into `matches`.

ponytail: cosine similarity is computed in-process over every embedded job
(O(n) scan), not via pgvector's ivfflat index (already created by migration
0004 for when this matters). Fine at MVP job volume; switch to an
`ORDER BY embedding <=> centroid` query when job count makes an in-process
scan too slow.
"""
import logging

from sqlalchemy.orm import Session

import models
from events.outbox import write_event
from matching.embeddings import compute_centroid, cosine_similarity, embed_texts
from matching.filters import passes_hard_filters
from matching.scoring import compute_match_score


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
    candidates = {j.id: j for c in active for j in _in_bounds(embedded, c)}.values() if active else embedded.all()
    jobs = [job for job in candidates if passes_hard_filters(prefs, job, profile.country_code)]
    if not jobs:
        return []

    profile_skills = sorted({tag for fact in profile.resume_facts for tag in (fact.tags or [])})
    # pgvector returns numpy.float32 arrays on a real Postgres connection (not
    # on the SQLite unit-test engine, where it round-trips plain lists) — cast
    # to native floats here so json.dumps on the `breakdown` column downstream
    # doesn't choke on a numpy scalar buried in the dict.
    centroid = [float(x) for x in profile.fact_centroid]

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
