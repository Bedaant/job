from unittest.mock import patch

from formfill.map_fields import (
    CONFIDENCE_THRESHOLD, FORBIDDEN_LABEL_KEYWORDS, is_forbidden_label, map_form_fields,
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
    fields = [{"field_id": "f1", "label_text": "Full name", "input_type": "text"}]

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
    fields = [{"field_id": "f1", "label_text": "Full name", "input_type": "text"}]

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
