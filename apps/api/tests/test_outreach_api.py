"""REACH-D/E — the outreach HTTP surface.

Four properties here are worth more than the rest, because each is a thing a plausible
future edit would break silently:

- **Tenancy** (ADR-007). Another user's outreach row must 404, not 403 — 403 confirms it
  exists.
- **The truth-check is a gate, not a display field.** A flagged row cannot be approved,
  and editing one re-runs the check rather than clearing it.
- **Approval is not idempotent and must not be.** Approving twice would queue two sends
  of an irreversible outward action.
- **Unsubscribe answers identically whether or not it wrote anything.** It is
  unauthenticated by necessity, so a different response for a real id would turn it into
  an id oracle.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base, get_db
from outreach import api as outreach_api


@pytest.fixture()
def ctx():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    app = FastAPI()
    app.include_router(outreach_api.router)
    app.dependency_overrides[get_db] = lambda: db

    users = {}

    def seed_user(email):
        u = models.User(email=email, password_hash="x")
        db.add(u)
        db.flush()
        p = models.Profile(user_id=u.id, full_name="Asha Rao")
        db.add(p)
        db.flush()
        users[email] = (u, p)
        return u, p

    def act_as(email):
        app.dependency_overrides[outreach_api.current_user] = lambda: users[email][0]

    try:
        yield app, db, seed_user, act_as, TestClient(app)
    finally:
        db.close()
        engine.dispose()


def _row(db, profile, *, status=models.OutreachStatus.ready_for_review, flags=None,
         email="b@acme.com", subject="Hi", body="Body"):
    job = models.Job(
        source="clipped", external_id=f"e{email}{status}{subject}",
        canonical_hash=f"h{email}{status}{subject}", title="Product Manager",
        company="Acme", apply_url="https://e.com/j",
    )
    db.add(job)
    db.flush()
    appn = models.Application(profile_id=profile.id, job_id=job.id)
    db.add(appn)
    db.flush()
    c = models.Contact(profile_id=profile.id, company="Acme", full_name="B", email=email,
                       email_verification_status="valid")
    db.add(c)
    db.flush()
    o = models.Outreach(
        profile_id=profile.id, application_id=appn.id, contact_id=c.id, status=status,
        subject=subject, body=body, flagged_unsupported_claims=flags or [],
    )
    db.add(o)
    db.flush()
    return o


# ---------- tenancy (ADR-007) ----------

def test_another_users_outreach_is_not_found(ctx):
    _, db, seed, act_as, client = ctx
    _, pa = seed("a@example.com")
    seed("b@example.com")
    o = _row(db, pa)
    act_as("b@example.com")
    assert client.post(f"/outreach/{o.id}/approve").status_code == 404, (
        "404 not 403 — 403 would confirm the row exists"
    )
    assert client.patch(f"/outreach/{o.id}", json={"body": "x"}).status_code == 404


def test_review_queue_shows_only_this_profiles_rows(ctx):
    _, db, seed, act_as, client = ctx
    _, pa = seed("a@example.com")
    _, pb = seed("b@example.com")
    _row(db, pa, email="mine@acme.com")
    _row(db, pb, email="theirs@acme.com")
    act_as("a@example.com")
    got = client.get("/outreach/review-queue", params={"profile_id": pa.id}).json()
    assert [r["contact"]["email"] for r in got] == ["mine@acme.com"]


def test_review_queue_shows_only_rows_awaiting_review(ctx):
    _, db, seed, act_as, client = ctx
    _, p = seed("a@example.com")
    _row(db, p, email="waiting@acme.com")
    _row(db, p, status=models.OutreachStatus.sent, email="done@acme.com")
    _row(db, p, status=models.OutreachStatus.skipped, email="skipped@acme.com")
    act_as("a@example.com")
    got = client.get("/outreach/review-queue", params={"profile_id": p.id}).json()
    assert [r["contact"]["email"] for r in got] == ["waiting@acme.com"]


def test_the_queue_says_why_this_person(ctx):
    """The user is about to send this under their own name, so the UI must be able to
    show the recipient, the signal and the verification status."""
    _, db, seed, act_as, client = ctx
    _, p = seed("a@example.com")
    o = _row(db, p)
    o.warm_signal_used = {"kind": "same_role", "value": "Product Manager",
                          "asserts_about_user": True}
    db.flush()
    act_as("a@example.com")
    row = client.get("/outreach/review-queue", params={"profile_id": p.id}).json()[0]
    assert row["warm_signal_used"]["kind"] == "same_role"
    assert row["contact"]["email_verification_status"] == "valid"
    assert row["subject"] == "Hi"


# ---------- approval is a gate ----------

def test_a_flagged_row_cannot_be_approved(ctx):
    """ADR-006's check is a gate, not a display field."""
    _, db, seed, act_as, client = ctx
    _, p = seed("a@example.com")
    o = _row(db, p, flags=["claims a title no fact supports"])
    act_as("a@example.com")
    r = client.post(f"/outreach/{o.id}/approve")
    assert r.status_code == 409
    assert o.status is models.OutreachStatus.ready_for_review


