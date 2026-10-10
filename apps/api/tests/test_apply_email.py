"""Apply by email: a job whose apply_url is `mailto:` (a LinkedIn hiring post saying
"email your CV to ...") is sent the tailored resume from the user's own mailbox once
the application is approved.

State machine (mirrors claim-submission + submission-result, server-side):
  approved --claim (row lock)--> submitting --delivered--> applied
  approved --refused (address/suppressed/cap/no sender/no resume)--> ready_for_review
  submitting --sender falsy--> ready_for_review; raised--> submitted_unconfirmed
  anything not approved --> untouched (the second trigger is a no-op)

At-most-once is tested via the state transition, like test_outreach_send.py: the lock
is a no-op on SQLite, so what is provable here is that a second trigger is refused.
"""
import smtplib
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

import apply_email
import models

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _profile(db, email="u@example.com"):
    user = models.User(email=email, password_hash="x")
    db.add(user)
    db.flush()
    p = models.Profile(user_id=user.id, full_name="Asha Rao", headline="Backend engineer")
    db.add(p)
    db.flush()
    fact = models.ResumeFact(profile_id=p.id, category="experience",
                             achievement="Built a payments ledger in Python")
    db.add(fact)
    db.flush()
    return p, fact


def _app(db, profile, fact, *, apply_url="mailto:hr@acme.com", n=0,
         status=models.ApplicationStatus.approved, cover="Dear team, I built a ledger."):
    job = models.Job(source="linkedin_posts", external_id=f"e{n}", canonical_hash=f"h{n}",
                     title="Backend Engineer", company="Acme", apply_url=apply_url)
    db.add(job)
    db.flush()
    a = models.Application(
        profile_id=profile.id, job_id=job.id, status=status,
        tailored_resume_json={"bullets": [
            {"text": "Built a payments ledger in Python", "source_fact_ids": [fact.id]}]},
        tailored_cover_letter=cover,
    )
    db.add(a)
    db.commit()
    return a


def _capture():
    calls = []

    def sender(to, subject, body, attachments=None):
        calls.append((to, subject, body, attachments))
        return "msg-1"

    return sender, calls


def _send(db, application, sender):
    with patch("apply_email._sender_for", return_value=sender), \
         patch("workers.jobs.get_queue"):
        return apply_email.send_application_email(db, application.id)


def test_mailto_approved_sends_once_with_docx_and_marks_applied(db_session):
    p, f = _profile(db_session)
    a = _app(db_session, p, f)
    sender, calls = _capture()

    assert _send(db_session, a, sender) == "sent"

    assert len(calls) == 1
    to, subject, body, attachments = calls[0]
    assert to == "hr@acme.com"
    assert subject == "Application: Backend Engineer"
    # Already greets, so no "Hello,"; has no close, so one is added.
    assert body == "Dear team, I built a ledger.\n\nBest regards,\nAsha Rao"
    (name, data, mime), = attachments
    assert name.endswith(".docx") and mime == DOCX_MIME and data[:2] == b"PK"
    db_session.refresh(a)
    assert a.status == models.ApplicationStatus.applied
    assert a.applied_at is not None


def test_second_trigger_does_not_send_again(db_session):
    p, f = _profile(db_session)
    a = _app(db_session, p, f)
    sender, calls = _capture()
    _send(db_session, a, sender)

    assert _send(db_session, a, sender) == "not_approved"
    assert len(calls) == 1


def test_query_string_is_dropped_from_the_address(db_session):
    p, f = _profile(db_session)
    a = _app(db_session, p, f, apply_url="mailto:HR@acme.com?subject=Hello%20there")
    sender, calls = _capture()
    _send(db_session, a, sender)
    assert calls[0][0] == "HR@acme.com"


@pytest.mark.parametrize("url", [
    "mailto:a@acme.com,b@acme.com", "mailto:", "mailto:not-an-address",
    "mailto:a@acme.com%0D%0ABcc:x@evil.com", "https://acme.com/apply",
])
def test_anything_but_one_plain_address_is_refused(db_session, url):
    p, f = _profile(db_session)
    a = _app(db_session, p, f, apply_url=url)
    sender, calls = _capture()
    assert _send(db_session, a, sender) == "bad_address"
    assert calls == []
    db_session.refresh(a)
    assert a.status == models.ApplicationStatus.ready_for_review
    assert "address" in a.notes


def test_suppressed_address_is_refused(db_session):
    p, f = _profile(db_session)
    a = _app(db_session, p, f)
    db_session.add(models.Suppression(profile_id=None, email="hr@acme.com", reason="opt_out"))
    db_session.commit()
    sender, calls = _capture()

    assert _send(db_session, a, sender) == "suppressed"
    assert calls == []
    db_session.refresh(a)
    assert a.status == models.ApplicationStatus.ready_for_review
    assert "suppress" in a.notes


