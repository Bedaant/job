"""Job discovery, the job list, and campaigns (ADR-015 section 2).

One module because `/discover/run` and `/campaigns/{id}/run` share the worker check
and the RQ enqueue path.
"""

import hashlib
import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from rq.exceptions import DuplicateJobError
from rq.job import Job as RQJob
from rq.worker import Worker as RQWorker

from core.deps import get_current_user, resolve_profile_ownership
from database import get_db
import models
import schemas
from events.outbox import record_funnel
from workers.jobs import (
    BACKGROUND_QUEUE, DISCOVERY_TIMEOUT_SECONDS, discover_jobs_task, get_queue, get_redis_connection,
    campaign_search_task, run_campaign_task,
)
import campaigns as campaigns_service

router = APIRouter()

# ---------- Job discovery ----------

def _workers_online() -> bool:
    return RQWorker.count(connection=get_redis_connection()) > 0


NO_WORKER = ("The background worker isn't running, so this can't start. "
             "Start it with: python -m workers.run_worker (in apps/api).")


@router.post("/discover/run")
def run_discovery(_user: models.User = Depends(get_current_user)):
    """Enqueues onto RQ instead of running inline — fixes CODE-REVIEW.md B6.
    Requires a worker process running `rq worker` to actually process it.

    SPEC.md §3.6 idempotency, layer 1 — enqueue dedupe: job_id is derived
    from a 1-minute time bucket, enqueued with unique=True (raises
    DuplicateJobError, verified against the installed rq's own source, if a
    job with that ID is already queued/running) — a second call within the
    same minute returns the existing task_id instead of double-enqueuing.
    Layer 2 (the execution claim) lives in discover_jobs_task itself.
    """
    if not _workers_online():  # queued with no worker = silently never runs (found live)
        raise HTTPException(503, NO_WORKER)
    job_id = f"discover-{int(time.time() // 60)}"  # rq: [A-Za-z0-9_-] only
    try:
        job = get_queue(BACKGROUND_QUEUE).enqueue(
            discover_jobs_task, job_id=job_id, unique=True, kwargs={"job_id": job_id},
            job_timeout=DISCOVERY_TIMEOUT_SECONDS,
        )
    except DuplicateJobError:
        job = RQJob.fetch(job_id, connection=get_redis_connection())
    return {"task_id": job.id, "status": job.get_status()}


@router.get("/discover/run/{task_id}")
def get_discovery_status(task_id: str, _user: models.User = Depends(get_current_user)):
    job = RQJob.fetch(task_id, connection=get_redis_connection())
    return {
        "task_id": job.id,
        "status": job.get_status(),
        "result": job.result,
    }


@router.get("/jobs", response_model=list[schemas.JobOut])
def list_jobs(db: Session = Depends(get_db), limit: int = 100, _user: models.User = Depends(get_current_user)):
    # Task 5 (freshness): never list a job that's disappeared from its source.
    return (
        db.query(models.Job)
        .filter(models.Job.delisted_at.is_(None))
        .order_by(models.Job.fetched_at.desc())
        .limit(limit)
        .all()
    )


# ---------- Campaigns (ADR-015 §2 — the unit of approval) ----------

