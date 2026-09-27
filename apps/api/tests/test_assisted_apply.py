"""Assisted apply: Maggie prepares, the user sends.

Four contracts:
- GET /applications/{id}/resume.docx — the TAILORED resume, grounded bullets only,
  with the applicant's name/contact header, through the same ATS linter and
  parse-back check as the base resume.
- PATCH /applications/{id} accepts only real statuses; `applied` stamps
  applied_at and records a manual `application.submitted` ("You sent it").
- GET /applications/ready-to-send — prepared applications the user can send now.
"""
import io

import docx

import models
from documents.ats_safety import lint_docx
from tests.test_submission_loop import _auth, _bind, _client, _seed


def _setup(email, statuses=(models.ApplicationStatus.ready_for_review,)):
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, email)
    profile_id, ids = _seed(client, headers, list(statuses))
    return client, SessionLocal, headers, profile_id, ids


def _fact(SessionLocal, profile_id, achievement, category="experience"):
    db = SessionLocal()
    fact = models.ResumeFact(profile_id=profile_id, category=category, achievement=achievement)
    db.add(fact)
    db.commit()
    fid = fact.id
    db.close()
    return fid


def _update(SessionLocal, model, row_id, **fields):
    db = SessionLocal()
    row = db.get(model, row_id)
    for k, v in fields.items():
        setattr(row, k, v)
    db.commit()
    db.close()


def _text(docx_bytes):
    return "\n".join(p.text for p in docx.Document(io.BytesIO(docx_bytes)).paragraphs)


# ---------- tailored resume ----------

def test_tailored_resume_has_grounded_bullets_and_contact_header():
    client, SessionLocal, headers, profile_id, (app_id,) = _setup("tailored-docx@example.com")
    fid = _fact(SessionLocal, profile_id, "Led a team of 5 engineers")
    _update(SessionLocal, models.Profile, profile_id, full_name="Asha Rao", phone="+91 98765 43210",
            city="Pune", website_url="https://asha.dev")
    _update(SessionLocal, models.Application, app_id, tailored_resume_json={"summary": "S", "bullets": [
        {"text": "Led a five-person backend team shipping payments APIs", "source_fact_ids": [fid]},
        {"text": "Invented claim nobody can back", "source_fact_ids": ["not-a-real-fact"]},
        {"text": "Uncited line", "source_fact_ids": []},
    ]})

    resp = client.get(f"/applications/{app_id}/resume.docx", headers=headers)

    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert lint_docx(resp.content) == []
    text = _text(resp.content)
    assert "Led a five-person backend team shipping payments APIs" in text
    assert "Invented claim" not in text
    assert "Uncited line" not in text
    assert "Asha Rao" in text
    for part in ("tailored-docx@example.com", "+91 98765 43210", "Pune", "https://asha.dev"):
        assert part in text


def test_tailored_resume_409_when_nothing_is_grounded():
    client, SessionLocal, headers, profile_id, (app_id,) = _setup("tailored-409@example.com")
    _update(SessionLocal, models.Application, app_id, tailored_resume_json={"bullets": [
        {"text": "Made up", "source_fact_ids": ["ghost"]},
    ]})
    assert client.get(f"/applications/{app_id}/resume.docx", headers=headers).status_code == 409


def test_tailored_resume_409_when_never_tailored():
    client, _, headers, _, (app_id,) = _setup("tailored-none@example.com")
    assert client.get(f"/applications/{app_id}/resume.docx", headers=headers).status_code == 409


def test_tailored_resume_is_owner_scoped():
    client, SessionLocal, headers, profile_id, (app_id,) = _setup("tailored-owner@example.com")
    fid = _fact(SessionLocal, profile_id, "Led a team")
    _update(SessionLocal, models.Application, app_id,
            tailored_resume_json={"bullets": [{"text": "Led a team", "source_fact_ids": [fid]}]})
    other = _auth(client, "tailored-intruder@example.com")
    assert client.get(f"/applications/{app_id}/resume.docx", headers=other).status_code == 404


def test_base_resume_gains_the_contact_header():
    client, SessionLocal, headers, profile_id, _ = _setup("base-header@example.com")
    _fact(SessionLocal, profile_id, "Led a team of 5 engineers")
    _update(SessionLocal, models.Profile, profile_id, given_name="Asha", family_name="Rao")
    resp = client.get(f"/profiles/{profile_id}/resume.docx", headers=headers)
    assert resp.status_code == 200
    assert lint_docx(resp.content) == []
    text = _text(resp.content)
    assert "Asha Rao" in text
    assert "base-header@example.com" in text


