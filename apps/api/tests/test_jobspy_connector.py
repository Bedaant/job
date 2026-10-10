import pytest
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from connectors.jobspy_connector import fetch_jobspy_jobs


@pytest.fixture(autouse=True)
def _jobspy_venv(tmp_path_factory, monkeypatch):
    # The tests fake subprocess.run; only the interpreter lookup needs a venv to exist (CI has none).
    import connectors.jobspy_connector as jc
    tools = tmp_path_factory.mktemp("tools")
    py = tools / ".venv-jobspy" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("")
    monkeypatch.setattr(jc, "_TOOLS_DIR", str(tools))



@patch("connectors.jobspy_connector.subprocess.run")
def test_fetch_jobspy_jobs_parses_subprocess_json(mock_run):
    payload = [{"title": "Backend Engineer", "company": "Acme", "site": "google", "job_url": "https://x", "location": "Remote", "date_posted": "2026-08-16"}]
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(payload))

    from connectors.jobspy_connector import fetch_jobspy_jobs
    jobs = fetch_jobspy_jobs("backend engineer", results_wanted=5)

    assert jobs == [{
        "source": "jobspy_google",
        "external_id": "https://x",
        "title": "Backend Engineer",
        "company": "Acme",
        "location": "Remote",
        "apply_url": "https://x",
        "posted_at": datetime(2026, 8, 16),
    }]


@patch("connectors.jobspy_connector.subprocess.run")
def test_fetch_jobspy_jobs_posted_at_none_when_date_posted_missing(mock_run):
    payload = [{"title": "PM", "company": "Acme", "site": "google", "job_url": "https://y", "location": "Remote", "date_posted": None}]
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(payload))

    from connectors.jobspy_connector import fetch_jobspy_jobs
    jobs = fetch_jobspy_jobs("pm", results_wanted=5)
    assert jobs[0]["posted_at"] is None


@patch("connectors.jobspy_connector.subprocess.run")
def test_fetch_jobspy_jobs_returns_empty_on_subprocess_failure(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="boom")

    from connectors.jobspy_connector import fetch_jobspy_jobs
    assert fetch_jobspy_jobs("backend engineer") == []


@patch("connectors.jobspy_connector.subprocess.run")
def test_fetch_jobspy_jobs_returns_empty_on_no_results(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="[]")

    from connectors.jobspy_connector import fetch_jobspy_jobs
    assert fetch_jobspy_jobs("backend engineer") == []


@patch("connectors.jobspy_connector.subprocess.run")
def test_fetch_jobspy_jobs_tags_source_per_site_not_always_google(mock_run):
    """ADR-015 lifted the Google-only restriction. A row scraped from
    ZipRecruiter must not be recorded as coming from Google."""
    payload = [{"title": "PM", "company": "Acme", "site": "zip_recruiter",
                "job_url": "https://z", "location": "Remote", "date_posted": "2026-09-26"}]
    mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(payload))

    from connectors.jobspy_connector import fetch_jobspy_jobs
    assert fetch_jobspy_jobs("pm")[0]["source"] == "jobspy_zip_recruiter"


def test_jobspy_never_scrapes_linkedin_or_indeed():
    """ADR-015 parks LinkedIn (special case) and defers Indeed to Tier C.
    Neither may appear in the default site list."""
    from connectors import config
    assert "linkedin" not in config.JOBSPY_SITES
    assert "indeed" not in config.JOBSPY_SITES
    assert config.JOBSPY_SITES, "at least one JobSpy site must be enabled"


# ---------- GAPS 3.2: wiring it into ingestion, and the three defects that blocked it ----------

@patch("connectors.jobspy_connector.subprocess.run")
def test_location_is_passed_to_the_scraper(mock_run):
    """MEASURED 2026-10-09, and it is the whole reason this connector returned nothing
    useful: the scrape script never passed `location`, so Glassdoor answered without one
    and every row arrived with `location=None` — while the library populates it 8/8 when
    asked. Location-less rows are worse than missing rows here, because
    `passes_hard_filters` is built so missing data never excludes a job (GAPS 2.4), so
    they pass the India filter wherever they actually are.
    """
    mock_run.return_value = SimpleNamespace(returncode=0, stdout="[]", stderr="")
    fetch_jobspy_jobs("product manager", results_wanted=5, sites=["glassdoor"],
                      location="Bengaluru, India")
    argv = mock_run.call_args.args[0]
    assert "Bengaluru, India" in argv


@patch("connectors.jobspy_connector.subprocess.run")
def test_location_survives_into_the_normalized_row(mock_run):
    mock_run.return_value = SimpleNamespace(
        returncode=0,
        stdout=json.dumps([{
            "job_url": "https://g.example/1", "title": "Product Manager",
            "company": "Acme", "location": "Bengaluru, India", "site": "glassdoor",
            "date_posted": "2026-10-01",
        }]),
        stderr="",
    )
    rows = fetch_jobspy_jobs("product manager", sites=["glassdoor"], location="Bengaluru, India")
    assert rows[0]["location"] == "Bengaluru, India"


