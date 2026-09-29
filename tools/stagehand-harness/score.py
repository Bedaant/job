"""Score Stagehand plans (out/*.json) with phase0.score against the SAME DOM snapshots and extension
baseline as the browser-use Phase 0 run, and write docs/harness-reports/stagehand-greenhouse.md.

  ..\\.venv-browser-use\\Scripts\\python score.py
"""

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BU = HERE.parent / "browser-use-harness"
sys.path.insert(0, str(BU))
import phase0  # noqa: E402

DOC = HERE.parent.parent / "docs" / "harness-reports" / "stagehand-greenhouse.md"


def main() -> int:
    rows = []
    for bu in phase0._rows("greenhouse"):
        sh_file = HERE / "out" / f"greenhouse-{bu['company']}-{bu['job_id']}.json"
        snap = phase0.union_snapshot(json.loads(phase0.plan_file(bu).read_text(encoding="utf-8")))
        sh = json.loads(sh_file.read_text(encoding="utf-8")) if sh_file.exists() else {"planner": {}, "guard": {}}
        pl = sh["planner"]
        rows.append({"bu": bu, "pl": pl, "guard": sh["guard"], "sh": phase0.score(pl.get("plan"), snap),
                     "b": bu.get("baseline") or {}})

    tot = lambda k: sum(r["sh"][k] for r in rows)  # noqa: E731
    bu_tot = lambda k: sum(r["bu"]["score"][k] for r in rows)  # noqa: E731
    med = lambda xs: statistics.median(xs) if xs else None  # noqa: E731
    b = [r["b"] for r in rows if r["b"].get("required_total") is not None]
    req = sum(x["required_total"] for x in b)
    req_empty = sum(len(x["required_empty"]) for x in b)
    flagged = sum(x.get("required_flagged", 0) for x in b)
    pct = phase0._pct
    summary = [
        "| | Stagehand extract() | browser-use planner | extension |", "|---|---|---|---|",
        f"| Field recall | **{pct(tot('matched'), tot('dom_fields'))}** | {pct(bu_tot('matched'), bu_tot('dom_fields'))} | — |",
        f"| Precision | {pct(tot('matched'), tot('plan_fields'))} | {pct(bu_tot('matched'), bu_tot('plan_fields'))} | — |",
        f"| Required flag correct | {pct(tot('required_ok'), tot('matched'))} | {pct(bu_tot('required_ok'), bu_tot('matched'))} | — |",
        f"| Widget correct | {pct(tot('widget_ok'), tot('matched'))} | {pct(bu_tot('widget_ok'), bu_tot('matched'))} | — |",
        f"| Dropdown options captured | {pct(tot('options_ok'), tot('options_total'))} | {pct(bu_tot('options_ok'), bu_tot('options_total'))} | — |",
        f"| Consent/demographic marked never | {pct(tot('sensitive_never'), tot('sensitive_total'))} | {pct(bu_tot('sensitive_never'), bu_tot('sensitive_total'))} | never filled |",
        f"| Median time per job | **{med([r['pl'].get('agent_s') for r in rows if r['pl'].get('agent_s')])} s** | "
        f"{med([r['bu']['planner']['agent_s'] for r in rows])} s | seconds |",
        f"| Median LLM calls | {med([r['pl'].get('llm_calls') for r in rows])} | {med([r['bu']['planner']['llm_calls'] for r in rows])} | 1 |",
        f"| Median tokens | {med([(r['pl'].get('prompt_tokens') or 0) + (r['pl'].get('completion_tokens') or 0) for r in rows])} | "
        f"{med([(r['bu']['planner'].get('prompt_tokens') or 0) + (r['bu']['planner'].get('completion_tokens') or 0) for r in rows])} | — |",
        f"| Required fields filled or flagged | — | — | {pct(req - req_empty + flagged, req)} |",
        f"| Submits | {sum(r['guard'].get('submit_attempts_blocked') or 0 for r in rows)} | 0 | 0 |",
    ]
    table = ["| posting | DOM fields | SH fields | SH recall | SH precision | required | widget | options | never | SH s | "
             "LLM calls | tokens | BU recall | guard (canary/blocked/submits) | SH error |", "|" + "---|" * 15]
    details = []
    for r in rows:
        s, pl, bu, g = r["sh"], r["pl"], r["bu"], r["guard"]
        table.append(
            f"| [{bu['company']} {bu['job_id']}]({bu['url']}) | {s['dom_fields']} | {s['plan_fields']} | {s['recall']:.0%} | "
            f"{s['precision']:.0%} | {s['required_acc']:.0%} | {s['widget_acc']:.0%} | {s['options_ok']}/{s['options_total']} | "
            f"{s['sensitive_never']}/{s['sensitive_total']} | {pl.get('agent_s')} | {pl.get('llm_calls')} | "
            f"{(pl.get('prompt_tokens') or 0) + (pl.get('completion_tokens') or 0)} | {bu['score']['recall']:.0%} | "
            f"{g.get('canary_blocked')}/{g.get('blocked_non_get_requests')}/{g.get('submit_attempts_blocked')} | "
            f"{pl.get('error') or (pl.get('errors') or [''])[0] or '-'} |")
        details += [f"### {bu['company']} {bu['job_id']}: {bu['title']}", "",
                    f"- Missed: {s['missed']}", f"- Unmatched plan fields: {s['extra']}",
                    f"- Required wrong: {s['required_wrong']}", f"- Widget wrong: {s['widget_wrong']}",
                    f"- Sensitive not 'never': {s['sensitive_violations']}", ""]
    prev = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
    head = prev.split("## Totals")[0] if "## Totals" in prev else \
        "# Stagehand vs browser-use vs extension: Greenhouse\n\n<!-- VERDICT (hand-written, kept on rerun) -->\n\n"
    DOC.write_text(head + "\n".join(
        ["## Totals (5 postings)", "",
         *summary, "", "## Per posting", "",
         "Generated by `tools/stagehand-harness/score.py`. Stagehand 3.7.3, one `extract()` call, no clicks or typing, "
         f"model `{rows[0]['pl'].get('model')}` on NIM. Scored with `phase0.score` against the DOM snapshots "
         "of the browser-use Phase 0 run (same day); extension numbers are that run's baseline. Guard on "
         "(CDP: non-GET requests failed, canary POST verified; DOM: submits cancelled).", "",
         *table, "", "## Per posting details", "", *details]) + "\n", encoding="utf-8")
    print("\n".join(summary + [""] + table))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
