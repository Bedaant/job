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
    mock_call_llm.return_value = (
        '[{"field_id": "f1", "maps_to": "profile.email", "confidence": 0.95, "value": "jane@example.com"}]'
    )
    fields = [{"field_id": "f1", "label_text": "Email", "input_type": "email"}]

    result = map_form_fields(fields, {"email": "jane@example.com"})

    assert result[0]["maps_to"] == "profile.email"
    assert result[0]["confidence"] == 0.95
    assert result[0]["value"] == "jane@example.com"


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
