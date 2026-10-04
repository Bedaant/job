"""GAPS 5.8 — `redact_pii` must not depend on NER guessing a name correctly.

Found live on 2026-10-04: spaCy's `en_core_web_lg` classifies "Bedaant
Srivastav" as **ORG**, not PERSON, so that name survived redaction while
"John Smith", "Priya Sharma", "Rahul Gupta" and "Barack Obama" were all
detected. That is a model limitation on uncommon names, and it matters here
because the product targets Indian users — an un-redacted name is the main
thing redaction exists to remove.

The fix does not try to improve the model. The one name that matters is already
known: a profile stores `full_name`, so it is passed in and matched exactly via
a presidio deny-list recognizer (`PatternRecognizer(supported_entity="PERSON",
deny_list=[...])`, handed to `analyze(ad_hoc_recognizers=[...])` — signature
checked against the installed 2.2.358, not guessed).

These tests mock the engines: they assert the deny-list recognizer is built and
passed, not that presidio's NER works, which is upstream's job. The live
behaviour was verified by hand (deny-list hit PERSON at score 1.0).
"""
from unittest.mock import MagicMock, patch


def _anonymized(text):
    m = MagicMock()
    m.text = text
    return m


@patch("pii.redact._anonymizer")
@patch("pii.redact._analyzer")
def test_a_known_name_is_passed_as_a_deny_list_recognizer(mock_analyzer, mock_anonymizer):
    mock_analyzer.analyze.return_value = []
    mock_anonymizer.anonymize.return_value = _anonymized("<PERSON> applied")

    from pii.redact import redact_pii

    redact_pii("Bedaant Srivastav applied", known_names=["Bedaant Srivastav"])

    kwargs = mock_analyzer.analyze.call_args.kwargs
    recognizers = kwargs["ad_hoc_recognizers"]
    assert len(recognizers) == 1
    assert recognizers[0].supported_entities == ["PERSON"]
    assert recognizers[0].deny_list == ["Bedaant Srivastav"]


@patch("pii.redact._anonymizer")
@patch("pii.redact._analyzer")
def test_no_known_names_means_no_ad_hoc_recognizers(mock_analyzer, mock_anonymizer):
    """The default path must stay exactly what it was."""
    mock_analyzer.analyze.return_value = []
    mock_anonymizer.anonymize.return_value = _anonymized("x")

    from pii.redact import redact_pii

    redact_pii("some text")

    assert mock_analyzer.analyze.call_args.kwargs.get("ad_hoc_recognizers") is None


@patch("pii.redact._anonymizer")
@patch("pii.redact._analyzer")
def test_blank_and_duplicate_names_are_dropped(mock_analyzer, mock_anonymizer):
    """A profile with an empty `full_name` must not build a recognizer whose
    deny_list contains "" — that would match everywhere."""
    mock_analyzer.analyze.return_value = []
    mock_anonymizer.anonymize.return_value = _anonymized("x")

    from pii.redact import redact_pii

    redact_pii("text", known_names=["", "  ", "Ada Lovelace", "Ada Lovelace", None])

    recognizers = mock_analyzer.analyze.call_args.kwargs["ad_hoc_recognizers"]
    assert recognizers[0].deny_list == ["Ada Lovelace"]


@patch("pii.redact._anonymizer")
@patch("pii.redact._analyzer")
def test_only_blank_names_behaves_like_no_names(mock_analyzer, mock_anonymizer):
    mock_analyzer.analyze.return_value = []
    mock_anonymizer.anonymize.return_value = _anonymized("x")

    from pii.redact import redact_pii

    redact_pii("text", known_names=["", None])

    assert mock_analyzer.analyze.call_args.kwargs.get("ad_hoc_recognizers") is None


@patch("pii.redact._anonymizer")
@patch("pii.redact._analyzer")
def test_empty_text_still_short_circuits(mock_analyzer, mock_anonymizer):
    from pii.redact import redact_pii

    assert redact_pii("", known_names=["Ada Lovelace"]) == ""
    mock_analyzer.analyze.assert_not_called()
