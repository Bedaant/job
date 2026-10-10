"""Discovery as one RQ job per board/source (architecture plan, intake).

The old shape fetched every source into memory and saved once at the end: three real runs on
2026-10-10 lost ~50 minutes of fetching each because the single save at the end failed. Now
the coordinator only enqueues; each unit fetches, saves, sweeps and logs its own run row, so
a failure costs that unit alone.
"""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

import models
import workers.jobs as wj

PM = "Senior Product Manager"


def _board(source, token, *titles):
    return [{"source": source, "external_id": f"{token}-{i}", "company": token.title(),
             "title": t, "location": "Remote", "apply_url": f"https://x/{token}/{i}",
             "description": "d", "board_token": token} for i, t in enumerate(titles)]


@contextmanager
def _offline(db, **overrides):
    stubs = {
        "fetch_remotive_jobs": MagicMock(return_value=[]),
        "fetch_reed_jobs": MagicMock(return_value=[]),
        "fetch_greenhouse_jobs": MagicMock(return_value=[]),
        "fetch_lever_jobs": MagicMock(return_value=[]),
        "fetch_ashby_jobs": MagicMock(return_value=[]),
        "fetch_workday_jobs": MagicMock(return_value=[]),
        "fetch_jobspy_jobs": MagicMock(return_value=[]),
        "fetch_linkedin_jobs": MagicMock(return_value=[]),
        "fetch_linkedin_posts": MagicMock(return_value=[]),
        "fetch_enabled_feeds": MagicMock(return_value=([], {})),
        **overrides,
    }
    scope = MagicMock()
    scope.return_value.__enter__.return_value = db
    scope.return_value.__exit__.return_value = False
    patches = [patch(f"workers.jobs.{n}", s) for n, s in stubs.items()]
    patches += [
        patch("workers.jobs.session_scope", scope),
        patch("workers.jobs.time.sleep"),
        patch("workers.jobs.conn_config.GREENHOUSE_BOARD_TOKENS", ["acme", "bolt"]),
        patch("workers.jobs.conn_config.LEVER_COMPANY_TOKENS", []),
        patch("workers.jobs.conn_config.ASHBY_ORG_TOKENS", []),
        patch("workers.jobs.conn_config.WORKDAY_BOARDS", {}),
    ]
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()
        db.commit()


def test_the_coordinator_enqueues_one_background_job_per_board_and_saves_nothing_itself(db_session):
    queue = MagicMock()
    with _offline(db_session), patch("workers.jobs.get_queue", return_value=queue) as get_queue:
        result = wj.discover_jobs_task()

    get_queue.assert_called_with(wj.BACKGROUND_QUEUE)
    units = [(c.kwargs["kwargs"]["source"], c.kwargs["kwargs"]["token"]) for c in queue.enqueue.call_args_list]
    assert ("greenhouse", "acme") in units and ("greenhouse", "bolt") in units
    assert ("feeds", None) in units and ("remotive", None) in units
    assert result == {"enqueued": len(units)}
    assert all(c.args[0] is wj.discover_unit_task for c in queue.enqueue.call_args_list)
    assert all(c.kwargs["job_timeout"] == wj.DISCOVERY_TIMEOUT_SECONDS for c in queue.enqueue.call_args_list)
    assert db_session.query(models.ConnectorRun).count() == 0


def test_a_held_claim_enqueues_nothing():
    redis, queue = MagicMock(), MagicMock()
    redis.set.return_value = False
    with patch("workers.jobs.get_redis_connection", return_value=redis), \
         patch("workers.jobs.get_queue", return_value=queue):
        assert wj.discover_jobs_task(job_id="discover-1") == {"skipped": True, "reason": "already claimed"}
    queue.enqueue.assert_not_called()


def test_a_board_whose_save_fails_loses_only_that_board(db_session):
    real = wj.upsert_jobs

    def upsert(db, jobs):
        if jobs[0]["board_token"] == "acme":
            raise RuntimeError("save blew up")
        return real(db, jobs)

    gh = MagicMock(side_effect=lambda token: _board("greenhouse", token, PM))
    with _offline(db_session, fetch_greenhouse_jobs=gh), patch("workers.jobs.upsert_jobs", side_effect=upsert):
        wj.discover_inline()

    assert [j.board_token for j in db_session.query(models.Job)] == ["bolt"]
    runs = {(r.source, r.token): r for r in db_session.query(models.ConnectorRun)}
    assert runs[("greenhouse", "acme")].failed == 1
    assert "RuntimeError" in runs[("greenhouse", "acme")].error
    assert runs[("greenhouse", "bolt")].failed == 0


def test_a_unit_run_row_carries_its_board_honest_insert_count_and_stage_timings(db_session):
    gh = MagicMock(side_effect=lambda token: _board("greenhouse", token, PM, "Designer"))
    with _offline(db_session, fetch_greenhouse_jobs=gh):
        result = wj.discover_unit_task("greenhouse", "acme")

    assert result["inserted"] == 2
    run = db_session.query(models.ConnectorRun).one()
    assert (run.source, run.token, run.fetched, run.inserted) == ("greenhouse", "acme", 2, 2)
    assert run.fetch_ms is not None and run.save_ms is not None


def test_consecutive_boards_of_one_host_are_paced_but_the_first_is_not(db_session):
    queue = MagicMock()
    with _offline(db_session), patch("workers.jobs.get_queue", return_value=queue):
        wj.discover_jobs_task()
    pace = {c.kwargs["kwargs"]["token"]: c.kwargs["kwargs"]["pace"]
            for c in queue.enqueue.call_args_list if c.kwargs["kwargs"]["source"] == "greenhouse"}
    assert pace == {"acme": False, "bolt": True}


@pytest.mark.parametrize("pace, sleeps", [(True, 1), (False, 0)])
def test_a_paced_unit_waits_before_fetching(db_session, pace, sleeps):
    with _offline(db_session):
        with patch("workers.jobs.time.sleep") as sleep:
            wj.discover_unit_task("greenhouse", "acme", pace=pace)
    assert sleep.call_count == sleeps