def test_no_sender_configured_fails_with_reason_not_stuck(db_session):
    from outreach.gmail import GmailNotConnected
    p, f = _profile(db_session)
    a = _app(db_session, p, f)

    with patch("apply_email._sender_for", side_effect=GmailNotConnected("no grant")):
        assert apply_email.send_application_email(db_session, a.id) == "no_sender"

    db_session.refresh(a)
    assert a.status == models.ApplicationStatus.ready_for_review
    assert "Gmail" in a.notes


def test_sender_returning_none_is_failed_not_applied(db_session):
    p, f = _profile(db_session)
    a = _app(db_session, p, f)
    assert _send(db_session, a, lambda *args, **kw: None) == "failed"
    db_session.refresh(a)
    assert a.status == models.ApplicationStatus.ready_for_review
    assert a.applied_at is None


def test_raising_sender_is_unconfirmed_and_records_type_only(db_session):
    p, f = _profile(db_session)
    a = _app(db_session, p, f)

    def boom(*args, **kw):
        raise RuntimeError("secret body hr@acme.com")

    # It may have been delivered, so never back to a re-approvable state.
    assert _send(db_session, a, boom) == "unconfirmed"
    db_session.refresh(a)
    assert a.status == models.ApplicationStatus.submitted_unconfirmed
    assert "RuntimeError" in a.notes and "secret body" not in a.notes


def test_empty_cover_letter_uses_a_fixed_template(db_session):
    p, f = _profile(db_session)
    a = _app(db_session, p, f, cover="")
    sender, calls = _capture()
    _send(db_session, a, sender)
    body = calls[0][2]
    assert "Backend Engineer" in body and "Acme" in body and "attached" in body


def test_no_grounded_bullets_is_refused(db_session):
    p, f = _profile(db_session)
    a = _app(db_session, p, f)
    a.tailored_resume_json = {"bullets": [{"text": "Invented", "source_fact_ids": ["nope"]}]}
    db_session.commit()
    sender, calls = _capture()
    assert _send(db_session, a, sender) == "no_resume"
    assert calls == []


def test_daily_cap_blocks_the_eleventh_email_application(db_session):
    p, f = _profile(db_session)
    for i in range(apply_email.DAILY_CAP):
        done = _app(db_session, p, f, n=i, status=models.ApplicationStatus.applied)
        done.applied_at = datetime.utcnow()
    # Applied yesterday, and a non-email apply today: neither counts.
    _app(db_session, p, f, n=90, status=models.ApplicationStatus.applied).applied_at = \
        datetime.utcnow() - timedelta(days=1)
    _app(db_session, p, f, n=91, apply_url="https://x.com/j",
         status=models.ApplicationStatus.applied).applied_at = datetime.utcnow()
    db_session.commit()
    a = _app(db_session, p, f, n=99)
    sender, calls = _capture()

    assert _send(db_session, a, sender) == "daily_cap"
    assert calls == []
    db_session.refresh(a)
    assert a.status == models.ApplicationStatus.ready_for_review


# --- the two approval sites ------------------------------------------------------

def test_campaign_auto_submit_sends_mailto_jobs_only(db_session):
    import campaigns
    p, f = _profile(db_session)
    mail = _app(db_session, p, f, n=1, status=models.ApplicationStatus.approved)
    web = _app(db_session, p, f, n=2, apply_url="https://x.com/j")
    with patch("apply_email.enqueue_send") as enqueue:
        campaigns.send_if_mailto(db_session, mail)
        campaigns.send_if_mailto(db_session, web)
    enqueue.assert_called_once_with(db_session, mail)


@patch("campaigns.prepare_application_for_review")
def test_run_campaign_auto_submit_triggers_the_email(mock_prepare):
    import campaigns
    from tests.test_campaigns import _campaign, _job, _match, _profile as _cprofile, _session

    def fake_prepare(db, application):
        application.status = models.ApplicationStatus.ready_for_review
        db.commit()

    mock_prepare.side_effect = fake_prepare
    db = _session()
    profile = _cprofile(db)
    campaign = _campaign(db, profile, daily_cap=1, auto_submit=True)
    _match(db, profile, _job(db, 1))

    with patch("campaigns.send_if_mailto") as trigger:
        campaigns.run_campaign(db, campaign)

    row = db.query(models.Application).one()
    trigger.assert_called_once_with(db, row)


