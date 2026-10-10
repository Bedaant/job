"""Opt-in, PAID: grade the model checker (truth_check pass 2) on cases.json.

    cd apps/api && RUN_LLM_EVAL=1 .venv/Scripts/python tests/fixtures/truthcheck_eval/run_llm_eval.py

Never run by pytest (conftest blocks network). Exit code 1 if any trap case gets no finding
from either layer. True cases are reported, not failed: model findings are advisory (GAPS 6.7).
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tailoring.engine import truth_check  # noqa: E402


def main() -> int:
    if os.getenv("RUN_LLM_EVAL") != "1":
        print("Set RUN_LLM_EVAL=1 to run (makes paid LLM calls).")
        return 2
    cases = json.loads((Path(__file__).parent / "cases.json").read_text("utf-8"))
    missed = 0
    for case in cases:
        model, det = truth_check(case["facts"], "", case["draft"], "")
        caught = bool(model or det)
        trap = case["expect"] in ("flag", "llm_only")
        verdict = ("ok" if caught else "MISSED") if trap else ("ok" if not caught else "false positive")
        missed += trap and not caught
        print(f"{case['id']:<32} {case['expect']:<9} model={len(model)} det={len(det)} {verdict}")
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main())
