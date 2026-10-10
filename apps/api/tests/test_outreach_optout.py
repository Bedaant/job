"""REACH-E — opt-out tokens (`docs/PLAN-OUTREACH.md`).

The endpoint these back is unauthenticated by necessity: the recipient has no account
and must never need one to be left alone. So the signature is the only thing standing
between it and mass-suppression or address enumeration, and the forgery cases below are
the actual security surface rather than paperwork.
"""
import models
from outreach.optout import make_token, record_optout, verify_token


def _outreach(db, email="b@acme.com", with_contact=True):
    user = models.User(email=f"u-{email}", password_hash="x")
    db.add(user)
    db.flush()
    profile = models.Profile(user_id=user.id, full_name="Asha Rao")
    db.add(profile)
    db.flush()
    job = models.Job(
        source="clipped", external_id=f"x-{email}", canonical_hash=f"h-{email}",
        title="Product Manager", company="Acme", apply_url="https://e.com/j",
    )
    db.add(job)
    db.flush()
    app = models.Application(profile_id=profile.id, job_id=job.id)
    db.add(app)
    db.flush()
    contact_id = None
    if with_contact:
        contact = models.Contact(
            profile_id=profile.id, company="Acme", full_name="B", email=email,
        )
        db.add(contact)
        db.flush()
        contact_id = contact.id
    o = models.Outreach(
        profile_id=profile.id, application_id=app.id, contact_id=contact_id,
        subject="Hi", body="Body",
    )
    db.add(o)
    db.flush()
    return o, profile


# ---------- round trip ----------

def test_a_token_round_trips():
    assert verify_token(make_token("abc-123")) == "abc-123"


def test_tokens_differ_per_outreach():
    assert make_token("one") != make_token("two")


def test_a_token_is_url_safe():
    """It goes in a path segment, so anything needing escaping would break the link."""
    token = make_token("11111111-2222-3333-4444-555555555555")
    assert all(c.isalnum() or c in "-._~" for c in token), token


# ---------- forgery: the actual security surface ----------

def test_an_unsigned_id_is_refused():
    """Otherwise anyone could walk the id space and suppress strangers."""
    assert verify_token("11111111-2222-3333-4444-555555555555") is None


def test_a_tampered_id_is_refused():
    """Swapping the id while keeping a valid signature must not verify."""
    token = make_token("victim-id")
    _, _, sig = token.rpartition(".")
    assert verify_token(f"other-id.{sig}") is None


def test_a_tampered_signature_is_refused():
    token = make_token("abc-123")
    body, _, sig = token.rpartition(".")
    flipped = ("A" if sig[0] != "A" else "B") + sig[1:]
    assert verify_token(f"{body}.{flipped}") is None


def test_a_truncated_token_is_refused():
    token = make_token("abc-123")
    assert verify_token(token[: len(token) // 2]) is None


def test_garbage_is_refused_without_raising():
    """Reached by arbitrary internet traffic, including scanners that mangle links."""
    for junk in (None, "", ".", "..", "no-dot-here", "a.b.c", "/etc/passwd", "a." + "x" * 500):
        assert verify_token(junk) is None


# ---------- recording ----------

def test_record_writes_a_global_suppression(db_session):
    """Global is the point: someone who asks not to be contacted should not have to ask
    each user of this product separately."""
    o, _ = _outreach(db_session, "stop@acme.com")
    assert record_optout(db_session, o.id) == "stop@acme.com"
    row = db_session.query(models.Suppression).one()
    assert row.profile_id is None
    assert row.email == "stop@acme.com"
    assert row.reason == "opt_out"


def test_record_suppresses_the_contact_not_our_own_user(db_session):
    """Getting this backwards would silently suppress our own user and quietly stop
    their outreach working."""
    o, profile = _outreach(db_session, "contact@acme.com")
    record_optout(db_session, o.id)
    suppressed = {r.email for r in db_session.query(models.Suppression).all()}
    assert suppressed == {"contact@acme.com"}
    assert profile.user.email not in suppressed


def test_record_is_idempotent(db_session):
    """Mail clients prefetch links and people click twice."""
    o, _ = _outreach(db_session, "twice@acme.com")
    assert record_optout(db_session, o.id) == "twice@acme.com"
    assert record_optout(db_session, o.id) == "twice@acme.com"
    assert db_session.query(models.Suppression).count() == 1


def test_record_is_case_insensitive_and_stores_folded(db_session):
    """Addresses arrive from three adapters with inconsistent casing; an opt-out that
    only works in one casing is not an opt-out."""
    o, _ = _outreach(db_session, "Mixed@Acme.COM")
    assert record_optout(db_session, o.id) == "mixed@acme.com"
    assert db_session.query(models.Suppression).one().email == "mixed@acme.com"


def test_an_unknown_outreach_writes_nothing(db_session):
    assert record_optout(db_session, "11111111-2222-3333-4444-555555555555") is None
    assert db_session.query(models.Suppression).count() == 0


def test_an_outreach_with_no_contact_writes_nothing(db_session):
    """A "nobody found" skip has no contact to point at."""
    o, _ = _outreach(db_session, "none@acme.com", with_contact=False)
    assert record_optout(db_session, o.id) is None
    assert db_session.query(models.Suppression).count() == 0


def test_a_contact_with_no_address_writes_nothing(db_session):
    """An adapter can know who someone is before it knows how to reach them."""
    o, profile = _outreach(db_session, "placeholder@acme.com")
    o.contact.email = None
    db_session.flush()
    assert record_optout(db_session, o.id) is None
    assert db_session.query(models.Suppression).count() == 0


# ---------- the whole path, as the endpoint will use it ----------

def test_the_endpoint_path_suppresses_and_then_blocks_sending(db_session):
    """verify -> record -> `is_suppressed` now refuses. That chain is the feature."""
    from outreach.suppression import is_suppressed
    o, profile = _outreach(db_session, "done@acme.com")
    assert is_suppressed(db_session, profile.id, "done@acme.com") is False
    outreach_id = verify_token(make_token(o.id))
    assert outreach_id == o.id
    record_optout(db_session, outreach_id)
    assert is_suppressed(db_session, profile.id, "done@acme.com") is True


def test_a_forged_token_cannot_suppress_anyone(db_session):
    """The two halves together: a bad token yields no id, so nothing is recorded and the
    address stays contactable."""
    from outreach.suppression import is_suppressed
    o, profile = _outreach(db_session, "safe@acme.com")
    assert verify_token(o.id) is None, "unsigned id must not verify"
    assert db_session.query(models.Suppression).count() == 0
    assert is_suppressed(db_session, profile.id, "safe@acme.com") is False


def test_verify_token_survives_non_ascii_input():
    """Found by probing after the module was written, not by its own tests.

    `hmac.compare_digest` raises TypeError when given a `str` containing non-ASCII, and
    this endpoint is reached by arbitrary internet traffic — mail scanners and
    prefetchers mangle links routinely. A raise here is a 500 on the unsubscribe path,
    which means someone trying to be left alone gets an error page. That is the one
    failure this endpoint must never have.
    """
    from outreach.optout import verify_token
    for bad in ["abc.ééé", "é.é", "id.sig❤", "❤"]:
        assert verify_token(bad) is None
