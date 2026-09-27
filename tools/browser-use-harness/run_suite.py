"""Run check_form on the three forms from docs/LIVE-FORM-TEST.md (all open on 2026-09-27) and
print a summary table. Each form runs in its own process so one crash can't skip the rest.

  ..\\.venv-browser-use\\Scripts\\python run_suite.py [--no-audit] [--only greenhouse]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FORMS = {
    "greenhouse": "https://job-boards.greenhouse.io/anthropic/jobs/4461450008",
    "lever": "https://jobs.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd/apply",
    "ashby": "https://jobs.ashbyhq.com/ashby/7458d4e9-da2e-47bd-98cb-adfda43d42b2/application",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-audit", action="store_true")
    ap.add_argument("--only", choices=list(FORMS))
    a = ap.parse_args()
    rows, worst = [], 0
    for ats, url in FORMS.items():
        if a.only and ats != a.only:
            continue
        before = set((HERE / "reports").glob(f"*-{ats}.json"))
        cmd = [sys.executable, str(HERE / "check_form.py"), "--url", url, "--ats", ats] + (["--no-audit"] * a.no_audit)
        code = subprocess.run(cmd, cwd=HERE).returncode
        worst = max(worst, code)
        new = sorted(set((HERE / "reports").glob(f"*-{ats}.json")) - before)
        if not new:
            rows.append((ats, "CRASH", "-", "-", "-", "-", "-", "-"))
            continue
        r = json.loads(new[-1].read_text(encoding="utf-8"))
        dom, g = r.get("dom", {}), r["guard"]
        rows.append((
            ats, "PASS" if r["passed"] else "FAIL", str(r.get("extension_response", {}).get("ok")),
            str(len(dom.get("filled", []))), str(len(dom.get("empty_required", []))),
            str(len(dom.get("demographic_violations", []))), str(len(r.get("auditor", {}).get("flagged", []))),
            f"{g.get('blocked_non_get_requests', 0)}/{g.get('submit_attempts_blocked', 0)}",
        ))
    head = ("ats", "result", "fill ok", "filled", "empty req", "demo w/ value", "auditor flags", "blocked req/submit")
    print("\n| " + " | ".join(head) + " |\n|" + "---|" * len(head))
    for row in rows:
        print("| " + " | ".join(row) + " |")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
