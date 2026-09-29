"""Server plan vs no plan: fill each posting in out/<ats>-<company>-<external_id>.json twice with the extension
and write docs/harness-reports/plan-vs-extension.md.

Per posting: `python -m formplans` (apps/api) stores the Stagehand plan -> check_form.py --no-audit (baseline)
-> check_form.py --no-audit --job-id J (map-fields uses the plan; skipped unless the plan is ok) -> both reports
scored with phase0.baseline_from. Rows append to out/measure.jsonl; postings already there are skipped (resume).

  ..\\.venv-browser-use\\Scripts\\python measure.py [--ats greenhouse|lever|ashby]

Thin orchestration over tested helpers (check_form, phase0), no unit test of its own.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BU = HERE.parent / "browser-use-harness"
sys.path.insert(0, str(BU))
import phase0  # noqa: E402
from check_form import API_PY, MAIN  # noqa: E402

OUT = HERE / "out"
ROWS = OUT / "measure.jsonl"
DOC = HERE.parent.parent / "docs" / "harness-reports" / "plan-vs-extension.md"
ATSES = ("greenhouse", "lever", "ashby")


def postings(ats: str | None) -> list[dict]:
    out = []
    for f in sorted(OUT.glob("*.json")):
        parts = f.stem.split("-", 2)  # Lever/Ashby ids contain dashes
        if len(parts) == 3 and parts[0] in ATSES and ats in (None, parts[0]):
            out.append({"ats": parts[0], "company": parts[1], "external_id": parts[2],
                        "url": json.loads(f.read_text(encoding="utf-8"))["url"]})
    return out


def make_plan(p: dict) -> dict:
    try:
        r = subprocess.run([str(API_PY), "-m", "formplans", "--ats", p["ats"], "--token", p["company"],
                            "--external-id", p["external_id"], "--url", p["url"]], cwd=MAIN / "apps" / "api",
                           capture_output=True, encoding="utf-8", errors="replace", timeout=900)
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
    try:
        return json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        return {"status": f"cli failed ({r.returncode})", "error": (r.stderr or r.stdout).strip()[-300:]}


def fill(url: str, ats: str, *extra: str) -> dict:
    """phase0.run_baseline with extra check_form args (it takes none); same newest-new-report rule."""
    reports = BU / "reports"
    before = set(reports.glob(f"*-{ats}.json"))
    try:
        subprocess.run([phase0.PY, str(BU / "check_form.py"), "--url", url, "--ats", ats, "--no-audit", *extra],
                       cwd=BU, timeout=900)
    except subprocess.TimeoutExpired:
        return {"error": "check_form timed out"}
    new = sorted(set(reports.glob(f"*-{ats}.json")) - before)
    if not new:
        return {"error": "check_form wrote no report"}
    b = phase0.baseline_from(new[-1])
    dom = json.loads(new[-1].read_text(encoding="utf-8")).get("dom", {})
    b["values"] = {f["label"]: f["value"] for f in dom.get("filled", [])}
    return b


def measure(p: dict) -> dict:
    plan = make_plan(p)
    fields = plan.get("fields")
    row = {**p, "plan": {"status": plan.get("status"), "job_id": plan.get("job_id"), "error": plan.get("error"),
                         "fields": len(fields) if isinstance(fields, list) else fields}}
    row["base"] = fill(p["url"], p["ats"])
    if plan.get("status") == "ok" and plan.get("job_id"):
        row["with_plan"] = fill(p["url"], p["ats"], "--job-id", plan["job_id"])
    return row


def done_urls() -> set[str]:
    return {json.loads(ln)["url"] for ln in ROWS.read_text(encoding="utf-8").splitlines() if ln.strip()} \
        if ROWS.exists() else set()


def req(b: dict, flagged: bool = False):
    if b.get("required_total") is None:
        return None
    return b["required_total"] - len(b["required_empty"]) + (b.get("required_flagged", 0) if flagged else 0)


def write_doc() -> None:
    rows = [json.loads(ln) for ln in ROWS.read_text(encoding="utf-8").splitlines() if ln.strip()]
    one = lambda f, x: f(x) if x and "error" not in x else "-"  # noqa: E731
    pair = lambda f, a, b: f"{one(f, a)} / {one(f, b)}"  # noqa: E731
    guard = lambda b: "/".join(str(b.get("guard", {}).get(k)) for k in  # noqa: E731
                               ("canary_blocked", "blocked_non_get_requests", "submit_attempts_blocked"))
    cols = ["posting", "plan", "plan fields", "required filled", "required filled or flagged", "filled fields",
            "fill s", "demographic violations", "guard canary/blocked/submits", "error"]
    table = ["Cells are baseline / with plan.", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    details, tot = [], {k: [0, 0] for k in ("required", "filled", "flagged", "fields", "demo", "submits")}
    for r in rows:
        b, w = r.get("base") or {}, r.get("with_plan") or {}
        req_s = lambda x, fl=False: f"{req(x, fl)}/{x['required_total']}" if req(x) is not None else "-"  # noqa: E731
        table.append("| " + " | ".join(str(c) for c in [
            f"[{r['ats']} {r['company']}]({r['url']})", r["plan"]["status"], r["plan"]["fields"],
            pair(req_s, b, w), pair(lambda x: req_s(x, True), b, w), pair(lambda x: x.get("filled_fields"), b, w),
            pair(lambda x: x.get("fill_s"), b, w), pair(lambda x: x.get("demographic_violations"), b, w),
            pair(guard, b, w), r["plan"].get("error") or b.get("error") or w.get("error") or "-"]) + " |")
        if req(b) is not None and req(w) is not None:
            for i, x in enumerate((b, w)):
                tot["required"][i] += req(x)
                tot["flagged"][i] += req(x, True)
                tot["fields"][i] += x["required_total"]
                tot["filled"][i] += x["filled_fields"]
                tot["demo"][i] += x["demographic_violations"]
                tot["submits"][i] += x["guard"].get("submit_attempts_blocked") or 0
        bv, wv = b.get("values") or {}, w.get("values") or {}
        details += [f"### {r['ats']} {r['company']} {r['external_id']}", "",
                    "- Only baseline filled: " + (", ".join(f"{k} = `{v}`" for k, v in bv.items() if k not in wv) or "none"),
                    "- Only with plan filled: " + (", ".join(f"{k} = `{v}`" for k, v in wv.items() if k not in bv) or "none"),
                    ""]
    both = sum(1 for r in rows if req(r.get("base") or {}) is not None and req(r.get("with_plan") or {}) is not None)
    t = lambda k: f"{tot[k][0]} / {tot[k][1]}"  # noqa: E731
    summary = [f"## Totals ({len(rows)} postings, {both} with both runs)", "", "| | baseline / with plan |", "|---|---|",
               f"| Plans ok | {sum(1 for r in rows if r['plan']['status'] == 'ok')}/{len(rows)} |",
               f"| Required filled | {t('required')} of {tot['fields'][0]} |",
               f"| Required filled or flagged | {t('flagged')} of {tot['fields'][0]} |",
               f"| Filled fields | {t('filled')} |", f"| Demographic violations | {t('demo')} |",
               f"| Submit attempts (all blocked) | {t('submits')} |"]
    prev = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
    head = prev.split("## Totals")[0] if "## Totals" in prev else \
        "# Server plan vs extension alone\n\n<!-- VERDICT (hand-written, kept on rerun) -->\n\n"
    DOC.write_text(head + "\n".join(
        [*summary, "", "## Per posting", "",
         "Generated by `tools/stagehand-harness/measure.py`: `python -m formplans` stores the plan, then "
         "`check_form.py --no-audit` fills the form without and with `--job-id` (guard on, never submitted), "
         "both scored with `phase0.baseline_from`.", "", *table, "",
         "## Fields filled in only one run (check the values by hand; target 0 wrong)", "", *details]) + "\n",
        encoding="utf-8")
    print("\n".join(summary))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ats", choices=ATSES)
    a = ap.parse_args()
    done = done_urls()
    for p in postings(a.ats):
        if p["url"] in done:
            continue
        print(f"== {p['ats']} {p['company']} {p['external_id']}", flush=True)
        row = measure(p)
        with ROWS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    if ROWS.exists():
        write_doc()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
