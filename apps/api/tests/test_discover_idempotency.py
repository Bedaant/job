from unittest.mock import MagicMock, patch

from workers.jobs import discover_inline, discover_jobs_task


def _patch_connectors():
    return (
        patch("workers.jobs.fetch_remotive_jobs", return_value=[]),
        patch("workers.jobs.fetch_reed_jobs", return_value=[]),
        patch("workers.jobs.fetch_greenhouse_jobs", return_value=[]),
        patch("workers.jobs.fetch_lever_jobs", return_value=[]),
        patch("workers.jobs.fetch_ashby_jobs", return_value=[]),
        patch("workers.jobs.fetch_workday_jobs", return_value=[]),
        # ADR-015's six public feeds. Without this stub these tests make real
        # network calls (and real Voyage embedding calls) — it happened once.
        patch("workers.jobs.fetch_enabled_feeds", return_value=([], {})),
    )


@patch("workers.jobs.get_queue")
@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.session_scope")
def test_discover_runs_when_claim_acquired(mock_session_scope, mock_get_redis, mock_get_queue):
    redis = MagicMock()
    redis.set.return_value = True  # SETNX succeeded
    mock_get_redis.return_value = redis
    mock_session_scope.return_value.__enter__.return_value = MagicMock()

    result = discover_jobs_task(job_id="discover:123")

    assert result.get("skipped") is not True
    assert result["enqueued"] == mock_get_queue.return_value.enqueue.call_count > 0
    redis.set.assert_called_once_with("idempotency:discover:discover:123", "1", nx=True, ex=600)


@patch("workers.jobs.get_redis_connection")
def test_discover_skips_when_claim_already_held(mock_get_redis):
    redis = MagicMock()
    redis.set.return_value = False  # SETNX failed — another worker already claimed it
    mock_get_redis.return_value = redis

    result = discover_jobs_task(job_id="discover:123")

    assert result == {"skipped": True, "reason": "already claimed"}


@patch("workers.jobs.get_queue")
@patch("workers.jobs.session_scope")
def test_discover_without_job_id_runs_unguarded(mock_session_scope, mock_get_queue):
    """Scheduler-invoked path (no job_id) never attempts a Redis claim — the
    scheduler already prevents duplicate registration on its own (run_scheduler.py)."""
    mock_session_scope.return_value.__enter__.return_value = MagicMock()

    with patch("workers.jobs.get_redis_connection") as mock_get_redis:
        result = discover_jobs_task()
        mock_get_redis.return_value.set.assert_not_called()

    assert result["enqueued"] > 0


@patch("workers.jobs.upsert_jobs", return_value=(1, 0, 0))
@patch("workers.jobs.backfill_job_embeddings")
@patch("workers.jobs.session_scope")
def test_ats_boards_keep_every_posting(mock_scope, _embed, mock_upsert):
    """A company board returns every opening (Databricks: 879) and ADR-021 stores
    ALL of it — the keyword gate that used to trim this was a GLOBAL ingest
    filter, so a user's description now filters at match time instead."""
    mock_scope.return_value.__enter__.return_value = MagicMock()
    board = [{"company": "acme", "title": t, "location": "Bengaluru"} for t in ("Senior Product Manager", "Staff Engineer")]
    patches = _patch_connectors()
    for p in patches:
        p.start()
    try:
        with patch("workers.jobs.conn_config.GREENHOUSE_BOARD_TOKENS", ["acme"]), \
             patch("workers.jobs.conn_config.FEED_KEYWORDS", ["product manager"]), \
             patch("workers.jobs.fetch_greenhouse_jobs", return_value=board):
            discover_inline()
    finally:
        for p in patches:
            p.stop()
    # ADR-021: a company board returns every opening and we now store ALL of it.
    # This test previously asserted only the FEED_KEYWORDS match survived, which
    # was exactly the global ingest gate that decision removed — a user's
    # description filters at match time, not at collection time.
    assert [j["title"] for j in mock_upsert.call_args.args[1]] == [
        "Senior Product Manager", "Staff Engineer",
    ]
