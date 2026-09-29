"""ADR-016 (2026-09-29 amendment): one read-only Stagehand plan per job, stored on
the server and shared by every user's fill. These pin what may be stored (only
fields that exist on the live page, never files, never from an unguarded run),
the one-row-per-job rule, and the map-fields / work-queue / sweep wiring.
"""
import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import formplans
import main
import models
import workers.jobs as jobs
from tests.test_scheduled_runs import _wire
from tests.test_submission_loop import _auth, _bind, _client, _seed

FIXTURE = (Path(__file__).resolve().parents[3] / "tools" / "stagehand-harness" / "out"
           / "lever-outreach-5becd4e1-3474-4f36-b5dd-4b2cd0eb1179.json")
GH_URL = "https://boards.greenhouse.io/acme/jobs/1"


def _entry(type_, id_="", name="", visible=True, label=""):
    return {"type": type_, "id": id_, "name": name, "visible": visible, "label": label, "group": ""}


def _report(fields, snapshot, canary=1, error=None):
    return {
        "url": GH_URL,
        "planner": {"plan": {"fields": fields}, "error": error},
        "snapshot_before": snapshot,
        "guard": {"canary_blocked": canary},
    }


SNAPSHOT = [
    _entry("text", id_="first_name", name="job_application[first_name]"),
    _entry("radio", id_="auth_yes", name="work_auth", label="Yes"),
    _entry("radio", id_="auth_no", name="work_auth", label="No"),
    _entry("file", id_="resume", name="resume"),
    _entry("text", id_="hidden_token", visible=False),
]
FIELDS = [
    {"label": "First Name", "selector_hint": "#first_name", "fill_from": "given_name",
     "required": True, "options": [], "widget": "text"},
    {"label": "Authorized?", "selector_hint": "[3-70] radiogroup: work_auth", "fill_from": "answer_bank_question",
     "required": True, "options": ["Yes", "No"], "widget": "radio"},
    {"label": "Favourite colour", "selector_hint": "#made_up", "fill_from": "unknown"},
    {"label": "Resume", "selector_hint": "#resume", "fill_from": "resume"},
    {"label": "Token", "selector_hint": "#hidden_token", "fill_from": "unknown"},
]
EXPECTED = {"fields": [
    {"key": "first_name", "label": "First Name", "fill_from": "given_name"},
    {"key": "work_auth", "label": "Authorized?", "fill_from": "answer_bank_question"},
]}


# ---- build_plan: pure -------------------------------------------------------

def test_build_plan_keeps_only_live_visible_non_file_fields():
    plan, error = formplans.build_plan(_report(FIELDS, SNAPSHOT))
    assert error is None
    # Values, options and `required` are never stored — only key/label/fill_from.
    assert plan == EXPECTED


def test_fingerprint_ignores_field_order():
    assert formplans.fingerprint(["a", "b", "c"]) == formplans.fingerprint(["c", "a", "b"])
    assert len(formplans.fingerprint(["a"])) == 16


def test_build_plan_refuses_an_unguarded_run():
    assert formplans.build_plan(_report(FIELDS, SNAPSHOT, canary=0)) == (None, "guard not verified")


def test_build_plan_surfaces_planner_error():
    assert formplans.build_plan(_report(FIELDS, SNAPSHOT, error="timeout")) == (None, "timeout")


def test_build_plan_rejects_made_up_fields_on_a_blank_page():
    assert formplans.build_plan(_report(FIELDS, [])) == (None, "no plan field matched the page")


def test_build_plan_on_real_lever_output():
    report = json.loads(FIXTURE.read_text(encoding="utf-8"))
    plan, error = formplans.build_plan(report)
    assert error is None and plan["fields"]
    live = {e["id"] for e in report["snapshot_before"]} | {e["name"] for e in report["snapshot_before"]}
    assert all(f["key"] in live for f in plan["fields"])
    assert all(f["fill_from"] != "resume" for f in plan["fields"])


# ---- plan_job: subprocess mocked -------------------------------------------

def _job(db, apply_url=GH_URL, n=1):
    job = models.Job(source="greenhouse", external_id=str(n), canonical_hash=f"h{n}",
                     title="Engineer", company="Acme", apply_url=apply_url)
    db.add(job)
    db.commit()
    return job


def _writes(report):
    def run(cmd, **kwargs):
        Path(cmd[3]).write_text(json.dumps(report), encoding="utf-8")
        return MagicMock(returncode=0, stderr=b"")
    return run


@patch("formplans.subprocess.run")
def test_plan_job_writes_one_ok_row_and_replan_replaces_it(mock_run, db_session):
    job = _job(db_session)
    mock_run.side_effect = _writes(_report(FIELDS, SNAPSHOT))

    row = formplans.plan_job(db_session, job)
    assert mock_run.call_args.args[0][:3] == ["node", str(formplans.PLANNER), GH_URL]
    assert row.status == "ok" and row.plan == EXPECTED and row.ats == "greenhouse"
    assert row.fingerprint == formplans.fingerprint(["first_name", "work_auth"])

    mock_run.side_effect = _writes(_report(FIELDS, SNAPSHOT, error="boom"))
    formplans.plan_job(db_session, job)
    rows = db_session.query(models.FormPlan).all()
    assert len(rows) == 1 and rows[0].status == "failed" and rows[0].error == "boom"
    assert formplans.current_plan(db_session, job.id) is None


@patch("formplans.subprocess.run", side_effect=subprocess.TimeoutExpired("node", 300))
def test_plan_job_timeout_is_a_failed_row(_run, db_session):
    row = formplans.plan_job(db_session, _job(db_session))
    assert row.status == "failed" and row.plan is None and "Timeout" in row.error


