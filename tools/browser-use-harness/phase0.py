"""PLAN-MULTI-ATS Phase 0: browser-use form plans vs the DOM, plus the extension baseline.

  ..\\.venv-browser-use\\Scripts\\python phase0.py --ats greenhouse --n 5 [--embed]   # run (resumable)
  ..\\.venv-browser-use\\Scripts\\python phase0.py --report                           # write docs/harness-reports

Per posting, ONE browser at a time: plan_form.py (guarded, read-only, synthetic identity) ->
score its plan against the DOM snapshot (check_form.SNAPSHOT_JS) -> check_form.py --no-audit
(the extension's own fill, guarded, throwaway account). Rows append to reports/phase0/<ats>.jsonl,
so a rerun skips postings already done.
"""

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

HERE = Path(__file__).resolve().parent
OUT = HERE / "reports" / "phase0"
DOCS = HERE.parent.parent / "docs" / "harness-reports"
PY = sys.executable

DEMOGRAPHIC = re.compile(  # same as check_form.DEMOGRAPHIC (kept here so the scorer imports nothing heavy)
    r"(?<![a-z])(gender|sex|sexual|race|racial|ethnicity|ethnic|hispanic|latin[oax]?|veteran|"
    r"disabilit\w*|disabled|pronouns?|transgender|lgbtq?|age range)(?![a-z])", re.I)
CONSENT = re.compile(r"consent|acknowledg|i agree|agree to|privacy (policy|notice)|arbitration|i certify|attest", re.I)
WIDGETS = {"select": {"select"}, "combobox": {"react_select", "typeahead", "select"}, "textarea": {"textarea"},
           "radio": {"radio"}, "checkbox": {"checkbox"}, "file": {"file"}, "date": {"date"}}

COMPANIES = {
    "greenhouse": ["anthropic", "stripe", "robinhood", "airbnb", "figma", "discord", "cloudflare", "datadog",
                   "dropbox", "databricks", "brex", "instacart", "lyft", "reddit", "vercel", "asana",
                   "pinterest", "duolingo", "samsara", "twilio", "carta", "checkr"],
    "lever": ["palantir", "plaid", "spotify", "mistral", "zoox", "whoop", "eventbrite", "outreach", "attentive",
              "highspot", "cloudbees", "ro", "shieldai", "matchgroup", "binance", "gopuff", "dnb", "hive",
              "aircall", "weride"],
    "ashby": ["ashby", "openai", "notion", "linear", "ramp", "vercel", "supabase", "replit", "posthog", "zapier",
              "lemonade", "cursor"],
}
EMBED = "https://job-boards.greenhouse.io/embed/job_app?for={board}&token={token}"


# ---------- scoring (test_phase0.py) ----------

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (s or "").lower())).strip()


def dom_fields(snapshot: list[dict]) -> list[dict]:
    """Ground-truth fields: visible controls (+ file inputs, usually hidden behind a button), a
    radio/checkbox group as one field. A control with no id, name or label of its own is dropped:
    that is react-select's required-validation twin, not a question."""
    out, groups = [], {}
    for f in snapshot:
        if not f["visible"] and f["type"] != "file":
            continue
        if not (f["id"] or f["name"] or f["label"]):
            continue
        kind = "combobox" if f["role"] == "combobox" else f["type"]
        if f["type"] in ("radio", "checkbox") and f["name"]:
            g = groups.get(f["name"])
            if g:
                g["keys"] |= {f["id"]} - {""}
                g["required"] |= f["required"]
                g["filled"] |= bool(f["value"])
                continue
            g = groups[f["name"]] = {"label": f["group"] or f["label"], "keys": {f["id"], f["name"]} - {""},
                                     "required": f["required"], "kind": kind, "text": f["group"] + " " + f["label"],
                                     "filled": bool(f["value"]),
                                     "names": {_norm(f["group"] or f["label"])} - {""}}
            out.append(g)
            continue
        out.append({"label": f["label"] or f["group"] or f["id"] or f["name"], "keys": {f["id"], f["name"]} - {""},
                    "required": f["required"], "kind": kind, "text": f["label"] + " " + f["group"],
                    "filled": bool(f["display"] or f["value"]),
                    "names": {_norm(f["label"]), _norm(f["group"])} - {""}})
    for d in out:
        d["sensitive"] = bool(DEMOGRAPHIC.search(d["text"] + " " + " ".join(d["keys"])) or CONSENT.search(d["text"]))
    return out


def _hint_tokens(hint: str) -> set[str]:
    return set(re.findall(r"[\w\-\[\]\.:]+", hint or ""))


