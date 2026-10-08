"""REACH-C — may we contact this address at all? (`docs/PLAN-OUTREACH.md`)

Checked before a draft is written AND again immediately before send, because a
suppression written between those two moments must still take effect — the gap is
minutes at best and an opt-out that loses that race is not an opt-out.

Fails CLOSED. Every path that cannot prove an address is contactable returns True.
"""
import models


def is_suppressed(db, profile_id: str, email: str | None) -> bool:
    """True = do not contact.

    A `Suppression` row with `profile_id IS NULL` is GLOBAL and blocks every user:
    someone who asks not to be contacted should not have to ask each user of this
    product separately. A row with a `profile_id` blocks only that profile, which is
    what "this user decided not to contact them" means.

    `domain` blocks every address at a company, so an employer asking to be left alone
    entirely is one row rather than one per employee.
    """
    # No address is not "not suppressed" — nothing may be sent to an unknown address, so
    # the absence of one can never be a reason to proceed.
    if not email or not email.strip():
        return True

    addr = email.strip().casefold()
    domain = addr.rpartition("@")[2]
    if not domain:
        return True

    # Case-folded on both sides: addresses arrive from three adapters with inconsistent
    # casing, and an opt-out that only works in lowercase is not an opt-out. Done in
    # Python rather than SQL `lower()` so the behaviour is identical on SQLite and
    # Postgres — the suppression table is small by construction (one row per person who
    # ever opted out), so scanning the candidate rows is not worth an index trick.
    rows = (
        db.query(models.Suppression)
        .filter(
            (models.Suppression.profile_id == profile_id)
            | (models.Suppression.profile_id.is_(None))
        )
        .all()
    )
    for row in rows:
        if row.email and row.email.strip().casefold() == addr:
            return True
        if row.domain and row.domain.strip().casefold() == domain:
            return True
    return False