@patch("formplans.subprocess.run")
def test_plan_job_skips_a_non_ats_url(mock_run, db_session):
    job = _job(db_session, apply_url="https://acme.example/careers/1")
    with patch("formplans.resolve_apply_target", return_value={
        "final_url": job.apply_url, "ats_type": None, "board_token": None, "resolved": True,
    }):
        assert formplans.plan_job(db_session, job) is None
    mock_run.assert_not_called()
    assert db_session.query(models.FormPlan).count() == 0


@patch("formplans.subprocess.run")
def test_current_plan_serves_ok_row_and_tolerates_bad_ids(mock_run, db_session):
    job = _job(db_session)
    mock_run.side_effect = _writes(_report(FIELDS, SNAPSHOT))
    formplans.plan_job(db_session, job)
    assert formplans.current_plan(db_session, job.id) == EXPECTED
    assert formplans.current_plan(db_session, "not-a-uuid") is None


# ---- CLI --ats path: fetch + upsert only the matching job ------------------

@patch("formplans.plan_job", return_value=None)
@patch("connectors.pipeline.embed_texts", side_effect=RuntimeError("offline"))
def test_find_job_fetches_and_upserts_only_the_matching_posting(_embed, _plan, db_session):
    posting = {"source": "greenhouse", "external_id": "42", "title": "Engineer", "company": "Acme",
               "location": "Remote", "apply_url": GH_URL}
    other = {**posting, "external_id": "43", "title": "Designer"}
    with patch.dict(formplans.FETCHERS, {"greenhouse": lambda token: [other, posting]}):
        job = formplans.find_job(db_session, "greenhouse", "acme", "42")
    assert job.external_id == "42"
    assert db_session.query(models.Job).count() == 1


# ---- API wiring --------------------------------------------------------------

def _plan_row(SessionLocal, job_id, status="ok"):
    db = SessionLocal()
    db.add(models.FormPlan(job_id=job_id, url=GH_URL, ats="greenhouse", status=status, plan=EXPECTED))
    db.commit()
    db.close()


def _job_id(SessionLocal, application_id):
    db = SessionLocal()
    try:
        return db.get(models.Application, application_id).job_id
    finally:
        db.close()


@patch("main.map_form_fields", return_value=[])
def test_map_fields_passes_the_stored_plan(mock_map):
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "plan@example.com")
    profile_id, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])
    job_id = _job_id(SessionLocal, app_id)
    _plan_row(SessionLocal, job_id)
    body = {"profile_id": profile_id, "url": GH_URL,
            "fields": [{"field_id": "f1", "label_text": "Email", "input_type": "email"}]}

    assert client.post("/extension/map-fields", headers=headers, json={**body, "job_id": job_id}).status_code == 200
    assert mock_map.call_args.kwargs["plan"] == EXPECTED

    assert client.post("/extension/map-fields", headers=headers, json=body).status_code == 200
    assert mock_map.call_args.kwargs["plan"] is None

    assert client.post("/extension/map-fields", headers=headers, json={**body, "job_id": "junk"}).status_code == 200
    assert mock_map.call_args.kwargs["plan"] is None


def test_work_queue_items_carry_job_id():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "wqjob@example.com")
    _, (app_id,) = _seed(client, headers, [models.ApplicationStatus.approved])

    (item,) = client.get("/extension/work-queue", headers=headers).json()
    assert item["job_id"] == _job_id(SessionLocal, app_id)


# ---- sweep -------------------------------------------------------------------

@patch("workers.jobs.get_redis_connection")
@patch("workers.jobs.get_queue")
@patch("workers.jobs.session_scope")
def test_sweep_enqueues_unplanned_jobs_only(mock_scope, mock_queue, mock_redis, db_session):
    user = models.User(email="s@x.com", password_hash="x")
    db_session.add(user)
    db_session.commit()
    profile = models.Profile(user_id=user.id, persona=models.Persona.developer)
    db_session.add(profile)
    db_session.commit()
    unplanned, planned, idle = _job(db_session, n=1), _job(db_session, n=2), _job(db_session, n=3)
    for job, status in [(unplanned, models.ApplicationStatus.approved),
                        (planned, models.ApplicationStatus.ready_for_review),
                        (idle, models.ApplicationStatus.saved)]:
        db_session.add(models.Application(profile_id=profile.id, job_id=job.id, status=status))
    db_session.add(models.FormPlan(job_id=planned.id, url=GH_URL, status="failed", error="x"))
    db_session.commit()
    enqueue = _wire(db_session, mock_scope, mock_queue, mock_redis)

    assert jobs.sweep_form_plans_task() == {"enqueued": [unplanned.id]}
    call = enqueue.call_args
    assert call.args[0] is jobs.plan_form_task
    assert call.kwargs == {"job_id": f"plan-{unplanned.id}", "unique": True, "job_timeout": 600,
                           "kwargs": {"job_id": unplanned.id}}


@patch("workers.run_scheduler.get_redis_connection")
@patch("workers.run_scheduler.Scheduler")
def test_form_plan_sweep_is_scheduled_hourly(mock_scheduler_cls, _redis):
    import workers.run_scheduler as run_scheduler
    mock_scheduler_cls.return_value.get_jobs.return_value = []
    run_scheduler.start_scheduler()
    registered = {c.kwargs["func"]: c.kwargs["interval"]
                  for c in mock_scheduler_cls.return_value.schedule.call_args_list}
    assert registered[jobs.sweep_form_plans_task] == 3600
