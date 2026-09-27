"""ADR-015: the answer bank fills itself at the `needs_human` boundary.

Before this, a run that stopped on "why do you want to work here?" reported only a
free-text reason. The question itself was lost, so the user had nowhere to answer
it and the bank never grew. Now the driver reports the unanswered questions, the
review queue shows the ones the bank still can't answer, and saving an answer is
what clears them — no second piece of state to keep in sync.
"""
from tests.test_submission_loop import _auth, _bind, _client, _seed

import models


def _needs_human(client, headers, app_id, questions):
    client.post(f"/applications/{app_id}/claim-submission", headers=headers)
    return client.post(
        f"/applications/{app_id}/submission-result", headers=headers,
        json={"outcome": "needs_human", "reason": "unanswered", "unanswered_questions": questions},
    )


def _pending(client, headers, profile_id):
    queue = client.get(f"/applications/review-queue?profile_id={profile_id}", headers=headers).json()
    return {q["id"]: q["pending_questions"] for q in queue}


def test_needs_human_questions_surface_in_the_review_queue():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "pq-surface@example.com")
    profile_id, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])

    resp = _needs_human(client, headers, app_id,
                        ["Why do you want to work here?", "How did you hear about us?"])
    assert resp.status_code == 200

    assert _pending(client, headers, profile_id)[app_id] == [
        "Why do you want to work here?", "How did you hear about us?",
    ]


def test_demographic_questions_are_never_stored_as_pending():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "pq-demo@example.com")
    profile_id, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])

    _needs_human(client, headers, app_id, ["What is your gender?", "Why do you want to work here?"])

    assert _pending(client, headers, profile_id)[app_id] == ["Why do you want to work here?"]


def test_saving_an_answer_clears_the_pending_question():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "pq-clear@example.com")
    profile_id, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])
    _needs_human(client, headers, app_id,
                 ["Why do you want to work here?", "How did you hear about us?"])

    client.put(f"/profiles/{profile_id}/answers", headers=headers,
               json={"question_text": "Why do you want to work here?", "answer_text": "The mission."})

    assert _pending(client, headers, profile_id)[app_id] == ["How did you hear about us?"]


def test_questions_are_deduplicated_and_blank_ones_dropped():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "pq-dedupe@example.com")
    profile_id, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])

    _needs_human(client, headers, app_id, ["  ", "Portfolio URL", "Portfolio URL"])

    assert _pending(client, headers, profile_id)[app_id] == ["Portfolio URL"]


def test_a_later_submitted_outcome_clears_pending_questions():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "pq-submitted@example.com")
    profile_id, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])
    _needs_human(client, headers, app_id, ["Portfolio URL"])

    db = SessionLocal()
    row = db.query(models.Application).filter(models.Application.id == app_id).first()
    row.status = models.ApplicationStatus.approved  # the user re-approved it
    db.commit()
    db.close()
    client.post(f"/applications/{app_id}/claim-submission", headers=headers)
    client.post(f"/applications/{app_id}/submission-result", headers=headers,
                json={"outcome": "submitted"})

    db = SessionLocal()
    row = db.query(models.Application).filter(models.Application.id == app_id).first()
    assert not row.pending_questions
    db.close()


def test_question_list_is_bounded():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "pq-bound@example.com")
    _, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])

    resp = _needs_human(client, headers, app_id, [f"Question {i}" for i in range(51)])
    assert resp.status_code == 422
