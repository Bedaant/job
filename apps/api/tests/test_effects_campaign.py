"""Campaign auto-submit hands mailto: sends to the `effects` queue instead of sending inside the
campaign worker, so an irreversible send never runs in (or waits behind) a campaign run."""
from unittest.mock import MagicMock, patch

from rq.exceptions import DuplicateJobError

import apply_email
import campaigns
import models
from outreach.send import EFFECTS_QUEUE
from tests.test_apply_email import _app, _profile


def test_campaign_mailto_is_enqueued_on_effects_with_a_stable_id_and_never_sent_inline(db_session):
    p, f = _profile(db_session)
    mail = _app(db_session, p, f, n=1)
    queue = MagicMock()
    with patch("workers.jobs.get_queue", return_value=queue) as get_queue, \
            patch("apply_email.send_application_email") as send:
        campaigns.send_if_mailto(db_session, mail)
    send.assert_not_called()
    get_queue.assert_called_once_with(EFFECTS_QUEUE)
    args, kwargs = queue.enqueue.call_args
    assert args == (apply_email.send_application_email_task, mail.id)
    assert kwargs["job_id"] == f"apply-email-{mail.id}" and kwargs["unique"] is True


def test_web_jobs_are_not_enqueued(db_session):
    p, f = _profile(db_session)
    web = _app(db_session, p, f, n=2, apply_url="https://x.com/j")
    with patch("workers.jobs.get_queue") as get_queue:
        campaigns.send_if_mailto(db_session, web)
    get_queue.assert_not_called()


def test_a_rerun_that_finds_it_already_queued_is_not_a_failure(db_session):
    p, f = _profile(db_session)
    mail = _app(db_session, p, f, n=3)
    queue = MagicMock()
    queue.enqueue.side_effect = DuplicateJobError("already queued")
    pending = MagicMock(**{"get_status.return_value": "queued"})
    with patch("workers.jobs.get_queue", return_value=queue),             patch("rq.job.Job.fetch", return_value=pending):
        campaigns.send_if_mailto(db_session, mail)
    db_session.refresh(mail)
    assert mail.status == models.ApplicationStatus.approved
    assert not mail.notes
    assert queue.enqueue.call_count == 1
    pending.delete.assert_not_called()


def test_a_reapproval_after_a_finished_send_attempt_is_queued_again(db_session):
    """The stable id stays in Redis after the job ends (finished: result_ttl, failed: failure_ttl).
    A re-approve inside that window hit DuplicateJobError and returned, leaving the application
    `approved` with nothing queued — sent by nothing, ever."""
    p, f = _profile(db_session)
    mail = _app(db_session, p, f, n=5)
    queue = MagicMock()
    queue.enqueue.side_effect = [DuplicateJobError("stale"), MagicMock()]
    done = MagicMock(**{"get_status.return_value": "finished"})
    with patch("workers.jobs.get_queue", return_value=queue),             patch("rq.job.Job.fetch", return_value=done):
        campaigns.send_if_mailto(db_session, mail)
    done.delete.assert_called_once()
    assert queue.enqueue.call_count == 2
    db_session.refresh(mail)
    assert mail.status == models.ApplicationStatus.approved


def test_redis_down_hands_it_back_visibly_instead_of_dropping_it(db_session, caplog):
    p, f = _profile(db_session)
    mail = _app(db_session, p, f, n=4)
    with patch("workers.jobs.get_queue", side_effect=ConnectionError("redis down")):
        campaigns.send_if_mailto(db_session, mail)
    db_session.refresh(mail)
    # `approved` would be stuck forever (nothing re-polls mailto rows); same rule as batch-approve.
    assert mail.status == models.ApplicationStatus.ready_for_review
    assert "Could not queue the email (ConnectionError)" in mail.notes
    assert "ConnectionError" in caplog.text and "redis down" not in caplog.text
