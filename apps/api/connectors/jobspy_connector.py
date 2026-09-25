"""JobSpy connector (DEPENDENCIES.md §3, speedyapply/JobSpy, MIT) — Google
Jobs / ZipRecruiter / Glassdoor only, per ADR-002 (LinkedIn/Indeed scraping
is explicitly excluded regardless of this library's own support for them).

JobSpy's pinned `numpy==1.26.3` hard-conflicts with this app's numpy 2.x
requirement (pgvector/scikit-learn) — installing it in the main venv broke a
real, previously-passing test (see WORKLOG 2026-08-16). Isolated instead:
its own venv at tools/.venv-jobspy/, invoked as a subprocess, same pattern
as agent-reach. Same contract as the other connectors (ARCHITECTURE.md §3):
returns a list of normalized job dicts for connectors.pipeline.upsert_jobs.
"""
import json
import os
import subprocess
import sys

_TOOLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "tools")
_JOBSPY_PYTHON = os.path.join(_TOOLS_DIR, ".venv-jobspy", "Scripts", "python.exe")

_SCRAPE_SCRIPT = """
import json, sys
from jobspy import scrape_jobs
df = scrape_jobs(site_name=["google"], google_search_term=sys.argv[1], results_wanted=int(sys.argv[2]))
df = df.where(df.notnull(), None)
print(json.dumps(df.to_dict(orient="records")))
"""


def fetch_jobspy_jobs(search_term: str, results_wanted: int = 20) -> list[dict]:
    result = subprocess.run(
        [_JOBSPY_PYTHON, "-c", _SCRAPE_SCRIPT, search_term, str(results_wanted)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if result.returncode != 0 or not result.stdout.strip():
        return []

    raw = json.loads(result.stdout)
    jobs = []
    for r in raw:
        url = r.get("job_url")
        if not url:
            continue
        jobs.append({
            "source": "jobspy_google",
            "external_id": url,
            "title": r.get("title", ""),
            "company": r.get("company", ""),
            "location": r.get("location"),
            "apply_url": url,
            "posted_at": r.get("date_posted"),
        })
    return jobs
