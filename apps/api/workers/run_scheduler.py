"""Periodic discovery runs (ARCHITECTURE.md §4.1: "nightly full poll, every 4h
incremental"). rq-scheduler just enqueues on schedule — the enqueued job still
runs on workers/run_worker.py, so no os.fork/SIGALRM concerns here.
Run: python -m workers.run_scheduler
"""
from datetime import datetime

from rq_scheduler import Scheduler

from workers.jobs import discover_jobs_task, get_redis_connection

DISCOVERY_INTERVAL_SECONDS = 4 * 60 * 60  # 4h incremental, ARCHITECTURE.md §4.1


def start_scheduler() -> Scheduler:
    scheduler = Scheduler(queue_name="default", connection=get_redis_connection())
    # Clear any existing schedule for this job before re-registering, so restarting
    # the scheduler process doesn't pile up duplicate recurring jobs.
    for job in scheduler.get_jobs():
        if job.func_name == "workers.jobs.discover_jobs_task":
            scheduler.cancel(job)

    scheduler.schedule(
        scheduled_time=datetime.utcnow(),
        func=discover_jobs_task,
        interval=DISCOVERY_INTERVAL_SECONDS,
        repeat=None,  # repeat forever
    )
    return scheduler


if __name__ == "__main__":
    scheduler = start_scheduler()
    scheduler.run()
