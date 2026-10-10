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

# Source trust order for collapsing duplicate live rows (GAPS 4.3), best first.
# The only question being answered is "which of these two rows should the user
# see", and the answer is whichever one they can actually apply through:
#
#   0  direct ATS — apply_url IS the employer's form, a form_plan can exist for
#      it, and these are the SWEEPABLE_SOURCES, so their freshness is measured
#      rather than assumed.
#   1  linkedin_external / clipped — apply_url resolves to the employer's own
#      ATS (measured 2026-10-09: 56% of LinkedIn rows), so the extension fills it.
#   2  everything else — aggregator and feed links. Openable, not fillable.
#   3  linkedin_easy_apply — apply_url is linkedin.com. The extension cannot fill
#      it and this project does not automate LinkedIn, so it is the row to drop
#      whenever any alternative exists.
_DIRECT_ATS = {"greenhouse", "lever", "ashby", "workday"}


def _source_trust(source: str) -> int:
    if source in _DIRECT_ATS:
        return 0
    if source in ("linkedin_external", "clipped"):
        return 1
    if source == "linkedin_easy_apply":
        return 3
    return 2


def _collapse_key(row):
    """Trust, then oldest, then id.

    Trust first because an unfillable row is worth less than a fillable one however
    new it is. Oldest second because that row is the one most likely to already
    carry an embedding and `Match` history, so keeping it avoids re-embedding and
    preserves what the user has seen. `id` last so the order is TOTAL — GAPS 6.6
    was a real nondeterminism bug from ranking without a tiebreaker, and here the
    tiebreaker decides which copy of a job a user is shown.
    """
    return (_source_trust(row.source), row.fetched_at or datetime.min, row.id)


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

    # PASS 1 — re-seen rows, matched on (source, external_id).
    #
    # Resolved before any insert decision because an update can REWRITE a row's
    # canonical_hash (that is `canonical_hash` in _UPDATE_FIELDS, and ADR-017 §5's
    # whole point). The insert guard in pass 2 therefore has to test against the
    # live hash set as it will be AFTER this run, not as it was before — otherwise
    # a row rewritten into hash H this run and a new row inserted with hash H in
    # the same batch both end up live, and the collision survives until the next
    # discovery run happens to fetch both.
    for job in jobs:
        existing = existing_by_key.get((job["source"], job["external_id"]))
        if existing is None:
            continue
        mapping = {"id": existing.id, "last_seen_at": now, "delisted_at": None}
        for field in _UPDATE_FIELDS:
            mapping[field] = job.get(field) or getattr(existing, field)
        to_update.append(mapping)
        updated += 1

    # The live hash set as of the end of this run. A row updated above counts at
    # its NEW hash, and a tombstoned row that an update revived (delisted_at reset
    # to None) counts as live again.
    #
    # Delisted rows are excluded on purpose: a tombstone must not suppress the
    # same role arriving live from another source, nor a board re-posting a closed
    # req under a new external_id. Both would otherwise be skipped forever,
    # serving zero live rows for a job that is open.
    update_by_id = {m["id"]: m for m in to_update}
    live_by_hash: dict[str, list] = {}
    for row in existing_rows:
        mapping = update_by_id.get(row.id)
        if mapping is not None:
            final_hash = mapping["canonical_hash"]
            live = mapping.get("delisted_at") is None
        else:
            final_hash = row.canonical_hash
            live = row.delisted_at is None
        if live:
            live_by_hash.setdefault(final_hash, []).append(row)
    existing_hashes = set(live_by_hash)

    # PASS 2 — rows this batch has not seen before.
    for job in jobs:
        if (job["source"], job["external_id"]) in existing_by_key:
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

    # --- collapse live rows that share a canonical_hash (GAPS 4.3) ------------
    #
    # ADR-017 §5 keeps the hash non-unique deliberately, so nothing in the schema
    # stops two live rows describing the same role, and nothing re-collapsed such
    # a pair. That was tolerable while sources barely overlapped. It is not now:
    # linkedin_external, linkedin_easy_apply, jobspy_glassdoor and 77 newly probed
    # ATS boards all return the same req, with different (source, external_id) but
    # the SAME hash — so a user sees one job several times and could apply twice.
    #
    # Pass 2's guard stops insert-vs-anything. This handles the case ADR-017 §5
    # actually names and the guard cannot: the UPDATE path rewriting a re-seen
    # row's hash into one another live row already holds, plus any pair that was
    # already stored colliding before this change existed.
    #
    # No extra query and no schema change: these rows are already in memory from
    # the single SELECT above, and re-adding the UNIQUE constraint is what turned
    # a legitimate hash rewrite into a run-killing IntegrityError.
    collapsed = 0
    # A row the user has ALREADY APPLIED THROUGH must never lose, and this is a
    # correctness requirement rather than a courtesy. `campaigns.select_candidates`
    # excludes already-applied jobs by **job_id**, not by `canonical_hash`. So
    # tombstoning the applied row leaves its higher-trust duplicate live, un-applied and
    # matchable — and the campaign applies a SECOND time to the same role at the same
    # employer. `main.py::claim_submission`'s at-most-once lock cannot see it, because
    # these are two different `Application` rows.
    #
    # Keeping the applied row fixes both halves: the history stays attached, and the
    # survivor is the row `already_applied` already filters out.
    #
    # One scoped query, only when a collision actually exists — the common case does no
    # work at all.
    collision_ids = [r.id for g in live_by_hash.values() if len(g) > 1 for r in g]
    applied_ids: set[str] = set()
    if collision_ids:
        applied_ids = {
            row[0]
            for row in db.query(models.Application.job_id)
            .filter(models.Application.job_id.in_(collision_ids))
            .all()
        }

    def _key(row):
        # Applied first, then the trust order, then the deterministic tiebreakers.
        return (row.id not in applied_ids, *_collapse_key(row))

    for dupes in live_by_hash.values():
        if len(dupes) < 2:
            continue
        _winner, *losers = sorted(dupes, key=_key)
        for loser in losers:
            mapping = update_by_id.get(loser.id)
            if mapping is None:
                mapping = {"id": loser.id}
                to_update.append(mapping)
            # Tombstoned, never deleted: an Application may already point at this
            # row, and `delisted_at` is what every live-pool query filters on
            # already (matching, embedding backfill, /sources counts), so one flag
            # removes the duplicate everywhere at once.
            #
            # This overloads delisted_at's meaning from "its source stopped listing
            # it" to also "superseded by a better duplicate". Accepted: it is the
            # only mechanism that drops a row out of the live pool without losing
            # data or breaking a foreign key.
            mapping["delisted_at"] = now
            collapsed += 1
    if collapsed:
        # ponytail: a loser is revived by its own source's update every run and
        # re-collapsed here, so this logs a steady non-zero count rather than
        # trending to zero. Idempotent and one write per duplicate per run; worth
        # a real fix only if the write volume ever shows up.
        logging.getLogger(__name__).info(
            "collapsed %d duplicate live job row(s) sharing a canonical_hash", collapsed
        )

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
