"""The suite must never touch the real Redis.

Found in the user-zero end-to-end run (2026-10-10): `REDIS_URL` in `.env` is the production
Redis Cloud instance, and every test that approved or submitted an application enqueued a real
`draft_outreach_task` there. 39 of them sat in the live queue ahead of a real user's tailoring
job, each for an application id that exists only in a test's in-memory SQLite. Harmless only
by luck: once a worker is deployed on that Redis, every local `pytest` run feeds it.
"""
import pytest


def test_a_redis_connection_cannot_reach_the_real_server():
    from workers.jobs import get_redis_connection

    with pytest.raises(RuntimeError, match="real Redis"):
        get_redis_connection().ping()


def test_enqueue_records_instead_of_sending():
    """Code under test still gets a job back, so enqueue-then-commit paths behave normally."""
    from workers.jobs import get_queue

    job = get_queue().enqueue(len, [1, 2])
    assert job is not None
