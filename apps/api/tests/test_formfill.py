from unittest.mock import patch

import pytest

from formfill.map_fields import (
    CONFIDENCE_THRESHOLD, DEMOGRAPHIC_LABEL_KEYWORDS, ESSAY_LABEL_KEYWORDS,
    FORBIDDEN_LABEL_KEYWORDS, is_demographic_label, is_essay_label, is_forbidden_label,
    map_form_fields,
)


def test_forbidden_label_keywords_cover_demographic_and_essay_questions():
    assert any("gender" in kw for kw in FORBIDDEN_LABEL_KEYWORDS)
    assert any("why do you want to work" in kw for kw in FORBIDDEN_LABEL_KEYWORDS)


def test_is_forbidden_label_matches_case_insensitively():
    assert is_forbidden_label("What is your Gender?") is True
    assert is_forbidden_label("Email address") is False
    assert is_forbidden_label(None) is False


@patch("formfill.map_fields.call_llm")
def test_map_form_fields_forces_forbidden_fields_flagged_regardless_of_model_output(mock_call_llm):
    """Defense-in-depth: even if the model confidently maps a demographic field,
    the client-side (here: server-side pre/post filter) override always wins."""
    mock_call_llm.return_value = (
        '[{"field_id": "f1", "maps_to": "literal:Male", "confidence": 0.99, "value": "Male"}]'
    )
    fields = [{"field_id": "f1", "label_text": "Gender", "input_type": "text"}]

    result = map_form_fields(fields, {"name": "Jane Doe", "email": "jane@example.com"})

    assert result[0]["field_id"] == "f1"
    assert result[0]["maps_to"] == "unknown"
    assert result[0]["confidence"] == 0.0
    mock_call_llm.assert_not_called()  # never even asked the model about a forbidden field


@patch("formfill.map_fields.call_llm")
def test_map_form_fields_passes_through_high_confidence_mapping(mock_call_llm):
    """A field's label alone must not be enough to resolve it deterministically
    — "Years of experience" isn't in the deterministic rule table, so this
    still genuinely exercises the LLM passthrough path."""
    mock_call_llm.return_value = (
        '[{"field_id": "f1", "maps_to": "resume_fact:experience", "confidence": 0.95, "value": "5 years"}]'
    )
    fields = [{"field_id": "f1", "label_text": "Years of experience", "input_type": "text"}]

    result = map_form_fields(fields, {"email": "jane@example.com"})

    assert result[0]["maps_to"] == "resume_fact:experience"
    assert result[0]["confidence"] == 0.95
    assert result[0]["value"] == "5 years"


@patch("formfill.map_fields.call_llm")
def test_map_form_fields_handles_malformed_json_with_one_retry_then_gives_up_safely(mock_call_llm):
    mock_call_llm.side_effect = ["not json", "still not json"]
    # A label no deterministic rule recognises, so the LLM retry path is what runs.
    fields = [{"field_id": "f1", "label_text": "Preferred name on badge", "input_type": "text"}]

    result = map_form_fields(fields, {"name": "Jane Doe"})

    assert mock_call_llm.call_count == 2  # ADR-011: bounded retry, not an open loop
    assert result[0]["maps_to"] == "unknown"
    assert result[0]["confidence"] == 0.0


@patch("formfill.map_fields.call_llm")
def test_map_form_fields_recovers_on_second_attempt(mock_call_llm):
    mock_call_llm.side_effect = [
        "not json",
        '[{"field_id": "f1", "maps_to": "profile.name", "confidence": 0.9, "value": "Jane Doe"}]',
    ]
    # A label no deterministic rule recognises, so the LLM retry path is what runs.
    fields = [{"field_id": "f1", "label_text": "Preferred name on badge", "input_type": "text"}]

    result = map_form_fields(fields, {"name": "Jane Doe"})

    assert mock_call_llm.call_count == 2
    assert result[0]["maps_to"] == "profile.name"


def test_confidence_threshold_is_075():
    assert CONFIDENCE_THRESHOLD == 0.75


# ---------- deterministic-first orchestration ----------

@patch("formfill.map_fields.call_llm")
def test_map_form_fields_resolves_deterministic_fields_without_any_llm_call(mock_call_llm):
    """An email field with a real autocomplete attribute must never reach the
    model at all — zero LLM calls for something structurally unambiguous."""
    fields = [{"field_id": "f1", "label_text": "Email", "input_type": "email", "autocomplete": "email"}]
    profile_summary = {"email": "a@b.com"}

    result = map_form_fields(fields, profile_summary)

    assert result == [{"field_id": "f1", "maps_to": "profile.email", "confidence": 1.0, "value": "a@b.com"}]
    mock_call_llm.assert_not_called()


