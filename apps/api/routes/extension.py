"""Browser extension: status, work queue, form-field mapping."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import answer_bank as answer_bank_service
import ats_controls
from core.deps import get_current_user, resolve_profile_ownership
from database import get_db
import models
import schemas
import send_gate
from connectors.apply_target import resolve_apply_target
from formfill.map_fields import build_profile_summary, map_form_fields
from formplans import current_plan

router = APIRouter()

# "Connected" = the extension called in this recently. The driver only calls in
# when the popup opens or a queue run happens, so this is "recently used", not a
# live socket; 10 minutes covers a user moving between the web app and the popup.
EXTENSION_CONNECTED_WINDOW = timedelta(minutes=10)


def extension_connected(last_seen_at: datetime | None, now: datetime) -> bool:
    return last_seen_at is not None and now - last_seen_at <= EXTENSION_CONNECTED_WINDOW


def _mark_extension_seen(db: Session, user: models.User) -> None:
    user.extension_last_seen_at = datetime.utcnow()
    db.commit()


def _work_queue_query(db: Session, user: models.User):
    """What the extension driver would pick up: `approved`, owned, actionable."""
    return (
        db.query(models.Application)
        .join(models.Profile, models.Application.profile_id == models.Profile.id)
        .join(models.Job, models.Application.job_id == models.Job.id)
        .filter(
            models.Profile.user_id == user.id,
            models.Application.status == models.ApplicationStatus.approved,
            # An empty apply_url is unactionable: handing it to the driver buys a
            # guaranteed failure report and burns a retry for nothing.
            models.Job.apply_url != "",
            models.Job.apply_url.isnot(None),
            # A mailto: has no form to fill. Hiring posts that say "email your CV" land
            # here as jobs the user sees but the extension must never be handed.
            ~models.Job.apply_url.like("mailto:%"),
        )
    )


@router.get("/extension/status", response_model=schemas.ExtensionStatusOut)
def extension_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Read by the web app, so it never stamps last-seen itself."""
    return schemas.ExtensionStatusOut(
        connected=extension_connected(current_user.extension_last_seen_at, datetime.utcnow()),
        last_seen_at=current_user.extension_last_seen_at,
        approved_waiting=_work_queue_query(db, current_user).count(),
    )


@router.get("/extension/work-queue", response_model=list[schemas.WorkQueueItemOut])
def extension_work_queue(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """ADR-015 Phase 1: the missing link between a campaign run and a sent
    application. `run_campaign_task` produced `approved` rows and nothing ever
    collected them, so a campaign ended in a queue. This is what the extension
    driver pulls.

    Only `approved` is work. A `submitting` row has already been claimed by a
    driver pass, so re-serving it is exactly how the same job gets applied to
    twice — the claim moving the row out of `approved` is what makes this queue
    self-draining.
    """
    _mark_extension_seen(db, current_user)
    if not send_gate.can_send(db, current_user)[0]:  # paused: hand the driver nothing
        return []
    rows = (
        _work_queue_query(db, current_user)
        .order_by(models.Application.created_at.asc())
        .limit(limit)
        .all()
    )
    items = []
    for row in rows:
        original = row.job.apply_url
        # ADR-015 Phase 2: a feed's apply_url is usually an aggregator redirector,
        # not the form. Resolving it is an optimisation, so a resolver failure
        # degrades to the original URL rather than emptying the queue.
        try:
            target = resolve_apply_target(original)
        except Exception:
            target = {"final_url": original, "ats_type": None, "board_token": None, "resolved": False}
        items.append(schemas.WorkQueueItemOut(
            application_id=row.id,
            profile_id=row.profile_id,
            apply_url=target["final_url"] if target["resolved"] else original,
            company=row.job.company,
            title=row.job.title,
            original_apply_url=original,
            ats_type=target["ats_type"],
            board_token=target["board_token"],
            job_id=row.job_id,
        ))
    return items


# ---------- F11 form-fill agent (ADR-011, SPEC.md §3.7) ----------

@router.post("/extension/map-fields", response_model=list[schemas.FieldMappingOut])
def extension_map_fields(
    payload: schemas.MapFieldsRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Proxies the bounded Claude/nvidia_smoke call for the extension's
    content script — the model call happens here, server-side, never from
    extension code, so no Anthropic/NVIDIA key ever ships client-side.
    """
    profile = resolve_profile_ownership(db, current_user, payload.profile_id)
    _mark_extension_seen(db, current_user)
    ats_controls.ensure_fill_enabled(db, payload.ats_type, payload.url)

    profile_summary = build_profile_summary(profile, current_user.email)
    fields = [f.model_dump() for f in payload.fields]

    # The answer bank, scoped to this profile and injected as a plain callable —
    # a question the user has already answered in their own words is filled here
    # instead of interrupting them again. serve_answer refuses demographic
    # questions itself, and map_form_fields never reaches it for one anyway.
    def answer_lookup(question_text: str | None) -> str | None:
        if not question_text:
            return None
        return answer_bank_service.serve_answer(db, profile.id, question_text)

    # ADR-016: the job's shared form plan (no PII, so no ownership check). None = fill as before.
    plan = current_plan(db, payload.job_id) if payload.job_id else None
    return map_form_fields(
        # The popup's fill sends no ats_type: the page URL decides, as for the kill switch.
        fields, profile_summary, answer_lookup=answer_lookup,
        ats_type=ats_controls._ats_of(payload.ats_type, payload.url), plan=plan,
    )
