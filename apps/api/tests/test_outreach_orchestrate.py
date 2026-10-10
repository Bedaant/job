"""REACH-D — the task that runs after an application goes out.

This is the piece that ties REACH-B/C/D together: find people, rank them, check they may
be contacted, draft, persist. Everything it calls is already tested in isolation, so what
matters here is the ORCHESTRATION — ordering, idempotency, and that every refusal leaves
a visible row instead of silence.

The silence point is the one worth stating. A user who applied and got no outreach must
be able to see WHY: nobody found, suppressed, no verified address, nothing groundable.
Each of those is a `skipped` row with a reason, never an absent row.
"""
from unittest.mock import patch

import pytest

import models
from outreach.contacts import ContactCandidate


def _profile(db, email="a@example.com", per_app=2, with_facts=True):
    u = models.User(email=email, password_hash="x")
    db.add(u)
    db.flush()
    p = models.Profile(user_id=u.id, full_name="Asha Rao", city="Bengaluru",
                       outreach_contacts_per_application=per_app)
    db.add(p)
    db.flush()
    if with_facts:
        db.add(models.ResumeFact(
            profile_id=p.id, category="experience",
            achievement="Product manager for payments at Flipkart", proof="Payments",
        ))
        db.flush()
    return p


def _application(db, profile, status=models.ApplicationStatus.applied, company="Acme"):
    job = models.Job(
        source="clipped", external_id=f"e-{company}-{status}", canonical_hash=f"h-{company}-{status}",
        title="Product Manager", company=company, apply_url="https://e.com/j",
        description="Build great products.",
    )
    db.add(job)
    db.flush()
    a = models.Application(profile_id=profile.id, job_id=job.id, status=status)
    db.add(a)
    db.flush()
    return a


class _Source:
    """A ContactSource that returns what it was given and records being asked."""

    def __init__(self, name, candidates):
        self.name = name
        self._candidates = candidates
        self.calls = []

    def find(self, company, titles, limit):
        self.calls.append((company, tuple(titles), limit))
        return list(self._candidates)[:limit]


def _cand(name, email, title="Product Manager", company="Acme"):
    return ContactCandidate(full_name=name, company=company, title=title, email=email,
                            source="test")


_DRAFT = {
    "subject": "Quick question about the PM role",
    "body": "Body text here.",
    "flagged_unsupported_claims": [],
    "advisory_claims": [],
}


def _run(db, application_id, sources, draft=None):
    from outreach.orchestrate import draft_outreach_for_application
    with patch("outreach.orchestrate.draft_outreach", return_value=dict(draft or _DRAFT)):
        return draft_outreach_for_application(db, application_id, sources=sources)


# ---------- the happy path ----------

def test_it_creates_one_outreach_row_per_contact(db_session):
    p = _profile(db_session, per_app=2)
    a = _application(db_session, p)
    src = _Source("test", [_cand("One", "one@acme.com"), _cand("Two", "two@acme.com")])
    _run(db_session, a.id, [src])
    rows = db_session.query(models.Outreach).all()
    assert len(rows) == 2
    assert {r.status for r in rows} == {models.OutreachStatus.ready_for_review}
    assert all(r.subject and r.body for r in rows)


def test_it_persists_the_contact_it_found(db_session):
    p = _profile(db_session)
    a = _application(db_session, p)
    _run(db_session, a.id, [_Source("test", [_cand("One", "one@acme.com")])])
    c = db_session.query(models.Contact).one()
    assert (c.full_name, c.email, c.profile_id) == ("One", "one@acme.com", p.id)


def test_it_searches_by_the_jobs_company_and_title(db_session):
    """The whole point of the owner's `same_role` idea: ask someone doing the job."""
    p = _profile(db_session)
    a = _application(db_session, p, company="Globex")
    src = _Source("test", [_cand("One", "one@globex.com", company="Globex")])
    _run(db_session, a.id, [src])
    company, titles, limit = src.calls[0]
    assert company == "Globex"
    assert "Product Manager" in titles


