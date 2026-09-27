"""Applications tracker + detail page, match actions (WORKLOG latest+46).

- GET /applications rows carry the job's title/company (the tracker can't name a card without it).
- GET /applications/{id}: owner-scoped detail — job, status, timestamps, tailored bullets
  next to the text of the facts they came from, cover letter, stored keyword_gap, the
  matched / reworded / missing keywords, why Maggie stopped, the attempt history.
- PATCH /matches/{id}: saved / dismissed / new; GET /matches hides dismissed ones and says
  which already have an application.
- POST /matches/{id}/prepare: get-or-create the Application and enqueue the existing
  batch-prep task (never a second tailoring path).
- `withdrawn`: a closed status the user sets after sending; applied_at is kept.
"""
from unittest.mock import patch

import models
from tests.test_submission_loop import _auth, _bind, _client, _seed

S = models.ApplicationStatus


def _setup(email, statuses=(S.applied,)):
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, email)
    profile_id, ids = _seed(client, headers, list(statuses))
    return client, SessionLocal, headers, profile_id, ids


def _add(SessionLocal, row):
    db = SessionLocal()
    db.add(row)
    db.commit()
    row_id = row.id
    db.close()
    return row_id


def _update(SessionLocal, model, row_id, **fields):
    db = SessionLocal()
    row = db.get(model, row_id)
    for k, v in fields.items():
        setattr(row, k, v)
    db.commit()
    db.close()


def _get(SessionLocal, model, row_id):
    db = SessionLocal()
    row = db.get(model, row_id)
    db.expunge(row)
    db.close()
    return row


# ---------- list ----------

def test_list_names_the_job_on_every_row():
    client, _, headers, profile_id, (app_id,) = _setup("list-job@example.com")
    rows = client.get(f"/applications?profile_id={profile_id}", headers=headers).json()
    assert len(rows) == 1
    assert rows[0]["id"] == app_id
    assert rows[0]["job"]["title"] == "Backend Engineer 0"
    assert rows[0]["job"]["company"] == "Acme"
    assert rows[0]["created_at"] is not None
    assert "updated_at" in rows[0]


# ---------- detail ----------

