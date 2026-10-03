"""RQ job definitions (ARCHITECTURE.md §3 `workers/`). Fixes CODE-REVIEW.md B6:
`/discover/run` used to do all connector I/O inline on the request thread. This
runs in a worker process instead.
"""
import logging
import time
from datetime import datetime
from functools import lru_cache

from redis import Redis
from rq import Queue
from rq.exceptions import DuplicateJobError

from connectors import config as conn_config
from connectors.ashby import fetch_ashby_jobs
from connectors.feeds import fetch_enabled_feeds, filter_by_keywords
from connectors.greenhouse import fetch_greenhouse_jobs
from connectors.lever import fetch_lever_jobs
from connectors.normalize import canonical_hash
from connectors.pipeline import backfill_job_embeddings, upsert_jobs
from connectors.reed import fetch_reed_jobs
from connectors.remotive import fetch_remotive_jobs
from core.config import get_settings
from database import session_scope

import models
from batch_prep import prepare_application_for_review
from campaigns import run_campaign
from events.outbox import write_event
from formplans import ROUTED_ATS, plan_job
from matching.service import build_matches

logger = logging.getLogger(__name__)

# ADR-015 "approve once, Maggie works for you": how often every active campaign
# gets fresh matches and a run. Also the job-id time bucket, so a re-fired sweep
# in the same window dedupes. The daily cap is enforced inside run_campaign, so
# a shorter interval can't send more — it only notices new jobs sooner.
CAMPAIGN_SWEEP_INTERVAL_SECONDS = 60 * 60
# One embedding pass every 2 minutes: ~6 jobs a pass on Voyage's free tier (3 RPM / 10K TPM).
EMBED_BACKLOG_INTERVAL_SECONDS = 2 * 60

# Task 5 (freshness, phase 1): sources that return a FULL listing per fetch —
# a job's absence from this run's payload is real signal it left the board.
# remotive and reed always fetch a keyword slice (connectors/config.py) —
# absence there means "not in that search", not "gone" — so they never
# qualify and must never appear here. jobspy isn't wired into ingestion at
# all (main.py), so it's moot.
#
# A feed that returns only the newest N listings does not qualify either:
# absence from a newest-N window IS age, and this phase expires by source
# absence, never by age. Verified against live responses (2026-10-03) — five
# of the six keyless feeds are truncated and were removed:
#   remoteok       fixed 100-row payload (99 jobs), limit/offset ignored
#   himalayas      capped at 20/page server-side; totalCount 115415, nextCursor
#   jobicy         `count` parameter; response carries hasMore + nextCursor
#   arbeitnow      page 1 only (meta.current_page, links.next -> page=2)
#   weworkremotely RSS, latest ~90 items
#   workingnomads  one bare JSON list, no cursor/page/count knob, but its age
#                  distribution is [1, 1, 2, 3, ..., 28, 28, 29] days -- a
#                  rolling ~30-day window, nothing at or beyond 30. A job
#                  aging past 30 days would vanish from the payload while
#                  still live, which is age, not absence. Whether Working
#                  Nomads itself expires postings at 30 days is unverified
#                  either way -- unproven absence does not qualify.
# greenhouse/lever/ashby each hit one unpaginated board endpoint per token.
# Paginating the truncated fetchers to exhaustion is new ingestion work, not
# this phase; until then all six feeds accumulate stale rows. workingnomads
# keeps being ingested (ENABLED_FEEDS), it just stops being swept.
# tests/test_delisting_sweep.py pins this set so re-adding a disqualified
# source cannot be quiet.
SWEEPABLE_SOURCES = {"greenhouse", "lever", "ashby"}


