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
from sqlalchemy.orm import Session, defer

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
# board_token is refreshed too (COLLECT-D): rows stored before migration 0023
# carry NULL, and a token-scoped sweep deliberately skips NULL rows, so they
# stay unsweepable until their board lists them again and fills it in.
_UPDATE_FIELDS = ("title", "company", "location", "salary", "description", "apply_url", "posted_at", "canonical_hash", "board_token")


def upsert_jobs(db: Session, jobs: list[dict]) -> tuple[int, int, int]:
    """jobs: dicts with all Job columns, including a precomputed canonical_hash
    (connectors.normalize.canonical_hash). Returns (inserted, updated, skipped_duplicates).
    """
    if not jobs:
        return 0, 0, 0

    batch_hashes = [j["canonical_hash"] for j in jobs]
    batch_keys = [(j["source"], j["external_id"]) for j in jobs]
    # defer(embedding): every matching row used to arrive carrying a 1024-dim
    # vector it is never read for, and since ADR-021 re-fetches whole boards the
    # match set in a steady-state run is the ENTIRE live pool, hourly, in one
    # SimpleWorker process.
    #
    # Only `embedding` is deferred, deliberately. `description` is in
    # _UPDATE_FIELDS and the loop below reads `getattr(existing, field)` as a
    # fallback, so deferring it would lazy-load per row — an N+1 strictly worse
    # than the thing being fixed.
    existing_rows = (
        db.query(models.Job)
        .options(defer(models.Job.embedding))
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
    # Keyed by company, not a flat list: the scan is per-company anyway (the
    # company equality check short-circuits), and ADR-021 made the batch the
    # whole pool rather than ~100 rows.
    accepted_fingerprints: dict[str, list[int]] = {}
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
        same_company = accepted_fingerprints.setdefault(job["company"], [])
        if any(is_near_duplicate(fingerprint, other_fp) for other_fp in same_company):
            skipped += 1
            continue
        same_company.append(fingerprint)

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
        # Chunked to BACKFILL_REQUEST_CHARS, the same budget backfill_job_embeddings
        # uses. This used to be ONE call with every new job's text: fine at ~100
        # keyword-filtered inserts a run, guaranteed to fail once ADR-021 made
        # discovery store whole boards. Measured on the first unfiltered run —
        # 3,351 new jobs in one batch, one request, 429, and the except below
        # silently saved every single one un-embedded (6 of 3,351 ended up with a
        # vector). An unembedded job cannot be matched, so that was the whole
        # pool invisible until the 2-minute backfill ground through it.
        #
        # First failure stops the pass and keeps what was embedded: on Voyage's
        # free tier (3 RPM) the minute's budget is spent, and the rest is picked
        # up by embed_backlog_task rather than retried in the worker.
        texts = [_embed_text(j["title"], j["company"], j.get("description")) for j in to_insert]
        for start, end in _embed_chunks(texts):
            try:
                embeddings = embed_texts(texts[start:end], input_type="document")
            except Exception:
                # An embeddings outage/rate limit must not throw away what discovery
                # found: save the jobs un-embedded (matching skips them until backfilled).
                logging.getLogger(__name__).exception(
                    "embedding jobs %d-%d of %d failed; saving the rest un-embedded",
                    start, end, len(to_insert),
                )
                break
            if not embeddings:
                break
            for job, embedding in zip(to_insert[start:end], embeddings):
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


def _embed_chunks(texts: list[str]) -> list[tuple[int, int]]:
    """(start, end) slices whose text fits one BACKFILL_REQUEST_CHARS request.

    Shared by the insert path and backfill_job_embeddings so the per-request
    budget is defined once. A single text longer than the budget still gets its
    own chunk rather than being dropped — EMBED_CHARS already caps each one well
    under it, so that is a guard, not a normal case.
    """
    chunks: list[tuple[int, int]] = []
    start = size = 0
    for i, text in enumerate(texts):
        if size and size + len(text) > BACKFILL_REQUEST_CHARS:
            chunks.append((start, i))
            start, size = i, 0
        size += len(text)
    if start < len(texts):
        chunks.append((start, len(texts)))
    return chunks


def backfill_job_embeddings(db, limit: int = 50, only_ids=None) -> int:
    """Embed jobs saved without a vector (an embeddings outage during discovery).
    Bounded per run and failure-tolerant, like the insert path. Requests are
    sized to fit a 10K-tokens-per-minute cap; the first failure (a 429 once the
    minute's budget is spent) ends the pass, keeping what was embedded — the
    rest waits for the next discover run rather than sleeping in the worker.
    Returns how many were embedded."""
    # Newest first, still-listed only: on a 3 RPM free tier the backlog clears
    # slowly, so the budget must not go to jobs that are already dead.
    query = db.query(models.Job).filter(
        models.Job.embedding.is_(None), models.Job.delisted_at.is_(None)
    )
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
