"""The ADR-014 eval golden set must exercise the path production actually uses.

`tailoring/engine.py` chooses its path on `_settings.llm_provider == "nvidia_smoke"
or not known_fact_ids`. `known_fact_ids` is built from the `id` on each fact
handed to `tailor_application`, so **a golden row whose facts have no `id`
silently routes that eval row down the unvalidated smoke path** — no
`TailoredDraft` validation, no `source_fact_ids` (min_length=1), no
KB-existence check on cited ids. The harness then reports on a code path the
API never takes for a real profile, whose `ResumeFact` rows always have a PK.

That was the state until 2026-10-04: all 30 rows lacked ids, so every row ran
the smoke path. Observed consequences on a live NIM call, before the fix:
`source_fact_ids` empty on every bullet, and the model's own citation markers
leaking into user-visible text ("...to FastAPI microservices [0]"). After adding
ids, the same two rows came back 4/4 and 6/6 bullets grounded with real ids and
no markers in the text.

This test is the guard. It is cheap and offline — it reads the CSV, it does not
call a model.
"""
import csv
import json
from pathlib import Path

import pytest

GOLDEN = Path(__file__).resolve().parents[3] / "eval" / "golden.csv"


def _rows():
    if not GOLDEN.exists():
        pytest.skip(f"eval golden set not present at {GOLDEN}")
    with GOLDEN.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_the_golden_set_is_not_empty():
    assert len(_rows()) >= 10, "ADR-014 specified a 30-row golden set"


def test_every_golden_fact_has_an_id_so_the_grounded_path_runs():
    """Without ids, `known_fact_ids` is empty and engine.py takes the smoke
    path — the harness would measure something production never runs."""
    missing = []
    for i, row in enumerate(_rows()):
        for n, fact in enumerate(json.loads(row["facts_json"])):
            if not fact.get("id"):
                missing.append(f"row {i} fact {n}")
    assert missing == [], (
        "these golden facts have no 'id', so their eval rows silently run the "
        f"unvalidated smoke path: {missing[:10]}"
    )


def test_fact_ids_are_unique_within_a_row():
    """The engine validates a cited id against the ids given for THAT call. A
    duplicate id inside one row makes a citation ambiguous."""
    for i, row in enumerate(_rows()):
        ids = [f["id"] for f in json.loads(row["facts_json"])]
        assert len(ids) == len(set(ids)), f"row {i} repeats a fact id: {ids}"


def test_every_golden_row_has_a_job_and_facts_to_tailor_from():
    for i, row in enumerate(_rows()):
        assert row["jd_title"].strip(), f"row {i} has no job title"
        assert row["jd_description"].strip(), f"row {i} has no job description"
        assert json.loads(row["facts_json"]), f"row {i} has no facts"
