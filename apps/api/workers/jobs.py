"""RQ job definitions (ARCHITECTURE.md §3 `workers/`). Fixes CODE-REVIEW.md B6:
`/discover/run` used to do all connector I/O inline on the request thread. This
runs in a worker process instead.
"""
import logging
import re
import time
from datetime import datetime, timedelta
from functools import lru_cache

from redis import Redis
from rq import Queue
from rq.exceptions import DuplicateJobError
from rq.timeouts import JobTimeoutException
from sqlalchemy import or_

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
from connectors.linkedin_jobs import fetch_linkedin_jobs
from connectors.linkedin_posts import fetch_linkedin_posts
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
    except JobTimeoutException:
        # The run's own deadline, not this source's failure. Swallowing it silently cut off
        # the source in flight and let the run continue past its limit (tests/test_queues.py).
        raise
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


def _fetch_linkedin_source(keywords: list[str], locations: list[str]) -> tuple[list[dict], list]:
    """One Apify search per keyword per location (GAPS 3.1).

    The only source that reaches the companies GAPS 3.1 lists as having no
    greenhouse/lever/ashby board at all — PhonePe appeared in the first 15 rows measured.
    A bare country works here, unlike JobSpy/Glassdoor where "India" returns Indianapolis,
    so the cross product stays small and cheap (~$0.0015/row).

    Contributes **no sweep batch**: a keyword+location slice is not a complete listing, so
    absence means "not in that search", not "gone" (ADR-017 §2). `SWEEPABLE_SOURCES`
    enforces that independently and a test pins that no `linkedin_*` source joins it.

    Each query is isolated: this is a paid third-party browser-driven actor, so one
    keyword timing out must not cost the others or the sources queued behind it.
    """
    jobs: list[dict] = []
    i = 0
    for keyword in keywords:
        for location in locations:
            _pace(i)
            i += 1
            try:
                jobs.extend(fetch_linkedin_jobs(keyword, location,
                                                rows=conn_config.LINKEDIN_JOB_ROWS))
            except Exception:
                logger.warning("linkedin query failed for %r in %r", keyword, location)
    return jobs, []


def _fetch_linkedin_posts_source(queries: list[str]) -> tuple[list[dict], list]:
    """Hiring posts: all queries in one Apify run. No sweep batch, same reason as
    `_fetch_linkedin_source` — a search slice is not a complete listing."""
    return fetch_linkedin_posts(queries, rows=conn_config.LINKEDIN_POST_ROWS), []


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


# Slow batch work (discovery, form planning, the embedding backlog). Kept off `default` so a
# user's click never waits behind a discovery pass (tests/test_queues.py).
BACKGROUND_QUEUE = "background"
# RQ's default is 180 s; one LinkedIn Apify call alone may take 240 s, and every source
# runs in sequence before a single upsert. Measured in the user-zero run.
DISCOVERY_TIMEOUT_SECONDS = 30 * 60


def get_queue(name: str = "default") -> Queue:
    return Queue(name, connection=get_redis_connection())


_ATS_FETCHERS = ("greenhouse", "lever", "ashby", "workday")


def _discovery_units() -> list[tuple[str, str | None]]:
    """One (source, board) per unit of work: a board per token for the ATS sources, one
    unit for each search-slice source, and one for the keyless feeds (which already
    isolate per feed inside fetch_enabled_feeds)."""
    return [
        ("remotive", None), ("reed", None),
        *(("greenhouse", t) for t in conn_config.GREENHOUSE_BOARD_TOKENS),
        *(("lever", t) for t in conn_config.LEVER_COMPANY_TOKENS),
        *(("ashby", t) for t in conn_config.ASHBY_ORG_TOKENS),
        # Workday is skipped on runs where it is not due (_workday_tokens).
        *(("workday", t) for t in _workday_tokens()),
        ("jobspy", None), ("linkedin", None), ("linkedin_posts", None), ("feeds", None),
    ]