def test_it_honours_the_per_application_contact_cap(db_session):
    p = _profile(db_session, per_app=1)
    a = _application(db_session, p)
    src = _Source("test", [_cand("One", "one@acme.com"), _cand("Two", "two@acme.com")])
    _run(db_session, a.id, [src])
    assert db_session.query(models.Outreach).count() == 1


def test_the_warm_signal_is_recorded_on_the_row(db_session):
    """The email asserts the connection out loud, so what it claimed is stored."""
    p = _profile(db_session)
    a = _application(db_session, p)
    _run(db_session, a.id, [_Source("test", [_cand("One", "one@acme.com")])])
    row = db_session.query(models.Outreach).one()
    assert row.warm_signal_used["kind"] in ("same_role", "holds_target_role")


def test_the_body_carries_this_rows_own_unsubscribe_token(db_session):
    """The token is per-outreach, so it cannot be minted before the row exists — and the
    link in the body must resolve back to THIS row, not another."""
    from outreach.optout import verify_token
    p = _profile(db_session)
    a = _application(db_session, p)
    captured = {}

    def fake_draft(facts, job, contact, unsubscribe_url):
        captured["url"] = unsubscribe_url
        return dict(_DRAFT)

    from outreach.orchestrate import draft_outreach_for_application
    with patch("outreach.orchestrate.draft_outreach", side_effect=fake_draft):
        draft_outreach_for_application(
            db_session, a.id, sources=[_Source("test", [_cand("One", "one@acme.com")])]
        )
    row = db_session.query(models.Outreach).one()
    assert verify_token(captured["url"].rstrip("/").rsplit("/", 1)[-1]) == row.id


# ---------- when it must not run ----------

def test_it_does_nothing_for_an_application_that_never_went_out(db_session):
    """README: "After you apply…". Drafting for an unsent application would waste tokens
    and let the email claim an application that does not exist."""
    p = _profile(db_session)
    a = _application(db_session, p, status=models.ApplicationStatus.ready_for_review)
    _run(db_session, a.id, [_Source("test", [_cand("One", "one@acme.com")])])
    assert db_session.query(models.Outreach).count() == 0


def test_it_runs_for_a_sent_but_unconfirmed_application(db_session):
    """`submitted_unconfirmed` means the submit was sent and the employer's page never
    confirmed it. Treated as sent — see the module docstring for the trade-off."""
    p = _profile(db_session)
    a = _application(db_session, p, status=models.ApplicationStatus.submitted_unconfirmed)
    _run(db_session, a.id, [_Source("test", [_cand("One", "one@acme.com")])])
    assert db_session.query(models.Outreach).count() == 1


def test_a_second_run_creates_nothing_new(db_session):
    """ADR-008 documents RQ retrying on crash, so this WILL run twice for one
    application. A retry must not produce a second email to the same person."""
    p = _profile(db_session)
    a = _application(db_session, p)
    src = _Source("test", [_cand("One", "one@acme.com")])
    _run(db_session, a.id, [src])
    _run(db_session, a.id, [src])
    assert db_session.query(models.Outreach).count() == 1


# ---------- every refusal is visible ----------

def test_no_contacts_found_leaves_a_row_saying_so(db_session):
    """Measured reality, not a corner case: Swiggy exposes 0 public GitHub members, and
    Apify's email coverage is explicitly "not guaranteed". The user must be able to see
    that nobody was found rather than wondering."""
    p = _profile(db_session)
    a = _application(db_session, p)
    _run(db_session, a.id, [_Source("test", [])])
    row = db_session.query(models.Outreach).one()
    assert row.status is models.OutreachStatus.skipped
    assert row.skip_reason == "no_contact_found"
    assert row.contact_id is None