def _sweep_delisted(db, source: str, jobs: list[dict]) -> None:
    """Set delisted_at=now on currently-listed (NULL) rows for `source` that
    are absent from `jobs` — this run's fetched (and keyword-filtered)
    payload for that source (see _fetch_ats_source for how an ATS source's
    per-token fetches are combined into one trustworthy-or-nothing `jobs`
    list before this is called). One bulk UPDATE, not per-row.

    Traps this guards against:
    - A non-qualifying or unrecognized source is a no-op, defense in depth
      against a caller passing one by mistake (remotive/reed never should).
    - An EMPTY `jobs` list is treated as "no signal", never as "the board is
      actually empty". greenhouse.py/lever.py/ashby.py return [] on a
      non-200 exactly like a genuinely empty board — the two are
      indistinguishable from an empty list alone — so sweeping on empty
      would delist every still-open job the first time a source has a bad
      day. This is the whole reason the sweep is safe without the
      per-source error isolation / ConnectorRun health rows that Phase 2
      adds; that work is explicitly out of scope here.
    - A payload entry with no external_id is dropped from the comparison
      set rather than left in as a bare None, which would otherwise put a
      NULL into the NOT IN list and make every row's comparison NULL (SQL's
      NOT IN + NULL trap) instead of a real id check. If nothing in `jobs`
      carries an external_id, there's nothing to compare against: no
      signal, no sweep.
    """
    if source not in SWEEPABLE_SOURCES or not jobs:
        return
    seen_ids = {j["external_id"] for j in jobs if j.get("external_id") is not None}
    if not seen_ids:
        return
    db.query(models.Job).filter(
        models.Job.source == source,
        models.Job.delisted_at.is_(None),
        models.Job.external_id.notin_(seen_ids),
    ).update({"delisted_at": datetime.utcnow()}, synchronize_session=False)


def _fetch_ats_source(fetcher, tokens: list[str], keywords: list[str]) -> tuple[list[dict], bool]:
    """Fetch every token's board for one ATS source (greenhouse/lever/ashby)
    and say whether the combined result is trustworthy enough to sweep.

    Per-token delisting needs a stable per-token identity on the stored row.
    Task 4 made `Job.company` a display name resolved from the API payload
    or a token->name map (connectors/config.py) — not the raw token — and it
    can legitimately vary in formatting (seen live: a trailing space on one
    board, "Rubrik Job Board" instead of "Rubrik" on another), so it is not
    a safe key to filter a delisting UPDATE on: a mismatch there would
    either silently sweep nothing (filter matches zero rows) or, worse,
    nothing stable to tell one company's rows apart from another's at all.

    What IS stable: `external_id` is unique per `source` across every
    company (models.Job's uq_job_source_external_id spans the whole source,
    and greenhouse/lever/ashby ids are platform-wide, not per-token), so a
    SOURCE-wide sweep using every token's combined ids is safe — PROVIDED
    every token this run actually returned something. If even one token
    came back empty (a dead board, or a config.py token that's gone 404 —
    indistinguishable from each other, same empty-payload trap as any other
    source), the whole source is marked untrustworthy for this run: callers
    must not sweep using jobs from an untrustworthy fetch, because an empty
    token's rows would otherwise look "absent" from the combined id set and
    get delisted by mistake. This trades per-token availability (one flaky
    board no longer blocks delisting for only that board) for correctness
    (never cross-contaminate between companies) — the next run picks it back
    up once the flaky token recovers. See task-5-report.md for the schema
    constraint this works around (no persisted token column on Job).

    Trust is judged on the RAW fetch, before keyword filtering: a board that
    responded but has no role matching FEED_KEYWORDS is a working fetch, not a
    dead one. Judging it after filtering meant all nine Greenhouse tokens had to
    have an open PM role in the same run or nothing was ever delisted.
    """
    source_jobs = []
    trustworthy = True
    for token in tokens:
        raw = fetcher(token)
        if not raw:
            trustworthy = False
        source_jobs.extend(filter_by_keywords(raw, keywords))
    return source_jobs, trustworthy


@lru_cache(maxsize=1)
def get_redis_connection() -> Redis:
    # One client per process: its pool reuses sockets. A new client per call leaked
    # one socket each in the worker until Redis Cloud's 30-client cap was hit.
    return Redis.from_url(get_settings().redis_url)


def get_queue(name: str = "default") -> Queue:
    return Queue(name, connection=get_redis_connection())


