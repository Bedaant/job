"""Events-relay worker entrypoint (ARCHITECTURE.md §4.6) — one more
RQ-adjacent process in the existing worker pool, not an RQ job itself (it's a
tight Postgres+Redis poll loop, not queued work). Run: python -m events.run_relay
"""
import time

from redis import Redis

from core.config import get_settings
from database import session_scope
from events.relay import relay_once

POLL_INTERVAL_SECONDS = 2


def run_forever() -> None:
    redis = Redis.from_url(get_settings().redis_url)
    while True:
        with session_scope() as db:
            published = relay_once(db, redis)
        if published == 0:
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run_forever()
