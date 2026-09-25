"""Worker entrypoint. `rq worker`'s default Worker forks (os.fork, POSIX-only)
and enforces job timeouts via SIGALRM (also POSIX-only) — both crash on
Windows. SimpleWorker skips forking; TimerDeathPenalty replaces SIGALRM with
threading.Timer for the timeout enforcement. Run: python -m workers.run_worker
"""
from rq.timeouts import TimerDeathPenalty
from rq.worker import SimpleWorker

from workers.jobs import get_redis_connection


class WindowsSafeWorker(SimpleWorker):
    death_penalty_class = TimerDeathPenalty


if __name__ == "__main__":
    worker = WindowsSafeWorker(["default"], connection=get_redis_connection())
    worker.work()
