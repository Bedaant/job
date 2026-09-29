"""Score Stagehand plans (out/<ats>-*.json) with phase0.score and write docs/harness-reports/stagehand-<ats>.md.

Greenhouse: scored against the DOM snapshots of the browser-use Phase 0 run, with browser-use and extension
columns. Other ATSes: scored against the snapshot plan.mjs took itself (Stagehand only).

  ..\\.venv-browser-use\\Scripts\\python score.py [greenhouse|lever|ashby]
"""

import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BU = HERE.parent / "browser-use-harness"
sys.path.insert(0, str(BU))
import phase0  # noqa: E402

DOCS = HERE.parent.parent / "docs" / "harness-reports"


def rows_for(ats: str) -> list[dict]:
    rows = []
    if ats == "greenhouse":
        for bu in phase0._rows("greenhouse"):
            sh_file = HERE / "out" / f"greenhouse-{bu['company']}-{bu['job_id']}.json"
            snap = phase0.union_snapshot(json.loads(phase0.plan_file(bu).read_text(encoding="utf-8")))
            sh = json.loads(sh_file.read_text(encoding="utf-8")) if sh_file.exists() else {"planner": {}, "guard": {}}
            rows.append({"name": f"{bu['company']} {bu['job_id']}", "title": bu["title"], "url": bu["url"],
                         "sh": sh, "snap": snap, "bu": bu})
    else:
        for f in sorted((HERE / "out").glob(f"{ats}-*.json")):
            sh = json.loads(f.read_text(encoding="utf-8"))
            rows.append({"name": f.stem[len(ats) + 1:], "title": "", "url": sh["url"], "sh": sh,
                         "snap": sh.get("snapshot_before") or [], "bu": None})
    for r in rows:
        r["pl"], r["guard"] = r["sh"].get("planner") or {}, r["sh"].get("guard") or {}
        r["s"] = phase0.score(r["pl"].get("plan"), r["snap"])
        r["b"] = (r["bu"] or {}).get("baseline") or {}
    return rows


def main() -> int:
    ats = sys.argv[1] if len(sys.argv) > 1 else "greenhouse"
    rows = rows_for(ats)
    has_bu = ats == "greenhouse"
    tot = lambda k: sum(r["s"][k] for r in rows)  # noqa: E731
    bu_tot = lambda k: sum(r["bu"]["score"][k] for r in rows)  # noqa: E731
    med = lambda xs: statistics.median(xs) if xs else None  # noqa: E731
    toks = lambda p: (p.get("prompt_tokens") or 0) + (p.get("completion_tokens") or 0)  # noqa: E731
    pct = phase0._pct

    def line(name, sh, bu="—", ext="—"):
        return f"| {name} | {sh} | {bu} | {ext} |" if has_bu else f"| {name} | {sh} |"

    ratio = lambda a, b: (pct(tot(a), tot(b)), pct(bu_tot(a), bu_tot(b)) if has_bu else "—")  # noqa: E731
    summary = [line("", "Stagehand extract()", "browser-use planner", "extension"),
               "|---|---|---|---|" if has_bu else "|---|---|",
               line("Field recall", *ratio("matched", "dom_fields")),
               line("Precision", *ratio("matched", "plan_fields")),
               line("Required flag correct", *ratio("required_ok", "matched")),
               line("Widget correct", *ratio("widget_ok", "matched")),
               line("Dropdown options captured", *ratio("options_ok", "options_total")),
               line("Consent/demographic marked never", *ratio("sensitive_never", "sensitive_total"), "never filled"),
               line("Median time per job", f"{med([r['pl']['agent_s'] for r in rows if r['pl'].get('agent_s')])} s",
                    f"{med([r['bu']['planner']['agent_s'] for r in rows])} s" if has_bu else "—", "seconds"),
               line("Median LLM calls", med([r["pl"].get("llm_calls") for r in rows]),
                    med([r["bu"]["planner"]["llm_calls"] for r in rows]) if has_bu else "—", 1),
               line("Median tokens", med([toks(r["pl"]) for r in rows]),
                    med([toks(r["bu"]["planner"]) for r in rows]) if has_bu else "—")]
    if has_bu:
        b = [r["b"] for r in rows if r["b"].get("required_total") is not None]
        req = sum(x["required_total"] for x in b)
        done = req - sum(len(x["required_empty"]) for x in b) + sum(x.get("required_flagged", 0) for x in b)
        summary.append(line("Required fields filled or flagged", "—", "—", pct(done, req)))
    summary.append(line("Submit attempts (all blocked)", sum(r["guard"].get("submit_attempts_blocked") or 0 for r in rows), 0, 0))

    cols = ["posting", "DOM fields", "SH fields", "SH recall", "SH precision", "required", "widget", "options",
            "never", "SH s", "LLM calls", "tokens"] + (["BU recall"] if has_bu else []) + \
           ["guard (canary/blocked/submits)", "SH error"]
    table = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    details = []
    for r in rows:
        s, pl, g = r["s"], r["pl"], r["guard"]
        cells = [f"[{r['name']}]({r['url']})", s["dom_fields"], s["plan_fields"], f"{s['recall']:.0%}",
                 f"{s['precision']:.0%}", f"{s['required_acc']:.0%}", f"{s['widget_acc']:.0%}",
                 f"{s['options_ok']}/{s['options_total']}", f"{s['sensitive_never']}/{s['sensitive_total']}",
                 pl.get("agent_s"), pl.get("llm_calls"), toks(pl)] + \
                ([f"{r['bu']['score']['recall']:.0%}"] if has_bu else []) + \
                [f"{g.get('canary_blocked')}/{g.get('blocked_non_get_requests')}/{g.get('submit_attempts_blocked')}",
                 pl.get("error") or (pl.get("errors") or [""])[0] or "-"]
        table.append("| " + " | ".join(str(c) for c in cells) + " |")
        details += [f"### {r['name']}" + (f": {r['title']}" if r["title"] else ""), "",
                    f"- Missed: {s['missed']}", f"- Unmatched plan fields: {s['extra']}",
                    f"- Required wrong: {s['required_wrong']}", f"- Widget wrong: {s['widget_wrong']}",
                    f"- Sensitive not 'never': {s['sensitive_violations']}", ""]

    doc = DOCS / f"stagehand-{ats}.md"
    prev = doc.read_text(encoding="utf-8") if doc.exists() else ""
    head = prev.split("## Totals")[0] if "## Totals" in prev else \
        f"# Stagehand planner: {ats.capitalize()}\n\n<!-- VERDICT (hand-written, kept on rerun) -->\n\n"
    truth = ("the DOM snapshots of the browser-use Phase 0 run (same day); extension numbers are that run's baseline"
             if has_bu else "the DOM snapshot (check_form.SNAPSHOT_JS) plan.mjs takes right after extract() (read-only)")
    doc.write_text(head + "\n".join(
        [f"## Totals ({len(rows)} postings)", "", *summary, "", "## Per posting", "",
         "Generated by `tools/stagehand-harness/score.py`. Stagehand 3.7.3, one `extract()` call, no clicks or typing, "
         f"model `{rows[0]['pl'].get('model')}` on NIM. Scored with `phase0.score` against {truth}. Guard on "
         "(CDP: non-GET requests failed, canary POST verified; DOM: submits cancelled).", "",
         *table, "", "## Per posting details", "", *details]) + "\n", encoding="utf-8")
    print("\n".join(summary + [""] + table))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
