"""Referral message rules (NEXT-WORK-PLAN §5.3).

One specific real reason, give before asking, one small ask, at most two follow-ups,
and REFUSE when there is no specific reason. The refusal and the follow-up cap are code,
checked before any model call, so a prompt can't talk its way past them.
"""
from unittest.mock import patch

from outreach.draft import (
    FOLLOW_UP_CAP_REACHED,
    MAX_FOLLOW_UPS,
    NO_SPECIFIC_REASON,
    OutreachDraft,
    draft_follow_up,
    draft_outreach,
)
from tailoring.engine import ClaimAudit
from tests.test_outreach_draft import FACTS, JOB, MUTUAL, NO_SIGNAL, ONE_SIDED, _contact

URL = "https://e.com/u/tok"


def _drafted(body="Body text."):
    return OutreachDraft.model_validate(
        {"subject": "About the PM role", "body": body, "source_fact_ids": ["f2"]},
        context={"known_fact_ids": {"f1", "f2"}},
    )


def _patched():
    return (patch("outreach.draft._call_claude_structured", return_value=_drafted()),
            patch("tailoring.engine._call_claude_structured", return_value=ClaimAudit()))


def test_no_specific_reason_refuses_without_calling_the_model():
    p1, p2 = _patched()
    with p1 as m1, p2:
        result = draft_outreach(FACTS, JOB, _contact(NO_SIGNAL), URL)
    assert result == {"refused": NO_SPECIFIC_REASON}
    m1.assert_not_called()


def test_an_empty_signal_also_refuses():
    p1, p2 = _patched()
    with p1 as m1, p2:
        assert draft_outreach(FACTS, JOB, _contact({}), URL)["refused"] == NO_SPECIFIC_REASON
    m1.assert_not_called()


def test_a_real_reason_drafts_and_the_prompt_carries_the_rules():
    p1, p2 = _patched()
    with p1 as m1, p2:
        result = draft_outreach(FACTS, JOB, _contact(ONE_SIDED), URL)
    assert "refused" not in result and result["body"]
    system = m1.call_args.args[0]
    assert "give before you ask" in system.lower()
    assert "exactly one small ask" in system.lower()


def test_two_questions_is_an_advisory_finding():
    with patch("outreach.draft._call_claude_structured",
               return_value=_drafted("Could you refer me? Could we also talk?")), \
            patch("tailoring.engine._call_claude_structured", return_value=ClaimAudit()):
        result = draft_outreach(FACTS, JOB, _contact(MUTUAL), URL)
    assert any("one ask" in f for f in result["advisory_claims"])
    assert result["flagged_unsupported_claims"] == []


def test_first_and_second_follow_ups_are_allowed():
    for already_sent in range(MAX_FOLLOW_UPS):
        p1, p2 = _patched()
        with p1 as m1, p2:
            result = draft_follow_up(FACTS, JOB, _contact(MUTUAL), already_sent, URL)
        assert "refused" not in result
        assert f"follow-up {already_sent + 1} of {MAX_FOLLOW_UPS}" in m1.call_args.args[0]


def test_the_third_follow_up_is_blocked_in_code():
    assert MAX_FOLLOW_UPS == 2
    p1, p2 = _patched()
    with p1 as m1, p2:
        result = draft_follow_up(FACTS, JOB, _contact(MUTUAL), 2, URL)
    assert result == {"refused": FOLLOW_UP_CAP_REACHED}
    m1.assert_not_called()


def test_a_follow_up_with_no_reason_is_refused_too():
    p1, p2 = _patched()
    with p1 as m1, p2:
        assert draft_follow_up(FACTS, JOB, _contact(NO_SIGNAL), 0, URL)["refused"] == NO_SPECIFIC_REASON
    m1.assert_not_called()


def test_orchestrator_records_the_refusal_as_a_skip(db_session):
    import models
    from tests.test_outreach_orchestrate import _Source, _application, _cand, _profile
    from outreach.orchestrate import draft_outreach_for_application

    p = _profile(db_session, per_app=1)
    a = _application(db_session, p)
    with patch("outreach.orchestrate.draft_outreach", return_value={"refused": NO_SPECIFIC_REASON}):
        draft_outreach_for_application(db_session, a.id, sources=[_Source("t", [_cand("One", "one@acme.com")])])
    row = db_session.query(models.Outreach).one()
    assert row.status == models.OutreachStatus.skipped
    assert row.skip_reason == NO_SPECIFIC_REASON
    assert row.body is None
