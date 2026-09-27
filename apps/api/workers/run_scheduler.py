"""Periodic discovery runs (ARCHITECTURE.md §4.1: "nightly full poll, every 4h
incremental"). rq-scheduler just enqueues on schedule — the enqueued job still
runs on workers/run_worker.py, so no os.fork/SIGALRM concerns here.
Run: python -m workers.run_scheduler
"""
from datetime import datetime

from rq_scheduler import Scheduler

from workers.jobs import (
    CAMPAIGN_SWEEP_INTERVAL_SECONDS,
    discover_jobs_task,
    get_redis_connection,
    sweep_campaigns_task,
)

DISCOVERY_INTERVAL_SECONDS = 4 * 60 * 60  # 4h incremental, ARCHITECTURE.md §4.1


def start_scheduler() -> Scheduler:
    scheduler = Scheduler(queue_name="default", connection=get_redis_connection())
    recurring = {
        discover_jobs_task: DISCOVERY_INTERVAL_SECONDS,
        # ADR-015: every active campaign gets fresh matches + a run, unasked.
        sweep_campaigns_task: CAMPAIGN_SWEEP_INTERVAL_SECONDS,
    }
    names = {f"{func.__module__}.{func.__name__}" for func in recurring}
    # Clear any existing schedule for these jobs before re-registering, so restarting
    # the scheduler process doesn't pile up duplicate recurring jobs.
    for job in scheduler.get_jobs():
        if job.func_name in names:
            scheduler.cancel(job)

    for func, interval in recurring.items():
        scheduler.schedule(
            scheduled_time=datetime.utcnow(),
            func=func,
            interval=interval,
            repeat=None,  # repeat forever
        )
    return scheduler


if __name__ == "__main__":
    scheduler = start_scheduler()
    scheduler.run()
