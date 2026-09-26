"""JobSpy connector (DEPENDENCIES.md §3, speedyapply/JobSpy, MIT).

ADR-015 lifted the Google-only restriction this file used to carry: the sites
scraped are now whatever `connectors.config.JOBSPY_SITES` lists. LinkedIn stays
excluded (ADR-015 parks it as a special case) and Indeed is Tier C, so neither
is in the default list — that exclusion is a tested config value now, not a
hardcoded string buried in this module.

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

from connectors import config

_TOOLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "tools")
_JOBSPY_PYTHON = os.path.join(_TOOLS_DIR, ".venv-jobspy", "Scripts", "python.exe")

_SCRAPE_SCRIPT = """
import json, sys
from jobspy import scrape_jobs
sites = sys.argv[3].split(",")
df = scrape_jobs(
    site_name=sites,
    search_term=sys.argv[1],
    google_search_term=sys.argv[1],
    results_wanted=int(sys.argv[2]),
)
df = df.where(df.notnull(), None)
print(json.dumps(df.to_dict(orient="records"), default=str))
"""


def fetch_jobspy_jobs(search_term: str, results_wanted: int = 20,
                      sites: list[str] | None = None) -> list[dict]:
    sites = sites or config.JOBSPY_SITES
    result = subprocess.run(
        [_JOBSPY_PYTHON, "-c", _SCRAPE_SCRIPT, search_term, str(results_wanted), ",".join(sites)],
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
            # Per-site, not a constant: a ZipRecruiter row recorded as coming
            # from Google would make source-level yield stats meaningless.
            "source": f"jobspy_{r.get('site') or 'unknown'}",
            "external_id": url,
            "title": r.get("title", ""),
            "company": r.get("company", ""),
            "location": r.get("location"),
            "apply_url": url,
            "posted_at": r.get("date_posted"),
        })
    return jobs
