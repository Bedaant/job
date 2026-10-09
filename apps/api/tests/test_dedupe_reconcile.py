"""GAPS 4.3 — two live rows must not share a `canonical_hash`.

ADR-017 §5 keeps the hash non-unique on purpose: a re-seen row's company is refreshed in
place, so its hash can be rewritten into one another source already stored, and a UNIQUE
constraint turned that rewrite into a run-killing IntegrityError (migration 0022 dropped
it). The consequence was recorded but never resolved — "nothing re-collapses such a pair".

That was tolerable while sources barely overlapped. It stopped being tolerable when
`linkedin_external`, `linkedin_easy_apply`, `jobspy_glassdoor` and 77 newly probed ATS
boards all started returning the same requisition: different `(source, external_id)`,
identical hash. The user sees one job several times, and could apply to it twice.

Collapsing tombstones the loser rather than deleting it: an `Application` may already
point at the row, and `delisted_at` is what every live-pool query filters on already.
"""
from datetime import datetime, timedelta

import models
from connectors.pipeline import upsert_jobs

HASH = "shared-canonical-hash"


def _stored(db, *, source, external_id, canonical_hash=HASH, company="PhonePe",
            title="Product Manager", fetched_at=None, delisted_at=None,
            apply_url=None):
    row = models.Job(
        source=source,
        external_id=external_id,
        canonical_hash=canonical_hash,
        title=title,
        company=company,
        apply_url=apply_url or f"https://example.com/{source}/{external_id}",
        fetched_at=fetched_at or datetime(2026, 1, 1),
        last_seen_at=fetched_at or datetime(2026, 1, 1),
        delisted_at=delisted_at,
    )
    db.add(row)
    db.flush()
    return row


def _payload(*, source, external_id, canonical_hash=HASH, company="PhonePe",
             title="Product Manager"):
    return {
        "source": source,
        "external_id": external_id,
        "canonical_hash": canonical_hash,
        "title": title,
        "company": company,
        "location": "Bengaluru, India",
        "apply_url": f"https://example.com/{source}/{external_id}",
        "description": "Own the payments product.",
        "posted_at": None,
    }


def _live(db):
    return db.query(models.Job).filter(models.Job.delisted_at.is_(None)).all()


# ---------- the collision ADR-017 §5 names, and nothing used to re-collapse ----------

def test_an_update_that_rewrites_a_hash_into_a_collision_is_collapsed(db_session):
    """The exact mechanism ADR-017 §5 describes. Two live rows from different sources with
    DIFFERENT hashes; this run's payload rewrites one of them onto the other's hash."""
    _stored(db_session, source="jobspy_glassdoor", external_id="g1", canonical_hash=HASH)
    _stored(db_session, source="linkedin_easy_apply", external_id="l1",
            canonical_hash="other-hash")

    # linkedin re-seen, and its company now normalises to the same hash as the
    # jobspy row — the rewrite the UNIQUE constraint used to make impossible.
    upsert_jobs(db_session, [_payload(source="linkedin_easy_apply", external_id="l1")])

    live = _live(db_session)
    assert len(live) == 1, "two live rows with one hash is the bug"
    assert live[0].source == "jobspy_glassdoor"


def test_a_pair_that_was_already_stored_colliding_is_collapsed(db_session):
    """Rows that collided before this change existed. Nothing in the batch rewrites
    anything — they are simply both live with one hash, and must be reconciled on the
    next run that touches either."""
    _stored(db_session, source="jobspy_glassdoor", external_id="g1")
    _stored(db_session, source="linkedin_easy_apply", external_id="l1")
    assert len(_live(db_session)) == 2, "precondition: the un-reconciled state"

    upsert_jobs(db_session, [_payload(source="jobspy_glassdoor", external_id="g1")])

    assert len(_live(db_session)) == 1


def test_an_existing_row_is_reconciled_against_a_newly_fetched_one(db_session):
    """A new source returns a role already stored under a different source. Pass 2's
    guard should skip the insert outright rather than creating the collision."""
    _stored(db_session, source="greenhouse", external_id="gh1")

    inserted, _updated, skipped = upsert_jobs(
        db_session, [_payload(source="linkedin_external", external_id="li1")]
    )

    assert (inserted, skipped) == (0, 1)
    assert len(_live(db_session)) == 1


