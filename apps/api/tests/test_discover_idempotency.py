from unittest.mock import MagicMock, patch

from workers.jobs import discover_jobs_task


def _patch_connectors():
    return (
        patch("workers.jobs.fetch_remotive_jobs", return_value=[]),
        patch("workers.jobs.fetch_reed_jobs", return_value=[]),
        patch("workers.jobs.fetch_greenhouse_jobs", return_value=[]),
        patch("workers.jobs.fetch_lever_jobs", return_value=[]),
        patch("workers.jobs.fetch_ashby_jobs", return_value=[]),
    )


@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.session_scope")
def test_discover_runs_when_claim_acquired(mock_session_scope, mock_get_redis):
    redis = MagicMock()
    redis.set.return_value = True  # SETNX succeeded
    mock_get_redis.return_value = redis
    mock_session_scope.return_value.__enter__.return_value = MagicMock()

    patches = _patch_connectors()
    for p in patches:
        p.start()
    try:
        result = discover_jobs_task(job_id="discover:123")
    finally:
        for p in patches:
            p.stop()

    assert result.get("skipped") is not True
    assert result["fetched"] == 0
    redis.set.assert_called_once_with("idempotency:discover:discover:123", "1", nx=True, ex=600)


@patch("workers.jobs.get_redis_connection")
def test_discover_skips_when_claim_already_held(mock_get_redis):
    redis = MagicMock()
    redis.set.return_value = False  # SETNX failed — another worker already claimed it
    mock_get_redis.return_value = redis

    result = discover_jobs_task(job_id="discover:123")

    assert result == {"skipped": True, "reason": "already claimed"}


@patch("workers.jobs.session_scope")
def test_discover_without_job_id_runs_unguarded(mock_session_scope):
    """Scheduler-invoked path (no job_id) never attempts a Redis claim — the
    scheduler already prevents duplicate registration on its own (run_scheduler.py)."""
    mock_session_scope.return_value.__enter__.return_value = MagicMock()

    patches = _patch_connectors()
    for p in patches:
        p.start()
    try:
        with patch("workers.jobs.get_redis_connection") as mock_get_redis:
            result = discover_jobs_task()
            mock_get_redis.assert_not_called()
    finally:
        for p in patches:
            p.stop()

    assert result["fetched"] == 0