def _unit_fetch(source: str, token: str | None):
    """The fetch for one unit, returning (jobs, [(token, jobs)] sweep batches).
    Looked up at call time so tests can patch the module-level connector functions."""
    if source in _ATS_FETCHERS:
        fetcher = {"greenhouse": fetch_greenhouse_jobs, "lever": fetch_lever_jobs,
                   "ashby": fetch_ashby_jobs, "workday": fetch_workday_jobs}[source]
        return lambda: _fetch_ats_source(fetcher, [token])
    return {
        "remotive": lambda: _fetch_keyword_source(fetch_remotive_jobs, conn_config.REMOTIVE_KEYWORDS),
        "reed": lambda: _fetch_keyword_source(fetch_reed_jobs, conn_config.REED_KEYWORDS),
        "jobspy": lambda: _fetch_jobspy_source(conn_config.JOBSPY_KEYWORDS, conn_config.JOBSPY_LOCATIONS),
        "linkedin": lambda: _fetch_linkedin_source(
            conn_config.LINKEDIN_JOB_KEYWORDS, conn_config.LINKEDIN_JOB_LOCATIONS),
        "linkedin_posts": lambda: _fetch_linkedin_posts_source(conn_config.LINKEDIN_POST_QUERIES),
    }[source]


def _fetch_unit(source: str, token: str | None):
    """(jobs, [(source, token, jobs)] sweep batches, connector_runs rows, feed report)."""
    if source == "feeds":
        started = time.monotonic()
        jobs, report = fetch_enabled_feeds(conn_config.ENABLED_FEEDS, [])
        runs = _feed_report_rows(report)
        fetch_ms = int((time.monotonic() - started) * 1000)
        for run in runs:
            run["fetch_ms"] = fetch_ms
        batches = [(name, None, [j for j in jobs if j["source"] == name]) for name in conn_config.ENABLED_FEEDS]
        return jobs, batches, runs, report
    jobs, batches, run = _isolate(source, _unit_fetch(source, token))
    run.update(token=token, fetch_ms=run["duration_ms"])
    return jobs, [(source, t, b) for t, b in batches], [run], None


def discover_unit_task(source: str, token: str | None = None, pace: bool = False) -> dict:
    """Fetch, save, sweep and log ONE board or source in its own transaction, so a failure
    or timeout here costs this unit alone. Saving never embeds: embed_backlog_task does."""
    if pace:
        # ponytail: spacing assumes one background worker; a shared per-host limiter if that grows.
        time.sleep(HOST_PACING_SECONDS)
    jobs, batches, runs, report = _fetch_unit(source, token)
    inserted, updated, skipped = _save_unit(source, token, jobs, batches, runs)
    return {"source": source, "token": token, "fetched": len(jobs), "inserted": inserted,
            "updated": updated, "skipped_duplicates": skipped, "feeds": report}


def _save_unit(source, token, jobs, batches, runs) -> tuple[int, int, int]:
    """Upsert, sweep and log one unit's fetch in its own transaction."""
    for j in jobs:
        j["canonical_hash"] = canonical_hash(j["company"], j["title"], j.get("location"))

    started = time.monotonic()
    inserted = updated = skipped = 0
    try:
        with session_scope() as db:
            if jobs:
                inserted, updated, skipped = upsert_jobs(db, jobs)
            for batch_source, batch_token, batch_jobs in batches:
                _sweep_delisted(db, batch_source, batch_token, batch_jobs)
            save_ms = int((time.monotonic() - started) * 1000)
            for run in runs:
                run["save_ms"] = save_ms
            if len(runs) == 1:
                runs[0]["inserted"] = inserted
            db.add_all(models.ConnectorRun(**run) for run in runs)
    except JobTimeoutException:
        raise
    except Exception as exc:
        # Logged as a failed run, then re-raised so RQ records the failure too.
        logger.exception("discovery save failed for %s/%s", source, token)
        with session_scope() as db:
            db.add(models.ConnectorRun(source=source, token=token, fetched=len(jobs), failed=1,
                                       error=f"save: {type(exc).__name__}",
                                       fetch_ms=runs[0].get("fetch_ms") if runs else None))
        raise
    return inserted, updated, skipped


def _rq_id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", text)  # rq 2.x job ids: [A-Za-z0-9_-] only


def discover_jobs_task(job_id: str | None = None) -> dict:
    """Coordinator: enqueue one discover_unit_task per board/source on the background queue.

    job_id (SPEC.md §3.6 idempotency, layer 2 — execution claim): when set (the manual
    /discover/run path, which also enqueues with unique=True), a Redis SETNX claim stops a
    retried or duplicate execution from enqueueing the same window twice. The scheduler's
    call passes no job_id; it prevents duplicate registration itself (run_scheduler.py).
    """
    if job_id is not None:
        claimed = get_redis_connection().set(f"idempotency:discover:{job_id}", "1", nx=True, ex=600)
        if not claimed:
            return {"skipped": True, "reason": "already claimed"}

    with session_scope() as db:
        _prune_connector_runs(db)
        _expire_unseen(db)

    stamp = job_id or datetime.utcnow().strftime("%Y%m%d%H%M")
    queue = get_queue(BACKGROUND_QUEUE)
    units = _discovery_units()
    previous = None
    for source, token in units:
        try:
            queue.enqueue(
                discover_unit_task, job_id=_rq_id(f"discover-{source}-{token or 'all'}-{stamp}"),
                unique=True, job_timeout=DISCOVERY_TIMEOUT_SECONDS,
                kwargs={"source": source, "token": token, "pace": source == previous},
            )
        except DuplicateJobError:
            pass  # this window's unit is already queued
        previous = source
    return {"enqueued": len(units)}