def score(plan: dict | None, snapshot: list[dict]) -> dict:
    dom = dom_fields(snapshot)
    pf = list((plan or {}).get("fields") or [])
    pairs, used_d, used_p = [], set(), set()

    def pick(test):
        for pi, p in enumerate(pf):
            if pi in used_p:
                continue
            for di, d in enumerate(dom):
                if di not in used_d and test(p, d):
                    pairs.append((p, d))
                    used_p.add(pi)
                    used_d.add(di)
                    break

    pick(lambda p, d: bool(_hint_tokens(p.get("selector_hint")) & d["keys"]))
    pick(lambda p, d: _norm(p.get("label")) in d["names"])

    def contains(p, d):
        a = _norm(p.get("label"))
        return any(min(len(a), len(b)) >= 4 and (a in b or b in a) for b in d["names"])
    pick(contains)

    k = len(pairs)
    opt = [(p, d) for p, d in pairs if d["kind"] in ("select", "combobox")]
    opt_total = sum(1 for d in dom if d["kind"] in ("select", "combobox"))  # a missed dropdown = no options
    sens = [d for d in dom if d["sensitive"]]
    sens_ok = sum(1 for p, d in pairs if d["sensitive"] and p.get("fill_from") == "never")
    ratio = lambda a, b: a / b if b else 0.0  # noqa: E731
    return {
        "dom_fields": len(dom), "plan_fields": len(pf), "matched": k,
        "recall": ratio(k, len(dom)), "precision": ratio(k, len(pf)),
        "required_ok": sum(1 for p, d in pairs if bool(p.get("required")) == d["required"]),
        "required_acc": ratio(sum(1 for p, d in pairs if bool(p.get("required")) == d["required"]), k),
        "options_ok": sum(1 for p, _ in opt if p.get("options")), "options_total": opt_total,
        "widget_ok": sum(1 for p, d in pairs if p.get("widget") in WIDGETS.get(d["kind"], {"text"})),
        "widget_acc": ratio(sum(1 for p, d in pairs if p.get("widget") in WIDGETS.get(d["kind"], {"text"})), k),
        "sensitive_never": sens_ok, "sensitive_total": len(sens),
        "sensitive_violations": [p.get("label") for p in pf if p.get("fill_from") != "never" and (
            DEMOGRAPHIC.search(f"{p.get('label')} {p.get('selector_hint')}") or CONSENT.search(p.get("label") or ""))],
        "missed": [d["label"] for i, d in enumerate(dom) if i not in used_d],
        "extra": [p.get("label") for i, p in enumerate(pf) if i not in used_p],
        "widget_wrong": [f"{d['label']}: {p.get('widget')} (dom {d['kind']})" for p, d in pairs
                         if p.get("widget") not in WIDGETS.get(d["kind"], {"text"})],
        "required_wrong": [f"{d['label']}: plan {bool(p.get('required'))} dom {d['required']}" for p, d in pairs
                           if bool(p.get("required")) != d["required"]],
    }


# ---------- picking postings ----------

def pick_postings(ats: str, n: int) -> list[dict]:
    got = []
    with httpx.Client(timeout=30, follow_redirects=False) as c:
        for co in COMPANIES[ats]:
            if len(got) >= n:
                break
            try:
                if ats == "greenhouse":
                    jobs = c.get(f"https://boards-api.greenhouse.io/v1/boards/{co}/jobs").json()["jobs"]
                    cands = [(f"https://job-boards.greenhouse.io/{co}/jobs/{j['id']}", j["title"], j["id"]) for j in jobs]
                elif ats == "lever":
                    jobs = c.get(f"https://api.lever.co/v0/postings/{co}?mode=json").json()
                    cands = [(j["applyUrl"], j["text"], j["id"]) for j in jobs]
                else:
                    jobs = c.get(f"https://api.ashbyhq.com/posting-api/job-board/{co}").json()["jobs"]
                    cands = [(j["applyUrl"], j["title"], j["id"]) for j in jobs if j.get("isListed", True)]
            except Exception:
                continue
            for url, title, jid in cands[:3]:  # one live posting per company
                if c.get(url).status_code == 200:
                    got.append({"ats": ats, "company": co, "title": title, "url": url, "job_id": str(jid)})
                    break
    return got


# ---------- running ----------

