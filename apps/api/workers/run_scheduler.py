"""Periodic discovery runs (ARCHITECTURE.md §4.1: "nightly full poll, every 4h
incremental"). rq-scheduler just enqueues on schedule — the enqueued job still
runs on workers/run_worker.py, so no os.fork/SIGALRM concerns here.
Run: python -m workers.run_scheduler
"""
import logging
import time
from datetime import datetime, timedelta

from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

from rq_scheduler import Scheduler

from digest import daily_digest_task
from observability import canary_task, check_and_alert_task
from workers.jobs import (
    BACKGROUND_QUEUE,
    CAMPAIGN_SWEEP_INTERVAL_SECONDS,
    DISCOVERY_TIMEOUT_SECONDS,
    EMBED_BACKLOG_INTERVAL_SECONDS,
    discover_jobs_task,
    embed_backlog_task,
    get_redis_connection,
    refresh_campaign_searches_task,
    sweep_campaigns_task,
    sweep_form_plans_task,
)

DISCOVERY_INTERVAL_SECONDS = 4 * 60 * 60  # 4h incremental, ARCHITECTURE.md §4.1
DIGEST_INTERVAL_SECONDS = 24 * 60 * 60


def start_scheduler() -> Scheduler:
    scheduler = Scheduler(queue_name="default", connection=get_redis_connection())
    recurring = {
        discover_jobs_task: DISCOVERY_INTERVAL_SECONDS,
        # ADR-015: every active campaign gets fresh matches + a run, unasked.
        sweep_campaigns_task: CAMPAIGN_SWEEP_INTERVAL_SECONDS,
        # ADR-015 "a digest of what went out": yesterday's UTC day, just after it closes.
        daily_digest_task: DIGEST_INTERVAL_SECONDS,
        # ADR-016: plan the forms of jobs about to be applied to, before the fill needs them.
        sweep_form_plans_task: 60 * 60,
        # Voyage free tier: the discovery pass alone never clears the embedding backlog.
        embed_backlog_task: EMBED_BACKLOG_INTERVAL_SECONDS,
        # Failed discovery, queue backlog, slow stage -> one email to the owner per kind per hour.
        check_and_alert_task: 15 * 60,
        canary_task: DIGEST_INTERVAL_SECONDS,
        # Each active campaign's own titles, searched again daily (they start on activation).
        refresh_campaign_searches_task: DIGEST_INTERVAL_SECONDS,
    }
    now = datetime.utcnow()
    digest_at = now.replace(hour=0, minute=5, second=0, microsecond=0)
    first_run = {daily_digest_task: digest_at if digest_at > now else digest_at + timedelta(days=1)}
    names = {f"{func.__module__}.{func.__name__}" for func in recurring}
    # Clear any existing schedule for these jobs before re-registering, so restarting
    # the scheduler process doesn't pile up duplicate recurring jobs.
    for job in scheduler.get_jobs():
        if job.func_name in names:
            scheduler.cancel(job)

    background = {discover_jobs_task, embed_backlog_task, sweep_form_plans_task, check_and_alert_task, canary_task,
                  refresh_campaign_searches_task}
    for func, interval in recurring.items():
        scheduler.schedule(
            scheduled_time=first_run.get(func, now),
            func=func,
            interval=interval,
            repeat=None,  # repeat forever
            queue_name=BACKGROUND_QUEUE if func in background else "default",
            timeout=DISCOVERY_TIMEOUT_SECONDS if func in (discover_jobs_task, refresh_campaign_searches_task) else None,
        )
    return scheduler


def run_forever(start=start_scheduler, sleep=time.sleep) -> None:
    """A Redis blip (live: DNS "getaddrinfo failed") used to kill the scheduler for
    good. Retry with backoff (5 s doubling, 60 s cap) and re-register on reconnect."""
    delay = 5
    while True:
        try:
            start().run()
            return
        except (RedisConnectionError, RedisTimeoutError) as e:
            logging.getLogger(__name__).warning("scheduler lost Redis (%s); retrying in %ss", e, delay)
            sleep(delay)
            delay = min(delay * 2, 60)


if __name__ == "__main__":
    run_forever()