@patch("formfill.map_fields.call_llm")
def test_map_form_fields_sends_only_unresolved_fields_to_the_llm(mock_call_llm):
    """A mix of one deterministic field and one ambiguous field must only put
    the ambiguous one in the model prompt."""
    mock_call_llm.return_value = (
        '[{"field_id": "f2", "maps_to": "resume_fact:experience", "confidence": 0.8, "value": "5 years"}]'
    )
    fields = [
        {"field_id": "f1", "label_text": "Email", "input_type": "email", "autocomplete": "email"},
        {"field_id": "f2", "label_text": "Years of experience", "input_type": "text"},
    ]
    profile_summary = {"email": "a@b.com"}

    result = map_form_fields(fields, profile_summary)

    sent_fields_json = mock_call_llm.call_args[0][1]
    assert "f1" not in sent_fields_json
    assert "f2" in sent_fields_json
    by_id = {r["field_id"]: r for r in result}
    assert by_id["f1"]["maps_to"] == "profile.email"
    assert by_id["f2"]["maps_to"] == "resume_fact:experience"


@patch("formfill.map_fields.call_llm")
def test_map_form_fields_skips_llm_entirely_when_everything_resolves_deterministically(mock_call_llm):
    fields = [{"field_id": "f1", "label_text": "Email", "input_type": "email", "autocomplete": "email"}]
    map_form_fields(fields, {"email": "a@b.com"})
    mock_call_llm.assert_not_called()


@patch("formfill.map_fields.call_llm")
def test_map_form_fields_forbidden_field_never_reaches_deterministic_or_llm(mock_call_llm):
    """A forbidden field must not even be checked by the deterministic
    matcher — order matters, forbidden-check runs first."""
    fields = [{"field_id": "f1", "label_text": "What is your gender?", "input_type": "text", "autocomplete": "sex"}]
    result = map_form_fields(fields, {"email": "a@b.com"})
    assert result == [{"field_id": "f1", "maps_to": "unknown", "confidence": 0.0, "value": None}]
    mock_call_llm.assert_not_called()


# ---------- the demographic / essay split (ADR-015 answer bank) ----------
#
# These two used to be one list, which is why "why do you want to work here"
# could never be filled even from an answer the user wrote themselves. Splitting
# them is what makes the answer bank possible; keeping the demographic half
# unconditional is what keeps that safe.

def test_the_two_keyword_lists_are_disjoint_and_together_are_the_old_list():
    assert set(DEMOGRAPHIC_LABEL_KEYWORDS) & set(ESSAY_LABEL_KEYWORDS) == set()
    assert set(FORBIDDEN_LABEL_KEYWORDS) == set(DEMOGRAPHIC_LABEL_KEYWORDS) | set(
        ESSAY_LABEL_KEYWORDS
    )


def test_demographic_and_essay_classifications_do_not_overlap():
    assert is_demographic_label("What is your gender?") is True
    assert is_essay_label("What is your gender?") is False
    assert is_essay_label("Why do you want to work here?") is True
    assert is_demographic_label("Why do you want to work here?") is False


@pytest.mark.parametrize(
    "label",
    [
        "What is your race?",
        "Please select your ethnicity",
        "Gender",
        "Protected veteran status",
        "Disability status",
        "Sexual orientation",
    ],
)
@patch("formfill.map_fields.call_llm")
def test_a_demographic_field_is_never_filled_from_the_answer_bank(mock_call_llm, label):
    """THE test for this feature's one unacceptable failure mode. The answer
    bank here is a lookup that answers EVERY question — the most hostile bank
    possible, standing in for a row that arrived by some route save_answer
    doesn't control. A demographic field must still come back empty."""
    answers_everything = lambda question: "SHOULD NEVER BE FILLED"  # noqa: E731

    result = map_form_fields(
        [{"field_id": "f1", "label_text": label, "input_type": "select"}],
        {"email": "a@b.com"},
        answer_lookup=answers_everything,
    )

    assert result == [{"field_id": "f1", "maps_to": "unknown", "confidence": 0.0, "value": None}]
    mock_call_llm.assert_not_called()


@patch("formfill.map_fields.call_llm")
def test_a_demographic_field_never_even_reaches_the_answer_lookup(mock_call_llm):
    """Not just "the value is discarded" — the bank is never consulted at all,
    so a demographic question cannot so much as bump a times_used counter."""
    asked = []

    def spy(question):
        asked.append(question)
        return None

    map_form_fields(
        [
            {"field_id": "f1", "label_text": "Gender", "input_type": "select"},
            {"field_id": "f2", "label_text": "Notice period", "input_type": "text"},
        ],
        {"email": "a@b.com"},
        answer_lookup=spy,
    )

    assert asked == ["Notice period"]