def test_approving_a_clean_row_queues_exactly_one_send(ctx):
    _, db, seed, act_as, client = ctx
    _, p = seed("a@example.com")
    o = _row(db, p)
    act_as("a@example.com")
    sent = []
    outreach_api._enqueue_send = lambda oid: sent.append(oid)
    assert client.post(f"/outreach/{o.id}/approve").status_code == 200
    assert o.status is models.OutreachStatus.approved
    assert o.approved_by == "user"
    assert sent == [o.id]


def test_approving_twice_does_not_queue_two_sends(ctx):
    """Sending an email is irreversible, so a double-click must not produce two."""
    _, db, seed, act_as, client = ctx
    _, p = seed("a@example.com")
    o = _row(db, p)
    act_as("a@example.com")
    sent = []
    outreach_api._enqueue_send = lambda oid: sent.append(oid)
    assert client.post(f"/outreach/{o.id}/approve").status_code == 200
    assert client.post(f"/outreach/{o.id}/approve").status_code == 409
    assert sent == [o.id]


def test_a_failed_enqueue_leaves_the_row_reviewable(ctx):
    """Mirrors main.py's prepare path: the work is not lost and the user is told to retry,
    rather than the row sitting `approved` with nothing ever sending it."""
    _, db, seed, act_as, client = ctx
    _, p = seed("a@example.com")
    o = _row(db, p)
    act_as("a@example.com")

    def boom(_):
        raise RuntimeError("redis down")

    outreach_api._enqueue_send = boom
    assert client.post(f"/outreach/{o.id}/approve").status_code == 503
    assert o.status is models.OutreachStatus.ready_for_review


# ---------- editing cannot bypass the gate ----------

def test_editing_a_draft_reruns_the_truth_check(ctx):
    _, db, seed, act_as, client = ctx
    _, p = seed("a@example.com")
    o = _row(db, p, flags=["old finding"])
    act_as("a@example.com")
    calls = []

    def recheck(subject, body, facts):
        calls.append(body)
        return ["still unsupported"]

    outreach_api._recheck = recheck
    r = client.patch(f"/outreach/{o.id}", json={"body": "a rewritten note"})
    assert r.status_code == 200
    assert calls == ["a rewritten note"]
    assert o.flagged_unsupported_claims == ["still unsupported"], (
        "the edit replaced the findings rather than clearing them"
    )
    assert client.post(f"/outreach/{o.id}/approve").status_code == 409


def test_a_clean_edit_clears_the_flags_and_unblocks_approval(ctx):
    _, db, seed, act_as, client = ctx
    _, p = seed("a@example.com")
    o = _row(db, p, flags=["old finding"])
    act_as("a@example.com")
    outreach_api._recheck = lambda subject, body, facts: []
    outreach_api._enqueue_send = lambda oid: None
    assert client.patch(f"/outreach/{o.id}", json={"body": "grounded rewrite"}).status_code == 200
    assert o.flagged_unsupported_claims == []
    assert client.post(f"/outreach/{o.id}/approve").status_code == 200


def test_a_sent_row_cannot_be_edited(ctx):
    _, db, seed, act_as, client = ctx
    _, p = seed("a@example.com")
    o = _row(db, p, status=models.OutreachStatus.sent)
    act_as("a@example.com")
    assert client.patch(f"/outreach/{o.id}", json={"body": "too late"}).status_code == 409