def test_batch_approve_enqueues_mailto_and_leaves_web_jobs_to_the_extension():
    from tests.test_submission_loop import _auth, _bind, _client
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "ba@example.com")
    profile = client.post("/profiles", headers=headers, json={"persona": "developer"}).json()
    db = SessionLocal()
    ids = {}
    for n, url in (("mail", "mailto:hr@acme.com"), ("web", "https://acme.com/apply")):
        job = models.Job(source="s", external_id=n, canonical_hash=n, title="T",
                         company="Acme", apply_url=url)
        db.add(job)
        db.flush()
        app = models.Application(profile_id=profile["id"], job_id=job.id,
                                 status=models.ApplicationStatus.ready_for_review)
        db.add(app)
        db.commit()
        ids[n] = app.id
    db.close()

    queue = MagicMock()
    with patch("workers.jobs.get_queue", return_value=queue):
        resp = client.post("/applications/batch-approve", headers=headers,
                           json={"application_ids": list(ids.values())})
    assert resp.status_code == 200
    queue.enqueue.assert_called_once_with(apply_email.send_application_email_task, ids["mail"],
                                          job_id=f"apply-email-{ids['mail']}", unique=True)
    # The web job is still in the extension's queue; the mailto one never is.
    queued = client.get("/extension/work-queue", headers=headers).json()
    assert [q["application_id"] for q in queued] == [ids["web"]]


# --- senders gain attachments, backwards compatibly ------------------------------

def test_gmail_raw_mime_contains_the_attachment(db_session):
    import base64
    import email

    import crypto
    from outreach import gmail

    user = models.User(email="g@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    cred = models.GmailCredential(user_id=user.id, refresh_token_encrypted="x",
                                  email_address="g@example.com",
                                  scopes=[models.GMAIL_SEND_SCOPE])
    db_session.add(cred)
    db_session.commit()
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"id": "gm-1"}
    with patch("outreach.gmail._access_token", return_value="tok"), \
         patch("outreach.gmail.httpx.post", return_value=resp) as post:
        sender = gmail.gmail_sender(db_session, user.id)
        assert sender("hr@acme.com", "S", "B", [("cv.docx", b"PKdata", DOCX_MIME)]) == "gm-1"
        assert sender("hr@acme.com", "S", "B") == "gm-1"  # old callers unchanged

    raw = post.call_args_list[0].kwargs["json"]["raw"]
    msg = email.message_from_bytes(base64.urlsafe_b64decode(raw))
    parts = [p for p in msg.walk() if p.get_filename() == "cv.docx"]
    assert len(parts) == 1 and parts[0].get_payload(decode=True) == b"PKdata"
    assert parts[0].get_content_type() == DOCX_MIME


def test_smtp_sender_attaches_and_still_works_without(monkeypatch):
    import digest
    from workers.outreach_tasks import smtp_outreach_sender

    monkeypatch.setattr(digest, "get_settings", lambda: MagicMock(
        smtp_host="smtp.x", smtp_port=587, smtp_user="", smtp_from="me@x.com"))
    conn = MagicMock()
    conn.__enter__.return_value = conn
    with patch.object(smtplib, "SMTP", return_value=conn):
        sender = smtp_outreach_sender()
        assert sender("hr@acme.com", "S", "B", [("cv.docx", b"PKdata", DOCX_MIME)])
        assert sender("hr@acme.com", "S", "B")
    first = conn.send_message.call_args_list[0].args[0]
    assert [p.get_filename() for p in first.iter_attachments()] == ["cv.docx"]
    assert list(conn.send_message.call_args_list[1].args[0].iter_attachments()) == []


# ---- the email reads like an email (found in the user-zero run, 2026-10-10) ----
#
# The real cover letter starts "I am writing to express..." and ends on its last argument:
# no greeting, no sign-off, no name. As a letter inside a form that's fine; as the whole body
# of an email to a recruiter it reads like a pasted fragment.

def test_a_letter_without_greeting_or_signoff_gets_both(db_session):
    p, fact = _profile(db_session)
    a = _app(db_session, p, fact, cover="I am writing to apply for the role.")
    sender, calls = _capture()
    _send(db_session, a, sender)
    body = calls[0][2]
    assert body.startswith("Hello,\n\nI am writing to apply for the role.")
    assert body.rstrip().endswith("Best regards,\nAsha Rao")


def test_a_letter_that_already_greets_and_signs_is_not_doubled(db_session):
    p, fact = _profile(db_session, email="u2@example.com")
    letter = "Dear Hiring Team,\n\nI built a ledger.\n\nSincerely,\nAsha Rao"
    a = _app(db_session, p, fact, cover=letter)
    sender, calls = _capture()
    _send(db_session, a, sender)
    assert calls[0][2] == letter


def test_an_all_caps_stored_name_is_recased_in_the_signoff_and_filename(db_session):
    p, fact = _profile(db_session, email="u3@example.com")
    p.full_name = "ASHA RAO"
    db_session.commit()
    a = _app(db_session, p, fact, cover="I am writing to apply.")
    sender, calls = _capture()
    _send(db_session, a, sender)
    assert calls[0][2].rstrip().endswith("Best regards,\nAsha Rao")
    assert calls[0][3][0][0] == "Asha Rao - Resume.docx"