def test_detail_puts_each_bullet_next_to_the_fact_it_came_from():
    client, SessionLocal, headers, profile_id, (app_id,) = _setup("detail@example.com")
    fid = _add(SessionLocal, models.ResumeFact(
        profile_id=profile_id, category="experience", achievement="Built payment APIs in Python",
    ))
    _update(SessionLocal, models.Application, app_id,
            tailored_resume_json={
                "summary": "Backend engineer",
                "bullets": [
                    {"text": "Built Python payment APIs", "source_fact_ids": [fid]},
                    {"text": "Claim with a ghost source", "source_fact_ids": ["ghost"]},
                ],
                "keyword_gap": {"coverage_before": 0.4, "coverage_after": 0.6, "missing": [{"keyword": "terraform", "importance": "high"}]},
            },
            tailored_cover_letter="Dear Acme",
            notes="[needs_human] captcha on the form\n[failed] timed out",
            pending_questions=[])
    _update(SessionLocal, models.Job, _get(SessionLocal, models.Application, app_id).job_id,
            description="We need Python and Terraform experience.")

    resp = client.get(f"/applications/{app_id}", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "applied"
    assert body["job"]["company"] == "Acme"
    assert body["tailored_summary"] == "Backend engineer"
    assert body["tailored_cover_letter"] == "Dear Acme"
    first, second = body["tailored_bullets"]
    assert first["sources"] == [{"id": fid, "achievement": "Built payment APIs in Python"}]
    assert second["sources"] == [], "an id that isn't the user's fact has no source text to show"
    assert body["keyword_gap"]["coverage_before"] == 0.4
    kw = body["keywords"]
    assert "python" in [k.lower() for k in kw["matched"]]
    assert "terraform" in [k.lower() for k in kw["missing"]]
    assert "terraform" not in [k.lower() for k in kw["matched"] + kw["reworded"]]
    assert body["last_attempt"] == {"outcome": "failed", "message": "timed out"}
    assert body["history"] == [
        {"outcome": "needs_human", "message": "captcha on the form"},
        {"outcome": "failed", "message": "timed out"},
    ]
    for key in ("created_at", "updated_at", "applied_at", "needs_input", "pending_questions",
                "flagged_unsupported_claims", "match_score"):
        assert key in body


def test_detail_is_owner_scoped():
    client, _, _, _, (app_id,) = _setup("detail-owner@example.com")
    other = _auth(client, "detail-intruder@example.com")
    assert client.get(f"/applications/{app_id}", headers=other).status_code == 404


def test_detail_of_an_untailored_application_is_empty_not_an_error():
    client, _, headers, _, (app_id,) = _setup("detail-empty@example.com", (S.saved,))
    body = client.get(f"/applications/{app_id}", headers=headers).json()
    assert body["tailored_bullets"] == []
    assert body["keyword_gap"] is None
    assert body["history"] == []


# ---------- withdrawn ----------

def test_withdrawn_is_a_status_and_keeps_applied_at():
    client, _, headers, _, (app_id,) = _setup("withdraw@example.com", (S.saved,))
    client.patch(f"/applications/{app_id}", headers=headers, json={"status": "applied"})
    resp = client.patch(f"/applications/{app_id}", headers=headers, json={"status": "withdrawn"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "withdrawn"
    assert resp.json()["applied_at"] is not None


# ---------- match actions ----------

def _match(SessionLocal, profile_id, company="Globex", n=0):
    job_id = _add(SessionLocal, models.Job(
        source="remoteok", external_id=f"m{company}{n}", canonical_hash=f"m{company}{n}",
        title=f"Data Engineer {n}", company=company, apply_url=f"https://globex.example/{n}",
    ))
    match_id = _add(SessionLocal, models.Match(
        profile_id=profile_id, job_id=job_id, score=81, breakdown={"score": 81}, state="new",
    ))
    return match_id, job_id


def test_patch_match_state_saved_and_dismissed():
    client, SessionLocal, headers, profile_id, _ = _setup("match-state@example.com", ())
    match_id, _ = _match(SessionLocal, profile_id)
    for state in ("saved", "dismissed", "new"):
        resp = client.patch(f"/matches/{match_id}", headers=headers, json={"state": state})
        assert resp.status_code == 200
        assert resp.json()["state"] == state
        assert _get(SessionLocal, models.Match, match_id).state == state


def test_patch_match_rejects_unknown_state_and_other_users():
    client, SessionLocal, headers, profile_id, _ = _setup("match-guard@example.com", ())
    match_id, _ = _match(SessionLocal, profile_id)
    assert client.patch(f"/matches/{match_id}", headers=headers, json={"state": "yolo"}).status_code == 422
    other = _auth(client, "match-intruder@example.com")
    assert client.patch(f"/matches/{match_id}", headers=other, json={"state": "saved"}).status_code == 404


def test_list_matches_hides_dismissed_and_links_existing_applications():
    client, SessionLocal, headers, profile_id, _ = _setup("match-list@example.com", ())
    kept_id, kept_job = _match(SessionLocal, profile_id, n=1)
    gone_id, _ = _match(SessionLocal, profile_id, n=2)
    _update(SessionLocal, models.Match, gone_id, state="dismissed")
    app_id = _add(SessionLocal, models.Application(profile_id=profile_id, job_id=kept_job, status=S.ready_for_review))

    def fake_build(db, profile):
        return db.query(models.Match).filter(models.Match.profile_id == profile.id).all()

    with patch("main.build_matches", side_effect=fake_build):
        rows = client.get(f"/matches?profile_id={profile_id}", headers=headers).json()

    assert [r["id"] for r in rows] == [kept_id]
    assert rows[0]["application_id"] == app_id
    assert rows[0]["application_status"] == "ready_for_review"


def test_prepare_creates_the_application_and_enqueues_batch_prep():
    client, SessionLocal, headers, profile_id, _ = _setup("prepare@example.com", ())
    match_id, job_id = _match(SessionLocal, profile_id)

    with patch("main.get_queue") as queue:
        resp = client.post(f"/matches/{match_id}/prepare", headers=headers)
        again = client.post(f"/matches/{match_id}/prepare", headers=headers)

    assert resp.status_code == 200
    app_id = resp.json()["application_id"]
    assert again.json()["application_id"] == app_id, "a second press reuses the same application"
    row = _get(SessionLocal, models.Application, app_id)
    assert row.job_id == job_id and row.profile_id == profile_id and row.status == S.saved
    from workers.jobs import prepare_applications_task
    calls = queue.return_value.enqueue.call_args_list
    assert calls[0].args == (prepare_applications_task, [app_id])
    assert _get(SessionLocal, models.Match, match_id).state == "saved"


def test_prepare_does_not_retailor_an_already_prepared_application():
    client, SessionLocal, headers, profile_id, _ = _setup("prepare-done@example.com", ())
    match_id, job_id = _match(SessionLocal, profile_id)
    app_id = _add(SessionLocal, models.Application(profile_id=profile_id, job_id=job_id, status=S.ready_for_review))
    with patch("main.get_queue") as queue:
        resp = client.post(f"/matches/{match_id}/prepare", headers=headers)
    assert resp.json() == {"application_id": app_id, "status": "ready_for_review", "queued": False}
    queue.return_value.enqueue.assert_not_called()


def test_prepare_says_so_when_the_queue_is_down_and_keeps_the_application():
    client, SessionLocal, headers, profile_id, _ = _setup("prepare-down@example.com", ())
    match_id, _ = _match(SessionLocal, profile_id)
    with patch("main.get_queue") as queue:
        queue.return_value.enqueue.side_effect = ConnectionError("redis gone")
        resp = client.post(f"/matches/{match_id}/prepare", headers=headers)
    assert resp.status_code == 503
    db = SessionLocal()
    assert db.query(models.Application).filter(models.Application.profile_id == profile_id).count() == 1
    db.close()


def test_prepare_is_owner_scoped():
    client, SessionLocal, _, profile_id, _ = _setup("prepare-owner@example.com", ())
    match_id, _ = _match(SessionLocal, profile_id)
    other = _auth(client, "prepare-intruder@example.com")
    with patch("main.get_queue"):
        assert client.post(f"/matches/{match_id}/prepare", headers=other).status_code == 404
