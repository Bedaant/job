"""User clicks must never wait behind a discovery run.

Found in the user-zero end-to-end run (2026-10-10): with one worker on one queue, pressing
"Prepare" queued the tailoring job behind a discovery pass that had just started — every
board, every paid Apify search, minutes of work — so the user's click sat idle the whole time.

Slow batch work (discovery, form planning, the embedding backlog) now goes to `background`.
Everything a user is waiting on stays on `default`. Production runs one worker per queue;
a single local worker listens to both, `default` first.
"""
from unittest.mock import MagicMock, patch

from workers import jobs, run_scheduler, run_worker


def test_the_two_queues():
    assert jobs.BACKGROUND_QUEUE == "background"
    assert run_worker.queues_from_argv([]) == ["effects", "default", "background"]
    assert run_worker.queues_from_argv(["background"]) == ["background"]


def test_manual_discovery_goes_to_the_background_queue():
    import main
    from tests.test_submission_loop import _auth, _bind, _client

    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "queue-discover@example.com")
    with patch("main.get_queue") as get_queue, patch("main._workers_online", return_value=True):
        get_queue.return_value.enqueue.return_value = MagicMock(id="d1", get_status=lambda: "queued")
        assert client.post("/discover/run", headers=headers).status_code == 200
    get_queue.assert_called_with("background")


@patch("workers.run_scheduler.get_redis_connection")
@patch("workers.run_scheduler.Scheduler")
def test_scheduled_batch_work_goes_to_background_and_user_work_to_default(mock_cls, _redis):
    mock_cls.return_value.get_jobs.return_value = []
    run_scheduler.start_scheduler()
    queues = {c.kwargs["func"]: c.kwargs.get("queue_name")
              for c in mock_cls.return_value.schedule.call_args_list}
    assert queues[jobs.discover_jobs_task] == "background"
    assert queues[jobs.embed_backlog_task] == "background"
    assert queues[jobs.sweep_form_plans_task] == "background"
    # A campaign run tailors applications a user is waiting to review; the digest is cheap.
    assert queues[jobs.sweep_campaigns_task] == "default"


@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.get_queue")
@patch("workers.jobs.session_scope")
def test_form_planning_goes_to_the_background_queue(mock_scope, mock_queue, _redis, db_session):
    import models

    user = models.User(email="fp@x.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    profile = models.Profile(user_id=user.id, persona=models.Persona.developer)
    db_session.add(profile)
    job = models.Job(source="greenhouse", external_id="g1", canonical_hash="gh1", title="PM",
                     company="Acme", apply_url="https://boards.greenhouse.io/acme/jobs/1")
    db_session.add(job)
    db_session.commit()
    db_session.add(models.Application(profile_id=profile.id, job_id=job.id,
                                      status=models.ApplicationStatus.approved))
    db_session.commit()
    mock_scope.return_value.__enter__.return_value = db_session
    jobs.sweep_form_plans_task()
    mock_queue.assert_called_with("background")


def test_deploy_runs_one_worker_per_queue():
    from tests.test_deploy_commands import _command

    assert _command("worker") == ["python", "-m", "workers.run_worker", "default"]
    assert _command("worker-background") == ["python", "-m", "workers.run_worker", "background"]


# ---- discovery's time limit (also found in the user-zero run) ----------------
#
# RQ's default job timeout is 180 s. Discovery passed it within three minutes of starting —
# one LinkedIn Apify call alone may take 240 s — and `_isolate`, which turns any source's
# exception into a "source failed" row, caught the timeout like a network error. So the
# limit neither stopped the run nor saved it: the source in flight (ashby) was silently cut
# off and the run carried on past its own deadline.

def test_a_job_timeout_is_not_swallowed_as_a_source_failure():
    import pytest
    from rq.timeouts import JobTimeoutException

    def hung():
        raise JobTimeoutException("over the limit")

    with pytest.raises(JobTimeoutException):
        jobs._isolate("ashby", hung)


def test_an_ordinary_source_failure_is_still_isolated():
    def broken():
        raise ValueError("shape drift")

    found, batches, run = jobs._isolate("ashby", broken)
    assert (found, batches, run["failed"]) == ([], [], 1)


def test_manual_discovery_gets_the_discovery_time_limit():
    from tests.test_submission_loop import _auth, _bind, _client

    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "queue-timeout@example.com")
    with patch("main.get_queue") as get_queue, patch("main._workers_online", return_value=True):
        get_queue.return_value.enqueue.return_value = MagicMock(id="d1", get_status=lambda: "queued")
        client.post("/discover/run", headers=headers)
    assert get_queue.return_value.enqueue.call_args.kwargs["job_timeout"] == jobs.DISCOVERY_TIMEOUT_SECONDS
    assert jobs.DISCOVERY_TIMEOUT_SECONDS > 180


@patch("workers.run_scheduler.get_redis_connection")
@patch("workers.run_scheduler.Scheduler")
def test_scheduled_discovery_gets_the_discovery_time_limit(mock_cls, _redis):
    mock_cls.return_value.get_jobs.return_value = []
    run_scheduler.start_scheduler()
    call = next(c for c in mock_cls.return_value.schedule.call_args_list
                if c.kwargs["func"] is jobs.discover_jobs_task)
    assert call.kwargs["timeout"] == jobs.DISCOVERY_TIMEOUT_SECONDS
