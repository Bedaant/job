"""RQ job definitions (ARCHITECTURE.md §3 `workers/`). Fixes CODE-REVIEW.md B6:
`/discover/run` used to do all connector I/O inline on the request thread. This
runs in a worker process instead.
"""
from redis import Redis
from rq import Queue

from connectors import config as conn_config
from connectors.ashby import fetch_ashby_jobs
from connectors.greenhouse import fetch_greenhouse_jobs
from connectors.lever import fetch_lever_jobs
from connectors.normalize import canonical_hash
from connectors.pipeline import upsert_jobs
from connectors.reed import fetch_reed_jobs
from connectors.remotive import fetch_remotive_jobs
from core.config import get_settings
from database import session_scope

import models
from batch_prep import prepare_application_for_review


def get_redis_connection() -> Redis:
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

    for kw in conn_config.REMOTIVE_KEYWORDS:
        all_jobs.extend(fetch_remotive_jobs(kw))
    for kw in conn_config.REED_KEYWORDS:
        all_jobs.extend(fetch_reed_jobs(kw))
    for token in conn_config.GREENHOUSE_BOARD_TOKENS:
        all_jobs.extend(fetch_greenhouse_jobs(token))
    for token in conn_config.LEVER_COMPANY_TOKENS:
        all_jobs.extend(fetch_lever_jobs(token))
    for token in conn_config.ASHBY_ORG_TOKENS:
        all_jobs.extend(fetch_ashby_jobs(token))

    for j in all_jobs:
        j["canonical_hash"] = canonical_hash(j["company"], j["title"], j.get("location"))

    with session_scope() as db:
        inserted, skipped = upsert_jobs(db, all_jobs)

    return {"fetched": len(all_jobs), "inserted": inserted, "skipped_duplicates": skipped}


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
