"""REACH-D — what happens after an application goes out (`docs/PLAN-OUTREACH.md`).

Ties REACH-B/C/D together: find people at the company, rank them by a connection that
is actually true, check they may be contacted, draft, persist. Everything called here is
tested in isolation; what this module owns is the ordering and the refusals.

**Every refusal leaves a visible row.** A user who applied and got no outreach must be
able to see why — nobody found, suppressed, no address, nothing groundable — so each of
those writes a `skipped` row with a reason. Silence would be indistinguishable from a
bug, and `GitHubContactSource` returning nothing is the measured NORMAL case for a
product role, not an exception.

**Free sources before paid ones.** `sources` is tried in order and stops as soon as the
quota is filled, so GitHub (free) spends Apify's per-profile charge only on the companies
it cannot reach.

WHEN THIS RUNS, and the one trade-off worth the owner's eye. `README.md` says "After you
apply…", so this fires for an application that reached the employer: `applied`, or
`submitted_unconfirmed`. The second is debatable — it means the submit was sent and the
employer's page never confirmed it, so an email saying "I've applied" *could* be false if
the submit silently failed. Included anyway, because `submitted_unconfirmed` is a real
and common end state (nothing auto-promotes it to `applied`) and excluding it would make
the whole feature almost never fire. If that trade is wrong it is a one-line change to
`_SENT_STATES`.
"""
import logging

import models
from outreach.contacts import ContactCandidate
from outreach.draft import draft_outreach
from outreach.optout import make_token
from outreach.signals import rank_contacts
from outreach.suppression import is_suppressed

logger = logging.getLogger(__name__)

# Both mean the form reached the employer. `submitting` is the in-flight window and is
# deliberately excluded: its own docstring says the submit may yet have failed.
_SENT_STATES = (
    models.ApplicationStatus.applied,
    models.ApplicationStatus.submitted_unconfirmed,
)


def _facts_for(profile) -> list[dict]:
    """The same shape `tailoring.tailor_application` takes. Only CONFIRMED facts reach
    generation (ADR-009), and only ones with an id can be cited by a bullet."""
    return [
        {"id": f.id, "category": f.category, "achievement": f.achievement,
         "proof": f.proof, "metric": f.metric}
        for f in profile.resume_facts
        if f.id
    ]


def _unsubscribe_url(outreach_id: str) -> str:
    from core.config import get_settings

    base = get_settings().api_base_url.rstrip("/")
    return f"{base}/outreach/unsubscribe/{make_token(outreach_id)}"


def _gather(sources, company: str, titles: list[str], wanted: int) -> list[ContactCandidate]:
    """Ask each source in turn until `wanted` candidates are collected.

    A source that raises is logged and skipped, never fatal: Apify is an untrusted
    network dependency and its outage must not cost the free source's results. Type only
    in the log — a vendor error body can echo what was sent.
    """
    found: list[ContactCandidate] = []
    seen: set[str] = set()
    for source in sources:
        if len(found) >= wanted:
            break
        try:
            candidates = source.find(company=company, titles=titles, limit=wanted - len(found))
        except Exception as exc:
            logger.warning("contact source %s failed: %s",
                           getattr(source, "name", "?"), type(exc).__name__)
            continue
        for c in candidates or []:
            key = (c.email or f"{c.full_name}|{c.company}").casefold()
            if key in seen:
                continue
            seen.add(key)
            found.append(c)
            if len(found) >= wanted:
                break
    return found


def _skip(db, application, reason: str, contact=None) -> models.Outreach:
    row = models.Outreach(
        profile_id=application.profile_id,
        application_id=application.id,
        contact_id=contact.id if contact is not None else None,
        status=models.OutreachStatus.skipped,
        skip_reason=reason,
    )
    db.add(row)
    db.flush()
    return row


