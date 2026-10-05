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
    from tailoring.engine import ClaimAudit

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
        ClaimAudit(),
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


# ---------- keyword-gap feed (latest+22) ----------

GAP_FACTS = [
    {"id": "k1", "category": "experience", "achievement": "Deployed 12 services on K8s",
     "proof": None, "metric": None, "tags": []},
    {"id": "k2", "category": "skill", "achievement": "Python", "proof": None, "metric": None, "tags": []},
]
GAP_JD = "Requirements: Kubernetes, Python, Terraform and Snowflake experience."


def _run_with_captured_prompt(facts, jd):
    from tailoring.engine import ClaimAudit

    bullet = Bullet.model_validate(
        {"text": "Deployed 12 services on Kubernetes", "source_fact_ids": ["k1"]},
        context={"known_fact_ids": {"k1", "k2"}},
    )
    mock_instructor = MagicMock()
    mock_instructor.messages.create.side_effect = [
        TailoredDraft(summary="S.", bullets=[bullet], cover_letter="C."),
        ClaimAudit(),
    ]
    with patch("tailoring.engine._get_instructor_client", return_value=mock_instructor), \
            patch("tailoring.engine._settings") as mock_settings:
        mock_settings.llm_provider = "anthropic"
        result = tailor_application({"title": "Platform Engineer", "company": "Acme", "description": jd}, facts)
    prompt = mock_instructor.messages.create.call_args_list[0].kwargs["messages"][0]["content"]
    return result, prompt


def _terms_section(prompt: str) -> str:
    from tailoring.engine import JD_TERMS_HEADER

    assert JD_TERMS_HEADER in prompt
    return prompt.split(JD_TERMS_HEADER, 1)[1].split("\n\n", 1)[0]


def test_supported_jd_terms_reach_the_prompt_with_their_backing_fact():
    _, prompt = _run_with_captured_prompt(GAP_FACTS, GAP_JD)
    section = _terms_section(prompt)
    # The "K8s" fact is steered to the JD's own word, tied to the fact backing it.
    assert "Kubernetes" in section and "k1" in section
    assert "Python" in section and "k2" in section


def test_missing_keyword_never_reaches_the_prompt_outside_the_raw_jd():
    """The rail: Terraform/Snowflake are in the JD but in no fact. They must not
    appear in the "use these terms" section, nor anywhere in the prompt except
    the untouched JD text itself. Fails if any code path injects `missing`."""
    result, prompt = _run_with_captured_prompt(GAP_FACTS, GAP_JD)
    section = _terms_section(prompt)
    outside_jd = prompt.replace(GAP_JD, "")
    for kw in ("Terraform", "Snowflake"):
        assert kw not in section
        assert kw not in outside_jd
    # Surfaced to the user as a gap, never written into the resume.
    assert {"Terraform", "Snowflake"} <= set(result["keyword_gap"]["missing"])


def test_keyword_gap_summary_reports_coverage_before_and_after():
    result, _ = _run_with_captured_prompt(GAP_FACTS, GAP_JD)
    gap = result["keyword_gap"]
    assert 0 < gap["coverage_before"] < 1
    assert 0 <= gap["coverage_after"] <= 1


# ---------- nvidia as the real provider (owner choice, 2026-09-27) ----------

