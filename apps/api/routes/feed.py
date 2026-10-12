"""Sources, real-time events, activity, today, digest preview, notifications, outcome prompts."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from core.config import get_settings
from core.deps import get_current_user
from database import get_db
import models
import schemas
import outcomes
from events.sse import event_stream
import campaigns as campaigns_service
from routes.applications import _ready_to_send

settings = get_settings()

router = APIRouter()

# Job sources the discovery worker actually searches (workers/jobs.py), with two
# health signals: how many jobs each has put in the shared pool, and whether its
# most recent discovery run failed (connector_runs, written per source per run
# since Phase 2 item 2).
_SOURCE_LABELS = {
    "remotive": ("Remotive", "Remote-first job board"),
    "remoteok": ("Remote OK", "Remote jobs board"),
    "himalayas": ("Himalayas", "Remote jobs board"),
    "workingnomads": ("Working Nomads", "Remote jobs board"),
    "jobicy": ("Jobicy", "Remote jobs board"),
    "arbeitnow": ("Arbeitnow", "Europe-focused listings"),
    "weworkremotely": ("We Work Remotely", "Remote jobs board"),
    "reed": ("Reed", "UK listings"),
    "greenhouse": ("Greenhouse", "Company career pages"),
    "lever": ("Lever", "Company career pages"),
    "ashby": ("Ashby", "Company career pages"),
    "workday": ("Workday", "Enterprise career sites, incl. India GCCs"),
}


@router.get("/sources", response_model=list[schemas.SourceOut])
def list_sources(db: Session = Depends(get_db), _user: models.User = Depends(get_current_user)):
    from sqlalchemy import func
    from connectors import config as conn_config

    reasons = {
        "remotive": None,  # searched with active campaigns' roles
        "reed": None if settings.reed_api_key else "Not connected yet.",
        "greenhouse": None if conn_config.GREENHOUSE_BOARD_TOKENS else "No company boards added yet.",
        "lever": None if conn_config.LEVER_COMPANY_TOKENS else "No company boards added yet.",
        "ashby": None if conn_config.ASHBY_ORG_TOKENS else "No company boards added yet.",
        "workday": None if conn_config.WORKDAY_BOARDS else "No company boards added yet.",
    }
    for feed in _SOURCE_LABELS:
        reasons.setdefault(feed, None if feed in conn_config.ENABLED_FEEDS else "Not searched right now.")

    # A source configured correctly but failing upstream is not "enabled" in any
    # sense the user cares about, so the last run's error wins over config.
    # ponytail: newest rows, first one per source wins — cheaper than a
    # per-source MAX(ran_at) join at ~14 sources an hour. Raise the limit (or
    # join) if the source list grows past what 200 rows covers.
    latest: dict[str, str | None] = {}
    for source, error in (
        db.query(models.ConnectorRun.source, models.ConnectorRun.error)
        .order_by(models.ConnectorRun.ran_at.desc())
        .limit(200)
        .all()
    ):
        latest.setdefault(source, error)  # newest first, so the first row per source is the latest
    for source, error in latest.items():
        if error and reasons.get(source) is None and source in _SOURCE_LABELS:
            reasons[source] = "Last check failed; trying again on the next run."

    # Live rows only (GAPS 2.5). This counted tombstones too, which mattered
    # little when the pool was ~1,800 keyword-filtered rows and matters a lot
    # now ADR-021 stores whole boards: the number a user reads as "jobs from
    # this source" should not include ones it stopped listing.
    counts = dict(
        db.query(models.Job.source, func.count(models.Job.id))
        .filter(models.Job.delisted_at.is_(None))
        .group_by(models.Job.source)
        .all()
    )
    return [
        schemas.SourceOut(id=sid, label=label, note=note, enabled=reasons[sid] is None,
                          reason=reasons[sid], job_count=counts.get(sid, 0))
        for sid, (label, note) in _SOURCE_LABELS.items()
    ]


# ---------- Real-time events / notifications (ADR-012, SPEC.md §2.6) ----------

@router.get("/events")
async def stream_events(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    last_event_id = request.headers.get("Last-Event-ID")
    return EventSourceResponse(event_stream(db, current_user.id, last_event_id))


# Event type -> (title, detail when the payload gives none). Only types something
# actually writes; `application.status_changed` is left out on purpose — it is
# the claim/PATCH plumbing, not something Maggie did that the user needs to see.
_ACTIVITY = {
    "match.new": ("New match", None),
    "application.ready_for_review": ("Ready for your review", None),
    "application.approved": ("Approved to send", None),
    "application.submitted": ("Applied", None),
    "application.unconfirmed": ("Sent — couldn't confirm it went through",
                                "Check your email for a confirmation, or open the form."),
    "application.needs_human": ("Stopped on a question", "Needs an answer from you before it can be sent."),
    "application.failed": ("Couldn't send", "Maggie will try again."),
    "campaign.skipped": ("Skipped", None),
    "campaign.scheduled_run": ("Ran on schedule", None),
}
# campaign.skipped rows without a job are run-level notes; title by reason_code.
_RUN_SKIP_TITLES = {"checked": "Checked new jobs", "daily_cap": "Daily limit reached", "not_active": "Didn't run"}


@router.get("/activity", response_model=list[schemas.ActivityItemOut])
def list_activity(
    since: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """What Maggie did, newest first, from the events outbox. Plain JSON, not
    SSE: a native EventSource can't send the bearer header."""
    query = db.query(models.Event).filter(
        models.Event.user_id == current_user.id, models.Event.type.in_(_ACTIVITY)
    )
    if since is not None:
        if since.tzinfo:
            since = since.astimezone(timezone.utc).replace(tzinfo=None)
        query = query.filter(models.Event.created_at >= since)
    events = query.order_by(models.Event.created_at.desc(), models.Event.id.desc()).limit(limit).all()

    # Two batched lookups, not one per row. Applications are reached only
    # through the caller's own profiles.
    app_ids = {e.payload.get("application_id") for e in events} - {None}
    apps = {
        a.id: a for a in db.query(models.Application).join(models.Profile)
        .filter(models.Application.id.in_(app_ids), models.Profile.user_id == current_user.id)
    } if app_ids else {}
    job_ids = {e.payload.get("job_id") for e in events} | {a.job_id for a in apps.values()}
    job_ids.discard(None)
    jobs = {j.id: j for j in db.query(models.Job).filter(models.Job.id.in_(job_ids))} if job_ids else {}

    items = []
    for e in events:
        p = e.payload or {}
        title, fallback = _ACTIVITY[e.type]
        application = apps.get(p.get("application_id"))
        job = jobs.get(application.job_id if application else p.get("job_id"))
        if e.type == "match.new" and p.get("score") is not None:
            detail = f"{round(float(p['score']))}% match"  # Match.score is 0..100
        else:
            detail = p.get("reason") or fallback
        if e.type == "campaign.skipped" and not job:
            title = _RUN_SKIP_TITLES.get(p.get("reason_code"), "Maggie didn't apply")
        if e.type == "application.submitted" and p.get("manual"):
            title = "You sent it"
        unconfirmed = e.type == "application.unconfirmed"
        if unconfirmed and job:
            title = f"Sent to {job.company} — couldn't confirm it went through"
        items.append(schemas.ActivityItemOut(
            id=e.id, type=e.type, at=e.created_at.replace(tzinfo=timezone.utc), title=title, detail=detail,
            application_id=application.id if application else None,
            job=schemas.ActivityJob(title=job.title, company=job.company) if job else None,
            apply_url=job.apply_url if unconfirmed and job else None,
        ))
    return items