# ---------- mark as applied ----------

def test_patch_rejects_an_unknown_status():
    client, _, headers, _, (app_id,) = _setup("patch-bogus@example.com")
    resp = client.patch(f"/applications/{app_id}", headers=headers, json={"status": "yolo"})
    assert resp.status_code == 422


def test_marking_applied_stamps_applied_at_and_says_you_sent_it():
    client, SessionLocal, headers, _, (app_id,) = _setup("patch-applied@example.com")
    resp = client.patch(f"/applications/{app_id}", headers=headers, json={"status": "applied"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "applied"
    assert resp.json()["applied_at"] is not None

    activity = client.get("/activity", headers=headers).json()
    sent = [a for a in activity if a["type"] == "application.submitted"]
    assert len(sent) == 1
    assert sent[0]["title"] == "You sent it"
    assert sent[0]["application_id"] == app_id
    assert client.get("/today", headers=headers).json()["sent_today"] == 1


def test_undo_of_applied_clears_applied_at():
    client, _, headers, _, (app_id,) = _setup("patch-undo@example.com")
    client.patch(f"/applications/{app_id}", headers=headers, json={"status": "applied"})
    resp = client.patch(f"/applications/{app_id}", headers=headers, json={"status": "ready_for_review"})
    assert resp.status_code == 200
    assert resp.json()["applied_at"] is None


# ---------- ready to send ----------

def test_ready_to_send_lists_prepared_unblocked_applications_with_answers():
    S = models.ApplicationStatus
    client, SessionLocal, headers, profile_id, ids = _setup(
        "ready@example.com", [S.ready_for_review, S.approved, S.ready_for_review, S.ready_for_review, S.applied,
                              S.ready_for_review])
    ready, approved, untailored, blocked, applied, flagged = ids
    fid = _fact(SessionLocal, profile_id, "Led a team")
    tailored = {"summary": "S", "bullets": [{"text": "Led a team", "source_fact_ids": [fid]}],
                "keyword_gap": {"coverage_before": 0.5, "coverage_after": 0.75, "missing": ["Go"]}}
    for app_id in (ready, approved, blocked, applied, flagged):
        _update(SessionLocal, models.Application, app_id, tailored_resume_json=tailored,
                tailored_cover_letter="Dear Acme")
    _update(SessionLocal, models.Application, ready, pending_questions=["Why do you want to work here?"])
    _update(SessionLocal, models.Application, blocked, pending_questions=["What is your notice period?"])
    _update(SessionLocal, models.Application, flagged, flagged_unsupported_claims=["10 years of Rust"])
    client.put(f"/profiles/{profile_id}/answers", headers=headers,
               json={"question_text": "Why do you want to work here?", "answer_text": "Your payments work."})

    resp = client.get(f"/applications/ready-to-send?profile_id={profile_id}", headers=headers)

    assert resp.status_code == 200
    rows = {r["id"]: r for r in resp.json()}
    assert set(rows) == {ready, approved}
    assert rows[ready]["prepared_answers"] == [
        {"question": "Why do you want to work here?", "answer": "Your payments work."}
    ]
    assert rows[ready]["keyword_gap"]["coverage_after"] == 0.75
    assert rows[ready]["tailored_cover_letter"] == "Dear Acme"


def test_ready_to_send_is_owner_scoped():
    client, _, headers, profile_id, _ = _setup("ready-owner@example.com")
    other = _auth(client, "ready-intruder@example.com")
    assert client.get(f"/applications/ready-to-send?profile_id={profile_id}", headers=other).status_code == 404


def test_today_counts_ready_to_send():
    client, SessionLocal, headers, profile_id, (app_id,) = _setup("today-ready@example.com")
    fid = _fact(SessionLocal, profile_id, "Led a team")
    _update(SessionLocal, models.Application, app_id,
            tailored_resume_json={"bullets": [{"text": "Led a team", "source_fact_ids": [fid]}]})
    today = client.get("/today", headers=headers).json()
    assert today["ready_to_send"] == 1
    # One list each: a prepared application is "ready to send", not also "needs you".
    assert today["needs_you"] == 0