def test_nvidia_provider_uses_the_validated_path_on_the_nvidia_model():
    """"nvidia" is a production provider, not the smoke test: it must go through
    the same instructor-validated path as Claude (every bullet cites a real fact
    id, bounded retry), never the unvalidated raw-JSON smoke branch."""
    from tailoring.engine import ClaimAudit

    bullet = Bullet.model_validate(
        {"text": "Led a team of 5 engineers", "source_fact_ids": ["f1"]},
        context={"known_fact_ids": {"f1", "f2"}},
    )
    nvidia_instructor = MagicMock()
    nvidia_instructor.chat.completions.create.side_effect = [
        TailoredDraft(summary="S.", bullets=[bullet], cover_letter="C."),
        ClaimAudit(),
    ]
    with patch("tailoring.engine._get_nvidia_instructor_client", return_value=nvidia_instructor), \
            patch("tailoring.engine._get_instructor_client") as anthropic_instructor, \
            patch("tailoring.engine.call_llm") as raw_call, \
            patch("tailoring.engine._settings") as mock_settings:
        mock_settings.llm_provider = "nvidia"
        mock_settings.nvidia_model = "nvidia/nemotron-3-super-120b-a12b"
        mock_settings.nvidia_extra_body.return_value = {"chat_template_kwargs": {"enable_thinking": False}}
        result = tailor_application({"title": "Backend Engineer", "company": "Acme"}, FACTS)

    anthropic_instructor.assert_not_called()
    raw_call.assert_not_called()
    first = nvidia_instructor.chat.completions.create.call_args_list[0].kwargs
    assert first["model"] == "nvidia/nemotron-3-super-120b-a12b"
    assert first["context"] == {"known_fact_ids": {"f1", "f2"}}
    assert first["messages"][0]["role"] == "system"  # OpenAI shape: no `system=` kwarg
    # Found live: at 1500 the NIM model's draft was cut off (IncompleteOutputException).
    assert first["max_tokens"] >= 4096
    # Found live: the model "thinks" for thousands of tokens by default and the
    # JSON got cut off; thinking off answered the same in 0.7s vs 4.4s.
    assert first["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert result["bullets"] == [{"text": "Led a team of 5 engineers", "source_fact_ids": ["f1"]}]


# ---------- truth-check on NVIDIA: measured, then fixed (latest+44) ----------

from tailoring.engine import (  # noqa: E402
    NO_PADDING_RULE, STRICT_CHECK_SYSTEM, ClaimAudit, ClaimCheck, deterministic_unsupported, truth_check,
)

DET_FACTS = [
    {"id": "d1", "category": "experience", "achievement": "Deployed 12 services on K8s", "proof": None,
     "metric": None, "tags": []},
    {"id": "d2", "category": "experience", "achievement": "Led a team of five engineers", "proof": None,
     "metric": "cut deploy time from 40min to 4min", "tags": ["kafka"]},
]


def test_deterministic_check_flags_tools_and_numbers_no_fact_contains():
    flags = deterministic_unsupported(DET_FACTS, [
        "Built pipelines with Terraform",
        "Cut p95 latency by 30%",
        "Led a team of 9 engineers",
    ])
    assert flags == [
        "Built pipelines with Terraform [not in facts: Terraform]",
        "Cut p95 latency by 30% [not in facts: 30]",
        "Led a team of 9 engineers [not in facts: 9]",
    ]


def test_deterministic_check_accepts_synonyms_number_words_tags_and_metrics():
    assert deterministic_unsupported(DET_FACTS, [
        "Deployed 12 services on Kubernetes",    # K8s alias
        "Managed a team of 5 engineers",         # "five"
        "Ran a Kafka pipeline",                  # tag
        "Cut deploy time from 40 minutes to 4",  # metric field
    ]) == []


def test_fact_ids_are_not_evidence_for_numbers():
    # The id "d1" must not make a "1" in the draft look supported.
    assert deterministic_unsupported(DET_FACTS, ["Ranked 1 in the org"]) == ["Ranked 1 in the org [not in facts: 1]"]


def test_claim_audit_flags_padding_phrases_uncited_claims_and_unknown_ids():
    audit = ClaimAudit(claims=[
        ClaimCheck(claim="Deployed 12 services on Kubernetes", fact_ids=["d1"]),
        ClaimCheck(claim="Led five engineers, ensuring on-time delivery", fact_ids=["d2"],
                   unsupported_phrases=["ensuring on-time delivery"]),
        ClaimCheck(claim="Won an award", fact_ids=[]),
        ClaimCheck(claim="Invented id", fact_ids=["zz"]),
    ])
    assert audit.unsupported({"d1", "d2"}) == [
        "Led five engineers, ensuring on-time delivery [not in facts: ensuring on-time delivery]",
        "Won an award",
        "Invented id",
    ]


def test_truth_check_uses_strict_prompt_blind_to_the_jd_and_adds_deterministic_flags():
    with patch("tailoring.engine._call_claude_structured", return_value=ClaimAudit()) as call:
        model_flags, det_flags = truth_check(
            DET_FACTS, "Platform engineer.", ["Deployed 12 services on K8s with Terraform"], "Hi."
        )
    system, user, model = call.call_args.args[:3]
    assert system == STRICT_CHECK_SYSTEM and model is ClaimAudit
    assert "JOB DESCRIPTION" not in user  # ADR-006
    # truth_check now returns the two halves SEPARATELY instead of concatenating
    # them (GAPS 6.7): only the deterministic half is a hard gate. The flag this
    # test has always asserted is a deterministic one — an unlisted tool.
    assert det_flags == ["Deployed 12 services on K8s with Terraform [not in facts: Terraform]"]
    assert model_flags == []


def test_tailor_prompt_forbids_padding():
    bullet = Bullet.model_validate({"text": "Python", "source_fact_ids": ["f2"]}, context={"known_fact_ids": {"f1", "f2"}})
    mock_instructor = MagicMock()
    mock_instructor.messages.create.side_effect = [
        TailoredDraft(summary="S.", bullets=[bullet], cover_letter="C."), ClaimAudit(),
    ]
    with patch("tailoring.engine._get_instructor_client", return_value=mock_instructor), \
            patch("tailoring.engine._settings") as mock_settings:
        mock_settings.llm_provider = "anthropic"
        tailor_application({"title": "Backend Engineer", "company": "Acme"}, FACTS)
    assert NO_PADDING_RULE in mock_instructor.messages.create.call_args_list[0].kwargs["system"]
    assert "why it mattered" in NO_PADDING_RULE


def test_deterministic_check_ignores_one_in_ordinary_prose():
    from tailoring.engine import deterministic_unsupported

    facts = [{"id": "f1", "achievement": "Built the billing service in Python"}]
    assert deterministic_unsupported(facts, ["This is one of the roles I want most."]) == []