def run_plan(url: str, out: Path, allow: list[str], mode: str) -> dict:
    cmd = [PY, str(HERE / "plan_form.py"), "--url", url, "--out", str(out), "--mode", mode] + \
        (["--allow", *allow] if allow else [])
    try:
        subprocess.run(cmd, cwd=HERE, timeout=1500)
    except subprocess.TimeoutExpired:
        return {"planner": {"error": "plan_form timed out after 1500 s"}, "guard": {}}
    return json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"planner": {"error": "no output"}, "guard": {}}


def run_baseline(url: str, ats: str) -> dict:
    before = set((HERE / "reports").glob(f"*-{ats}.json"))
    try:
        subprocess.run([PY, str(HERE / "check_form.py"), "--url", url, "--ats", ats, "--no-audit"], cwd=HERE,
                       timeout=900)
    except subprocess.TimeoutExpired:
        return {"error": "check_form timed out"}
    new = sorted(set((HERE / "reports").glob(f"*-{ats}.json")) - before)
    if not new:
        return {"error": "check_form wrote no report"}
    return baseline_from(new[-1])


def baseline_from(path: Path) -> dict:
    """The extension's result on one posting, counted over dom_fields (react-select twins dropped,
    radio groups as one), so it is comparable with the plan's ground truth."""
    r = json.loads(path.read_text(encoding="utf-8"))
    dom = r.get("dom", {})
    df = dom_fields(r.get("dom_snapshot") or [])
    req = [d for d in df if d["required"] and not d["sensitive"]]  # consent/demographic: never filled, by design
    flagged = {_norm(f.get("label")) for f in (r.get("extension_response") or {}).get("flagged") or []}
    empty = [d for d in req if not d["filled"]]
    return {"report": path.name, "required_empty": [d["label"] for d in empty],
            "required_flagged": sum(1 for d in empty if d["names"] & flagged),
            "filled_fields": sum(1 for d in df if d["filled"]), "passed": r.get("passed"), "failures": r.get("failures"),
            "ext_ok": (r.get("extension_response") or {}).get("ok"), "fields": len(dom_fields(r.get("dom_snapshot") or [])),
            "filled": len(dom.get("filled", [])), "required_total": len(req),
            "empty_required": dom.get("empty_required", []), "demographic_violations": len(dom.get("demographic_violations", [])),
            "fill_s": r.get("timings_s", {}).get("fill_s"), "cleanup": r.get("cleanup"),
            "guard": {k: r["guard"].get(k) for k in ("canary_blocked", "blocked_non_get_requests", "submit_attempts_blocked")}}


def serve_embed(board: str, token: str):
    from auto_apply import serve_host_page
    embed = EMBED.format(board=board, token=token)
    httpx.get(embed, timeout=30).raise_for_status()
    return serve_host_page(embed)


def plan_file(p: dict) -> Path:
    return OUT / (f"{p['ats']}-" + f"{p['company']}-{p['job_id']}"[:60] + ("-embed" if p.get("embed") else "")
                  + ("-list" if p.get("mode") == "list" else "") + "-plan.json")


def rows_file(ats: str, mode: str) -> Path:
    return OUT / f"{ats}{'-list' if mode == 'list' else ''}.jsonl"


def union_snapshot(r: dict) -> list[dict]:
    """Ground truth: the fresh-load snapshot plus any field the walk revealed (conditional questions)."""
    snap = r.get("snapshot_before") or []
    seen = {(f["id"], f["name"], f["label"]) for f in snap}
    return snap + [f for f in r.get("snapshot_after") or [] if (f["id"], f["name"], f["label"]) not in seen]


def run_one(p: dict) -> dict:
    ats = p["ats"]
    srv, allow, url = None, [], p["url"]
    if p.get("embed"):
        srv, url = serve_embed(p["company"], p["job_id"])
        allow = ["job-boards.greenhouse.io", "boards.greenhouse.io"]
    try:
        t = time.monotonic()
        r = run_plan(url, plan_file(p), allow, p.get("mode", "explore"))
        pl = r.get("planner", {})
        snap = union_snapshot(r)
        row = {**p, "plan_url": url, "score": score(pl.get("plan"), snap) if snap else None,
               "plan_wall_s": round(time.monotonic() - t, 1), "load_s": r.get("load_s"),
               "fingerprint": r.get("fingerprint"),
               "planner": {k: pl.get(k) for k in ("model", "agent_s", "steps", "llm_calls", "prompt_tokens",
                                                   "completion_tokens", "done", "error", "final_result")},
               "planner_errors": (pl.get("errors") or [])[:5], "plan_steps": (pl.get("plan") or {}).get("steps"),
               "plan_guard": {k: r.get("guard", {}).get(k) for k in ("canary_blocked", "blocked_non_get_requests",
                                                                     "submit_attempts_blocked",
                                                                     "allowed_readonly_graphql_queries")},
               "guard_error": r.get("guard_error"), "final_url": r.get("final_url")}
        if p.get("mode") != "list":  # the extension baseline does not depend on the planner mode
            row["baseline"] = run_baseline(url, ats)
    finally:
        if srv:
            srv.shutdown()
    return row


