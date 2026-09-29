"""ADR-016 (2026-09-29 amendment): plan each job's application form once, on the
server, with the read-only Stagehand planner (tools/stagehand-harness/plan.mjs),
and store the plan for every user's fill (/extension/map-fields).

The planner is an isolated Node tool run as a subprocess, same pattern as
connectors/jobspy_connector.py. Only fields that exist on the live page are kept:
a model reading a blank or half-loaded page invents plausible fields, and a plan
key that matches nothing would only mislead the fill.

Run: python -m formplans --job-id <id>
     python -m formplans --ats greenhouse --token <board> --external-id <id> --url <url>
"""
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import uuid
from datetime import datetime
from pathlib import Path

import models
from connectors.apply_target import resolve_apply_target
from connectors.ashby import fetch_ashby_jobs
from connectors.greenhouse import fetch_greenhouse_jobs
from connectors.lever import fetch_lever_jobs
from connectors.normalize import canonical_hash
from connectors.pipeline import upsert_jobs

PLANNER = Path(__file__).resolve().parents[2] / "tools" / "stagehand-harness" / "plan.mjs"
FETCHERS = {"greenhouse": fetch_greenhouse_jobs, "lever": fetch_lever_jobs, "ashby": fetch_ashby_jobs}
# Where a plan reaches the fill. docs/harness-reports/plan-vs-extension.md (2026-09-29):
# required fields filled Greenhouse +2, Lever -4, Ashby 0. The CLI still plans all three.
ROUTED_ATS = {"greenhouse"}
_TOKEN = re.compile(r"[\w\-\[\]\.:]+")  # selector_hint may be "#id", a name, or an a11y ref


def fingerprint(keys) -> str:
    return hashlib.sha256("\n".join(sorted(keys)).encode()).hexdigest()[:16]


def _key(entry: dict) -> str:
    """The key the extension finds the element by: a radio/checkbox group by its
    shared name, anything else by id, else name."""
    if entry["type"] in ("radio", "checkbox") and entry.get("name"):
        return entry["name"]
    return entry.get("id") or entry["name"]


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _match(field: dict, live: list[dict]) -> dict | None:
    """The live entry a plan field names: an id/name in selector_hint first, else
    the label. Stagehand's hint is usually an a11y ref ("[2-53] textbox: Full name*"),
    so the label (or a radio group's question) is the common path: exact, then one
    containing the other."""
    tokens = set(_TOKEN.findall(field.get("selector_hint") or ""))
    hit = next((e for e in live if e.get("id") in tokens or e.get("name") in tokens), None)
    label = _norm(field.get("label"))
    if hit or len(label) < 3:
        return hit
    # A radio/checkbox label is an option ("LinkedIn" under "How did you hear?"): match its question only.
    labelled = [(e, "" if e.get("type") in ("radio", "checkbox") else _norm(e.get("label")), _norm(e.get("group")))
                for e in live]
    return next((e for e, l, g in labelled if label in (l, g)), None) or         next((e for e, l, _ in labelled if len(l) >= 3 and (label in l or l in label)), None)


def build_plan(report: dict) -> tuple[dict | None, str | None]:
    """plan.mjs report -> ({"fields": [{key, label, fill_from}]}, None) or (None, error).
    Values, options and `required` are never kept: the plan is shared, the page
    is the source of truth for everything but "which profile key fills this"."""
    if (report.get("guard") or {}).get("canary_blocked", 0) < 1:
        return None, "guard not verified"  # an unguarded run is never stored
    planner = report.get("planner") or {}
    if planner.get("error"):
        return None, planner["error"]

    live = [e for e in report.get("snapshot_before") or [] if e.get("visible") and e.get("type") != "file"]
    fields, seen = [], set()
    for f in (planner.get("plan") or {}).get("fields") or []:
        if f.get("fill_from") == "resume":
            continue
        entry = _match(f, [e for e in live if _key(e) not in seen])
        if entry is None:
            continue
        seen.add(_key(entry))
        fields.append({"key": _key(entry), "label": f.get("label") or "", "fill_from": f.get("fill_from") or "unknown"})
    if not fields:
        return None, "no plan field matched the page"
    return {"fields": fields}, None


