"""Why Maggie stopped: the review card has to say it.

A `needs_human` report used to land in the review queue looking like any other
card — the reason lived only in `notes`. The user approved a captcha-blocked form
and it looped forever. `needs_input` is derived from the last stamped note line.
"""
import pytest

import models
from needs_input import last_attempt, needs_input
from tests.test_submission_loop import _auth, _bind, _client, _seed


@pytest.mark.parametrize("reason, kind", [
    ("reCAPTCHA challenge detected on page", "captcha"),
    ("Cloudflare challenge page", "captcha"),
    ("Please sign in to continue", "account"),
    ("You must create an account to apply", "account"),
    ("required file input could not be filled", "upload"),
    ("1 field(s) need your input and were not answered: file_upload", "upload"),
    ("something nobody predicted", "other"),
    # The extension's plain-words note (fieldDecision.needsHumanReason).
    ("Needs you: Portfolio (a file to upload)", "upload"),
    ("Needs you: Why Anthropic? (no saved answer)", "question"),
    ("Needs you: First Name (not sure what to enter)", "question"),
])
def test_kind_follows_the_reason(reason, kind):
    assert needs_input(f"[needs_human] {reason}", [])["kind"] == kind


def test_open_questions_make_it_a_question():
    got = needs_input("[needs_human] 1 field(s) need your input and were not answered: low_confidence",
                      ["Why us?"])
    assert got["kind"] == "question"
    assert got["demographic_left_blank"] is False


def test_still_a_question_once_every_question_is_answered():
    """Answering drops the question from pending; the card must still say retry helps."""
    got = needs_input("[needs_human] 1 field(s) need your input and were not answered: low_confidence", [])
    assert got["kind"] == "question"


def test_demographic_only_is_not_a_question():
    got = needs_input("[needs_human] 1 field(s) need your input and were not answered: demographic", [])
    assert got["kind"] == "other"
    assert got["demographic_left_blank"] is True


def test_captcha_beats_open_questions():
    assert needs_input("[needs_human] hcaptcha", ["Why us?"])["kind"] == "captcha"


def test_demographic_fields_are_flagged_as_left_blank():
    got = needs_input(
        "[needs_human] 2 field(s) need your input and were not answered: demographic, low_confidence",
        ["Why us?"],
    )
    assert got["kind"] == "question"
    assert got["demographic_left_blank"] is True


def test_only_the_last_stamp_counts():
    notes = "user note\n[needs_human] captcha\n[failed] timed out after 90000ms"
    assert needs_input(notes, []) is None
    assert last_attempt(notes) == {"outcome": "failed", "message": "timed out after 90000ms"}
    notes2 = "[failed] timed out\n[needs_human] please log in"
    assert needs_input(notes2, [])["kind"] == "account"
    assert needs_input(notes2, [])["message"] == "please log in"


def test_no_stamp_means_nothing():
    assert needs_input(None, []) is None
    assert needs_input("just a note the user wrote", ["q"]) is None
    assert last_attempt(None) is None


def test_review_queue_exposes_needs_input_and_last_attempt():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "needs-input@example.com")
    profile_id, (app_id, plain_id) = _seed(
        client, headers,
        [models.ApplicationStatus.approved, models.ApplicationStatus.ready_for_review],
    )
    client.post(f"/applications/{app_id}/claim-submission", headers=headers)
    client.post(f"/applications/{app_id}/submission-result", headers=headers,
                json={"outcome": "needs_human", "reason": "reCAPTCHA challenge detected"})

    queue = {q["id"]: q for q in client.get(
        f"/applications/review-queue?profile_id={profile_id}", headers=headers).json()}

    assert queue[app_id]["needs_input"] == {
        "kind": "captcha", "message": "reCAPTCHA challenge detected", "demographic_left_blank": False,
        "consent_required": False,
    }
    assert queue[app_id]["last_attempt"] == {"outcome": "needs_human", "message": "reCAPTCHA challenge detected"}
    assert queue[plain_id]["needs_input"] is None
    assert queue[plain_id]["last_attempt"] is None


@pytest.mark.parametrize("reason,kind,demo", [
    # Field labels sit inside the note; only the bracketed reason may decide the kind.
    ("Needs you: Upload your portfolio link (not sure what to enter)", "question", False),
    ("Needs you: Sign in email, Log in name (no saved answer)", "question", False),
    ("Needs you: Demographic survey opt-in (not sure what to enter)", "question", False),
    ("Needs you: Why us? (no saved answer); Portfolio (a file to upload)", "upload", False),
    ("Needs you: Phone (optional) (not sure what to enter); Gender "
     "(required demographic self-identification, only you can answer)", "question", True),
])
def test_labels_in_the_note_never_decide_the_kind(reason, kind, demo):
    got = needs_input(f"[needs_human] {reason}", [])
    assert (got["kind"], got["demographic_left_blank"]) == (kind, demo)