# ---------- reports ----------

def _rows(ats: str, mode: str = "explore") -> list[dict]:
    """Rows of a run, re-scored from the saved plan files (so scorer fixes apply to old runs)."""
    f = rows_file(ats, mode)
    rows = [json.loads(x) for x in f.read_text(encoding="utf-8").splitlines() if x.strip()] if f.exists() else []
    for row in rows:
        pf = plan_file(row)
        if pf.exists():
            r = json.loads(pf.read_text(encoding="utf-8"))
            if union_snapshot(r):
                row["score"] = score((r.get("planner") or {}).get("plan"), union_snapshot(r))
        rep = HERE / "reports" / (row.get("baseline") or {}).get("report", "-")
        if rep.is_file():
            row["baseline"] = baseline_from(rep)
    return rows


def _pct(a, b):
    return f"{100 * a / b:.0f}% ({a}/{b})" if b else "-"


def aggregate(rows: list[dict]) -> dict:
    sc = [r["score"] for r in rows if r.get("score")]
    s = lambda k: sum(x[k] for x in sc)  # noqa: E731
    pl = [r["planner"] for r in rows if r["planner"].get("agent_s") is not None]
    med = lambda k: statistics.median([p[k] for p in pl if p.get(k) is not None]) if pl else None  # noqa: E731
    b = [r["baseline"] for r in rows if r.get("baseline", {}).get("required_total") is not None]
    req = sum(x["required_total"] for x in b)
    req_empty = sum(len(x["required_empty"]) for x in b)
    flagged = sum(x.get("required_flagged", 0) for x in b)
    return {
        "postings": len(rows), "plans_ok": sum(1 for r in rows if r["planner"].get("done") and r.get("score")
                                                and r["score"]["plan_fields"]),
        "recall": _pct(s("matched"), s("dom_fields")) if sc else "-",
        "precision": _pct(s("matched"), s("plan_fields")) if sc else "-",
        "required": _pct(s("required_ok"), s("matched")) if sc else "-",
        "options": _pct(s("options_ok"), s("options_total")) if sc else "-",
        "widget": _pct(s("widget_ok"), s("matched")) if sc else "-",
        "sensitive": _pct(s("sensitive_never"), s("sensitive_total")) if sc else "-",
        "sensitive_violations": sum(len(x["sensitive_violations"]) for x in sc),
        "median_s": med("agent_s"), "median_steps": med("steps"), "median_calls": med("llm_calls"),
        "median_tokens": statistics.median([(p.get("prompt_tokens") or 0) + (p.get("completion_tokens") or 0)
                                            for p in pl]) if pl else None,
        "ext_required": _pct(req - req_empty, req) if b else "-",
        "ext_required_or_flagged": _pct(req - req_empty + flagged, req) if b else "-",
        "ext_filled": sum(x["filled"] for x in b), "ext_fields": sum(x["fields"] for x in b),
        "submits": sum((r.get("plan_guard") or {}).get("submit_attempts_blocked") or 0 for r in rows),
    }


