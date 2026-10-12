"""Sub-project #2 — batch prep pipeline: tailor + truth-check + persist an
Application into `ready_for_review`, ahead of the user, so the review queue
(sub-project #3) has something real to show. The async/batched wrapper
(workers/jobs.py::prepare_applications_task) just calls this once per
application — this function is the actual unit of work.
"""
import logging
import time

from sqlalchemy.orm import Session

import models
from events.outbox import write_event
from providers import guard
from tailoring.engine import tailor_application


def _record_tailoring(seconds: float, cost_usd: float) -> None:
    import observability  # lazy: it imports the ops router and connectors

    try:
        observability.record_tailoring(observability._redis(), seconds, cost_usd)
    except Exception as exc:  # a metric must never fail a tailoring
        logging.getLogger(__name__).warning("tailoring metric not recorded (%s)", type(exc).__name__)


def prepare_application_for_review(db: Session, application: models.Application) -> models.Application:
    profile = application.profile
    job = application.job

    facts = db.query(models.ResumeFact).filter(models.ResumeFact.profile_id == profile.id).all()
    facts_list = [
        {
            "id": f.id, "category": f.category, "achievement": f.achievement,
            "proof": f.proof, "metric": f.metric, "tags": f.tags,
        }
        for f in facts
    ]
    job_dict = {"title": job.title, "company": job.company, "description": job.description or ""}

    started, spent = time.monotonic(), guard.spent_here("llm")
    result = tailor_application(job_dict, facts_list)
    _record_tailoring(time.monotonic() - started, guard.spent_here("llm") - spent)

    application.tailored_resume_json = {
        "summary": result["summary"], "bullets": result["bullets"], "keyword_gap": result.get("keyword_gap"),
    }
    application.tailored_cover_letter = result["cover_letter"]
    application.flagged_unsupported_claims = result["flagged_unsupported_claims"]
    application.advisory_claims = result.get("advisory_claims") or []
    application.status = models.ApplicationStatus.ready_for_review

    write_event(
        db, profile.user_id, "application.ready_for_review",
        {"application_id": application.id, "job_title": job.title},
    )
    db.commit()
    db.refresh(application)
    return application
