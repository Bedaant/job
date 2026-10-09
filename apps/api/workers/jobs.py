"""RQ job definitions (ARCHITECTURE.md §3 `workers/`). Fixes CODE-REVIEW.md B6:
`/discover/run` used to do all connector I/O inline on the request thread. This
runs in a worker process instead.
"""
import logging
import time
from datetime import datetime, timedelta
from functools import lru_cache

from redis import Redis
from rq import Queue
from rq.exceptions import DuplicateJobError

from connectors import config as conn_config
from connectors.ashby import fetch_ashby_jobs
from connectors.feeds import fetch_enabled_feeds
from connectors.greenhouse import fetch_greenhouse_jobs
from connectors.lever import fetch_lever_jobs
from connectors.normalize import canonical_hash
from connectors.pipeline import backfill_job_embeddings, upsert_jobs
from connectors.reed import fetch_reed_jobs
from connectors.remotive import fetch_remotive_jobs
from connectors.jobspy_connector import fetch_jobspy_jobs
from connectors.workday import fetch_workday_jobs
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
# Per-campaign cap on the ids embed_backlog_task collects. backfill_job_embeddings
# only embeds ~50 a pass anyway, so gathering every in-bounds id is wasted work —
# and after ADR-021 that set is thousands of rows, re-queried every 2 minutes.
EMBED_BATCH_LIMIT = 50

# Task 5 (freshness, phase 1): sources that return a FULL listing per fetch —
# a job's absence from this run's payload is real signal it left the board.
# remotive and reed always fetch a keyword slice (connectors/config.py) —
# absence there means "not in that search", not "gone" — so they never
# qualify and must never appear here. jobspy IS wired into ingestion as of
# GAPS 3.2 (2026-10-09) and still must never appear here: it fetches a
# keyword+location slice, so absence from its payload means "not in that
# search", not "gone".
#
# A feed that returns only the newest N listings does not qualify either:
# absence from a newest-N window IS age, and this phase expires by source
# absence, never by age.
#
# Phase 2 item 4a re-measured all six keyless feeds live (2026-10-03, 1s
# pacing) to see which could be paginated to exhaustion. Exactly one can:
#   jobicy         cursor + hasMore. EXHAUSTED in 7 requests, 633 jobs.
#                  QUALIFIES — connectors/feeds.py::fetch_jobicy_jobs now
#                  pages to the end, so its payload is a complete listing.
#   himalayas      totalCount 115,729 at a server-FORCED limit of 20/page
#                  (limit=100 is ignored) = 5,786 requests per run. No.
#   arbeitnow      325/page then 100/page, links.last null; HTTP 429 at page
#                  21 (>2,450 jobs) and its terms say "please do not abuse".
#   remoteok       fixed 100-row payload (99 jobs), limit/offset ignored.
#   weworkremotely RSS, latest ~90 items.
#   workingnomads  no cursor/page/count knob; age distribution [1, 1, 2, ...,
#                  28, 29] days — a rolling ~30-day window. A job aging past
#                  30 days would vanish while still live, which is age.
# greenhouse/lever/ashby each hit one unpaginated board endpoint per token.
# So the five above keep accumulating stale rows, by decision rather than
# omission — the honest statement of coverage. They are still ingested
# (ENABLED_FEEDS), just never swept. Don't re-probe them; the numbers are in
# tests/test_feed_pagination.py's docstring, which pins this set so re-adding
# a disqualified source cannot be quiet.
# workday was REMOVED 2026-10-06. This set is documented above as "sources that
# return a FULL listing per fetch", and after ADR-021 every other member
# genuinely does — but `fetch_workday_jobs` still keyword-filters before
# hydrating (a cost control: each posting needs its own detail request, so a
# whole board is ~526 extra calls for Adobe). Its payload is therefore NOT a
# complete listing, which is exactly ADR-017 §3's trap: narrowing FEED_KEYWORDS
# would have tombstoned every live Adobe and Cisco product role on the next run.
# Workday keeps being ingested; it just stops being swept, like the five
# truncated feeds. Freshness for it needs the filter gone, which needs the
# per-job detail fetch to get cheaper.
SWEEPABLE_SOURCES = {"greenhouse", "lever", "ashby", "jobicy"}


