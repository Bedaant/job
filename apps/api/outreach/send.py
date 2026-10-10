"""REACH-D — claiming an outreach row and delivering it (`docs/PLAN-OUTREACH.md`).

Two functions, deliberately separate, because they have different failure semantics:

`claim_outreach` decides whether this email may go out at all, and takes exclusive
ownership of the row if so. Everything that must be true before mail leaves is checked
here, inside the lock.

`send_outreach` does the delivery and records the outcome. It refuses to run on a row
that was not claimed, so there is no path to mail that skipped the checks.

The sender is injected, following `digest.py`'s existing
`sender(to, subject, body) -> delivered?` contract. That is what lets this whole path
exist and be tested before REACH-A's Gmail credential does.
"""
import logging
from datetime import datetime

from sqlalchemy import or_

import models
from campaigns import utc_day_start
from outreach.suppression import is_suppressed

logger = logging.getLogger(__name__)

# ADR-003. Ten personalised emails a day is the line between outreach and spraying, and
# it is also what keeps us well inside Gmail's own quotas. Not configurable per profile:
# a cap a user can raise is not a cap.
DAILY_CAP = 10
# One ceiling per user across both irreversible email channels (outreach + apply-by-email),
# each of which also keeps its own 10: without it the two sum to 20 from one Gmail account.
ACCOUNT_DAILY_CAP = 15
# RQ queue for irreversible sends, so they never wait behind tailoring or discovery.
EFFECTS_QUEUE = "effects"


def email_applications_today(db, user_id: str) -> int:
    """`mailto:` applications this user sent today, plus any in flight (`submitting`)."""
    return (
        db.query(models.Application)
        .join(models.Profile, models.Application.profile_id == models.Profile.id)
        .join(models.Job, models.Application.job_id == models.Job.id)
        .filter(
            models.Profile.user_id == user_id,
            models.Job.apply_url.like("mailto:%"),
            or_(
                models.Application.applied_at >= utc_day_start(),
                models.Application.status == models.ApplicationStatus.submitting,
            ),
        )
        .count()
    )


def account_sends_today(db, user_id: str) -> int:
    """Everything this user's mailbox sent today or is sending now, across all profiles.
    Callers hold the user row lock (`lock_user`) so two workers cannot both count 14."""
    outreach = (
        db.query(models.Outreach)
        .join(models.Profile, models.Outreach.profile_id == models.Profile.id)
        .filter(
            models.Profile.user_id == user_id,
            or_(
                (models.Outreach.status == models.OutreachStatus.sent)
                & (models.Outreach.sent_at >= utc_day_start()),
                models.Outreach.status == models.OutreachStatus.sending,
            ),
        )
        .count()
    )
    return outreach + email_applications_today(db, user_id)


def lock_user(db, user_id: str) -> None:
    db.query(models.User).filter(models.User.id == user_id).with_for_update().first()


def sent_today(db, profile_id: str) -> int:
    """How many emails this profile has actually DELIVERED in the current UTC day.

    Counts `sent` only. A `failed` or `skipped` row delivered nothing and must not
    consume allowance. `sent_at` is naive UTC (`datetime.utcnow`), matching
    `campaigns.applied_today` — the day boundary is computed the same way, with no tz
    conversion.
    """
    return (
        db.query(models.Outreach)
        .filter(
            models.Outreach.profile_id == profile_id,
            models.Outreach.status == models.OutreachStatus.sent,
            models.Outreach.sent_at >= utc_day_start(),
        )
        .count()
    )


