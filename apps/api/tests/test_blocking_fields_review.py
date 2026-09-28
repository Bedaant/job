"""Every field that stopped a run reaches the Review queue, actionable (latest+55).

Two holes found live (latest+54): a required legal consent (Greenhouse "Agreement
to Arbitrate") was listed as an ordinary question whose save always 400s, and a
combobox question whose bank answer fits none of its options silently moved to
"prepared" — so the card said "needs input" with nothing the user could do.
"""
from answer_bank import find_answer, serve_answer
from tests.test_pending_questions import _needs_human
from tests.test_submission_loop import _auth, _bind, _client, _seed

import models

ARBITRATE = {"question": "Agreement to Arbitrate*",
             "options": ["I understand and agree to the terms of the Agreement to Arbitrate set forth above."]}


def _setup(email):
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, email)
    profile_id, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])
    return client, SessionLocal, headers, profile_id, app_id


def _card(client, headers, profile_id, app_id):
    queue = client.get(f"/applications/review-queue?profile_id={profile_id}", headers=headers).json()
    return next(q for q in queue if q["id"] == app_id)


def test_consent_is_its_own_item_not_an_answerable_question():
    client, _, headers, profile_id, app_id = _setup("blk-consent@example.com")
    resp = _needs_human(client, headers, app_id, [ARBITRATE, "Portfolio URL"])
    assert resp.status_code == 200

    card = _card(client, headers, profile_id, app_id)
    assert card["pending_questions"] == ["Portfolio URL"]
    assert card["consent_questions"] == ["Agreement to Arbitrate*"]
    assert card["needs_input"]["consent_required"] is True

    detail = client.get(f"/applications/{app_id}", headers=headers).json()
    assert detail["consent_questions"] == ["Agreement to Arbitrate*"]
    assert detail["pending_questions"] == ["Portfolio URL"]


def test_consent_named_only_by_its_option_is_still_consent():
    client, _, headers, profile_id, app_id = _setup("blk-consent-opt@example.com")
    _needs_human(client, headers, app_id, [{"question": "Terms*", "options": ["I agree"]}])

    card = _card(client, headers, profile_id, app_id)
    assert card["consent_questions"] == ["Terms*"]
    assert card["pending_questions"] == []


def test_consent_is_never_saved_nor_served():
    client, SessionLocal, headers, profile_id, app_id = _setup("blk-consent-rail@example.com")
    _needs_human(client, headers, app_id, [ARBITRATE])

    resp = client.put(f"/profiles/{profile_id}/answers", headers=headers,
                      json={"question_text": "Agreement to Arbitrate*", "answer_text": ARBITRATE["options"][0]})
    assert resp.status_code == 400
    db = SessionLocal()
    assert db.query(models.AnswerBank).count() == 0

    # Even a row that got in some other way is never served, nor shown as prepared.
    db.add(models.AnswerBank(profile_id=profile_id, question_text="Agreement to Arbitrate*",
                             question_normalized="agreement to arbitrate", answer_text="I agree"))
    db.commit()
    assert find_answer(db, profile_id, "Agreement to Arbitrate*") is None
    assert serve_answer(db, profile_id, "Agreement to Arbitrate*") is None
    db.close()

    card = _card(client, headers, profile_id, app_id)
    assert card["consent_questions"] == ["Agreement to Arbitrate*"]
    assert card["prepared_answers"] == []


def test_combobox_whose_bank_answer_fits_no_option_stays_pending_with_its_options():
    client, _, headers, profile_id, app_id = _setup("blk-combo@example.com")
    client.put(f"/profiles/{profile_id}/answers", headers=headers,
               json={"question_text": "Are you open to relocation?", "answer_text": "San Francisco"})
    _needs_human(client, headers, app_id,
                 [{"question": "Are you open to relocation?", "options": ["Yes", "No"]}])

    card = _card(client, headers, profile_id, app_id)
    assert card["pending_questions"] == ["Are you open to relocation?"]
    assert card["question_options"] == {"Are you open to relocation?": ["Yes", "No"]}
    assert card["prepared_answers"] == []

    # Picking an option saves through the normal bank path and clears it.
    client.put(f"/profiles/{profile_id}/answers", headers=headers,
               json={"question_text": "Are you open to relocation?", "answer_text": "Yes"})
    card = _card(client, headers, profile_id, app_id)
    assert card["pending_questions"] == []
    assert card["prepared_answers"] == [{"question": "Are you open to relocation?", "answer": "Yes"}]


def test_demographic_is_dropped_by_its_options_too():
    client, _, headers, profile_id, app_id = _setup("blk-demo-opt@example.com")
    _needs_human(client, headers, app_id,
                 [{"question": "Which describes you?", "options": ["Man", "Woman", "Decline to self-identify"]}])

    card = _card(client, headers, profile_id, app_id)
    assert card["pending_questions"] == [] and card["consent_questions"] == []