def test_a_suppressed_contact_is_skipped_with_a_reason(db_session):
    p = _profile(db_session)
    a = _application(db_session, p)
    db_session.add(models.Suppression(profile_id=None, email="one@acme.com", reason="opt_out"))
    db_session.flush()
    _run(db_session, a.id, [_Source("test", [_cand("One", "one@acme.com")])])
    rows = db_session.query(models.Outreach).all()
    assert [r.skip_reason for r in rows] == ["suppressed"]
    assert all(r.subject is None for r in rows), "a suppressed contact is never drafted for"


def test_a_contact_with_no_address_is_skipped(db_session):
    """Apify can return a profile with no email at all."""
    p = _profile(db_session)
    a = _application(db_session, p)
    _run(db_session, a.id, [_Source("test", [_cand("One", None)])])
    row = db_session.query(models.Outreach).one()
    assert row.skip_reason == "email_missing"


def test_nothing_groundable_is_skipped_not_sent_ungrounded(db_session):
    """`draft_outreach` raises when no confirmed fact has an id. An email with nothing
    behind it gives the recipient no reason to help and breaks ADR-009, so it becomes a
    skip rather than a send."""
    p = _profile(db_session, with_facts=False)
    a = _application(db_session, p)
    from outreach.orchestrate import draft_outreach_for_application
    with patch("outreach.orchestrate.draft_outreach",
               side_effect=ValueError("no confirmed facts with ids")):
        draft_outreach_for_application(
            db_session, a.id, sources=[_Source("test", [_cand("One", "one@acme.com")])]
        )
    row = db_session.query(models.Outreach).one()
    assert row.status is models.OutreachStatus.skipped
    assert row.skip_reason == "nothing_groundable"


def test_truth_check_flags_land_on_the_row_and_leave_it_for_review(db_session):
    """Expect this often: GAPS 6.7 measured 9 of 30 still blocking on resumes, and
    favour-asking prose carries more evaluative framing than a resume bullet."""
    p = _profile(db_session)
    a = _application(db_session, p)
    flagged = dict(_DRAFT, flagged_unsupported_claims=["claims a title no fact supports"])
    _run(db_session, a.id, [_Source("test", [_cand("One", "one@acme.com")])], draft=flagged)
    row = db_session.query(models.Outreach).one()
    assert row.status is models.OutreachStatus.ready_for_review
    assert row.flagged_unsupported_claims == ["claims a title no fact supports"]


# ---------- source ordering ----------

def test_sources_are_tried_in_order_and_stop_once_satisfied(db_session):
    """Free before paid: GitHub costs nothing, Apify costs per profile. The second source
    must not be called at all when the first already filled the quota."""
    p = _profile(db_session, per_app=1)
    a = _application(db_session, p)
    free = _Source("github", [_cand("Free", "free@acme.com")])
    paid = _Source("apify", [_cand("Paid", "paid@acme.com")])
    _run(db_session, a.id, [free, paid])
    assert free.calls, "the free source was asked"
    assert paid.calls == [], "the paid source was never asked"


def test_the_next_source_is_tried_when_the_first_finds_nobody(db_session):
    p = _profile(db_session, per_app=1)
    a = _application(db_session, p)
    free = _Source("github", [])
    paid = _Source("apify", [_cand("Paid", "paid@acme.com")])
    _run(db_session, a.id, [free, paid])
    assert paid.calls, "the paid source was asked once free found nobody"
    assert db_session.query(models.Contact).one().full_name == "Paid"


def test_a_raising_source_does_not_stop_the_others(db_session):
    """Apify is an untrusted network dependency. Its outage must not cost the free
    source's results."""
    p = _profile(db_session, per_app=1)

    class _Boom:
        name = "boom"

        def find(self, company, titles, limit):
            raise RuntimeError("vendor down")

    a = _application(db_session, p)
    _run(db_session, a.id, [_Boom(), _Source("github", [_cand("Free", "free@acme.com")])])
    assert db_session.query(models.Contact).one().full_name == "Free"