def draft_outreach_for_application(db, application_id: str, sources) -> dict:
    """Find contacts for one application and draft a note to each.

    Idempotent by a pre-check plus `UNIQUE(application_id, contact_id)` in the schema.
    ADR-008 documents RQ retrying on worker crash, so this WILL run twice for some
    applications, and a retry must not produce a second email to the same person.
    """
    application = (
        db.query(models.Application).filter(models.Application.id == application_id).first()
    )
    if application is None:
        return {"application_id": application_id, "result": "not_found"}

    if application.status not in _SENT_STATES:
        # Nothing went out, so there is nothing to ask about — and an email claiming an
        # application that does not exist is exactly the kind of unsupported claim this
        # product exists not to make.
        return {"application_id": application_id, "result": "not_sent"}

    existing = (
        db.query(models.Outreach)
        .filter(models.Outreach.application_id == application_id)
        .count()
    )
    if existing:
        return {"application_id": application_id, "result": "already_done", "outreach": existing}

    profile = application.profile
    job = application.job
    wanted = max(1, profile.outreach_contacts_per_application or 1)

    candidates = _gather(sources, company=job.company, titles=[job.title], wanted=wanted)
    if not candidates:
        _skip(db, application, "no_contact_found")
        db.commit()
        return {"application_id": application_id, "result": "no_contact_found"}

    facts = _facts_for(profile)
    ranked = rank_contacts(candidates, facts=profile.resume_facts, profile=profile,
                           job_title=job.title or "")

    created, skipped = 0, 0
    for candidate in ranked[:wanted]:
        contact = _persist_contact(db, profile, candidate)

        if not candidate.email:
            _skip(db, application, "email_missing", contact)
            skipped += 1
            continue
        # Checked here AND again at send time (`outreach/send.py`): an opt-out that lands
        # between drafting and approval must still take effect.
        if is_suppressed(db, profile.id, candidate.email):
            _skip(db, application, "suppressed", contact)
            skipped += 1
            continue

        # The row is created BEFORE the draft because the unsubscribe token is per-row:
        # the body cannot be written until the id it points at exists.
        row = models.Outreach(
            profile_id=profile.id,
            application_id=application.id,
            contact_id=contact.id,
            status=models.OutreachStatus.ready_for_review,
            warm_signal_used=candidate.warm_signal,
        )
        db.add(row)
        db.flush()

        try:
            drafted = draft_outreach(
                facts=facts,
                job={"title": job.title, "company": job.company},
                contact=candidate,
                unsubscribe_url=_unsubscribe_url(row.id),
            )
        except ValueError:
            # No confirmed fact has an id, so nothing could be grounded. ADR-009: a note
            # with nothing behind it gives the recipient no reason to help anyway.
            row.status = models.OutreachStatus.skipped
            row.skip_reason = "nothing_groundable"
            skipped += 1
            continue
        except Exception as exc:
            row.status = models.OutreachStatus.skipped
            row.skip_reason = "draft_failed"
            logger.warning("outreach draft failed for %s: %s", row.id, type(exc).__name__)
            skipped += 1
            continue

        row.subject = drafted.get("subject")
        row.body = drafted.get("body")
        row.flagged_unsupported_claims = drafted.get("flagged_unsupported_claims") or []
        created += 1

    db.commit()
    return {"application_id": application_id, "result": "drafted",
            "created": created, "skipped": skipped}


def _persist_contact(db, profile, candidate: ContactCandidate) -> models.Contact:
    """Reuse an existing row for this address rather than inserting a duplicate —
    `UNIQUE(profile_id, email)` would otherwise raise on the second application to the
    same company, which is a normal thing for a user to do."""
    existing = None
    if candidate.email:
        existing = (
            db.query(models.Contact)
            .filter(models.Contact.profile_id == profile.id,
                    models.Contact.email == candidate.email)
            .first()
        )
    if existing is not None:
        existing.warm_signal = candidate.warm_signal or existing.warm_signal
        db.flush()
        return existing

    contact = models.Contact(
        profile_id=profile.id,
        company=candidate.company,
        full_name=candidate.full_name,
        title=candidate.title,
        email=candidate.email,
        source=candidate.source,
        source_ref=candidate.source_ref,
        warm_signal=candidate.warm_signal,
    )
    db.add(contact)
    db.flush()
    return contact
