"""Truth-check regression set (tests/fixtures/truthcheck_eval/cases.json), no network.

`flag`/`pass` cases pin the HARD gate (deterministic_unsupported via split_gate_findings).
`llm_only` cases are known deterministic blind spots; the model checker is graded on them by
the opt-in tests/fixtures/truthcheck_eval/run_llm_eval.py (paid; never run by pytest).
"""
import json
from pathlib import Path

import pytest

from tailoring.engine import deterministic_unsupported, split_gate_findings

CASES = json.loads((Path(__file__).parent / "fixtures" / "truthcheck_eval" / "cases.json").read_text("utf-8"))
GATED = [c for c in CASES if c["expect"] in ("flag", "pass")]


def test_the_set_covers_every_trap_kind():
    ids = {c["id"] for c in CASES}
    assert 10 <= len(CASES) <= 20
    assert {"invented_skill", "invented_metric", "inflated_title", "invented_employer",
            "reworded_true_claim"} <= ids
    assert {c["expect"] for c in CASES} == {"flag", "pass", "llm_only"}


@pytest.mark.parametrize("case", GATED, ids=[c["id"] for c in GATED])
def test_hard_gate(case):
    hard, _ = split_gate_findings([], deterministic_unsupported(case["facts"], case["draft"]))
    assert bool(hard) == (case["expect"] == "flag"), hard
