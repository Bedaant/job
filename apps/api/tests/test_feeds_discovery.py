"""One dead feed must not take the whole discovery run down with it.

With six sources instead of one, a single board going 500 or changing its JSON
shape is a routine event, not an outage — ADR-015's "per-source adapters that
fail visibly" means the run continues and the failure is reported, not that it
aborts or is swallowed.
"""
from unittest.mock import MagicMock, patch

from connectors import feeds


def test_fetch_enabled_feeds_survives_one_broken_source_and_reports_it():
    fetchers = {
        "good": lambda: [{"title": "Product Manager", "company": "Acme"}],
        "broken": lambda: (_ for _ in ()).throw(RuntimeError("502 Bad Gateway")),
    }
    with patch.dict(feeds.FEED_FETCHERS, fetchers, clear=True):
        jobs, report = feeds.fetch_enabled_feeds(["good", "broken"], keywords=[])

    assert [j["title"] for j in jobs] == ["Product Manager"]
    assert report["good"] == 1
    assert "502 Bad Gateway" in report["broken"]


def test_fetch_enabled_feeds_applies_keyword_filter_per_source():
    fetchers = {
        "good": lambda: [
            {"title": "Product Manager", "company": "Acme"},
            {"title": "Pastry Chef", "company": "Acme"},
        ],
    }
    with patch.dict(feeds.FEED_FETCHERS, fetchers, clear=True):
        jobs, report = feeds.fetch_enabled_feeds(["good"], keywords=["product manager"])

    assert len(jobs) == 1
    assert report["good"] == 1


def test_fetch_enabled_feeds_ignores_unknown_source_names():
    with patch.dict(feeds.FEED_FETCHERS, {}, clear=True):
        jobs, report = feeds.fetch_enabled_feeds(["typo-in-config"], keywords=[])

    assert jobs == []
    assert "unknown" in report["typo-in-config"]


@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.session_scope")
@patch("workers.jobs.upsert_jobs", return_value=(1, 0, 0))
def test_discover_jobs_task_ingests_feed_jobs_and_reports_per_source(
    mock_upsert, mock_session_scope, mock_get_redis
):
    from workers import jobs as worker_jobs

    mock_get_redis.return_value = MagicMock()
    mock_session_scope.return_value.__enter__.return_value = MagicMock()

    feed_jobs = [{
        "source": "remoteok", "external_id": "1", "title": "Product Manager",
        "company": "Acme", "location": "Remote", "remote": True, "salary": None,
        "description": "d", "apply_url": "https://x", "tags": [], "posted_at": None,
    }]
    patches = [
        patch("workers.jobs.fetch_remotive_jobs", return_value=[]),
        patch("workers.jobs.fetch_reed_jobs", return_value=[]),
        patch("workers.jobs.fetch_greenhouse_jobs", return_value=[]),
        patch("workers.jobs.fetch_lever_jobs", return_value=[]),
        patch("workers.jobs.fetch_ashby_jobs", return_value=[]),
        patch("workers.jobs.fetch_enabled_feeds", return_value=(feed_jobs, {"remoteok": 1})),
    ]
    for p in patches:
        p.start()
    try:
        result = worker_jobs.discover_inline()
    finally:
        for p in patches:
            p.stop()

    assert result["fetched"] == 1
    assert result["feeds"] == {"remoteok": 1}
    # canonical_hash must be computed for feed jobs too, or upsert dedupe breaks
    assert mock_upsert.call_args[0][1][0]["canonical_hash"]
