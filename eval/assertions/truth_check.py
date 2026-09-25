"""python assertion (promptfoo docs: assert type `python`, file://path:function)
enforcing ADR-006/PRD.md's core invariant: pass-2 must not let unsupported
claims through silently. A test case whose tailoring produced any
`flagged_unsupported_claims` fails here, regardless of how good the prose
reads — this is the hard gate, `llm-rubric` (per-row __expected in
golden.csv) is the soft quality signal.
"""
import json


def no_unsupported_claims(output: str, context) -> dict:
    if not output:
        return {"pass": False, "score": 0.0, "reason": "empty output (see provider error)"}

    try:
        result = json.loads(output)
    except json.JSONDecodeError as exc:
        return {"pass": False, "score": 0.0, "reason": f"output was not valid JSON: {exc}"}

    flagged = result.get("flagged_unsupported_claims", [])
    if flagged:
        return {"pass": False, "score": 0.0, "reason": f"unsupported claims: {flagged}"}
    return {"pass": True, "score": 1.0, "reason": "no unsupported claims"}