def discover_jobs_task(job_id: str | None = None) -> dict:
    """Fetch from every configured connector, normalize, dedupe, upsert.
    Runs in an RQ worker process — no longer blocks an HTTP request.

    job_id (SPEC.md §3.6 idempotency, layer 2 — execution claim): when set
    (the manual /discover/run path, which derives a per-minute job_id and
    passes unique=True at enqueue for layer 1), a Redis SETNX claim guards
    against a retried/duplicate execution double-running the same window's
    fetch. The scheduler's own periodic call passes no job_id — it already
    prevents duplicate registration itself (run_scheduler.py's cancel loop),
    so no claim is needed there.
    """
    if job_id is not None:
        redis_conn = get_redis_connection()
        claimed = redis_conn.set(f"idempotency:discover:{job_id}", "1", nx=True, ex=600)
        if not claimed:
            return {"skipped": True, "reason": "already claimed"}

    all_jobs = []
    # Task 5: (source, jobs) per source this run fetched a qualifying,
    # trustworthy full listing for — swept for delistings after upsert_jobs,
    # below. remotive/reed never go in here (see SWEEPABLE_SOURCES).
    sweep_batches: list[tuple[str, list[dict]]] = []

    for kw in conn_config.REMOTIVE_KEYWORDS:
        all_jobs.extend(fetch_remotive_jobs(kw))
    for kw in conn_config.REED_KEYWORDS:
        all_jobs.extend(fetch_reed_jobs(kw))
    # A company board returns every opening; keep the target titles only (FEED_KEYWORDS).
    kw = conn_config.FEED_KEYWORDS
    for source_name, tokens, fetcher in (
        ("greenhouse", conn_config.GREENHOUSE_BOARD_TOKENS, fetch_greenhouse_jobs),
        ("lever", conn_config.LEVER_COMPANY_TOKENS, fetch_lever_jobs),
        ("ashby", conn_config.ASHBY_ORG_TOKENS, fetch_ashby_jobs),
    ):
        source_jobs, trustworthy = _fetch_ats_source(fetcher, tokens, kw)
        all_jobs.extend(source_jobs)
        sweep_batches.append((source_name, source_jobs if trustworthy else []))

    # ADR-015 multi-source: the keyless public feeds. Reported per source rather
    # than merged into one count — with six boards, "0 inserted" has to be
    # traceable to which board went quiet.
    feed_jobs, feed_report = fetch_enabled_feeds(
        conn_config.ENABLED_FEEDS, conn_config.FEED_KEYWORDS
    )
    all_jobs.extend(feed_jobs)
    # Each keyless feed returns its whole board in one fetch (no per-token
    # split), so the sweep scopes to source only — group this run's results
    # by source rather than re-fetching.
    for name in conn_config.ENABLED_FEEDS:
        sweep_batches.append((name, [j for j in feed_jobs if j["source"] == name]))

    for j in all_jobs:
        j["canonical_hash"] = canonical_hash(j["company"], j["title"], j.get("location"))

    with session_scope() as db:
        inserted, updated, skipped = upsert_jobs(db, all_jobs)
        for source, jobs in sweep_batches:
            _sweep_delisted(db, source, jobs)
        backfill_job_embeddings(db)

    return {
        "fetched": len(all_jobs),
        "inserted": inserted,
        "updated": updated,
        "skipped_duplicates": skipped,
        "feeds": feed_report,
    }


def prepare_applications_task(application_ids: list[str]) -> dict:
    """Sub-project #2's async batch-prep entrypoint — tailors + truth-checks
    each application and flips it to ready_for_review. Runs in an RQ worker
    process, same reasoning as discover_jobs_task: this can be slow (real
    LLM calls per application) and must not block the request thread.
    """
    prepared, failed = 0, []
    with session_scope() as db:
        for application_id in application_ids:
            application = db.query(models.Application).filter(models.Application.id == application_id).first()
            if application is None:
                failed.append(application_id)
                continue
            try:
                prepare_application_for_review(db, application)
                prepared += 1
            except Exception as exc:
                failed.append(application_id)
                db.rollback()
    return {"prepared": prepared, "failed": failed}


def run_campaign_task(campaign_id: str, run_id: str | None = None, scheduled: bool = False) -> dict:
    """ADR-015 §2 — one autonomous run of a campaign, inside its approved bounds.

    run_id (same two-layer idempotency as discover_jobs_task): layer 1 is the
    enqueue-side `unique=True` on a per-minute job_id in main.py; this is
    layer 2, the execution claim, so a retried or duplicated execution of the
    same run can't double-create. The real cap guarantee does NOT depend on
    this claim — campaigns.remaining_quota recounts the campaign's
    applications for today inside the run itself (test_campaigns.py's
    double-run test deliberately lets both claims succeed to prove that). The
    claim only avoids the wasted LLM work.
    """
    if run_id is not None:
        claimed = get_redis_connection().set(
            f"idempotency:campaign:{run_id}", "1", nx=True, ex=600
        )
        if not claimed:
            return {"skipped": True, "reason": "already claimed"}

    with session_scope() as db:
        campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
        if campaign is None:
            return {"skipped": True, "reason": "campaign not found", "created": 0, "prepared": 0}
        result = run_campaign(db, campaign)
        if scheduled and result["created"]:
            # One row per scheduled run that did something, so the user can see
            # Maggie ran unasked — but idle hourly sweeps stay out of the list.
            created = result["created"]
            reason = f"Started {created} application{'s' if created != 1 else ''}."
            write_event(db, campaign.profile.user_id, "campaign.scheduled_run",
                        {"campaign_id": campaign.id, "created": created, "reason": reason})
            db.commit()
        return result