def claim_outreach(db, outreach_id: str, profile_id: str) -> str | None:
    """Take exclusive ownership of one approved row. Returns None on success, else a
    reason string.

    `with_for_update()` locks the row for the transaction, so two concurrent claims on
    the same outreach cannot both succeed. This is the same mechanism and the same
    reasoning as `main.py::claim_submission`: **sending an email is irreversible and
    outward-facing, so this must fire at most once and must never be retriable into a
    duplicate send.** Do not remove the lock because the status check "looks sufficient"
    — the check and the lock guard different failures. The status check stops the
    sequential double-click; the lock stops two workers reading `approved` at the same
    instant. GAPS.md §2 records a reviewer nearly deleting the application-side lock for
    exactly this reason.

    Every precondition is evaluated INSIDE the lock. The cap especially: checked outside,
    two concurrent sends could both observe nine.
    """
    row = (
        db.query(models.Outreach)
        .filter(
            models.Outreach.id == outreach_id,
            models.Outreach.profile_id == profile_id,
        )
        .with_for_update()
        .first()
    )
    if row is None:
        return "not_found"

    # Not `!= approved`, because the distinction matters to the caller: an already-`sending`
    # row is a double-claim, which is the case this function exists to refuse.
    if row.status is not models.OutreachStatus.approved:
        return "not_approved"

    # Re-checked here and not only at drafting time: the gap between the two is minutes
    # at best, and an opt-out that loses that race is not an opt-out.
    contact = row.contact
    if contact is None or is_suppressed(db, profile_id, contact.email):
        row.status = models.OutreachStatus.skipped
        row.skip_reason = "suppressed"
        return "suppressed"

    # DEPLOY-A.4. Every body carries an unsubscribe link built from `api_base_url`, which
    # defaults to localhost. Sending on that default means THE RECIPIENT CANNOT OPT OUT,
    # which defeats the one guarantee REACH-E exists to provide — and by the time the mail
    # has gone, the dead link is already in someone's inbox and cannot be fixed.
    #
    # The owner's own address is exempt, because otherwise no end-to-end delivery test is
    # possible before deploying, and the gate exists to protect people who are NOT the
    # operator. Left `approved` rather than failed: it is a configuration problem, so the
    # row should send once the URL is public.
    if not _unsubscribe_is_reachable(contact.email, row.profile):
        return "unsubscribe_unreachable"

    # Deliberately left `approved` rather than failed: the cap is a pacing rule, not
    # an error, and this row should go out on the next day's first pass.
    user_id = row.profile.user_id
    lock_user(db, user_id)
    if sent_today(db, profile_id) >= DAILY_CAP or account_sends_today(db, user_id) >= ACCOUNT_DAILY_CAP:
        return "daily_cap"

    row.status = models.OutreachStatus.sending
    return None


def send_outreach(db, row: models.Outreach, sender) -> bool:
    """Deliver a claimed row. Returns whether mail actually left.

    `sender(to, subject, body)` returns a provider message id (truthy) or something
    falsy if nothing was delivered — `digest.log_only_sender` is the falsy case, and is
    what runs until Gmail is wired.
    """
    if row.status is not models.OutreachStatus.sending:
        # Sending an unclaimed row would bypass the lock, the cap and the suppression
        # re-check in one go.
        raise ValueError(f"outreach {row.id} was not claimed (status={row.status})")

    to = row.contact.email if row.contact else None
    if not to:
        row.status = models.OutreachStatus.skipped
        row.skip_reason = "email_missing"
        return False

    try:
        message_id = sender(to, row.subject or "", row.body or "")
    except Exception as exc:
        # TYPE only. A provider's reply can echo what was sent, and that includes the
        # credential — `digest.smtp_sender` sets this precedent.
        row.status = models.OutreachStatus.failed
        row.error = type(exc).__name__
        logger.warning("outreach %s failed: %s", row.id, type(exc).__name__)
        return False

    if not message_id:
        # A sender that delivered nothing must never leave the row reading `sent`.
        row.status = models.OutreachStatus.failed
        row.error = "not_delivered"
        return False

    row.status = models.OutreachStatus.sent
    row.sent_at = datetime.utcnow()
    row.gmail_message_id = str(message_id)
    return True


_LOCAL_HOSTS = ("localhost", "127.0.0.1", "0.0.0.0", "::1")


def _unsubscribe_is_reachable(recipient_email: str, profile) -> bool:
    """Could this recipient actually reach the unsubscribe link we are about to send?

    False when `api_base_url` is a local address AND the recipient is not the operator
    themselves. A self-test to one's own inbox is fine — a dead link to a stranger is not,
    and REACH-E's whole promise is that someone who asks not to be contacted can act on it
    without an account.
    """
    from core.config import get_settings

    base = (get_settings().api_base_url or "").casefold()
    if not any(h in base for h in _LOCAL_HOSTS):
        return True

    # Exempt the operator's own address, so delivery can be proven before deploying.
    own = {
        (getattr(profile, "user", None).email or "").casefold()
        if getattr(profile, "user", None) else "",
        (get_settings().smtp_from or "").casefold(),
        (get_settings().smtp_user or "").casefold(),
    }
    return (recipient_email or "").casefold() in {o for o in own if o}