def discover_inline() -> dict:
    """Every unit in this process, in order, for scripts and tests. A failing unit is
    logged and skipped, exactly as its own RQ job would fail alone."""
    totals = {"fetched": 0, "inserted": 0, "updated": 0, "skipped_duplicates": 0, "feeds": {}}
    previous = None
    for source, token in _discovery_units():
        try:
            result = discover_unit_task(source, token, pace=source == previous)
        except Exception:
            logger.exception("discovery unit %s/%s failed", source, token)
            continue
        finally:
            previous = source
        for key in ("fetched", "inserted", "updated", "skipped_duplicates"):
            totals[key] += result[key]
        totals["feeds"].update(result["feeds"] or {})
    with session_scope() as db:
        _prune_connector_runs(db)
        _expire_unseen(db)
    return totals


# A row nobody has listed for this long is gone, whatever its source said. Search results are
# only re-seen when the same search runs again, so they get longer.
UNSEEN_EXPIRY_DAYS = 7
SEARCH_UNSEEN_EXPIRY_DAYS = 14
_SEARCH_SOURCE_PREFIXES = ("linkedin", "jobspy")


def _expire_unseen(db) -> int:
    """Delist live rows not seen within their window. Feeds that never return a complete
    listing (arbeitnow: 1,351 rows, measured 2026-10-10) could otherwise never be delisted."""
    now = datetime.utcnow()
    is_search = or_(*[models.Job.source.like(f"{p}%") for p in _SEARCH_SOURCE_PREFIXES])
    expired = 0
    for scope, days in ((~is_search, UNSEEN_EXPIRY_DAYS), (is_search, SEARCH_UNSEEN_EXPIRY_DAYS)):
        expired += db.query(models.Job).filter(
            models.Job.delisted_at.is_(None), scope,
            models.Job.last_seen_at < now - timedelta(days=days),
        ).update({"delisted_at": now}, synchronize_session=False)
    if expired:
        logger.info("expired %d job row(s) not seen recently", expired)
    return expired


# On-demand search per campaign: its titles x locations, small enough that a start costs cents.
CAMPAIGN_SEARCH_MAX_ROLES = 3
CAMPAIGN_SEARCH_MAX_LOCATIONS = 2
CAMPAIGN_SEARCH_ROWS = 25
CAMPAIGN_SEARCH_EMBED_LIMIT = 100


def _first_unique(values, limit: int) -> list[str]:
    out, seen = [], set()
    for v in values or []:
        v = (v or "").strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out[:limit]


def campaign_search_plan(campaign) -> tuple[list[str], list[str]]:
    roles = _first_unique(campaign.roles, CAMPAIGN_SEARCH_MAX_ROLES)
    locations = (_first_unique(campaign.locations, CAMPAIGN_SEARCH_MAX_LOCATIONS)
                 or list(conn_config.LINKEDIN_JOB_LOCATIONS))
    return roles, locations


def _campaign_allows(campaign, prefix: str) -> bool:
    return not campaign.sources or any(s.startswith(prefix) for s in campaign.sources)


def _search_plan_parts(campaign) -> dict[str, list]:
    """One campaign's (role, location) pairs per search source, honouring its source choices."""
    roles, locations = campaign_search_plan(campaign)
    pairs = [(r, l) for r in roles for l in locations]
    return {
        "linkedin": pairs if _campaign_allows(campaign, "linkedin") else [],
        "linkedin_posts": ([f"hiring {r} {locations[0]}" for r in roles]
                           if _campaign_allows(campaign, "linkedin_post") else []),
        "jobspy": pairs if _campaign_allows(campaign, "jobspy") else [],
    }


def _fetch_pairs(fetch_one, pairs) -> tuple[list[dict], list]:
    jobs: list[dict] = []
    for i, (role, location) in enumerate(pairs):
        _pace(i)
        try:
            jobs.extend(fetch_one(role, location))
        except Exception:
            logger.warning("search failed for %r in %r", role, location)
    return jobs, []


