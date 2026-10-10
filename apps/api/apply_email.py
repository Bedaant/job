"""Apply by email: jobs whose `apply_url` is `mailto:` (hiring posts saying "email your
CV to ..."). The extension work queue excludes them, so this is the only thing that
submits them.

State machine — the extension's, run server-side:
  approved --claim (row lock)--> submitting --delivered--> applied (+applied_at)
  approved --refused (address / suppressed / cap / no resume / no sender)--> ready_for_review
  submitting --sender falsy--> ready_for_review
  submitting --sender raised (may have sent)--> submitted_unconfirmed, never re-approvable
  anything else --> untouched, so a retried task or a double approve never sends twice.

Failures land in `ready_for_review` with the reason in `notes`, not back in `approved`
as an extension `failed` does: nothing re-polls `approved` mailto rows, so `approved`
would be stuck forever. Re-approving is the retry.
"""
import logging
import re
from datetime import datetime
from urllib.parse import unquote

import models
from documents.tailored_resume import DOCX_MIME, render_verified_resume, tailored_facts
from events.outbox import write_event
from outreach.send import ACCOUNT_DAILY_CAP, account_sends_today, email_applications_today, lock_user
from outreach.suppression import is_suppressed
from workers.outreach_tasks import _sender_for

logger = logging.getLogger(__name__)

# Per user, separate from outreach.send.DAILY_CAP: an application the employer asked
# for is not cold outreach and must not starve it, but the same ADR-003 ceiling applies.
DAILY_CAP = 10

_PART = r"[^@\s,;<>\"'()\[\]\\:]+"
_ADDRESS = re.compile(rf"{_PART}@{_PART}\.{_PART}")


def recipient(apply_url: str | None) -> str | None:
    """The one plain address in a `mailto:` URL, query dropped; None for anything else.
    Whitespace is refused, which also refuses an encoded CR/LF header injection."""
    if not (apply_url or "").startswith("mailto:"):
        return None
    addr = unquote(apply_url[len("mailto:"):].split("?", 1)[0]).strip()
    return addr if _ADDRESS.fullmatch(addr) else None


def _sent_today(db, user_id: str) -> int:
    """Email applications sent today, plus any in flight (`submitting`)."""
    return email_applications_today(db, user_id)


_GREETING = re.compile(r"^(dear|hello|hi|hey|greetings)\b", re.I)
_SIGNOFF = re.compile(r"\b(regards|sincerely|thank you|thanks|best|cheers),?\s*\n[^\n]*$", re.I)


def _display_name(name: str | None) -> str | None:
    # Rows stored before parsing.llm_extract.tidy_basics existed can still be all caps.
    return name.title() if name and name.isupper() else name


def _email_body(letter: str, job, name: str | None) -> str:
    """A cover letter is written to sit inside a form; as the whole body of an email it needs
    a greeting and a signed close (found in the user-zero run). Never duplicates either."""
    if not letter:
        return (f"Hello,\n\nI would like to apply for the {job.title} role at {job.company}. "
                f"My resume is attached.\n\nThank you,\n{name or ''}").rstrip()
    body = letter if _GREETING.match(letter) else f"Hello,\n\n{letter}"
    if not _SIGNOFF.search(body):
        body += "\n\nBest regards," + (f"\n{name}" if name else "")
    return body


def _note(application, stamp: str) -> None:
    application.notes = f"{application.notes}\n{stamp}" if application.notes else stamp


def _back_to_review(db, application, outcome: str, code: str, reason: str) -> str:
    application.status = models.ApplicationStatus.ready_for_review
    _note(application, f"[{outcome}] {reason}")
    write_event(db, application.profile.user_id, f"application.{outcome}", {
        "application_id": application.id, "status": application.status.value, "reason": reason,
    })
    db.commit()
    logger.info("email application %s not sent: %s", application.id, code)
    return code


