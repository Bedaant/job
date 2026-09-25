from unittest.mock import MagicMock, patch


@patch("pii.redact._anonymizer")
@patch("pii.redact._analyzer")
def test_redact_pii_replaces_detected_entities(mock_analyzer, mock_anonymizer):
    mock_analyzer.analyze.return_value = ["fake-result"]
    mock_anonymizer.anonymize.return_value = MagicMock(text="Contact <PERSON> at <EMAIL_ADDRESS>")

    from pii.redact import redact_pii
    result = redact_pii("Contact John Smith at john@acme.com")

    assert result == "Contact <PERSON> at <EMAIL_ADDRESS>"
    mock_analyzer.analyze.assert_called_once_with(text="Contact John Smith at john@acme.com", language="en")


@patch("pii.redact._anonymizer")
@patch("pii.redact._analyzer")
def test_redact_pii_handles_empty_text(mock_analyzer, mock_anonymizer):
    from pii.redact import redact_pii
    assert redact_pii("") == ""
    mock_analyzer.analyze.assert_not_called()