def _search_and_save(parts: dict[str, list], token: str) -> int:
    """Fetch each search source for these pairs/queries and save it as its own unit.
    No transaction is open during any fetch."""
    fetches = {
        "linkedin": lambda: _fetch_pairs(
            lambda r, l: fetch_linkedin_jobs(r, l, rows=CAMPAIGN_SEARCH_ROWS), parts["linkedin"]),
        "linkedin_posts": lambda: _fetch_linkedin_posts_source(parts["linkedin_posts"]),
        "jobspy": lambda: _fetch_pairs(
            lambda r, l: fetch_jobspy_jobs(r, sites=conn_config.JOBSPY_SITES, location=l),
            parts["jobspy"]),
    }
    inserted = 0
    for source, fetch in fetches.items():
        if not parts[source]:
            continue
        jobs, _batches, run = _isolate(source, fetch)
        run.update(token=token, fetch_ms=run["duration_ms"])
        try:
            inserted += _save_unit(source, token, jobs, [], [run])[0]
        except JobTimeoutException:
            raise
        except Exception:
            continue  # logged and recorded by _save_unit; the other sources still count
    return inserted


def campaign_search_task(campaign_id: str) -> dict:
    """On activation: search for ONE campaign's titles and locations, save what is found, embed
    the new in-bounds jobs, then rebuild matches and run the campaign."""
    from campaigns import _in_bounds

    with session_scope() as db:
        campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
        if campaign is None or campaign.status != models.CampaignStatus.active:
            return {"skipped": True, "reason": "campaign not active"}
        parts = _search_plan_parts(campaign)
    if not any(parts.values()):
        return {"skipped": True, "reason": "nothing to search"}

    inserted = _search_and_save(parts, f"campaign-{campaign_id}")

    with session_scope() as db:
        campaign = db.query(models.Campaign).filter(models.Campaign.id == campaign_id).first()
        wanted = [row[0] for row in _in_bounds(
            db.query(models.Job.id).filter(models.Job.embedding.is_(None)), campaign
        ).limit(CAMPAIGN_SEARCH_EMBED_LIMIT)]
        if wanted:
            backfill_job_embeddings(db, limit=len(wanted), only_ids=wanted)
        build_matches(db, campaign.profile)

    run_id = _rq_id(f"campaign-{campaign_id}-search-{int(time.time() // 60)}")
    try:
        get_queue().enqueue(run_campaign_task, job_id=run_id, unique=True,
                            kwargs={"campaign_id": campaign_id, "run_id": run_id})
    except DuplicateJobError:
        pass
    return {"campaign_id": campaign_id, "inserted": inserted, "embedded_candidates": len(wanted)}


# A user's share of the daily union search, across all their campaigns (Apify bills per row).
CAMPAIGN_SEARCH_PAIRS_PER_USER = CAMPAIGN_SEARCH_MAX_ROLES * CAMPAIGN_SEARCH_MAX_LOCATIONS


def refresh_campaign_searches_task() -> dict:
    """Scheduled daily: ONE search over the union of every active campaign's titles and
    locations, deduplicated across users and capped per user. The hourly campaign sweep and the
    embedding backlog (campaign jobs first) take it from there."""
    union: dict[str, dict] = {"linkedin": {}, "linkedin_posts": {}, "jobspy": {}}
    with session_scope() as db:
        active = (db.query(models.Campaign)
                  .filter(models.Campaign.status == models.CampaignStatus.active)
                  .order_by(models.Campaign.created_at).all())
        per_user: dict[str, dict[str, set]] = {}
        for campaign in active:
            share = per_user.setdefault(campaign.profile.user_id, {k: set() for k in union})
            for source, items in _search_plan_parts(campaign).items():
                for item in items:
                    key = item.lower() if isinstance(item, str) else tuple(x.lower() for x in item)
                    if key in share[source] or len(share[source]) >= CAMPAIGN_SEARCH_PAIRS_PER_USER:
                        continue
                    share[source].add(key)
                    union[source].setdefault(key, item)
    parts = {source: list(items.values()) for source, items in union.items()}
    if not any(parts.values()):
        return {"pairs": 0, "inserted": 0}
    inserted = _search_and_save(parts, "campaign-union")
    return {"pairs": len(parts["linkedin"]), "inserted": inserted}


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
            get_queue(BACKGROUND_QUEUE).enqueue(
                plan_form_task, job_id=f"plan-{job_id}", unique=True, job_timeout=600,
                kwargs={"job_id": job_id},
            )
        except DuplicateJobError:
            pass  # already queued
    return {"enqueued": job_ids}