def _sweep_delisted(db, source: str, token: str | None, jobs: list[dict]) -> None:
    """Set delisted_at=now on currently-listed (NULL) rows for one BOARD that
    are absent from `jobs` — this run's fetched payload for that board (whole
    boards since ADR-021; the sources whose payload is still filtered are not in
    SWEEPABLE_SOURCES)
    for that board. One bulk UPDATE, not per-row.

    COLLECT-D: `token` scopes the sweep to a single board within the source
    (`Job.board_token`). `token=None` means the source has no per-board concept
    (jobicy), and then only its NULL-token rows are considered.

    Scoping per board is what makes two things safe that were not:
    - **Removing a token from config no longer tombstones that board.** Its
      jobs simply are not swept this run, because nothing swept them.
    - **A flaky board no longer blocks the rest of the source.** Only boards
      that answered get a batch (see _fetch_ats_source).

    A token-scoped sweep deliberately does NOT touch rows whose `board_token`
    is NULL: those predate migration 0023 and there is no way to tell which
    board they came from. `upsert_jobs` fills the token in the next time their
    board lists them, and they become sweepable then.

    Traps this guards against:
    - A non-qualifying or unrecognized source is a no-op, defense in depth
      against a caller passing one by mistake (remotive/reed never should).
    - An EMPTY `jobs` list is treated as "no signal", never as "the board is
      actually empty". greenhouse.py/lever.py/ashby.py return [] on a
      non-200 exactly like a genuinely empty board — the two are
      indistinguishable from an empty list alone — so sweeping on empty
      would delist every still-open job the first time a board has a bad day.
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
    scope = (
        models.Job.board_token == token if token is not None
        else models.Job.board_token.is_(None)
    )
    db.query(models.Job).filter(
        models.Job.source == source,
        scope,
        models.Job.delisted_at.is_(None),
        models.Job.external_id.notin_(seen_ids),
    ).update({"delisted_at": datetime.utcnow()}, synchronize_session=False)


# Phase 2 item 3 — per-host pacing. Every fetch loop below is N requests to a
# SINGLE host (9 Greenhouse tokens, 3 Remotive keywords), and no two loops share
# a host, so spacing requests inside a loop is per-host pacing.
# ponytail: lives at the loop, not in a shared HTTP client — these loops are the
# only bursts that exist. Move it into one paced client if connectors start
# sharing a host, or if a single call needs its own rate limit.
HOST_PACING_SECONDS = 1.0


def _pace(index: int) -> None:
    """Wait before every request in a loop except the first."""
    if index:
        time.sleep(HOST_PACING_SECONDS)


# COLLECT-F — `connector_runs` retention. COLLECT-B started writing one row per
# source per run (~14/hour) and nothing removed them. `/sources` reads only the
# newest rows, so older ones are pure growth.
RUN_RETENTION_DAYS = 30
# F5's ATS classifier writes its proposed patterns to the same table, and
# `models.ConnectorRun`'s docstring calls those rows **the review surface the
# owner promotes proposals from** (decided as "no new table, no admin UI, this
# is it"). They are a human decision queue, not a log, so they are never pruned
# — age-pruning them would destroy the only copy of an un-reviewed proposal.
CLASSIFIER_SOURCE = "ats_discovery_classify"


def _prune_connector_runs(db) -> None:
    """Drop ingestion health rows older than the retention window. One bulk
    DELETE, and never the classifier's proposals."""
    cutoff = datetime.utcnow() - timedelta(days=RUN_RETENTION_DAYS)
    db.query(models.ConnectorRun).filter(
        models.ConnectorRun.ran_at < cutoff,
        models.ConnectorRun.source != CLASSIFIER_SOURCE,
    ).delete(synchronize_session=False)