def write_reports() -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    summary = ["| ATS | postings | plans done | field recall | precision | required acc | options (select/combobox) "
               "| widget acc | consent/demographic = never | median plan s | median steps | median LLM calls "
               "| median tokens | extension: required filled | extension: required filled or flagged | submits blocked (planner) |",
               "|" + "---|" * 16]
    for ats, mode in [(a, m) for a in COMPANIES for m in ("explore", "list")]:
        rows = _rows(ats, mode)
        if not rows:
            continue
        a = aggregate(rows)
        summary.append(f"| {ats} ({mode}) | {a['postings']} | {a['plans_ok']} | {a['recall']} | {a['precision']} | "
                       f"{a['required']} | {a['options']} | {a['widget']} | {a['sensitive']} (violations "
                       f"{a['sensitive_violations']}) | {a['median_s']} | {a['median_steps']} | {a['median_calls']} | "
                       f"{a['median_tokens']} | {a['ext_required']} | {a['ext_required_or_flagged']} | {a['submits']} |")
        lines = [f"# Phase 0: {ats}, planner mode `{mode}`", "", "Generated by `tools/browser-use-harness/phase0.py --report`. "
                 "Guard on for every run (network: non-GET blocked; DOM: submits cancelled). Synthetic identity "
                 "only.", "", "| posting | DOM fields | plan fields | recall | precision | required | options | "
                 "widget | never | plan s | steps | LLM calls | tokens | ext filled | ext required empty | guard "
                 "(canary/blocked/submits) |", "|" + "---|" * 16]
        for r in rows:
            sc, pl, b, g = r.get("score") or {}, r["planner"], r.get("baseline") or {}, r.get("plan_guard") or {}
            name = f"[{r['company']} {r['job_id']}{' (embed)' if r.get('embed') else ''}]({r['url']})"
            lines.append(
                f"| {name} | {sc.get('dom_fields', '-')} | {sc.get('plan_fields', '-')} | "
                f"{sc.get('recall', 0):.0%} | {sc.get('precision', 0):.0%} | {sc.get('required_acc', 0):.0%} | "
                f"{sc.get('options_ok', '-')}/{sc.get('options_total', '-')} | {sc.get('widget_acc', 0):.0%} | "
                f"{sc.get('sensitive_never', '-')}/{sc.get('sensitive_total', '-')} | {pl.get('agent_s')} | "
                f"{pl.get('steps')} | {pl.get('llm_calls')} | "
                f"{(pl.get('prompt_tokens') or 0) + (pl.get('completion_tokens') or 0)} | "
                f"{b.get('filled_fields', '-')}/{b.get('fields', '-')} | "
                f"{len(b['required_empty']) if 'required_empty' in b else '-'}/{b.get('required_total', '-')} | "
                f"{g.get('canary_blocked')}/{g.get('blocked_non_get_requests')}/{g.get('submit_attempts_blocked')} |")
        lines += ["", "## Per posting details", ""]
        for r in rows:
            sc, pl, b = r.get("score") or {}, r["planner"], r.get("baseline") or {}
            lines += [f"### {r['company']} {r['job_id']}{' (embed)' if r.get('embed') else ''}: {r['title']}", "",
                      f"- Plan: done={pl.get('done')}, error={pl.get('error')}, fingerprint={r.get('fingerprint')}, "
                      f"steps listed={r.get('plan_steps')}, final url={r.get('final_url')}",
                      f"- Missed DOM fields: {sc.get('missed')}", f"- Invented / unmatched plan fields: {sc.get('extra')}",
                      f"- Required wrong: {sc.get('required_wrong')}", f"- Widget wrong: {sc.get('widget_wrong')}",
                      f"- Sensitive not 'never': {sc.get('sensitive_violations')}",
                      f"- Planner errors: {r.get('planner_errors')}",
                      f"- Extension baseline: ok={b.get('ext_ok')}, required empty={b.get('required_empty')}, "
                      f"failures={b.get('failures')}, error={b.get('error')}", ""]
            if pl.get("final_result"):
                lines.insert(-1, f"- Final text (no structured plan): {pl['final_result'][:300]!r}")
        doc = DOCS / f"phase0-{ats}.md"
        prev = doc.read_text(encoding="utf-8") if mode == "list" and doc.exists() else ""
        doc.write_text(prev + ("\n---\n\n" if prev else "") + "\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "summary-table.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print("\n".join(summary))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ats", choices=list(COMPANIES))
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--embed", action="store_true", help="also plan the first Greenhouse posting via a local embed page")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--pick-only", action="store_true")
    ap.add_argument("--mode", choices=["explore", "list"], default="explore",
                    help="list: re-plan the postings of the explore run with the done-only planner (no baseline)")
    a = ap.parse_args()
    if a.report:
        write_reports()
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    done = {(r["url"], bool(r.get("embed"))) for r in _rows(a.ats, a.mode)}
    if a.mode == "list":
        keep = ("ats", "company", "title", "url", "job_id", "embed")
        postings = [{**{k: r[k] for k in keep if k in r}, "mode": "list"} for r in _rows(a.ats)]
    else:
        postings = pick_postings(a.ats, a.n)
        if a.embed and postings:
            postings.append({**postings[0], "embed": True})
    print(json.dumps(postings, indent=1))
    if a.pick_only:
        return 0
    for p in postings:
        if (p["url"], bool(p.get("embed"))) in done:
            continue
        print(f"=== {p['ats']} {p['company']} {p['url']}{' (embed)' if p.get('embed') else ''}", flush=True)
        row = run_one(p)
        with open(rows_file(a.ats, a.mode), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(json.dumps({k: row.get(k) for k in ("score", "planner", "baseline")}, default=str)[:1500], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