def send_application_email(db, application_id: str) -> str:
    """Claim, send, record. Returns a result code; never raises for an expected failure."""
    application = (
        db.query(models.Application)
        .filter(models.Application.id == application_id)
        .with_for_update()
        .first()
    )
    if application is None:
        return "not_found"
    if application.status is not models.ApplicationStatus.approved:
        return "not_approved"

    profile, job = application.profile, application.job
    to = recipient(job.apply_url)
    if to is None:
        return _back_to_review(db, application, "needs_human", "bad_address",
                               "The job's apply address is not one plain email address, so nothing was sent.")
    if is_suppressed(db, profile.id, to):
        return _back_to_review(db, application, "needs_human", "suppressed",
                               "That address is on the suppression list, so nothing was sent.")

    # The user row serialises this user's claims, so two workers cannot both count nine.
    lock_user(db, profile.user_id)
    if _sent_today(db, profile.user_id) >= DAILY_CAP:
        return _back_to_review(db, application, "needs_human", "daily_cap",
                               f"Daily limit of {DAILY_CAP} email applications reached. Approve again tomorrow.")
    if account_sends_today(db, profile.user_id) >= ACCOUNT_DAILY_CAP:
        return _back_to_review(db, application, "needs_human", "daily_cap",
                               f"Your mailbox has sent {ACCOUNT_DAILY_CAP} emails today (applications and "
                               "referral notes together). Approve again tomorrow.")

    facts = tailored_facts(db, application)
    try:
        docx = render_verified_resume(profile, facts) if facts else None
    except Exception as exc:
        logger.warning("email application %s resume failed: %s", application.id, type(exc).__name__)
        docx = None
    if docx is None:
        return _back_to_review(db, application, "needs_human", "no_resume",
                               "No tailored resume grounded in your facts could be generated, so nothing was sent.")

    try:
        sender = _sender_for(db, application)
    except Exception as exc:
        return _back_to_review(db, application, "needs_human", "no_sender",
                               f"No Gmail connected and no SMTP configured ({type(exc).__name__}). "
                               "Connect Gmail, then approve again.")

    # Committed BEFORE the send: a crash mid-send leaves `submitting` (visible, never
    # re-sent) rather than `approved` (sent again by the next trigger).
    application.status = models.ApplicationStatus.submitting
    write_event(db, profile.user_id, "application.status_changed",
                {"application_id": application.id, "status": "submitting"})
    db.commit()

    name = _display_name(profile.full_name)
    body = _email_body((application.tailored_cover_letter or "").strip(), job, name)
    filename = f"{name} - Resume.docx" if name else "Resume.docx"
    try:
        message_id = sender(to, f"Application: {job.title}", body, [(filename, docx, DOCX_MIME)])
    except Exception as exc:
        # An error after the provider accepted the mail looks the same as one before it, so this
        # is never re-approvable: `submitted_unconfirmed`, like the extension's unconfirmed submit.
        # TYPE only: a provider error can echo the message or the credential.
        logger.warning("email application %s send unconfirmed: %s", application.id, type(exc).__name__)
        application.status = models.ApplicationStatus.submitted_unconfirmed
        _note(application, f"[unconfirmed] Sending to {to} raised {type(exc).__name__}; it may or may not "
                           "have gone. Check your Sent folder, then mark it applied.")
        write_event(db, profile.user_id, "application.status_changed",
                    {"application_id": application.id, "status": application.status.value})
        db.commit()
        return "unconfirmed"
    if not message_id:
        return _back_to_review(db, application, "failed", "failed", "The email was not delivered.")

    application.status = models.ApplicationStatus.applied
    application.applied_at = datetime.utcnow()
    _note(application, f"[submitted] Emailed your resume to {to}.")
    write_event(db, profile.user_id, "application.submitted",
                {"application_id": application.id, "status": "applied", "reason": None})
    db.commit()

    # Same stage-8 trigger as report_submission_result; never fatal to the send.
    try:
        from workers.jobs import get_queue
        from workers.outreach_tasks import draft_outreach_task
        get_queue().enqueue(draft_outreach_task, application.id)
    except Exception as exc:
        logger.warning("outreach enqueue failed for application %s: %s", application.id, type(exc).__name__)
    return "sent"


def enqueue_send(db, application) -> None:
    """Queue the send on `effects`. One stable job id per application, so a campaign re-run
    cannot queue it twice (the claim in send_application_email still guards execution)."""
    from rq.exceptions import DuplicateJobError
    from rq.job import Job as RQJob

    from outreach.send import EFFECTS_QUEUE
    from workers.jobs import get_queue

    job_id = f"apply-email-{application.id}"
    try:
        queue = get_queue(EFFECTS_QUEUE)
        try:
            queue.enqueue(send_application_email_task, application.id, job_id=job_id, unique=True)
        except DuplicateJobError:
            # The id outlives the job (result/failure TTL); only a still-pending one means "queued".
            existing = RQJob.fetch(job_id, connection=queue.connection)
            if existing.get_status() in ("queued", "started", "scheduled", "deferred"):
                return
            existing.delete()
            queue.enqueue(send_application_email_task, application.id, job_id=job_id, unique=True)
    except Exception as exc:
        # Left `approved`, nothing would ever send it — hand it back instead (as batch-approve does).
        logger.warning("email application %s enqueue failed: %s", application.id, type(exc).__name__)
        application.status = models.ApplicationStatus.ready_for_review
        _note(application, f"[needs_human] Could not queue the email ({type(exc).__name__}). Approve again.")
        db.commit()


def send_application_email_task(application_id: str) -> dict:
    """RQ entry point. RQ may run it twice; the claim makes the second a no-op."""
    from database import session_scope

    with session_scope() as db:
        return {"application_id": application_id, "result": send_application_email(db, application_id)}