def plan_job(db, job, url: str | None = None):
    """Run the guarded planner on the job's apply form and upsert its one row.
    Returns None (no row) when the URL is not an ATS the planner was measured on."""
    target = resolve_apply_target(url or job.apply_url)
    if target["ats_type"] not in FETCHERS:
        return None
    url = target["final_url"]

    job_id = job.id
    db.commit()  # release the connection: Neon drops it while the planner runs for minutes
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "plan.json"
        try:
            proc = subprocess.run(["node", str(PLANNER), url, str(out)], timeout=300, capture_output=True)
            if not out.exists():
                raise OSError(f"planner wrote no output: {(proc.stderr or b'')[-500:].decode(errors='replace')}")
            plan, error = build_plan(json.loads(out.read_text(encoding="utf-8")))
        except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
            plan, error = None, f"{type(exc).__name__}: {exc}"

    row = db.query(models.FormPlan).filter(models.FormPlan.job_id == job_id).first() or models.FormPlan(job_id=job_id)
    row.url, row.ats, row.status = url, target["ats_type"], "ok" if plan else "failed"
    row.plan, row.error, row.created_at = plan, error, datetime.utcnow()
    row.fingerprint = fingerprint(f["key"] for f in plan["fields"]) if plan else None
    db.add(row)
    db.commit()
    return row


def current_plan(db, job_id: str) -> dict | None:
    try:
        uuid.UUID(str(job_id))  # a junk id would be a Postgres cast error, not "no plan"
    except ValueError:
        return None
    row = db.query(models.FormPlan).filter(
        models.FormPlan.job_id == job_id, models.FormPlan.status == "ok", models.FormPlan.ats.in_(ROUTED_ATS)
    ).first()
    return row.plan if row else None


def find_job(db, ats: str, token: str, external_id: str):
    """The Job for an ATS posting, fetching and upserting just that one posting
    if discovery has not seen it yet."""
    job = db.query(models.Job).filter(models.Job.source == ats, models.Job.external_id == external_id).first()
    if job:
        return job
    posting = next((j for j in FETCHERS[ats](token) if j["external_id"] == external_id), None)
    if posting is None:
        return None
    posting["canonical_hash"] = canonical_hash(posting["company"], posting["title"], posting.get("location"))
    upsert_jobs(db, [posting])
    db.commit()
    # By hash, not (source, external_id): the same role from another source dedupes onto that row.
    return db.query(models.Job).filter(models.Job.canonical_hash == posting["canonical_hash"]).first()


def _main(argv=None) -> None:
    from database import session_scope

    p = argparse.ArgumentParser(prog="python -m formplans")
    p.add_argument("--job-id")
    p.add_argument("--ats", choices=sorted(FETCHERS))
    p.add_argument("--token")
    p.add_argument("--external-id")
    p.add_argument("--url")
    a = p.parse_args(argv)
    if not a.job_id and not (a.ats and a.token and a.external_id and a.url):
        p.error("give --job-id, or --ats --token --external-id --url")

    with session_scope() as db:
        if a.job_id:
            job = db.query(models.Job).filter(models.Job.id == a.job_id).first()
        else:
            job = find_job(db, a.ats, a.token, a.external_id)
        row = plan_job(db, job, a.url) if job else None
        print(json.dumps({
            "job_id": job.id if job else None,
            "status": row.status if row else "skipped",
            "fields": len(row.plan["fields"]) if row and row.plan else 0,
            "error": row.error if row else ("job not found" if job is None else "not a planned ATS"),
        }))


if __name__ == "__main__":
    _main()