def _workday_tokens() -> list[str]:
    """Workday's tenants, but only on runs where it is due.

    It is by far the most request-hungry source: a board costs
    `ceil(jobs/20)` list requests plus one detail fetch per keyword match, and
    the two configured boards measured ~4.3 minutes live. Discovery runs hourly
    and this machine runs a single RQ `SimpleWorker` (no `os.fork` on Windows),
    so fetching Workday every run would park the only worker for minutes every
    hour while campaign runs queue behind it.

    Skipping is safe, not a freshness hole: an empty token list gives an empty
    payload, and `_sweep_delisted` no-ops on empty, so a skipped run delists
    nothing rather than tombstoning the whole source.
    """
    every = getattr(conn_config, "WORKDAY_INTERVAL_HOURS", 1) or 1
    if every > 1 and datetime.utcnow().hour % every:
        return []
    return list(conn_config.WORKDAY_BOARDS)


def _isolate(source: str, fetch) -> tuple[list[dict], bool, dict]:
    """Phase 2 items 1+2 — run one source's whole fetch, isolated, and describe
    the outcome as a `connector_runs` row.

    `fetch` returns `(jobs, batches)` — the jobs to upsert, and one
    `(token, jobs)` sweep batch per board that answered (empty for sources with
    no per-board concept). This returns those plus the row.
    Nothing a connector raises may escape: `fetch_remotive_jobs` and
    `fetch_reed_jobs` call `raise_for_status()`, which used to propagate out of
    `discover_jobs_task` and throw away every OTHER source's jobs, the delisting
    sweep and the embedding backfill for the entire run.

    A failed source returns no payload and no batches, so absence from it can't
    delist anything (ADR-017 §3: a failed fetch delists nothing).

    `inserted` stays 0: dedupe happens across all sources at once in
    `upsert_jobs`, which returns batch totals, so there is no honest per-source
    insert count without attributing the batch. The row exists for health —
    "did this source answer, how much and how fast" — which `fetched`/`error`/
    `duration_ms` already say.
    """
    started = time.monotonic()
    try:
        jobs, batches = fetch()
        error = None
    except Exception as exc:  # network, auth, JSON/XML shape drift
        jobs, batches = [], []
        error = f"{type(exc).__name__}: {exc}"
        logger.exception("discovery source %s failed", source)
    return jobs, batches, {
        "source": source,
        "fetched": len(jobs),
        "failed": 1 if error else 0,
        "error": error,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }


def _feed_report_rows(report: dict) -> list[dict]:
    """`fetch_enabled_feeds` already isolates per feed and returns a kept-job
    count or an error string per source. Reuse that as the rows rather than
    building a second reporting path for the same thing.
    """
    return [{
        "source": name,
        "fetched": outcome if isinstance(outcome, int) else 0,
        "failed": 0 if isinstance(outcome, int) else 1,
        "error": None if isinstance(outcome, int) else outcome,
        "duration_ms": None,  # fetch_enabled_feeds doesn't time individual feeds
    } for name, outcome in report.items()]


def _fetch_keyword_source(fetcher, keywords: list[str]) -> tuple[list[dict], list]:
    """Remotive/Reed: one request per configured keyword, same host each time.
    Contributes no sweep batch — a keyword slice is not a full listing
    (ADR-017 §2), which `SWEEPABLE_SOURCES` enforces independently.
    """
    jobs: list[dict] = []
    for i, keyword in enumerate(keywords):
        _pace(i)
        jobs.extend(fetcher(keyword))
    return jobs, []


