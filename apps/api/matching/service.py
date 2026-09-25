"""F6 matching (SPEC.md §3.2, ARCHITECTURE.md §4.1): score every job with an
embedding against the profile's fact_centroid, upsert into `matches`.

ponytail: cosine similarity is computed in-process over every embedded job
(O(n) scan), not via pgvector's ivfflat index (already created by migration
0004 for when this matters). Fine at MVP job volume; switch to an
`ORDER BY embedding <=> centroid` query when job count makes an in-process
scan too slow.
"""
from sqlalchemy.orm import Session

import models
from events.outbox import write_event
from matching.embeddings import cosine_similarity
from matching.filters import passes_hard_filters
from matching.scoring import compute_match_score


def build_matches(db: Session, profile: models.Profile, limit: int = 20) -> list[models.Match]:
    if profile.fact_centroid is None:
        return []

    prefs = profile.prefs or {}
    jobs = [
        job for job in db.query(models.Job).filter(models.Job.embedding.isnot(None)).all()
        if passes_hard_filters(prefs, job)
    ]
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
