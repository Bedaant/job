import logging
"""fetch -> normalize -> dedupe -> upsert (ARCHITECTURE.md §3, §4.1).

Fixes CODE-REVIEW.md H1 (was 1 SELECT + 1 INSERT per job, N+1) and H3 (dedupe
was source+external_id only, so the same role from two sources landed twice).
Two queries total regardless of batch size: one SELECT of existing hashes,
one bulk INSERT of the new rows.
"""
from datetime import datetime

from sqlalchemy.orm import Session

import models
from matching.embeddings import embed_texts
from matching.filters import infer_seniority
from matching.near_duplicate import simhash, is_near_duplicate
from matching.skills import extract_skills


def upsert_jobs(db: Session, jobs: list[dict]) -> tuple[int, int]:
    """jobs: dicts with all Job columns, including a precomputed canonical_hash
    (connectors.normalize.canonical_hash). Returns (inserted, skipped_duplicates).
    """
    if not jobs:
        return 0, 0

    batch_hashes = [j["canonical_hash"] for j in jobs]
    existing = {
        row[0]
        for row in db.query(models.Job.canonical_hash)
        .filter(models.Job.canonical_hash.in_(batch_hashes))
        .all()
    }

    seen_in_batch: set[str] = set()
    # (company, simhash) for jobs already accepted this batch — catches a
    # reworded title from the same company that canonical_hash's exact match
    # misses (F4 gap, DEPENDENCIES.md §3). ponytail: scoped to the current
    # batch only, not a full-table scan against every existing job — that
    # needs its own index/architecture call, not made here.
    accepted_fingerprints: list[tuple[str, int]] = []
    to_insert = []
    skipped = 0
    now = datetime.utcnow()

    for job in jobs:
        h = job["canonical_hash"]
        if h in existing or h in seen_in_batch:
            skipped += 1
            continue

        fingerprint = simhash(f"{job['company']} {job['title']}")
        if any(
            company == job["company"] and is_near_duplicate(fingerprint, other_fp)
            for company, other_fp in accepted_fingerprints
        ):
            skipped += 1
            continue
        accepted_fingerprints.append((job["company"], fingerprint))

        seen_in_batch.add(h)
        to_insert.append({
            **job,
            "seniority": infer_seniority(job["title"]),
            "skills": extract_skills(f"{job['title']}. {job.get('description') or ''}"),
            "fetched_at": now,
            "last_seen_at": now,
        })

    if to_insert:
        try:
            embeddings = embed_texts(
                [f"{j['title']} at {j['company']}. {j.get('description') or ''}" for j in to_insert],
                input_type="document",
            )
        except Exception:
            # An embeddings outage/rate limit must not throw away what discovery
            # found: save the jobs un-embedded (matching skips them until backfilled).
            logging.getLogger(__name__).exception("embedding %d new jobs failed; saving without", len(to_insert))
            embeddings = None
        if embeddings:
            for job, embedding in zip(to_insert, embeddings):
                job["embedding"] = embedding
        db.bulk_insert_mappings(models.Job, to_insert)
        db.commit()

    return len(to_insert), skipped


# ponytail: ~4 chars/token guess keeps one request under Voyage's free-tier
# 10K TPM; use client.count_tokens (needs `tokenizers`) if descriptions skew dense.
BACKFILL_REQUEST_CHARS = 24_000


def backfill_job_embeddings(db, limit: int = 50) -> int:
    """Embed jobs saved without a vector (an embeddings outage during discovery).
    Bounded per run and failure-tolerant, like the insert path. Requests are
    sized to fit a 10K-tokens-per-minute cap; the first failure (a 429 once the
    minute's budget is spent) ends the pass, keeping what was embedded — the
    rest waits for the next discover run rather than sleeping in the worker.
    Returns how many were embedded."""
    # Newest first: on a 3 RPM free tier the backlog clears slowly, and fresh postings matter most.
    pending = (db.query(models.Job).filter(models.Job.embedding.is_(None))
               .order_by(models.Job.fetched_at.desc().nullslast()).limit(limit).all())
    batches, size = [], BACKFILL_REQUEST_CHARS
    for job in pending:
        text = f"{job.title} at {job.company}. {job.description or ''}"[:BACKFILL_REQUEST_CHARS]
        if size + len(text) > BACKFILL_REQUEST_CHARS:
            batches.append(([], []))
            size = 0
        batches[-1][0].append(job)
        batches[-1][1].append(text)
        size += len(text)

    done = 0
    for jobs, texts in batches:
        try:
            embeddings = embed_texts(texts, input_type="document")
        except Exception:
            logging.getLogger(__name__).exception("embedding backfill stopped after %d of %d jobs", done, len(pending))
            break
        if not embeddings:
            break
        for job, embedding in zip(jobs, embeddings):
            job.embedding = embedding
        db.commit()
        done += len(jobs)
    return done