def _fetch_jobspy_source(keywords: list[str], locations: list[str]) -> tuple[list[dict], list]:
    """One scrape per keyword PER LOCATION (GAPS 3.2).

    The cross product is the point, not laziness: `location="India"` returns Indianapolis
    because Glassdoor prefix-matches the string, so the only way to get Indian results is
    to ask city by city. Measured 2026-10-09 — 147 unique PM jobs across 101 companies
    from six cities, against a prior measured ceiling of 23.

    Contributes **no sweep batch**. A keyword+location slice is not a complete listing,
    so absence from a payload means "not in that search", not "gone" (ADR-017 §2). That
    is also enforced independently by `SWEEPABLE_SOURCES`, and a test asserts no
    `jobspy_*` source ever joins it.

    Each scrape is a subprocess into `tools/.venv-jobspy/` (its pinned numpy 1.26.3
    conflicts with this app's numpy 2.x), so failures are isolated per query: one city
    going 403 must not cost the other five.
    """
    jobs: list[dict] = []
    i = 0
    for keyword in keywords:
        for location in locations:
            _pace(i)
            i += 1
            try:
                jobs.extend(fetch_jobspy_jobs(keyword, sites=conn_config.JOBSPY_SITES,
                                              location=location))
            except Exception:
                logger.warning(
                    "jobspy query failed for %r in %r", keyword, location, exc_info=False
                )
    return jobs, []