def embed_backlog_task() -> dict:
    """Scheduled: one backfill pass over jobs saved without a vector. Discovery also
    runs one, but only hourly while it adds ~100 jobs; on the free tier that backlog
    never cleared and unembedded jobs can't be matched (found live, 2026-09-29)."""
    from campaigns import _in_bounds
    with session_scope() as db:
        # Jobs an active campaign asks for first; the free tier is too slow to spend on the rest.
        unembedded = db.query(models.Job).filter(models.Job.embedding.is_(None))
        active = db.query(models.Campaign).filter(models.Campaign.status == models.CampaignStatus.active).all()
        wanted = {j.id for c in active for j in _in_bounds(unembedded, c)}
        return {"embedded": backfill_job_embeddings(db, only_ids=wanted or None)}


def sweep_campaigns_task() -> dict:
    """Scheduled (workers/run_scheduler.py): for every active campaign, rebuild
    its profile's matches and enqueue a run. Runs on the owner role with no
    request, so there is no RLS tenant — every query here and downstream is
    scoped by campaign.id / profile_id explicitly.

    Each campaign gets its own session and try/except: one user's bad data
    must never stop everyone else's run.
    """
    bucket = int(time.time() // CAMPAIGN_SWEEP_INTERVAL_SECONDS)
    with session_scope() as db:
        campaign_ids = [cid for (cid,) in db.query(models.Campaign.id).filter(
            models.Campaign.status == models.CampaignStatus.active
        )]

    enqueued, failed = [], []
    for campaign_id in campaign_ids:
        try:
            with session_scope() as db:
                campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
                # No facts, or no job embeddings (no VOYAGE_API_KEY) → [] and the
                # run works from the matches that already exist.
                build_matches(db, campaign.profile)
            # rq 2.x ids: [A-Za-z0-9_-] only. "sweep" keeps these apart from manual run ids.
            run_id = f"campaign-{campaign_id}-sweep-{bucket}"
            try:
                get_queue().enqueue(
                    run_campaign_task, job_id=run_id, unique=True,
                    kwargs={"campaign_id": campaign_id, "run_id": run_id, "scheduled": True},
                )
            except DuplicateJobError:
                pass  # already queued in this window
            enqueued.append(campaign_id)
        except Exception:
            logger.exception("scheduled sweep failed for campaign %s", campaign_id)
            failed.append(campaign_id)
    return {"enqueued": enqueued, "failed": failed}


def plan_form_task(job_id: str) -> dict:
    """ADR-016: run the read-only Stagehand planner on one job's form and store the plan."""
    with session_scope() as db:
        job = db.query(models.Job).filter(models.Job.id == job_id).first()
        row = plan_job(db, job) if job else None
        return {"job_id": job_id, "status": row.status if row else "skipped"}


def sweep_form_plans_task() -> dict:
    """Scheduled (workers/run_scheduler.py): plan up to 10 jobs someone is about to
    apply to (ready_for_review / approved) that have no form_plans row yet. Owner
    role, no tenant, like sweep_campaigns_task: jobs and form_plans are global and
    the application join only reads status. A failed row is not retried here.

    ponytail: only jobs whose source is a routed ATS (formplans.ROUTED_ATS), so others (which never
    get a row) can't fill the 10 slots every hour. A feed job that resolves to an
    ATS is missed; plan it with `python -m formplans --job-id` if that matters.
    """
    with session_scope() as db:
        job_ids = [jid for (jid,) in db.query(models.Job.id)
                   .join(models.Application, models.Application.job_id == models.Job.id)
                   .outerjoin(models.FormPlan, models.FormPlan.job_id == models.Job.id)
                   .filter(models.Application.status.in_([models.ApplicationStatus.ready_for_review,
                                                          models.ApplicationStatus.approved]),
                           models.Job.source.in_(list(ROUTED_ATS)),
                           models.FormPlan.id.is_(None))
                   .distinct().limit(10)]

    for job_id in job_ids:
        try:
            get_queue().enqueue(
                plan_form_task, job_id=f"plan-{job_id}", unique=True, job_timeout=600,
                kwargs={"job_id": job_id},
            )
        except DuplicateJobError:
            pass  # already queued
    return {"enqueued": job_ids}
