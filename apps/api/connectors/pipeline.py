import logging
"""fetch -> normalize -> dedupe -> upsert (ARCHITECTURE.md §3, §4.1).

Fixes CODE-REVIEW.md H1 (was 1 SELECT + 1 INSERT per job, N+1) and H3 (dedupe
was source+external_id only, so the same role from two sources landed twice).
At most three queries regardless of batch size: one SELECT of existing rows,
one bulk INSERT of new rows, one bulk UPDATE of re-seen rows (Task 2,
freshness — a re-seen job refreshes last_seen_at/delisted_at/fields instead
of being silently skipped).
"""
from datetime import datetime

from sqlalchemy import or_, tuple_
from sqlalchemy.orm import Session

import models
from matching.embeddings import embed_texts
from matching.filters import infer_seniority
from matching.near_duplicate import simhash, is_near_duplicate
from matching.skills import extract_skills

# Fields refreshed on a re-seen job, filled from the incoming payload only
# where it's non-empty (never overwrite a stored value with NULL/""). Matched
# on (source, external_id) — not canonical_hash — because a connector can
# change `company` (and therefore the hash) for a job already on file; hash
# matching would duplicate that row instead of updating it.
_UPDATE_FIELDS = ("title", "company", "location", "salary", "description", "apply_url", "posted_at", "canonical_hash")


def upsert_jobs(db: Session, jobs: list[dict]) -> tuple[int, int, int]:
    """jobs: dicts with all Job columns, including a precomputed canonical_hash
    (connectors.normalize.canonical_hash). Returns (inserted, updated, skipped_duplicates).
    """
    if not jobs:
        return 0, 0, 0

    batch_hashes = [j["canonical_hash"] for j in jobs]
    batch_keys = [(j["source"], j["external_id"]) for j in jobs]
    existing_rows = (
        db.query(models.Job)
        .filter(
            or_(
                models.Job.canonical_hash.in_(batch_hashes),
                tuple_(models.Job.source, models.Job.external_id).in_(batch_keys),
            )
        )
        .all()
    )
    # Delisted rows are excluded on purpose: a tombstone must not suppress the
    # same role arriving live from another source, nor a board re-posting a
    # closed req under a new external_id. Both would otherwise be skipped
    # forever, serving zero live rows for a job that is open.
    existing_hashes = {row.canonical_hash for row in existing_rows if row.delisted_at is None}
    existing_by_key = {(row.source, row.external_id): row for row in existing_rows}

    seen_in_batch: set[str] = set()
    # (company, simhash) for jobs already accepted this batch — catches a
    # reworded title from the same company that canonical_hash's exact match
    # misses (F4 gap, DEPENDENCIES.md §3). ponytail: scoped to the current
    # batch only, not a full-table scan against every existing job — that
    # needs its own index/architecture call, not made here.
    accepted_fingerprints: list[tuple[str, int]] = []
    to_insert = []
    to_update = []
    updated = 0
    skipped = 0
    now = datetime.utcnow()

    for job in jobs:
        existing = existing_by_key.get((job["source"], job["external_id"]))
        if existing is not None:
            mapping = {"id": existing.id, "last_seen_at": now, "delisted_at": None}
            for field in _UPDATE_FIELDS:
                mapping[field] = job.get(field) or getattr(existing, field)
            to_update.append(mapping)
            updated += 1
            continue

        h = job["canonical_hash"]
        if h in existing_hashes or h in seen_in_batch:
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

    if to_update:
        db.bulk_update_mappings(models.Job, to_update)

    if to_insert:
        try:
            embeddings = embed_texts(
                [_embed_text(j["title"], j["company"], j.get("description")) for j in to_insert],
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

    if to_insert or to_update:
        db.commit()

    return len(to_insert), updated, skipped


# ponytail: ~4 chars/token guess keeps one request under Voyage's free-tier
# 10K TPM; use client.count_tokens (needs `tokenizers`) if descriptions skew dense.
BACKFILL_REQUEST_CHARS = 24_000
# What a job's vector is made of: its head (title, company, role summary). A whole
# description can fill a free-tier request alone; this packs ~6 jobs into one.
EMBED_CHARS = 4_000


def _embed_text(title, company, description) -> str:
    return f"{title} at {company}. {description or ''}"[:EMBED_CHARS]


def backfill_job_embeddings(db, limit: int = 50, only_ids=None) -> int:
    """Embed jobs saved without a vector (an embeddings outage during discovery).
    Bounded per run and failure-tolerant, like the insert path. Requests are
    sized to fit a 10K-tokens-per-minute cap; the first failure (a 429 once the
    minute's budget is spent) ends the pass, keeping what was embedded — the
    rest waits for the next discover run rather than sleeping in the worker.
    Returns how many were embedded."""
    # Newest first: on a 3 RPM free tier the backlog clears slowly, and fresh postings matter most.
    query = db.query(models.Job).filter(models.Job.embedding.is_(None))
    if only_ids is not None:
        query = query.filter(models.Job.id.in_(only_ids))
    pending = query.order_by(models.Job.fetched_at.desc().nullslast()).limit(limit).all()
    batches, size = [], BACKFILL_REQUEST_CHARS
    for job in pending:
        text = _embed_text(job.title, job.company, job.description)
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
