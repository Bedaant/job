"""REACH-D — the send claim, the daily cap, and delivery (`docs/PLAN-OUTREACH.md`).

The at-most-once property is tested the way the application side tests it
(`test_claim_submission_still_cannot_fire_twice`): via the STATE TRANSITION, not via
real concurrency. `with_for_update()` is what makes two simultaneous claims safe on
Postgres, and it is a no-op on the in-memory SQLite these tests run against — so what
is provable here is that after the first claim the row is no longer `approved` and a
second claim is refused. That covers the double-click and the retried task, which are
the cases that actually happen.

The sender is injected, following `digest.py`'s existing
`sender(to, subject, body) -> delivered?` contract. That is what lets the entire send
path — lock, cap, suppression re-check, failure handling — be built and tested before
the Gmail credential of REACH-A exists.
"""
from datetime import timedelta

import pytest

import models
from campaigns import utc_day_start


def _profile(db, email="a@example.com"):
    user = models.User(email=email, password_hash="x")
    db.add(user)
    db.flush()
    p = models.Profile(user_id=user.id, full_name="Asha Rao")
    db.add(p)
    db.flush()
    return p


def _outreach(db, profile, *, status=models.OutreachStatus.approved, email="b@acme.com",
              sent_at=None, subject="Hi", body="Body"):
    job = models.Job(
        source="clipped", external_id=f"x-{email}-{status}-{sent_at}",
        canonical_hash=f"h-{email}-{status}-{sent_at}", title="Product Manager",
        company="Acme", apply_url="https://e.com/j",
    )
    db.add(job)
    db.flush()
    app = models.Application(profile_id=profile.id, job_id=job.id)
    db.add(app)
    db.flush()
    contact = models.Contact(
        profile_id=profile.id, company="Acme", full_name="B", email=email,
        email_verification_status="valid",
    )
    db.add(contact)
    db.flush()
    o = models.Outreach(
        profile_id=profile.id, application_id=app.id, contact_id=contact.id,
        status=status, subject=subject, body=body, sent_at=sent_at,
    )
    db.add(o)
    db.flush()
    return o


# ---------- the claim ----------

def test_claim_moves_approved_to_sending(db_session):
    from outreach.send import claim_outreach
    p = _profile(db_session)
    o = _outreach(db_session, p)
    assert claim_outreach(db_session, o.id, p.id) is None, "None == claimed"
    assert o.status is models.OutreachStatus.sending


def test_claim_cannot_fire_twice(db_session):
    """The at-most-once guarantee. After the first claim the row is `sending`, so it is
    no longer `approved` and the second claim is refused."""
    from outreach.send import claim_outreach
    p = _profile(db_session)
    o = _outreach(db_session, p)
    assert claim_outreach(db_session, o.id, p.id) is None
    assert claim_outreach(db_session, o.id, p.id) == "not_approved"


def test_an_unapproved_row_cannot_be_claimed(db_session):
    from outreach.send import claim_outreach
    p = _profile(db_session)
    o = _outreach(db_session, p, status=models.OutreachStatus.ready_for_review)
    assert claim_outreach(db_session, o.id, p.id) == "not_approved"
    assert o.status is models.OutreachStatus.ready_for_review


def test_another_users_row_cannot_be_claimed(db_session):
    from outreach.send import claim_outreach
    a = _profile(db_session, "a@example.com")
    b = _profile(db_session, "b@example.com")
    o = _outreach(db_session, a)
    assert claim_outreach(db_session, o.id, b.id) == "not_found"
    assert o.status is models.OutreachStatus.approved


# ---------- the daily cap (ADR-003: 10/day) ----------

def test_cap_blocks_the_eleventh_send_of_the_day(db_session):
    from outreach.send import DAILY_CAP, claim_outreach
    p = _profile(db_session)
    for i in range(DAILY_CAP):
        _outreach(db_session, p, status=models.OutreachStatus.sent,
                  email=f"s{i}@acme.com", sent_at=utc_day_start() + timedelta(hours=1))
    o = _outreach(db_session, p, email="next@acme.com")
    assert claim_outreach(db_session, o.id, p.id) == "daily_cap"
    assert o.status is models.OutreachStatus.approved, (
        "the row stays approved and sends tomorrow — the cap is not an error"
    )