def test_an_insert_cannot_collide_with_a_hash_rewritten_in_the_same_batch(db_session):
    """Pass 1 runs before pass 2 precisely for this. Row A is rewritten onto hash H by
    this batch while row B arrives new at hash H; testing the PRE-update hash set would
    let B in and leave the collision to be found a run later."""
    _stored(db_session, source="greenhouse", external_id="gh1", canonical_hash="old-hash")

    inserted, updated, skipped = upsert_jobs(db_session, [
        _payload(source="greenhouse", external_id="gh1"),          # rewrites onto HASH
        _payload(source="linkedin_external", external_id="li1"),   # new, same HASH
    ])

    assert (inserted, updated, skipped) == (0, 1, 1)
    assert len(_live(db_session)) == 1


# ---------- the winner rule ----------

def test_a_fillable_row_beats_an_unfillable_one(db_session):
    """`linkedin_easy_apply`'s apply_url is linkedin.com — the extension cannot fill it
    and this project does not automate LinkedIn. A direct ATS row is the one the user can
    actually apply through, so it wins even though it is newer."""
    _stored(db_session, source="linkedin_easy_apply", external_id="l1",
            fetched_at=datetime(2026, 1, 1))
    _stored(db_session, source="greenhouse", external_id="gh1",
            fetched_at=datetime(2026, 6, 1))

    upsert_jobs(db_session, [_payload(source="greenhouse", external_id="gh1")])

    live = _live(db_session)
    assert [r.source for r in live] == ["greenhouse"]


def test_linkedin_external_beats_an_aggregator_link(db_session):
    """Measured 2026-10-09: 56% of LinkedIn rows carry a real employer ATS link, which
    the extension can fill. An aggregator link is openable but not fillable."""
    _stored(db_session, source="jobspy_glassdoor", external_id="g1")
    _stored(db_session, source="linkedin_external", external_id="li1")

    upsert_jobs(db_session, [_payload(source="linkedin_external", external_id="li1")])

    assert [r.source for r in _live(db_session)] == ["linkedin_external"]


def test_within_one_trust_tier_the_older_row_wins(db_session):
    """The older row is the one most likely to already carry an embedding and `Match`
    history, so keeping it avoids a re-embed and preserves what the user has seen."""
    old = _stored(db_session, source="greenhouse", external_id="gh1",
                  fetched_at=datetime(2026, 1, 1))
    _stored(db_session, source="lever", external_id="lv1",
            fetched_at=datetime(2026, 9, 1))

    upsert_jobs(db_session, [_payload(source="lever", external_id="lv1")])

    live = _live(db_session)
    assert [r.id for r in live] == [old.id]


def test_the_order_is_total_so_the_outcome_is_deterministic(db_session):
    """GAPS 6.6 was a real nondeterminism bug from ranking without a tiebreaker. Here the
    tiebreaker decides which copy of a job a user is shown, so identical trust AND
    identical timestamps must still resolve the same way every run."""
    same = datetime(2026, 5, 5)
    a = _stored(db_session, source="greenhouse", external_id="gh1", fetched_at=same)
    b = _stored(db_session, source="lever", external_id="lv1", fetched_at=same)
    expected = min(a.id, b.id)

    for _ in range(3):
        db_session.query(models.Job).update({models.Job.delisted_at: None})
        db_session.flush()
        upsert_jobs(db_session, [_payload(source="greenhouse", external_id="gh1")])
        assert [r.id for r in _live(db_session)] == [expected]


# ---------- what must NOT be touched ----------

def test_a_tombstoned_duplicate_does_not_interfere(db_session):
    """A tombstone is not a duplicate of a live row. It must neither be collapsed with
    one nor suppress it — ADR-017's reason for excluding delisted rows from the hash set
    in the first place."""
    dead = _stored(db_session, source="jobspy_glassdoor", external_id="g1",
                   delisted_at=datetime(2026, 2, 2))
    live_row = _stored(db_session, source="greenhouse", external_id="gh1")

    upsert_jobs(db_session, [_payload(source="greenhouse", external_id="gh1")])

    assert [r.id for r in _live(db_session)] == [live_row.id]
    assert db_session.get(models.Job, dead.id).delisted_at is not None, "left tombstoned"


