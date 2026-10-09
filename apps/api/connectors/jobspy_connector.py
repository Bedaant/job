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
import logging
import os
import subprocess
import sys

from connectors import config
from connectors.normalize import coerce_posted_at

logger = logging.getLogger(__name__)

_TOOLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "tools")
_JOBSPY_PYTHON = os.path.join(_TOOLS_DIR, ".venv-jobspy", "Scripts", "python.exe")

_SCRAPE_SCRIPT = """
import json, sys
from jobspy import scrape_jobs
sites = sys.argv[3].split(",")
location = sys.argv[4] or None
df = scrape_jobs(
    site_name=sites,
    search_term=sys.argv[1],
    google_search_term=sys.argv[1],
    results_wanted=int(sys.argv[2]),
    location=location,
)
df = df.where(df.notnull(), None)
print(json.dumps(df.to_dict(orient="records"), default=str))
"""


def fetch_jobspy_jobs(search_term: str, results_wanted: int = 20,
                      sites: list[str] | None = None,
                      location: str | None = None) -> list[dict]:
    """One scrape, for one search term in one location.

    `location` is not optional in practice and was the connector's central defect: the
    script never passed it, so Glassdoor answered without one and EVERY row arrived with
    `location=None`, while the library populates it on all rows when asked (measured
    2026-10-09). Location-less rows are worse here than no rows at all —
    `passes_hard_filters` is deliberately built so missing data never excludes a job
    (GAPS 2.4), so they would pass the India filter wherever they actually are, and
    `canonical_hash(company, title, location)` loses a third of its key.

    **Pass a CITY, never a bare country.** `location="India"` returns Indianapolis:
    Glassdoor prefix-matches the string. `config.JOBSPY_LOCATIONS` is city-qualified for
    that reason and a test enforces it.
    """
    sites = sites or config.JOBSPY_SITES
    result = subprocess.run(
        [_JOBSPY_PYTHON, "-c", _SCRAPE_SCRIPT, search_term, str(results_wanted),
         ",".join(sites), location or ""],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if result.returncode != 0:
        # Distinguishing a CRASH from an empty board is the whole reason GAPS 3.2 sat
        # unexplained: both used to return `[]`, so a site answering 403 looked exactly
        # like a site with nothing matching. ZipRecruiter and Glassdoor were BOTH 403 on
        # the old pinned version and nothing said so.
        logger.warning(
            "jobspy scrape failed for %s in %r (exit %s): %s",
            ",".join(sites), location, result.returncode,
            (result.stderr or "").strip()[-300:],
        )
        return []
    if not result.stdout.strip():
        # A board with nothing matching is normal and stays quiet, or the log becomes
        # noise nobody reads.
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
            "posted_at": coerce_posted_at(r.get("date_posted")),
        })
    return jobs
