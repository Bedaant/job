"""No test file existed for tailoring/engine.py before this — a real gap,
closed here alongside wiring `instructor` in (DEPENDENCIES.md: "Fixes
CODE-REVIEW.md B5 — tailoring/engine.py currently does an unhandled json.loads
on model output"). Covers the new SPEC.md §3.3 contract: every bullet must
carry source_fact_ids referencing a real fact id, enforced by Pydantic
validation against the actual facts given, not just requested in the prompt.
"""
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from tailoring.engine import Bullet, TailoredDraft, tailor_application


FACTS = [
    {"id": "f1", "category": "experience", "achievement": "Led a team of 5 engineers",
     "proof": None, "metric": None, "tags": []},
    {"id": "f2", "category": "skill", "achievement": "Python", "proof": None, "metric": None, "tags": []},
]


def test_bullet_rejects_source_fact_ids_not_in_the_given_kb():
    with pytest.raises(ValidationError):
        Bullet.model_validate(
            {"text": "Did something", "source_fact_ids": ["not-a-real-fact-id"]},
            context={"known_fact_ids": {"f1", "f2"}},
        )


def test_bullet_accepts_source_fact_ids_present_in_the_kb():
    bullet = Bullet.model_validate(
        {"text": "Led a team of 5 engineers", "source_fact_ids": ["f1"]},
        context={"known_fact_ids": {"f1", "f2"}},
    )
    assert bullet.source_fact_ids == ["f1"]


def test_bullet_rejects_empty_source_fact_ids():
    with pytest.raises(ValidationError):
        Bullet.model_validate(
            {"text": "Did something", "source_fact_ids": []},
            context={"known_fact_ids": {"f1", "f2"}},
        )


@patch("tailoring.engine._get_instructor_client")
def test_tailor_application_anthropic_path_returns_structured_bullets_with_fact_ids(mock_get_client):
    from tailoring.engine import TruthCheckResult

    bullet = Bullet.model_validate(
        {"text": "Led a team of 5 engineers", "source_fact_ids": ["f1"]},
        context={"known_fact_ids": {"f1", "f2"}},
    )
    mock_instructor = MagicMock()
    mock_instructor.messages.create.side_effect = [
        TailoredDraft(
            summary="A backend engineer.",
            bullets=[bullet],
            cover_letter="Dear hiring manager, ...",
            keywords_targeted=["python"],
        ),
        TruthCheckResult(unsupported_claims=[]),
    ]
    mock_get_client.return_value = mock_instructor

    with patch("tailoring.engine._settings") as mock_settings:
        mock_settings.llm_provider = "anthropic"
        result = tailor_application({"title": "Backend Engineer", "company": "Acme"}, FACTS)

    assert result["bullets"] == [{"text": "Led a team of 5 engineers", "source_fact_ids": ["f1"]}]
    assert result["flagged_unsupported_claims"] == []


@patch("tailoring.engine.call_llm")
def test_tailor_application_nvidia_smoke_path_never_fakes_source_fact_ids(mock_call_llm):
    """The free smoke model isn't validated against the real KB the same way
    — bullets come back with source_fact_ids=[] rather than inventing a link
    the model wasn't actually constrained to produce."""
    mock_call_llm.side_effect = [
        '{"summary": "A backend engineer.", "bullets": ["Led a team"], "cover_letter": "Dear..."}',
        '{"unsupported_claims": []}',
    ]

    with patch("tailoring.engine._settings") as mock_settings:
        mock_settings.llm_provider = "nvidia_smoke"
        result = tailor_application({"title": "Backend Engineer", "company": "Acme"}, FACTS)

    assert result["bullets"] == [{"text": "Led a team", "source_fact_ids": []}]