def _fetch_ats_source(
    fetcher, tokens: list[str]
) -> tuple[list[dict], list[tuple[str, list[dict]]]]:
    """Fetch every token's board for one per-board source (greenhouse / lever /
    ashby / workday). Returns `(all_jobs, batches)`, where `batches` has one
    `(token, jobs)` entry per board that ACTUALLY ANSWERED this run.

    COLLECT-D replaced an all-or-nothing trust flag with this. Before
    `Job.board_token` existed the sweep had to be source-wide, which forced two
    compromises:
      - if any one token returned empty, the whole source was untrustworthy and
        nothing was delisted anywhere, because an empty token's rows would look
        absent from the combined id set;
      - and removing a token from config tombstoned that board's inventory.
    Now each board is swept against its own payload, so a board that returned
    nothing simply gets no batch and nothing of its is touched.

    An empty board still contributes no batch: a 404'd or dead board and a
    genuinely empty one are indistinguishable from an empty list (ADR-017 §3),
    and guessing wrong tombstones live jobs.

    Nothing is filtered here. ADR-021 removed the keyword gate: the whole board
    is stored and a user's description filters at MATCH time instead of deciding
    what was ever collected. Trust therefore follows the fetch alone, which is
    what it always should have — judging it after filtering once meant every
    board had to have an open matching role in the same run or nothing was ever
    delisted (the latest+57 bug).

    `fetch_workday_jobs` is the one fetcher that still filters, inside itself and
    for a cost reason (one detail request per posting). This function does not
    know or care.
    """
    source_jobs: list[dict] = []
    batches: list[tuple[str, list[dict]]] = []
    for i, token in enumerate(tokens):
        _pace(i)
        raw = fetcher(token)
        # The whole board, unfiltered (ADR-021). Storing it also makes the
        # delisting sweep strictly more correct for these sources: ADR-017's
        # "editing FEED_KEYWORDS tombstones stored jobs" hazard only existed
        # because the sweep compared against a keyword-filtered payload.
        source_jobs.extend(raw)
        if raw:
            batches.append((token, list(raw)))
    return source_jobs, batches


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
    # (source, board_token, jobs) per BOARD this run got a qualifying, complete
    # listing for — swept for delistings after upsert_jobs, below. COLLECT-D
    # made this per board rather than per source; `board_token` is None for
    # sources with no per-board concept (the keyless feeds). remotive/reed never
    # go in here (see SWEEPABLE_SOURCES).
    sweep_batches: list[tuple[str, str | None, list[dict]]] = []
    # Phase 2 item 2: one connector_runs row per source per run, written in the
    # same transaction as the upsert below. Ingestion wrote none before, so
    # /sources had to infer health from job counts — which cannot tell "fetched
    # nothing this run" from "has never run".
    runs: list[dict] = []

    for source_name, fetch in (
        ("remotive", lambda: _fetch_keyword_source(fetch_remotive_jobs, conn_config.REMOTIVE_KEYWORDS)),
        ("reed", lambda: _fetch_keyword_source(fetch_reed_jobs, conn_config.REED_KEYWORDS)),
        ("greenhouse", lambda: _fetch_ats_source(fetch_greenhouse_jobs, conn_config.GREENHOUSE_BOARD_TOKENS)),
        ("lever", lambda: _fetch_ats_source(fetch_lever_jobs, conn_config.LEVER_COMPANY_TOKENS)),
        ("ashby", lambda: _fetch_ats_source(fetch_ashby_jobs, conn_config.ASHBY_ORG_TOKENS)),
        # COLLECT-C: one tenant per employer, same per-token shape as the three
        # ATS boards. fetch_workday_jobs filters on FEED_KEYWORDS inside itself
        # (it must — one detail request per posting, so a whole board is ~526
        # extra calls for Adobe). That is why workday is NOT in
        # SWEEPABLE_SOURCES: its payload is not a complete listing.
        ("workday", lambda: _fetch_ats_source(fetch_workday_jobs, _workday_tokens())),
        # GAPS 3.2, closed 2026-10-09. Built long ago and never wired; see
        # _fetch_jobspy_source for why it is per-city and why it is not sweepable.
        ("jobspy", lambda: _fetch_jobspy_source(
            conn_config.JOBSPY_KEYWORDS, conn_config.JOBSPY_LOCATIONS)),
    ):
        source_jobs, batches, run = _isolate(source_name, fetch)
        all_jobs.extend(source_jobs)
        runs.append(run)
        sweep_batches.extend((source_name, token, jobs) for token, jobs in batches)

    # ADR-015 multi-source: the keyless public feeds. Reported per source rather
    # than merged into one count — with six boards, "0 inserted" has to be
    # traceable to which board went quiet.
    # Empty keyword list = "keep everything" (filter_by_keywords' own contract).
    # Same reasoning as _fetch_ats_source: the feeds return their whole board and
    # we store it, so a user's description filters at MATCH time instead of
    # deciding what was ever collected (ADR-021).
    feed_jobs, feed_report = fetch_enabled_feeds(conn_config.ENABLED_FEEDS, [])
    all_jobs.extend(feed_jobs)
    runs.extend(_feed_report_rows(feed_report))
    # Each keyless feed returns its whole board in one fetch and has no
    # per-board split, so its batch carries board_token=None and the sweep
    # scopes to that source's NULL-token rows. Group this run's results by
    # source rather than re-fetching.
    for name in conn_config.ENABLED_FEEDS:
        sweep_batches.append((name, None, [j for j in feed_jobs if j["source"] == name]))

    for j in all_jobs:
        j["canonical_hash"] = canonical_hash(j["company"], j["title"], j.get("location"))

    with session_scope() as db:
        inserted, updated, skipped = upsert_jobs(db, all_jobs)
        for source, token, jobs in sweep_batches:
            _sweep_delisted(db, source, token, jobs)
        for run in runs:
            db.add(models.ConnectorRun(**run))
        _prune_connector_runs(db)
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
        active = db.query(models.Campaign).filter(models.Campaign.status == models.CampaignStatus.active).all()
        # ids only, capped per campaign. Was `db.query(models.Job)`, which
        # materialised full ORM rows (description included) for every unembedded
        # in-bounds job, once per campaign, every 2 minutes — fine at a
        # ~1,800-row pool, not after ADR-021 made it ~5,000 and growing.
        # `_in_bounds` only filters on Job columns, so an id-only query works.
        unembedded = db.query(models.Job.id).filter(models.Job.embedding.is_(None))
        wanted = {
            row[0]
            for c in active
            for row in _in_bounds(unembedded, c).limit(EMBED_BATCH_LIMIT)
        }
        # `wanted or None` is DELIBERATE, and a review of the ADR-021 change
        # called it starvation. It isn't: an empty `wanted` means no active
        # campaign has anything unembedded left in bounds, so nobody is waiting
        # and the pass spends otherwise-idle budget working through the rest —
        # "campaign jobs FIRST", not "campaign jobs only". The second assertion
        # in test_scheduled_runs.py::test_embed_backlog_task_embeds_jobs_the_
        # active_campaigns_want_first pins exactly that.
        #
        # What ADR-021 did change is the size of "the rest": thousands of
        # postings nobody asked for, which now consume the free tier's 200M-token
        # allowance in the background. That is a quota question, not a
        # correctness one — revisit if the allowance starts binding.
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