@patch("connectors.jobspy_connector.subprocess.run")
def test_a_crashed_scrape_is_logged_not_silently_empty(mock_run, caplog):
    """The defect that let GAPS 3.2 sit unexplained: a 403 and a genuinely empty board
    both returned `[]`. ZipRecruiter and Glassdoor were BOTH returning 403 on the pinned
    1.1.82, and nothing said so. Same bug class as the Apify token silently resolving to
    "no candidates".
    """
    mock_run.return_value = SimpleNamespace(
        returncode=1, stdout="", stderr="ZipRecruiter response status code 403",
    )
    with caplog.at_level("WARNING"):
        assert fetch_jobspy_jobs("pm", sites=["zip_recruiter"]) == []
    assert any("403" in r.message or "403" in str(r.args) for r in caplog.records), caplog.text


@patch("connectors.jobspy_connector.subprocess.run")
def test_an_empty_result_is_not_logged_as_a_failure(mock_run, caplog):
    """The other half: a board with nothing matching is normal and must stay quiet, or
    the log becomes noise nobody reads."""
    mock_run.return_value = SimpleNamespace(returncode=0, stdout="[]", stderr="")
    with caplog.at_level("WARNING"):
        assert fetch_jobspy_jobs("pm", sites=["glassdoor"]) == []
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_configured_sites_are_only_the_ones_measured_to_work():
    """Measured live on python-jobspy 1.3.0, 2026-10-09: glassdoor returned rows while
    google, zip_recruiter and indeed each returned 0. Carrying a dead site in the default
    list spends a request per keyword per location on nothing.
    """
    from connectors import config
    assert config.JOBSPY_SITES == ["glassdoor"]


def test_locations_are_cities_never_a_bare_country():
    """`location="India"` returns INDIANAPOLIS — Glassdoor prefix-matches the string, so
    a country-level query silently fills the pool with US jobs. Measured 2026-10-09.
    Per-city is what produced 147 unique India PM jobs across 101 companies.
    """
    from connectors import config
    assert config.JOBSPY_LOCATIONS, "an empty list means jobspy fetches nothing"
    for loc in config.JOBSPY_LOCATIONS:
        assert "," in loc, f"{loc!r} is not city-qualified — 'India' alone matches Indianapolis"


def test_keywords_are_not_empty():
    """`JOBSPY_KEYWORDS` was `[]`, so even once wired the connector would have searched
    for nothing — the second reason GAPS 3.2 produced no rows."""
    from connectors import config
    assert config.JOBSPY_KEYWORDS


def test_jobspy_is_never_swept_for_delistings():
    """A keyword+location slice is not a complete listing, so absence from a payload
    means "not in that search", not "gone" (ADR-017 §2). Sweeping it would tombstone
    live jobs."""
    from workers.jobs import SWEEPABLE_SOURCES
    assert not any(s.startswith("jobspy") for s in SWEEPABLE_SOURCES)


# ---------- DEPLOY-A.1: the interpreter path must not be Windows-only ----------

def test_the_jobspy_interpreter_is_resolved_not_hardcoded(tmp_path, monkeypatch):
    """`.venv-jobspy/Scripts/python.exe` is Windows-only; Linux is `bin/python`.

    Hardcoding it means `subprocess.run` raises FileNotFoundError on the box, the
    connector logs it and returns `[]`, and **JobSpy silently contributes nothing** —
    the exact failure shape GAPS 3.2 spent weeks being unexplained by. Resolved by what
    exists rather than by guessing the platform, so one code path works in both places.
    """
    from connectors import jobspy_connector as jc

    posix = tmp_path / ".venv-jobspy" / "bin"
    posix.mkdir(parents=True)
    (posix / "python").write_text("#!/bin/sh\n")
    monkeypatch.setattr(jc, "_TOOLS_DIR", str(tmp_path))
    assert jc._jobspy_python() == str(posix / "python")

    win = tmp_path / ".venv-jobspy" / "Scripts"
    win.mkdir(parents=True)
    (win / "python.exe").write_text("")
    assert jc._jobspy_python() == str(win / "python.exe"), "Windows layout still wins when present"


def test_a_missing_jobspy_venv_is_reported_not_silently_empty(monkeypatch, caplog):
    """Deploying without building the second venv must say so. Returning `[]` would look
    exactly like a board with nothing matching."""
    from connectors import jobspy_connector as jc

    monkeypatch.setattr(jc, "_TOOLS_DIR", "/nonexistent-tools-dir")
    with caplog.at_level("WARNING"):
        assert jc.fetch_jobspy_jobs("pm", sites=["glassdoor"], location="Bengaluru, India") == []
    assert any("venv" in r.getMessage().lower() for r in caplog.records), caplog.text
