"""ADR-001 ("human always clicks submit, the system never does") and
ADR-002 (no server-side scraping/submission) structural guards — backend
half. The extension has the matching guard in
apps/extension/src/content/architectureInvariants.test.mjs (static source
scan + a runtime HTMLFormElement.prototype patch); this is the server-side
equivalent: no function in apps/api/ is ever named like an autonomous
application-submitter, because today none should exist at all.
"""
import os
import re
from pathlib import Path

API_DIR = Path(__file__).resolve().parent.parent
SKIP_DIR_NAMES = {".venv", "__pycache__", "tests", ".pytest_cache", ".ruff_cache"}

FORBIDDEN_NAME_PATTERN = re.compile(
    r"\bdef\s+(submit_application|auto_apply|apply_to_job|autofill_and_submit|auto_submit)\s*\("
)

# Deliberately empty. Any entry here is a conscious, reviewed exception to
# ADR-001/ADR-002 — not a place to silence a real violation quietly.
ALLOWLIST: set[Path] = set()


def _iter_source_files():
    for dirpath, dirnames, filenames in os.walk(API_DIR):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
        for filename in filenames:
            if filename.endswith(".py"):
                yield Path(dirpath) / filename


def _scan_for_violations():
    violations = []
    for path in _iter_source_files():
        if path in ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if FORBIDDEN_NAME_PATTERN.search(text):
            violations.append(str(path.relative_to(API_DIR)))
    return violations


def test_no_backend_function_looks_like_an_autonomous_application_submitter():
    violations = _scan_for_violations()
    assert violations == [], (
        "ADR-001/ADR-002 would be violated by the file(s) above — a function named "
        "like an autonomous submitter exists in apps/api/. If this is truly intentional "
        "it needs explicit owner review, not a silent addition to ALLOWLIST."
    )


def test_the_scanner_itself_actually_detects_a_violation():
    """Not vacuously passing — confirm the pattern really matches what it's supposed to."""
    assert FORBIDDEN_NAME_PATTERN.search("def submit_application(job_id: str) -> None:\n    ...")
    assert FORBIDDEN_NAME_PATTERN.search("def auto_apply(profile, job):\n    pass")
    assert not FORBIDDEN_NAME_PATTERN.search("def get_owned_profile(profile_id: str):\n    ...")