@router.post("/campaigns", response_model=schemas.CampaignOut)
def create_campaign(
    payload: schemas.CampaignCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    profile = resolve_profile_ownership(db, current_user, payload.profile_id)
    campaign = models.Campaign(
        profile_id=profile.id, **payload.model_dump(exclude={"profile_id"})
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.get("/campaigns", response_model=list[schemas.CampaignOut])
def list_campaigns(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Every campaign across the caller's profiles. Scoped by the join, not by
    a client-supplied profile_id — there is nothing here to trust from the
    request at all.
    """
    return (
        db.query(models.Campaign)
        .join(models.Profile, models.Campaign.profile_id == models.Profile.id)
        .filter(models.Profile.user_id == current_user.id)
        .order_by(models.Campaign.created_at.desc())
        .all()
    )


@router.get("/campaigns/{campaign_id}", response_model=schemas.CampaignOut)
def get_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return campaigns_service.resolve_campaign_ownership(db, current_user, campaign_id)


@router.patch("/campaigns/{campaign_id}", response_model=schemas.CampaignOut)
def update_campaign(
    campaign_id: str,
    payload: schemas.CampaignUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Edit / pause / resume. Status moves only along
    campaigns.ALLOWED_TRANSITIONS — archived is terminal.
    """
    campaign = campaigns_service.resolve_campaign_ownership(db, current_user, campaign_id)
    fields = payload.model_dump(exclude_unset=True, exclude_none=True)
    was_active = campaign.status == models.CampaignStatus.active
    search_changed = bool(fields.keys() & {"roles", "locations", "sources"})

    new_status = fields.pop("status", None)
    if new_status is not None:
        try:
            target = models.CampaignStatus(new_status)
        except ValueError:
            raise HTTPException(422, f"Unknown campaign status {new_status!r}")
        if target != campaign.status and target not in campaigns_service.ALLOWED_TRANSITIONS[campaign.status]:
            raise HTTPException(422, f"Cannot move a {campaign.status.value} campaign to {target.value}")
        campaign.status = target

    for key, value in fields.items():
        setattr(campaign, key, value)

    # GAPS 2.4 — an ACTIVE campaign must name at least one role.
    #
    # ADR-021 stopped FEED_KEYWORDS gating ingest, so discovery stores whole
    # boards (1,768 -> 5,119 jobs on the first unfiltered run). That global
    # keyword list had been an accidental backstop: `campaigns._in_bounds`
    # applies its title filter only `if campaign.roles`, so a roles-less
    # campaign used to be harmless purely because nothing but product roles had
    # ever been collected. Now it draws from the entire pool, gated only by
    # min_match_score and passes_hard_filters — and the latter is deliberately
    # built so missing data never excludes a job. With auto_submit on, that is
    # an autonomous apply path to postings nobody asked for.
    #
    # Checked on the RESULTING state, which covers both ways in: activating a
    # roles-less campaign, and clearing roles on one that is already active.
    # Only the active end state binds, so pausing or archiving a pre-existing
    # roles-less row still works — that is how a user would fix one.
    #
    # Blank strings do not count: _in_bounds would build `title.ilike('%%')`,
    # which matches every job, so `[""]` is exactly as wide open as [].
    if campaign.status == models.CampaignStatus.active and not [
        r for r in (campaign.roles or []) if r and r.strip()
    ]:
        raise HTTPException(
            422,
            "An active campaign needs at least one role — it decides which jobs "
            "Maggie may apply to, and without it the campaign matches every "
            "posting we have collected. Add a role, or leave the campaign paused.",
        )

    if campaign.status == models.CampaignStatus.active:
        record_funnel(db, current_user.id, "campaign_active")
    db.commit()
    db.refresh(campaign)
    if campaign.status == models.CampaignStatus.active and (not was_active or search_changed):
        _queue_campaign_search(campaign)
    return campaign


def _queue_campaign_search(campaign: models.Campaign) -> None:
    """Search for this campaign's own titles now, not at the next scheduled pass. The id
    carries the titles/locations, so editing them right after starting still searches again."""
    plan = "|".join(sorted(campaign.roles or []) + sorted(campaign.locations or []))
    key = hashlib.sha1(plan.encode()).hexdigest()[:8]
    job_id = f"campaign-search-{campaign.id}-{key}-{int(time.time() // 300)}"
    try:
        get_queue(BACKGROUND_QUEUE).enqueue(
            campaign_search_task, job_id=job_id, unique=True,
            job_timeout=DISCOVERY_TIMEOUT_SECONDS, kwargs={"campaign_id": campaign.id},
        )
    except DuplicateJobError:
        pass
    except Exception as exc:
        # The campaign is saved either way; the daily refresh searches it if this missed.
        logging.getLogger(__name__).warning(
            "campaign search enqueue failed for %s: %s", campaign.id, type(exc).__name__)


@router.delete("/campaigns/{campaign_id}", response_model=schemas.CampaignOut)
def archive_campaign(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Archive, never a hard delete — the campaign is the record of what the
    user authorized, and its applications point back at it.
    """
    campaign = campaigns_service.resolve_campaign_ownership(db, current_user, campaign_id)
    campaign.status = models.CampaignStatus.archived
    db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/campaigns/{campaign_id}/run")
def run_campaign_endpoint(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Enqueues the autonomous run onto RQ — same two-layer idempotency as
    /discover/run: a per-minute job_id with unique=True here (layer 1), a
    Redis claim inside the task (layer 2).
    """
    campaign = campaigns_service.resolve_campaign_ownership(db, current_user, campaign_id)
    if not _workers_online():  # found live: a run sat in Redis for hours, reported as started
        raise HTTPException(503, NO_WORKER)
    # rq 2.x only accepts [A-Za-z0-9_-] in job ids (a ":" 500s the enqueue).
    run_id = f"campaign-{campaign.id}-{int(time.time() // 60)}"
    try:
        job = get_queue().enqueue(
            run_campaign_task, job_id=run_id, unique=True,
            kwargs={"campaign_id": campaign.id, "run_id": run_id},
        )
    except DuplicateJobError:
        job = RQJob.fetch(run_id, connection=get_redis_connection())
    return {"task_id": job.id, "status": job.get_status()}


@router.get("/campaigns/{campaign_id}/stats", response_model=schemas.CampaignStatsOut)
def get_campaign_stats(
    campaign_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    campaign = campaigns_service.resolve_campaign_ownership(db, current_user, campaign_id)
    today = campaigns_service.applied_today(db, campaign)
    return schemas.CampaignStatsOut(
        applied_today=today,
        daily_cap=campaign.daily_cap,
        # Same function the worker enforces with — never recomputed here.
        remaining_today=campaigns_service.remaining_quota(db, campaign),
        total_applied=db.query(models.Application).filter(
            models.Application.campaign_id == campaign.id
        ).count(),
        last_run_at=campaign.last_run_at,
    )
