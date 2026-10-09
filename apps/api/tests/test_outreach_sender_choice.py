"""REACH-D — which sender actually delivers an outreach email.

ADR-003 chose per-user Gmail OAuth, and that stays the preferred path. But the OAuth
client is the owner's to create, and until it exists nothing could send at all — while
`digest.smtp_sender` was already configured and proven delivering. So Gmail is tried
first and SMTP is the fallback.

**The deviation this introduces, stated plainly because it is real:** an SMTP send goes
out from the ONE configured account, not from the recipient-facing identity of whichever
user it belongs to. `PRD.md` §3 ("the user's identity, the user's reputation") holds for
the Gmail path and does NOT hold for the fallback. Acceptable while the product is the
owner plus a handful of friends; not acceptable as the permanent answer, which is why
the Gmail path is preferred the moment a grant exists.
"""
from unittest.mock import patch

import pytest

import models
from outreach.gmail import GmailNotConfigured, GmailNotConnected


def _row(db):
    u = models.User(email="s@example.com", password_hash="x")
    db.add(u)
    db.flush()
    p = models.Profile(user_id=u.id, full_name="Asha")
    db.add(p)
    db.flush()
    job = models.Job(source="clipped", external_id="s1", canonical_hash="sh1",
                     title="PM", company="Acme", apply_url="https://e.com/j")
    db.add(job)
    db.flush()
    app = models.Application(profile_id=p.id, job_id=job.id)
    db.add(app)
    db.flush()
    c = models.Contact(profile_id=p.id, company="Acme", full_name="B", email="b@acme.com")
    db.add(c)
    db.flush()
    o = models.Outreach(profile_id=p.id, application_id=app.id, contact_id=c.id,
                        status=models.OutreachStatus.sending, subject="S", body="B")
    db.add(o)
    db.flush()
    return o


def test_gmail_is_preferred_when_a_grant_exists(db_session):
    """ADR-003's path wins whenever it is available — the fallback must never shadow it."""
    from workers.outreach_tasks import _sender_for
    o = _row(db_session)
    with patch("outreach.gmail.gmail_sender", return_value="GMAIL") as g:
        assert _sender_for(db_session, o) == "GMAIL"
    assert g.called


def test_smtp_is_used_when_gmail_is_not_connected(db_session):
    from workers.outreach_tasks import _sender_for
    o = _row(db_session)
    with patch("outreach.gmail.gmail_sender", side_effect=GmailNotConnected("no grant")), \
         patch("workers.outreach_tasks._smtp_configured", return_value=True):
        sender = _sender_for(db_session, o)
    assert callable(sender)


def test_smtp_is_used_when_the_oauth_client_is_absent(db_session):
    """The actual state of this repo until the owner creates a Cloud project."""
    from workers.outreach_tasks import _sender_for
    o = _row(db_session)
    with patch("outreach.gmail.gmail_sender", side_effect=GmailNotConfigured("no client")), \
         patch("workers.outreach_tasks._smtp_configured", return_value=True):
        assert callable(_sender_for(db_session, o))


def test_no_gmail_and_no_smtp_raises_rather_than_silently_not_sending(db_session):
    """Both unavailable must be a visible failure. Returning a no-op sender would mark
    rows `sent` with nothing delivered — the one outcome worse than failing."""
    from workers.outreach_tasks import _sender_for
    o = _row(db_session)
    with patch("outreach.gmail.gmail_sender", side_effect=GmailNotConnected("no grant")), \
         patch("workers.outreach_tasks._smtp_configured", return_value=False):
        with pytest.raises(Exception):
            _sender_for(db_session, o)


def test_the_smtp_adapter_returns_an_id_not_a_bool(db_session):
    """`digest.smtp_sender` returns True/False, but `send_outreach` stores the return as
    `gmail_message_id` — passing the bool through would persist the string "True"."""
    from workers.outreach_tasks import smtp_outreach_sender
    with patch("digest.smtp_sender", return_value=True):
        got = smtp_outreach_sender()("b@acme.com", "S", "B")
    assert isinstance(got, str) and got not in ("True", "False") and got


def test_the_smtp_adapter_returns_none_when_nothing_was_delivered(db_session):
    """False from `smtp_sender` means no mail left, and `send_outreach` treats falsy as
    failure. Returning a truthy id here would mark the row `sent` on a failed send."""
    from workers.outreach_tasks import smtp_outreach_sender
    with patch("digest.smtp_sender", return_value=False):
        assert smtp_outreach_sender()("b@acme.com", "S", "B") is None


def test_a_real_send_marks_the_row_sent_with_that_id(db_session):
    from outreach.send import send_outreach
    from workers.outreach_tasks import smtp_outreach_sender
    o = _row(db_session)
    with patch("digest.smtp_sender", return_value=True):
        assert send_outreach(db_session, o, smtp_outreach_sender()) is True
    assert o.status is models.OutreachStatus.sent
    assert o.gmail_message_id and o.gmail_message_id != "True"
    assert o.sent_at is not None