@patch("formfill.map_fields.call_llm")
def test_map_form_fields_fills_an_essay_field_from_the_answer_bank(mock_call_llm):
    """The point of the whole task: a field that was unconditionally flagged
    is now filled, from text the user wrote, with no model call."""
    result = map_form_fields(
        [{"field_id": "f1", "label_text": "Why do you want to work here?", "input_type": "textarea"}],
        {"email": "a@b.com"},
        answer_lookup=lambda q: "Because I have shipped this exact problem twice.",
    )

    assert result == [{
        "field_id": "f1",
        "maps_to": "answer_bank",
        "confidence": 1.0,
        "value": "Because I have shipped this exact problem twice.",
    }]
    mock_call_llm.assert_not_called()


@patch("formfill.map_fields.call_llm")
def test_an_essay_field_with_no_stored_answer_is_still_flagged_and_never_sent_to_the_llm(mock_call_llm):
    """The bank is the only thing allowed to answer an essay question. On a
    miss the field is flagged exactly as before — a model must never write
    one (ADR-006/ADR-009)."""
    result = map_form_fields(
        [{"field_id": "f1", "label_text": "Why are you interested in this role?", "input_type": "textarea"}],
        {"email": "a@b.com"},
        answer_lookup=lambda q: None,
    )

    assert result == [{"field_id": "f1", "maps_to": "unknown", "confidence": 0.0, "value": None}]
    mock_call_llm.assert_not_called()


@patch("formfill.map_fields.call_llm")
def test_the_bank_answers_an_ordinary_field_that_would_otherwise_go_to_the_llm(mock_call_llm):
    """"Notice period" isn't demographic, isn't an essay question, and isn't in
    the deterministic rule table — today it costs an LLM call and usually comes
    back `unknown`. A stored answer removes the call entirely."""
    result = map_form_fields(
        [{"field_id": "f1", "label_text": "Notice period", "input_type": "text"}],
        {"email": "a@b.com"},
        answer_lookup=lambda q: "30 days",
    )

    assert result[0]["maps_to"] == "answer_bank"
    assert result[0]["value"] == "30 days"
    mock_call_llm.assert_not_called()


@patch("formfill.map_fields.call_llm")
def test_profile_data_still_wins_over_the_bank_for_a_deterministic_field(mock_call_llm):
    """The bank must not shadow the profile: an email field resolves from the
    profile even if the bank would happily answer it."""
    result = map_form_fields(
        [{"field_id": "f1", "label_text": "Email", "input_type": "email", "autocomplete": "email"}],
        {"email": "a@b.com"},
        answer_lookup=lambda q: "stale@old.com",
    )

    assert result[0]["maps_to"] == "profile.email"
    assert result[0]["value"] == "a@b.com"
    mock_call_llm.assert_not_called()


@patch("formfill.map_fields.call_llm")
def test_without_an_answer_lookup_behaviour_is_exactly_what_it_was_before(mock_call_llm):
    """`answer_lookup=None` is the pre-bank path — every existing caller keeps
    its behaviour unchanged."""
    mock_call_llm.return_value = "not json"
    fields = [
        {"field_id": "f1", "label_text": "Gender", "input_type": "select"},
        {"field_id": "f2", "label_text": "Why do you want to work here?", "input_type": "textarea"},
        {"field_id": "f3", "label_text": "Notice period", "input_type": "text"},
    ]

    result = map_form_fields(fields, {"email": "a@b.com"})

    assert [r["maps_to"] for r in result] == ["unknown", "unknown", "unknown"]
    # only f3 was ever a candidate for the model
    assert "f3" in mock_call_llm.call_args[0][1]
    assert "f1" not in mock_call_llm.call_args[0][1]
    assert "f2" not in mock_call_llm.call_args[0][1]


# Live, Zoox (2026-09-29): the model answered "How did you hear about us?" with
# "LinkedIn" in one run and flagged it in another. Only the user knows the answer:
# it is an essay-rail question (bank or nothing), bound to the live options.
HEAR = [{"field_id": "f1", "label_text": "How did you hear about us?", "input_type": "checkbox",
         "options": ["LinkedIn", "Company website", "Other"], "name": "cards[x][field3]"}]


@patch("formfill.map_fields.call_llm",
       return_value='[{"field_id": "f1", "maps_to": "profile.linkedin", "confidence": 0.9, "value": "LinkedIn"}]')
def test_how_did_you_hear_is_never_answered_by_the_model(llm):
    result = map_form_fields(HEAR, {"full_name": "Jane"}, answer_lookup=lambda q: None)
    llm.assert_not_called()
    assert all(not m.get("value") for m in result)


@patch("formfill.map_fields.call_llm")
def test_how_did_you_hear_comes_from_the_bank_bound_to_options(llm):
    result = map_form_fields(HEAR, {"full_name": "Jane"}, answer_lookup=lambda q: "company website")
    assert result == [{"field_id": "f1", "maps_to": "answer_bank", "confidence": 1.0, "value": "Company website"}]
    llm.assert_not_called()
