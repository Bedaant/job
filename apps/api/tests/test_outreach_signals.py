"""REACH-C — warm-signal ranking and suppression (`docs/PLAN-OUTREACH.md`).

WHAT THE DATA ACTUALLY SUPPORTS, because the spec was written before this was checked:

`ResumeFact` has no structured employer or school column. It has `category`
(experience|project|skill|certification|education), free-text `achievement` and `proof`,
`metric`, `tags` and a date range. So "same former employer" cannot be a key comparison —
it can only be a text match of a company name against the user's own experience facts.
That is a heuristic with a real ceiling and it is marked as one in the code.

Symmetrically, what is known about the CONTACT depends on which adapter found them:

| signal            | needs, from the contact | GitHub | Apify |
|-------------------|-------------------------|--------|-------|
| same_former_employer | their work history   | no     | yes   |
| same_role         | their current title     | weak   | yes   |
| same_university   | their education         | no     | yes   |
| same_city         | their location          | no     | yes   |

So the ranker must degrade: with a GitHub candidate it can usually only reach `same_role`
or `none`, and that is correct behaviour, not a bug. Tests below pin the degradation
explicitly so nobody "fixes" it by inventing a signal the data cannot support.
"""
import models
from outreach.contacts import ContactCandidate


def _profile(db, email="a@example.com", city="Bengaluru"):
    user = models.User(email=email, password_hash="x")
    db.add(user)
    db.flush()
    p = models.Profile(user_id=user.id, full_name="Asha Rao", city=city)
    db.add(p)
    db.flush()
    return p


def _fact(db, profile, category, achievement, proof=None):
    f = models.ResumeFact(
        profile_id=profile.id, category=category, achievement=achievement, proof=proof
    )
    db.add(f)
    db.flush()
    return f


# ---------- ranking order ----------

def test_former_employer_outranks_same_role(db_session):
    from outreach.signals import rank_contacts
    p = _profile(db_session)
    _fact(db_session, p, "experience", "Shipped checkout at Flipkart", proof="Payments team")
    overlap = ContactCandidate(
        full_name="Ex Colleague", company="Acme", title="Designer",
        past_companies=["Flipkart"],
    )
    same_role = ContactCandidate(full_name="A PM", company="Acme", title="Product Manager")
    ranked = rank_contacts(
        [same_role, overlap], facts=p.resume_facts, profile=p, job_title="Product Manager"
    )
    assert [c.full_name for c in ranked] == ["Ex Colleague", "A PM"]
    assert ranked[0].warm_signal["kind"] == "former_employer"
    assert ranked[0].warm_signal["value"] == "Flipkart"


def test_same_role_outranks_no_signal(db_session):
    from outreach.signals import rank_contacts
    p = _profile(db_session)
    pm = ContactCandidate(full_name="A PM", company="Acme", title="Senior Product Manager")
    other = ContactCandidate(full_name="An SRE", company="Acme", title="Site Reliability Engineer")
    ranked = rank_contacts([other, pm], facts=p.resume_facts, profile=p, job_title="Product Manager")
    assert [c.full_name for c in ranked] == ["A PM", "An SRE"]
    assert ranked[0].warm_signal["kind"] == "same_role"
    assert ranked[1].warm_signal["kind"] == "none"


def test_university_outranks_city(db_session):
    from outreach.signals import rank_contacts
    p = _profile(db_session, city="Bengaluru")
    _fact(db_session, p, "education", "B.Tech, VIT Vellore")
    uni = ContactCandidate(full_name="Alum", company="Acme", schools=["VIT Vellore"])
    city = ContactCandidate(full_name="Local", company="Acme", location="Bengaluru, India")
    ranked = rank_contacts([city, uni], facts=p.resume_facts, profile=p, job_title="PM")
    assert [c.full_name for c in ranked] == ["Alum", "Local"]
    assert ranked[0].warm_signal["kind"] == "same_university"
    assert ranked[1].warm_signal["kind"] == "same_city"


# ---------- traceability: the email asserts the signal out loud ----------

def test_a_signal_about_the_user_records_the_fact_that_backs_it(db_session):
    """The email says "we overlapped at Flipkart". ADR-006 exists to stop claims the
    Facts KB cannot support, so the signal carries the fact id that justified it."""
    from outreach.signals import rank_contacts
    p = _profile(db_session)
    f = _fact(db_session, p, "experience", "Led growth at Flipkart")
    c = ContactCandidate(full_name="X", company="Acme", past_companies=["Flipkart"])
    ranked = rank_contacts([c], facts=p.resume_facts, profile=p, job_title="PM")
    assert ranked[0].warm_signal["source_fact_id"] == f.id


def test_same_role_needs_no_fact_because_it_is_a_claim_about_the_recipient(db_session):
    """Unlike the others, this asserts nothing about the user — it is verifiable from
    Job.title plus the contact's own title, both of which the system already holds."""
    from outreach.signals import rank_contacts
    p = _profile(db_session)
    c = ContactCandidate(full_name="X", company="Acme", title="Group Product Manager")
    ranked = rank_contacts([c], facts=p.resume_facts, profile=p, job_title="Product Manager")
    assert ranked[0].warm_signal["kind"] == "same_role"
    assert ranked[0].warm_signal["source_fact_id"] is None


