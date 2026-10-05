"""GAPS 6.7, owner decision 2026-10-05: the DETERMINISTIC half of pass 2 is the
hard gate; the model checker's findings become advisory.

The measurement that forced this (`docs/harness-reports/adr014-first-eval-run.md`
plus its correction): on the 30-row golden set, **bullets were 107/107 grounded**
and pass 2 still flagged **29 of 30 rows** — every flag from the model checker,
none from `deterministic_unsupported`. `main.py` excludes any application with
`flagged_unsupported_claims` from the ready queue, so ~97% would never be sent.

The model checker was not malfunctioning: `STRICT_CHECK_SYSTEM` explicitly tells
it to flag "scope or scale", "titles, durations and praise adjectives". It
flagged "Senior Backend Engineer with expertise in…" and "Proven ability to…".
The owner's ruling: **that is framing, not fabrication.**

So the split is:
  hard gate  -> `deterministic_unsupported`: a tool/technology name or a number
                in the draft that no fact contains. Blocks sending. 0 false
                positives across the measured rows.
  advisory   -> the model checker's claim audit. Surfaced for a human, never
                blocking.

**The cost is real and must not be lost:** `deterministic_unsupported`'s own
docstring says an invented domain or outcome in plain words ("financial
transactions") is left to the model checker. Making that advisory means such a
claim can now reach an employer unless a human reads the advisory list. That is
the accepted trade, not an oversight.
"""
from unittest.mock import patch

import pytest

from tailoring.engine import split_gate_findings


def test_deterministic_findings_are_the_hard_gate():
    det = ["Built on Kafka [not in facts: Kafka]"]
    model = ["Proven ability to scale [not in facts: Proven ability]"]
    hard, advisory = split_gate_findings(model_findings=model, deterministic_findings=det)
    assert hard == det
    assert advisory == model


def test_model_findings_never_reach_the_hard_gate():
    """This is the whole point: 29 of 30 golden rows were blocked by these."""
    hard, advisory = split_gate_findings(
        model_findings=["Senior Backend Engineer [not in facts: Senior Backend Engineer]"],
        deterministic_findings=[],
    )
    assert hard == []
    assert len(advisory) == 1


def test_a_real_fabrication_still_blocks():
    """An unlisted tool or number is exactly what the deterministic half sees,
    and it must still stop the application."""
    hard, _ = split_gate_findings(
        model_findings=[],
        deterministic_findings=["Shipped 50M events/day [not in facts: 50]"],
    )
    assert hard, "an unlisted number must still block"


def test_both_empty_is_a_clean_draft():
    assert split_gate_findings(model_findings=[], deterministic_findings=[]) == ([], [])


def test_duplicates_across_the_halves_are_not_double_reported():
    """Both halves format findings identically, so the same string can appear in
    each — the hard gate keeps it, advisory drops the duplicate."""
    same = "Built on Kafka [not in facts: Kafka]"
    hard, advisory = split_gate_findings(model_findings=[same], deterministic_findings=[same])
    assert hard == [same]
    assert advisory == []


def test_tailor_application_returns_both_lists():
    """The engine's contract: `flagged_unsupported_claims` is now the hard gate
    only, and `advisory_claims` carries the model checker's findings."""
    import tailoring.engine as eng

    facts = [{"id": "f1", "category": "experience", "achievement": "Led a rewrite",
              "metric": None, "proof": None, "tags": []}]
    # model_construct: Bullet's field_validator needs the known_fact_ids
    # validation context that only _call_claude_structured supplies, and this
    # test is about the gate split, not that validator (which
    # tests/test_grounding.py covers).
    draft = eng.TailoredDraft.model_construct(
        summary="Proven ability to lead rewrites.",
        bullets=[eng.Bullet.model_construct(text="Led a rewrite", source_fact_ids=["f1"])],
        cover_letter="I led a rewrite.",
    )
    with patch.object(eng, "_call_claude_structured", return_value=draft), \
         patch.object(eng, "truth_check",
                      # truth_check returns (model_findings, deterministic_findings)
                      return_value=(["Proven ability [not in facts: Proven ability]"],
                                    ["Kafka [not in facts: Kafka]"])), \
         patch.object(eng, "compute_keyword_gap",
                      # Real shape, from matching/keyword_gap.py's own empty return.
                      return_value={"coverage": 0.0, "matched": [], "missing": [],
                                    "weak": [], "suggestions": []}):
        out = eng.tailor_application({"title": "Engineer", "company": "Acme",
                                      "description": "d"}, facts)

    assert out["flagged_unsupported_claims"] == ["Kafka [not in facts: Kafka]"]
    assert out["advisory_claims"] == ["Proven ability [not in facts: Proven ability]"]


def test_truth_check_returns_the_two_halves_separately():
    """`truth_check` used to concatenate them, which is what made the gate
    un-splittable at the call site."""
    import tailoring.engine as eng

    class _Audit:
        def unsupported(self, known_ids):
            return ["model finding [not in facts: x]"]

    with patch.object(eng, "_call_claude_structured", return_value=_Audit()), \
         patch.object(eng, "deterministic_unsupported", return_value=["det finding [not in facts: y]"]):
        model, det = eng.truth_check([{"id": "f1"}], "s", ["b"], "c")

    assert model == ["model finding [not in facts: x]"]
    assert det == ["det finding [not in facts: y]"]