def test_a_revived_row_participates_in_the_collapse(db_session):
    """The update path resets `delisted_at` on a re-seen row, so a revived tombstone is
    live again as of this run and has to be reconciled in the same pass — reading its
    stored flag instead of the pending update would miss it."""
    _stored(db_session, source="greenhouse", external_id="gh1")
    _stored(db_session, source="linkedin_easy_apply", external_id="l1",
            delisted_at=datetime(2026, 2, 2))

    upsert_jobs(db_session, [_payload(source="linkedin_easy_apply", external_id="l1")])

    assert [r.source for r in _live(db_session)] == ["greenhouse"]


def test_distinct_hashes_are_left_alone(db_session):
    """The regression guard: genuinely different roles must all stay live."""
    _stored(db_session, source="greenhouse", external_id="gh1", canonical_hash="h1",
            title="Product Manager")
    _stored(db_session, source="lever", external_id="lv1", canonical_hash="h2",
            title="Data Engineer")

    upsert_jobs(db_session, [
        _payload(source="greenhouse", external_id="gh1", canonical_hash="h1"),
        _payload(source="lever", external_id="lv1", canonical_hash="h2",
                 title="Data Engineer"),
    ])

    assert len(_live(db_session)) == 2


def test_a_single_live_row_is_never_collapsed(db_session):
    """Never lose a job: one row sharing its hash with nothing must survive."""
    _stored(db_session, source="greenhouse", external_id="gh1")
    upsert_jobs(db_session, [_payload(source="greenhouse", external_id="gh1")])
    assert len(_live(db_session)) == 1


def test_collapsing_is_idempotent_across_runs(db_session):
    """A loser is revived by its own source every run and re-collapsed here, so the
    steady state must stay one live row rather than oscillating."""
    _stored(db_session, source="greenhouse", external_id="gh1")
    _stored(db_session, source="linkedin_easy_apply", external_id="l1")

    for _ in range(3):
        upsert_jobs(db_session, [
            _payload(source="greenhouse", external_id="gh1"),
            _payload(source="linkedin_easy_apply", external_id="l1"),
        ])
        assert [r.source for r in _live(db_session)] == ["greenhouse"]


# ---------- a row the user has already applied through must never lose ----------

def test_a_row_with_an_application_wins_regardless_of_source_trust(db_session):
    """Found by review, not by the collapse's own tests, and it is a double-apply path.

    `campaigns.select_candidates` excludes already-applied jobs by **job_id**, not by
    `canonical_hash`. So if the user applied through a low-trust row and the collapse
    tombstones it in favour of a higher-trust duplicate, the surviving row is live,
    un-applied, and matchable — and the campaign applies a SECOND time to the same role
    at the same employer. That is the harm `main.py::claim_submission` exists to prevent,
    reached by a different route, and the at-most-once lock cannot see it because these
    are two different `Application` rows.

    Keeping the applied row fixes both halves: history is preserved, and the survivor is
    the one `already_applied` already filters out.
    """
    user = models.User(email="dup@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    profile = models.Profile(user_id=user.id, full_name="Dup Tester")
    db_session.add(profile)
    db_session.flush()
    applied = _stored(db_session, source="linkedin_easy_apply", external_id="ea-1")
    better = _stored(db_session, source="greenhouse", external_id="gh-1")
    db_session.add(models.Application(profile_id=profile.id, job_id=applied.id))
    db_session.commit()

    upsert_jobs(db_session, [
        _payload(source="linkedin_easy_apply", external_id="ea-1"),
        _payload(source="greenhouse", external_id="gh-1"),
    ])
    db_session.commit()

    db_session.refresh(applied)
    db_session.refresh(better)
    assert applied.delisted_at is None, (
        "the row carrying the application was tombstoned — its history is orphaned and "
        "the survivor is now applyable again"
    )
    assert better.delisted_at is not None, "the un-applied duplicate should be the loser"


def test_with_no_applications_the_trust_order_still_decides(db_session):
    """The new rule must not override the trust order in the ordinary case."""
    easy = _stored(db_session, source="linkedin_easy_apply", external_id="ea-2")
    direct = _stored(db_session, source="greenhouse", external_id="gh-2")
    db_session.commit()

    upsert_jobs(db_session, [
        _payload(source="linkedin_easy_apply", external_id="ea-2"),
        _payload(source="greenhouse", external_id="gh-2"),
    ])
    db_session.commit()
    db_session.refresh(easy)
    db_session.refresh(direct)
    assert direct.delisted_at is None and easy.delisted_at is not None
