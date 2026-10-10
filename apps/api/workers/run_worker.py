"""Worker entrypoint. `rq worker`'s default Worker forks (os.fork, POSIX-only)
and enforces job timeouts via SIGALRM (also POSIX-only) — both crash on
Windows. SimpleWorker skips forking; TimerDeathPenalty replaces SIGALRM with
threading.Timer for the timeout enforcement.

Run: python -m workers.run_worker [queue ...]
With no queue names it listens to `effects`, `default`, then `background` — right for one local
process. Production runs one worker per queue so a discovery pass never holds up a click.
"""
import sys

from rq.timeouts import TimerDeathPenalty
from rq.worker import SimpleWorker

from outreach.send import EFFECTS_QUEUE
from workers.jobs import BACKGROUND_QUEUE, get_redis_connection


class WindowsSafeWorker(SimpleWorker):
    death_penalty_class = TimerDeathPenalty


def queues_from_argv(argv: list[str]) -> list[str]:
    return list(argv) or [EFFECTS_QUEUE, "default", BACKGROUND_QUEUE]


if __name__ == "__main__":
    worker = WindowsSafeWorker(queues_from_argv(sys.argv[1:]), connection=get_redis_connection())
    worker.work()
