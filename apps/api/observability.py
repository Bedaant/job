"""Ops visibility: GET /ops/health, owner alerts, and the daily canary.

Every problem found on 2026-10-10 (a save killed by Neon, a 290 s stage, a click queued behind
discovery) was found with hand-written probes. This makes the system report them itself.
"""
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import models
from connectors.normalize import canonical_hash, coerce_posted_at, normalize_location
from connectors.pipeline import upsert_jobs
from core.config import get_settings
from core.deps import require_owner
from database import get_db
from digest import smtp_sender
from matching.scoring import compute_match_score

logger = logging.getLogger(__name__)

QUEUES = ("default", "background", "effects")
BACKLOG_THRESHOLD = 50
STAGE_BUDGET_MS = 10 * 60 * 1000
ALERT_TTL_SECONDS = 60 * 60
_RECENT_FAILURES = 50


def _utc_naive(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _redis():
    from workers.jobs import get_redis_connection
    return get_redis_connection()


def _queue_stats(redis) -> tuple[dict, datetime | None]:
    """Depth and failure count per queue, plus when discovery last failed."""
    from rq import Queue
    from rq.job import Job

    stats, last_failed = {}, None
    for name in QUEUES:
        queue = Queue(name, connection=redis)
        registry = queue.failed_job_registry
        stats[name] = {"queued": queue.count, "failed": registry.count}
        ids = registry.get_job_ids(0, _RECENT_FAILURES - 1, desc=True, cleanup=False)
        for job in Job.fetch_many(ids, connection=redis):
            if job and (job.func_name or "").endswith("discover_jobs_task") and job.ended_at:
                ended = _utc_naive(job.ended_at)
                last_failed = max(last_failed, ended) if last_failed else ended
    return stats, last_failed


def health(db: Session, redis) -> dict:
    queues, last_failed = _queue_stats(redis)
    now = datetime.utcnow()
    sources: dict[str, dict] = {}
    # ponytail: newest 500 rows, first per source wins (same as /sources); join if sources outgrow it.
    for run in db.query(models.ConnectorRun).order_by(models.ConnectorRun.ran_at.desc()).limit(500):
        if run.source in sources:
            continue
        sources[run.source] = {
            "ran_at": run.ran_at.isoformat() if run.ran_at else None,
            "age_minutes": round((now - run.ran_at).total_seconds() / 60) if run.ran_at else None,
            "fetched": run.fetched, "inserted": run.inserted,
            "error": run.error, "duration_ms": run.duration_ms,
        }
    # ConnectorRun rows are written in the same transaction as discovery's save, so the newest
    # one is the last discovery that actually landed.
    last_saved = max((r["ran_at"] for r in sources.values() if r["ran_at"]), default=None)
    last_saved = datetime.fromisoformat(last_saved) if last_saved else None
    return {
        "queues": queues,
        "sources": sources,
        "last_discovery_saved_at": last_saved.isoformat() if last_saved else None,
        "last_discovery_failed_at": last_failed.isoformat() if last_failed else None,
        "discovery_failed": bool(last_failed and (last_saved is None or last_failed > last_saved)),
    }


router = APIRouter()


@router.get("/ops/health")
def ops_health(db: Session = Depends(get_db), user: models.User = Depends(require_owner)):
    return health(db, _redis())


def send_alert(redis, kind: str, body: str, sender=None) -> bool:
    """Email the owner; at most one alert per kind per hour."""
    settings = get_settings()
    if not settings.alert_email or (sender is None and not settings.smtp_host):
        logger.warning("ops alert %s not sent: ALERT_EMAIL or SMTP_HOST unset", kind)
        return False
    if not redis.set(f"alert:{kind}", "1", nx=True, ex=ALERT_TTL_SECONDS):
        return False
    return bool((sender or smtp_sender)(settings.alert_email, f"[ApplyScout alert] {kind}", body))


def check_and_alert(db: Session, redis, sender=None) -> list[str]:
    snap = health(db, redis)
    problems = {}
    if snap["discovery_failed"]:
        problems["discovery_failed"] = (
            f"Discovery failed at {snap['last_discovery_failed_at']}; "
            f"last successful save {snap['last_discovery_saved_at']}. See the background failed registry.")
    backed_up = {q: s["queued"] for q, s in snap["queues"].items() if s["queued"] > BACKLOG_THRESHOLD}
    if backed_up:
        problems["backlog"] = f"Queues over {BACKLOG_THRESHOLD} waiting jobs: {backed_up}"
    slow = {src: r["duration_ms"] for src, r in snap["sources"].items()
            if (r["duration_ms"] or 0) > STAGE_BUDGET_MS}
    if slow:
        problems["stage_budget"] = f"Sources over the {STAGE_BUDGET_MS // 60000} min budget (ms): {slow}"
    return [kind for kind, body in problems.items() if send_alert(redis, kind, body, sender)]


def check_and_alert_task() -> list[str]:
    from database import session_scope
    with session_scope() as db:
        return check_and_alert(db, _redis())


# --- daily canary -----------------------------------------------------------------------------
CANARY_SOURCE = "canary"
CANARY_BOARD = [
    {"id": "c1", "title": "Senior Backend Engineer", "location": "Remote - India",
     "content": "Python, PostgreSQL and Docker. FastAPI services on AWS.", "posted": "2026-10-01"},
    {"id": "c2", "title": "Product Manager, Growth", "location": "Bengaluru, India",
     "content": "Own the roadmap, run A/B Testing, write OKRs, work in Agile teams.", "posted": "2026-10-02"},
    {"id": "c3", "title": "Data Analyst", "location": "Remote",
     "content": "SQL, Tableau and Data Analysis for marketing.", "posted": "2026-10-03"},
]
_CANARY_PROFILE_SKILLS = ["Python", "PostgreSQL", "SQL", "Agile"]


def _canary_jobs() -> list[dict]:
    jobs = []
    for raw in CANARY_BOARD:
        job = {
            "source": CANARY_SOURCE, "board_token": None, "external_id": raw["id"],
            "title": raw["title"], "company": "ApplyScout Canary",
            "location": normalize_location(raw["location"]), "remote": "remote" in raw["location"].lower(),
            "salary": None, "description": raw["content"],
            "apply_url": f"https://example.invalid/canary/{raw['id']}", "tags": [],
            "posted_at": coerce_posted_at(raw["posted"]),
        }
        job["canonical_hash"] = canonical_hash(job["company"], job["title"], job["location"])
        jobs.append(job)
    return jobs


def run_canary(db: Session, redis, sender=None) -> dict:
    """Fixture board -> normalize -> real upsert (twice, for idempotency) -> scoring, then cleanup.
    Stops before embeddings, semantic matching and the truth-check: each needs a paid network call."""
    result = {"ok": False}
    try:
        # Embedding is the paid step; returning None takes the pipeline's own "no vectors" path.
        with patch("connectors.pipeline.embed_texts", return_value=None):
            inserted, _, _ = upsert_jobs(db, _canary_jobs())
            _, updated, _ = upsert_jobs(db, _canary_jobs())
        rows = db.query(models.Job).filter(models.Job.source == CANARY_SOURCE).all()
        scores = [compute_match_score(0.5, r.skills or [], _CANARY_PROFILE_SKILLS, r.posted_at)["score"]
                  for r in rows]
        result.update(inserted=inserted, updated_on_rerun=updated,
                      with_skills=sum(bool(r.skills) for r in rows), scored=sum(s > 0 for s in scores))
        n = len(CANARY_BOARD)
        result["ok"] = inserted == n and updated == n and result["with_skills"] == n and result["scored"] == n
    except Exception as exc:
        db.rollback()
        result["error"] = type(exc).__name__
    finally:
        db.query(models.Job).filter(models.Job.source == CANARY_SOURCE).delete(synchronize_session=False)
        db.commit()
    if not result["ok"]:
        send_alert(redis, "canary", f"Daily canary failed: {result}", sender)
    return result


def canary_task() -> dict:
    from database import session_scope
    with session_scope() as db:
        return run_canary(db, _redis())
