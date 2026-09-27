"""ADR-015 §2 — campaign execution and the daily-cap rail.

The cap is the single reason this module exists as its own file rather than
living in main.py: `remaining_quota` is the ONE place that computes how many
applications a campaign may still create today, and both callers — the worker
(`run_campaign`) and `GET /campaigns/{id}/stats` — go through it. Two call
sites computing it separately is exactly the drift this avoids.

The cap is derived from `applications` rows (campaign_id + created_at today,
UTC), never from a counter column and never from a campaign_runs table. A
denormalized counter would drift from what actually went out; the rows are the
only number that can't.
"""
from datetime import datetime, timedelta

from fastapi import HTTPException, status as http_status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

import models
from batch_prep import prepare_application_for_review

# PATCH /campaigns/{id} is the only way status moves. Archived is terminal —
# DELETE lands there, and an archived campaign is history, not a draft.
ALLOWED_TRANSITIONS: dict[models.CampaignStatus, set[models.CampaignStatus]] = {
    models.CampaignStatus.draft: {models.CampaignStatus.active, models.CampaignStatus.archived},
    models.CampaignStatus.active: {models.CampaignStatus.paused, models.CampaignStatus.archived},
    models.CampaignStatus.paused: {models.CampaignStatus.active, models.CampaignStatus.archived},
    models.CampaignStatus.archived: set(),
}


def resolve_campaign_ownership(db: Session, current_user: models.User, campaign_id: str) -> models.Campaign:
    """Tenancy enforcement point for campaigns, mirroring core.deps::
    resolve_profile_ownership — a campaign is reachable only through a profile
    the caller owns. 404, never 403: a cross-tenant id must be indistinguishable
    from one that doesn't exist. Postgres RLS (migration 0010/0012) is the
    backstop underneath this, not a replacement for it.
    """
    campaign = (
        db.query(models.Campaign)
        .join(models.Profile, models.Campaign.profile_id == models.Profile.id)
        .filter(models.Campaign.id == campaign_id, models.Profile.user_id == current_user.id)
        .first()
    )
    if not campaign:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, "Campaign not found")
    return campaign


def utc_day_start() -> datetime:
    """Midnight of the current UTC day, naive (every timestamp column is naive UTC)."""
    return datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)


def applied_today(db: Session, campaign: models.Campaign) -> int:
    """Count of this campaign's applications created in the current UTC day.
    `Application.created_at` is naive UTC (models.py uses datetime.utcnow),
    so the day boundary is computed the same way — no tz conversion.
    """
    day_start = utc_day_start()
    return (
        db.query(models.Application)
        .filter(
            models.Application.campaign_id == campaign.id,
            models.Application.created_at >= day_start,
            models.Application.created_at < day_start + timedelta(days=1),
        )
        .count()
    )


def remaining_quota(db: Session, campaign: models.Campaign) -> int:
    """How many applications this campaign may still create today. THE cap
    function — never inline this computation anywhere else. Clamped at zero so
    a cap lowered below today's count reads as "done", not as a negative
    budget some caller might treat as truthy.
    """
    return max(0, campaign.daily_cap - applied_today(db, campaign))


def select_candidates(db: Session, campaign: models.Campaign, limit: int) -> list[models.Match]:
    """Matches inside the campaign's approved bounds, best first, excluding
    jobs this profile already has an application for.
    """
    already_applied = select(models.Application.job_id).where(
        models.Application.profile_id == campaign.profile_id
    )
    # Match.score is 0..100; campaign.min_match_score is a 0..1 fraction.
    threshold = float(campaign.min_match_score) * 100
    query = (
        db.query(models.Match)
        .join(models.Job, models.Match.job_id == models.Job.id)
        .filter(
            models.Match.profile_id == campaign.profile_id,
            models.Match.score >= threshold,
            models.Match.state != "dismissed",
            models.Match.job_id.notin_(already_applied),
        )
    )
    if campaign.remote_only:
        query = query.filter(models.Job.remote.is_(True))
    if campaign.sources:
        query = query.filter(models.Job.source.in_(campaign.sources))
    if campaign.roles:
        query = query.filter(or_(*[models.Job.title.ilike(f"%{r}%") for r in campaign.roles]))
    if campaign.locations:
        query = query.filter(or_(*[models.Job.location.ilike(f"%{l}%") for l in campaign.locations]))

    return query.order_by(models.Match.score.desc()).limit(limit).all()


def run_campaign(db: Session, campaign: models.Campaign) -> dict:
    """One campaign run: pick candidates inside the approved bounds, create at
    most `remaining_quota` applications, then prepare each one (tailor +
    truth-check) via the existing batch-prep unit of work.

    Stops at prepared/approved. Actual submission is NOT done here — that is a
    separate task; `auto_submit` only decides whether the optional human review
    step is skipped (approved) or kept (ready_for_review).
    """
    if campaign.status != models.CampaignStatus.active:
        return {"skipped": True, "reason": f"campaign is {campaign.status.value}, not active",
                "created": 0, "prepared": 0, "failed": []}

    remaining = remaining_quota(db, campaign)
    if remaining <= 0:
        return {"skipped": True, "reason": "daily cap reached",
                "created": 0, "prepared": 0, "failed": []}

    created = []
    for match in select_candidates(db, campaign, remaining):
        application = models.Application(
            profile_id=campaign.profile_id, job_id=match.job_id, campaign_id=campaign.id
        )
        db.add(application)
        created.append(application)

    campaign.last_run_at = datetime.utcnow()
    # Committed before any prep work: the applications are what the cap counts,
    # so they must be durable before the slow (LLM) part can crash or be retried.
    db.commit()

    prepared, failed = 0, []
    for application in created:
        try:
            prepare_application_for_review(db, application)
            if campaign.auto_submit:
                # ADR-015: campaign-level approval already happened, so there is
                # no per-item review step. Submission itself is out of scope here.
                application.status = models.ApplicationStatus.approved
                db.commit()
            prepared += 1
        except Exception:
            db.rollback()
            failed.append(application.id)

    return {"skipped": False, "campaign_id": campaign.id, "created": len(created),
            "prepared": prepared, "failed": failed}