def test_cap_counts_only_today(db_session):
    from outreach.send import DAILY_CAP, claim_outreach
    p = _profile(db_session)
    yesterday = utc_day_start() - timedelta(hours=1)
    for i in range(DAILY_CAP):
        _outreach(db_session, p, status=models.OutreachStatus.sent,
                  email=f"y{i}@acme.com", sent_at=yesterday)
    o = _outreach(db_session, p, email="today@acme.com")
    assert claim_outreach(db_session, o.id, p.id) is None


def test_cap_counts_only_this_profile(db_session):
    """One user's sending must not consume another user's allowance."""
    from outreach.send import DAILY_CAP, claim_outreach
    a = _profile(db_session, "a@example.com")
    b = _profile(db_session, "b@example.com")
    for i in range(DAILY_CAP):
        _outreach(db_session, a, status=models.OutreachStatus.sent,
                  email=f"a{i}@acme.com", sent_at=utc_day_start() + timedelta(hours=1))
    o = _outreach(db_session, b, email="forb@acme.com")
    assert claim_outreach(db_session, o.id, b.id) is None


def test_cap_counts_only_sent_rows(db_session):
    """A failed or skipped attempt delivered nothing, so it must not consume allowance."""
    from outreach.send import DAILY_CAP, claim_outreach
    p = _profile(db_session)
    for i in range(DAILY_CAP):
        _outreach(db_session, p, status=models.OutreachStatus.failed, email=f"f{i}@acme.com")
    o = _outreach(db_session, p, email="ok@acme.com")
    assert claim_outreach(db_session, o.id, p.id) is None


# ---------- suppression is re-checked at claim time ----------

def test_a_suppression_added_after_drafting_still_blocks_the_send(db_session):
    """The gap between drafting and approval is minutes at best. An opt-out that loses
    that race is not an opt-out."""
    from outreach.send import claim_outreach
    p = _profile(db_session)
    o = _outreach(db_session, p, email="no@acme.com")
    db_session.add(models.Suppression(profile_id=None, email="no@acme.com", reason="opt_out"))
    db_session.flush()
    assert claim_outreach(db_session, o.id, p.id) == "suppressed"
    assert o.status is models.OutreachStatus.skipped
    assert o.skip_reason == "suppressed"


# ---------- delivery ----------

def test_a_successful_send_records_the_message_id(db_session):
    from outreach.send import send_outreach
    p = _profile(db_session)
    o = _outreach(db_session, p, status=models.OutreachStatus.sending)
    send_outreach(db_session, o, sender=lambda to, subject, body: "msg-123")
    assert o.status is models.OutreachStatus.sent
    assert o.gmail_message_id == "msg-123"
    assert o.sent_at is not None


def test_a_sender_returning_falsy_marks_it_failed_not_sent(db_session):
    """`digest.log_only_sender` returns False when nothing was actually delivered. A row
    must never read `sent` when no mail left."""
    from outreach.send import send_outreach
    p = _profile(db_session)
    o = _outreach(db_session, p, status=models.OutreachStatus.sending)
    send_outreach(db_session, o, sender=lambda to, subject, body: None)
    assert o.status is models.OutreachStatus.failed
    assert o.sent_at is None


def test_a_raising_sender_records_the_error_type_only(db_session):
    """A provider reply can echo what was sent, including the credential.
    `digest.smtp_sender` sets this precedent: type only, never the body."""
    from outreach.send import send_outreach
    p = _profile(db_session)
    o = _outreach(db_session, p, status=models.OutreachStatus.sending)

    def boom(to, subject, body):
        raise RuntimeError("535 auth failed for secret-app-password")

    send_outreach(db_session, o, sender=boom)
    assert o.status is models.OutreachStatus.failed
    assert o.error == "RuntimeError"
    assert "secret-app-password" not in (o.error or "")


def test_only_a_claimed_row_may_be_sent(db_session):
    """Sending without claiming would bypass the lock and the cap entirely."""
    from outreach.send import send_outreach
    p = _profile(db_session)
    o = _outreach(db_session, p, status=models.OutreachStatus.approved)
    with pytest.raises(ValueError):
        send_outreach(db_session, o, sender=lambda to, subject, body: "x")


def test_the_sender_receives_the_contacts_address_and_the_drafted_text(db_session):
    from outreach.send import send_outreach
    p = _profile(db_session)
    o = _outreach(db_session, p, status=models.OutreachStatus.sending,
                  email="target@acme.com", subject="Subj", body="Hello there")
    seen = {}

    def capture(to, subject, body):
        seen.update(to=to, subject=subject, body=body)
        return "ok"

    send_outreach(db_session, o, sender=capture)
    assert seen == {"to": "target@acme.com", "subject": "Subj", "body": "Hello there"}