def test_employer_overlap_is_not_claimed_without_a_matching_fact(db_session):
    """No fact mentions Flipkart, so the overlap must not be asserted even though the
    contact really did work there."""
    from outreach.signals import rank_contacts
    p = _profile(db_session)
    _fact(db_session, p, "experience", "Shipped checkout at Razorpay")
    c = ContactCandidate(full_name="X", company="Acme", past_companies=["Flipkart"])
    ranked = rank_contacts([c], facts=p.resume_facts, profile=p, job_title="PM")
    assert ranked[0].warm_signal["kind"] == "none"


def test_short_company_names_do_not_match_loosely(db_session):
    """"HP" as a substring would hit "sHiPped", "PHP" and most prose. A two-letter
    employer is better missed than falsely asserted in an email."""
    from outreach.signals import rank_contacts
    p = _profile(db_session)
    _fact(db_session, p, "experience", "Shipped a PHP service")
    c = ContactCandidate(full_name="X", company="Acme", past_companies=["HP"])
    ranked = rank_contacts([c], facts=p.resume_facts, profile=p, job_title="PM")
    assert ranked[0].warm_signal["kind"] == "none"


def test_employer_match_ignores_corporate_suffixes_and_case(db_session):
    from outreach.signals import rank_contacts
    p = _profile(db_session)
    _fact(db_session, p, "experience", "Two years at flipkart internet pvt ltd")
    c = ContactCandidate(full_name="X", company="Acme", past_companies=["Flipkart"])
    ranked = rank_contacts([c], facts=p.resume_facts, profile=p, job_title="PM")
    assert ranked[0].warm_signal["kind"] == "former_employer"


# ---------- degradation and determinism ----------

def test_a_github_candidate_degrades_to_role_or_none(db_session):
    """GitHub supplies no work history, education or location. Reaching only `same_role`
    is the expected outcome for that adapter."""
    from outreach.signals import rank_contacts
    p = _profile(db_session)
    _fact(db_session, p, "experience", "Led growth at Flipkart")
    gh = ContactCandidate(full_name="Dev", company="Acme", title="Backend engineer", source="github")
    ranked = rank_contacts([gh], facts=p.resume_facts, profile=p, job_title="Product Manager")
    assert ranked[0].warm_signal["kind"] == "none", "no title overlap, and nothing else known"


def test_ranking_is_deterministic_for_equal_signals(db_session):
    """GAPS 6.6 was a real nondeterminism bug from ranking with no tiebreaker. With
    auto-send on, the tiebreaker decides who receives mail."""
    from outreach.signals import rank_contacts
    p = _profile(db_session)
    a = ContactCandidate(full_name="Bravo", company="Acme", email="b@acme.com")
    b = ContactCandidate(full_name="Alpha", company="Acme", email="a@acme.com")
    first = rank_contacts([a, b], facts=p.resume_facts, profile=p, job_title="PM")
    second = rank_contacts([b, a], facts=p.resume_facts, profile=p, job_title="PM")
    assert [c.full_name for c in first] == [c.full_name for c in second] == ["Alpha", "Bravo"]


def test_ranking_an_empty_list_is_not_an_error(db_session):
    from outreach.signals import rank_contacts
    p = _profile(db_session)
    assert rank_contacts([], facts=p.resume_facts, profile=p, job_title="PM") == []


# ---------- suppression ----------

def test_a_global_suppression_blocks_every_profile(db_session):
    from outreach.suppression import is_suppressed
    a = _profile(db_session, "a@example.com")
    b = _profile(db_session, "b@example.com")
    db_session.add(models.Suppression(profile_id=None, email="no@acme.com", reason="opt_out"))
    db_session.commit()
    assert is_suppressed(db_session, a.id, "no@acme.com") is True
    assert is_suppressed(db_session, b.id, "no@acme.com") is True


def test_a_scoped_suppression_blocks_only_its_own_profile(db_session):
    from outreach.suppression import is_suppressed
    a = _profile(db_session, "a@example.com")
    b = _profile(db_session, "b@example.com")
    db_session.add(models.Suppression(profile_id=a.id, email="x@acme.com", reason="manual"))
    db_session.commit()
    assert is_suppressed(db_session, a.id, "x@acme.com") is True
    assert is_suppressed(db_session, b.id, "x@acme.com") is False


def test_a_domain_suppression_blocks_every_address_at_it(db_session):
    from outreach.suppression import is_suppressed
    p = _profile(db_session)
    db_session.add(models.Suppression(profile_id=None, domain="acme.com", reason="opt_out"))
    db_session.commit()
    assert is_suppressed(db_session, p.id, "anyone@acme.com") is True
    assert is_suppressed(db_session, p.id, "someone@other.com") is False


def test_suppression_matching_is_case_insensitive(db_session):
    """Addresses arrive from three adapters with inconsistent casing. An opt-out that
    only works in lowercase is not an opt-out."""
    from outreach.suppression import is_suppressed
    p = _profile(db_session)
    db_session.add(models.Suppression(profile_id=None, email="No@Acme.com", reason="opt_out"))
    db_session.commit()
    assert is_suppressed(db_session, p.id, "no@acme.COM") is True


def test_a_missing_address_counts_as_suppressed(db_session):
    """Fail closed. Nothing may be sent to an unknown address, so the absence of one is
    never a reason to proceed."""
    from outreach.suppression import is_suppressed
    p = _profile(db_session)
    assert is_suppressed(db_session, p.id, None) is True
    assert is_suppressed(db_session, p.id, "") is True