@router.get("/today", response_model=schemas.TodayOut)
def get_today(
    tz: str | None = Query(None, max_length=64),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Home-screen counters across all the caller's profiles, over the caller's
    local day (`tz` = IANA name; invalid or missing → UTC) so they agree with the
    activity list. The daily cap stays on the UTC day. Campaign status and the
    cap come from /campaigns and /campaigns/{id}/stats, not here.
    """
    start = campaigns_service.local_day_start(tz)
    mine = db.query(models.Profile.id).filter(models.Profile.user_id == current_user.id)
    apps = db.query(models.Application).filter(models.Application.profile_id.in_(mine))
    sent = apps.filter(models.Application.applied_at >= start)
    ready = [
        r for p in db.query(models.Profile).filter(models.Profile.user_id == current_user.id)
        for r in _ready_to_send(db, p)
    ]
    return schemas.TodayOut(
        ready_to_send=len(ready),
        sent_today=sent.count(),
        unconfirmed_today=sent.filter(
            models.Application.status == models.ApplicationStatus.submitted_unconfirmed
        ).count(),
        # The review queue minus what's ready to send (needs_human lands back in ready_for_review).
        # A prepared one is counted once, as ready_to_send, not also here.
        needs_you=apps.filter(models.Application.status == models.ApplicationStatus.ready_for_review).count()
        - sum(r.status == models.ApplicationStatus.ready_for_review.value for r in ready),
        new_matches_today=db.query(models.Match).filter(
            models.Match.profile_id.in_(mine), models.Match.created_at >= start
        ).count(),
    )


@router.get("/digest/preview")
def preview_digest(
    tz: str | None = Query(None, max_length=64),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Today's digest so far, over the caller's local day (same `tz` rule as /today)."""
    import digest

    d = digest.build_digest(db, current_user, campaigns_service.local_day_start(tz), datetime.utcnow())
    return {**d, "text": digest.render_text(d)}


@router.get("/notifications", response_model=list[schemas.NotificationOut])
def list_notifications(
    status: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.Notification).filter(models.Notification.user_id == current_user.id)
    if status:
        query = query.filter(models.Notification.status == status)
    return query.order_by(models.Notification.created_at.desc()).all()


@router.patch("/notifications/{notification_id}", response_model=schemas.NotificationOut)
def update_notification(
    notification_id: str,
    payload: schemas.NotificationUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    notif = (
        db.query(models.Notification)
        .filter(models.Notification.id == notification_id, models.Notification.user_id == current_user.id)
        .first()
    )
    if not notif:
        raise HTTPException(404, "Notification not found")
    notif.status = payload.status
    db.commit()
    db.refresh(notif)
    return notif


@router.get("/outcome-prompts", response_model=list[schemas.OutcomePromptOut])
def list_outcome_prompts(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """The in-app "Heard back?" prompts still waiting for a tap (outcomes.py)."""
    return outcomes.pending_prompts(db, current_user.id)