# ---------- skip ----------

def test_skipping_records_the_users_reason(ctx):
    _, db, seed, act_as, client = ctx
    _, p = seed("a@example.com")
    o = _row(db, p)
    act_as("a@example.com")
    assert client.post(f"/outreach/{o.id}/skip", json={"reason": "wrong person"}).status_code == 200
    assert o.status is models.OutreachStatus.skipped
    assert o.skip_reason == "wrong person"


# ---------- unsubscribe: public, unauthenticated ----------

def test_unsubscribe_suppresses_the_contact_globally(ctx):
    from outreach.optout import make_token
    from outreach.suppression import is_suppressed
    _, db, seed, act_as, client = ctx
    _, p = seed("a@example.com")
    o = _row(db, p, email="leave@acme.com")
    r = client.get(f"/outreach/unsubscribe/{make_token(o.id)}")
    assert r.status_code == 200
    assert is_suppressed(db, p.id, "leave@acme.com") is True


def test_unsubscribe_needs_no_authentication(ctx):
    """The recipient has no account here and must never need one to be left alone."""
    from outreach.optout import make_token
    app, db, seed, act_as, client = ctx
    _, p = seed("a@example.com")
    o = _row(db, p, email="leave@acme.com")
    # No `act_as` — no identity override is registered at all.
    assert client.get(f"/outreach/unsubscribe/{make_token(o.id)}").status_code == 200


def test_unsubscribe_answers_identically_for_a_bad_token(ctx):
    """Otherwise the endpoint is an id oracle: a different answer for a real id would let
    anyone walk the id space."""
    from outreach.optout import make_token
    _, db, seed, act_as, client = ctx
    _, p = seed("a@example.com")
    o = _row(db, p, email="leave@acme.com")
    good = client.get(f"/outreach/unsubscribe/{make_token(o.id)}")
    bad = client.get("/outreach/unsubscribe/not-a-real-token")
    forged = client.get(f"/outreach/unsubscribe/{o.id}.deadbeef")
    assert bad.status_code == forged.status_code == good.status_code == 200
    assert bad.text == forged.text == good.text
    assert db.query(models.Suppression).count() == 1, "only the real one wrote a row"


def test_unsubscribe_is_idempotent(ctx):
    """Mail clients prefetch links and people click twice."""
    from outreach.optout import make_token
    _, db, seed, act_as, client = ctx
    _, p = seed("a@example.com")
    o = _row(db, p, email="leave@acme.com")
    token = make_token(o.id)
    assert client.get(f"/outreach/unsubscribe/{token}").status_code == 200
    assert client.get(f"/outreach/unsubscribe/{token}").status_code == 200
    assert db.query(models.Suppression).count() == 1


def test_unsubscribe_never_returns_an_address(ctx):
    """The page is served to whoever has the link. Echoing the address back would make a
    guessed or leaked token a disclosure."""
    from outreach.optout import make_token
    _, db, seed, act_as, client = ctx
    _, p = seed("a@example.com")
    o = _row(db, p, email="leave@acme.com")
    body = client.get(f"/outreach/unsubscribe/{make_token(o.id)}").text
    assert "leave@acme.com" not in body


def test_unsubscribe_is_the_only_unauthenticated_outreach_route():
    """Against the REAL app, not the test harness with its identity override — the
    harness is exactly where an auth regression would hide.

    Unsubscribe must be public (the recipient has no account) and everything else must
    not be. Verified by probing rather than by reading the decorators.
    """
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)
    must_refuse = [
        ("get", "/outreach?profile_id=x"),
        ("get", "/outreach/review-queue?profile_id=x"),
        ("patch", "/outreach/abc"),
        ("post", "/outreach/abc/approve"),
        ("post", "/outreach/abc/skip"),
        ("get", "/gmail/status"),
        ("get", "/gmail/authorize"),
        ("delete", "/gmail/connection"),
    ]
    for verb, path in must_refuse:
        kwargs = {"json": {}} if verb in ("patch", "post") else {}
        got = getattr(client, verb)(path, **kwargs).status_code
        assert got in (401, 403), f"{verb.upper()} {path} answered {got} unauthenticated"

    assert client.get("/outreach/unsubscribe/garbage").status_code == 200
