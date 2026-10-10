"""Architecture plan section 10: versioned form plans, a per-ATS kill switch, fill snapshots.

- A re-plan must never destroy the last good plan: a failed planner run used to overwrite an
  `ok` row with `failed`, turning a working fill back into the generic one.
- The kill switch is enforced on the server (map-fields), the one call every fill makes before
  touching the page, so an unreachable server can never mean "fill anyway".
- A snapshot records labels and sources only, never a value, and is size-capped.
"""
import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import ats_controls
import formplans
import models
from database import Base, get_db


@pytest.fixture()
def ctx(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    app = FastAPI()
    app.include_router(ats_controls.router)
    app.dependency_overrides[get_db] = lambda: db
    users = {}

    def seed(email):
        u = models.User(email=email, password_hash="x")
        db.add(u)
        db.flush()
        p = models.Profile(user_id=u.id, full_name="Asha Rao")
        db.add(p)
        db.flush()
        users[email] = (u, p)
        return u, p

    def act_as(email):
        app.dependency_overrides[ats_controls.current_user] = lambda: users[email][0]

    monkeypatch.setenv("OWNER_EMAILS", "owner@x.com")
    try:
        yield db, seed, act_as, TestClient(app)
    finally:
        db.close()
        engine.dispose()


def _job(db, n="1", url="https://boards.greenhouse.io/acme/jobs/1"):
    job = models.Job(source="greenhouse", external_id=n, canonical_hash=f"h{n}", title="PM",
                     company="Acme", apply_url=url)
    db.add(job)
    db.flush()
    return job


def _plan(*keys):
    return {"fields": [{"key": k, "label": k, "fill_from": "email"} for k in keys]}


def _planner(monkeypatch, plan, error=None):
    monkeypatch.setattr(formplans, "resolve_apply_target",
                        lambda url: {"ats_type": "greenhouse", "final_url": url})
    monkeypatch.setattr(formplans.subprocess, "run",
                        lambda *a, **k: type("P", (), {"stdout": b"{}\n", "stderr": b""})())
    monkeypatch.setattr(formplans, "build_plan", lambda report: (plan, error))


# ---------- 1. versioned form plans ----------

def test_each_good_plan_is_a_new_version_and_history_is_kept(ctx, monkeypatch):
    db, *_ = ctx
    job = _job(db)
    _planner(monkeypatch, _plan("email"))
    formplans.plan_job(db, job)
    _planner(monkeypatch, _plan("email", "phone"))
    row = formplans.plan_job(db, job)
    assert row.version == 2
    versions = db.query(models.FormPlanVersion).filter_by(form_plan_id=row.id).order_by(models.FormPlanVersion.version).all()
    assert [v.version for v in versions] == [1, 2]
    assert versions[0].plan == _plan("email")


def test_a_failed_replan_never_overwrites_the_last_good_plan(ctx, monkeypatch):
    db, *_ = ctx
    job = _job(db)
    _planner(monkeypatch, _plan("email"))
    formplans.plan_job(db, job)
    _planner(monkeypatch, None, "guard not verified")
    row = formplans.plan_job(db, job)
    assert (row.status, row.version, row.plan) == ("ok", 1, _plan("email"))
    assert row.error == "guard not verified"
    assert formplans.current_plan(db, job.id) == _plan("email")


def test_owner_can_roll_back_to_a_previous_version(ctx, monkeypatch):
    db, seed, act_as, client = ctx
    seed("owner@x.com")
    act_as("owner@x.com")
    job = _job(db)
    for plan in (_plan("email"), _plan("phone")):
        _planner(monkeypatch, plan)
        formplans.plan_job(db, job)
    r = client.post(f"/admin/form-plans/{job.id}/rollback", json={"version": 1})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 1
    assert formplans.current_plan(db, job.id) == _plan("email")
    assert client.post(f"/admin/form-plans/{job.id}/rollback", json={"version": 9}).status_code == 404


def test_rollback_and_switch_are_owner_only(ctx):
    db, seed, act_as, client = ctx
    seed("friend@x.com")
    act_as("friend@x.com")
    job = _job(db)
    assert client.post(f"/admin/form-plans/{job.id}/rollback", json={"version": 1}).status_code == 403
    assert client.put("/admin/ats-controls/workday", json={"fill_enabled": False}).status_code == 403


def test_no_owner_configured_means_nobody_is_owner(ctx, monkeypatch):
    db, seed, act_as, client = ctx
    monkeypatch.delenv("OWNER_EMAILS")
    seed("owner@x.com")
    act_as("owner@x.com")
    assert client.put("/admin/ats-controls/workday", json={"fill_enabled": False}).status_code == 403


# ---------- 2. per-ATS kill switch ----------

def test_switch_off_pauses_that_ats_only(ctx):
    db, seed, act_as, client = ctx
    seed("owner@x.com")
    act_as("owner@x.com")
    assert client.put("/admin/ats-controls/Workday", json={"fill_enabled": False}).status_code == 200
    assert client.get("/admin/ats-controls").json() == {"workday": False}
    with pytest.raises(HTTPException) as exc:
        ats_controls.ensure_fill_enabled(db, "workday", "https://x.wd5.myworkdayjobs.com/a")
    assert exc.value.status_code == 423
    assert "Filling paused for workday" in exc.value.detail
    ats_controls.ensure_fill_enabled(db, "greenhouse", "https://boards.greenhouse.io/acme/jobs/1")


def test_switch_applies_when_the_client_sends_no_ats_type(ctx):
    """The popup's manual fill sends ats_type null; the page URL still identifies the ATS."""
    db, *_ = ctx
    db.add(models.AtsControl(ats="workday", fill_enabled=False))
    db.flush()
    with pytest.raises(HTTPException):
        ats_controls.ensure_fill_enabled(db, None, "https://acme.wd5.myworkdayjobs.com/en-US/jobs/job/1")
    ats_controls.ensure_fill_enabled(db, None, "https://example.com/careers")


def test_switch_back_on_resumes(ctx):
    db, seed, act_as, client = ctx
    seed("owner@x.com")
    act_as("owner@x.com")
    client.put("/admin/ats-controls/lever", json={"fill_enabled": False})
    client.put("/admin/ats-controls/lever", json={"fill_enabled": True})
    ats_controls.ensure_fill_enabled(db, "lever", None)


def test_paused_ats_list_for_the_work_queue(ctx):
    db, *_ = ctx
    db.add_all([models.AtsControl(ats="workday", fill_enabled=False), models.AtsControl(ats="lever", fill_enabled=True)])
    db.flush()
    assert ats_controls.paused_ats(db) == {"workday"}


# ---------- 3. fill snapshots ----------

def _application(db, profile):
    job = _job(db, n=profile.id)
    app_row = models.Application(profile_id=profile.id, job_id=job.id, status=models.ApplicationStatus.approved)
    db.add(app_row)
    db.flush()
    return app_row, job


def _snapshot(app_id, n=2):
    return {"application_id": app_id, "page": 1, "fields": [
        {"label": f"Field {i}", "source": "email", "status": "filled", "required": True} for i in range(n)
    ]}


def test_snapshot_is_stored_against_the_application_with_the_active_plan_version(ctx, monkeypatch):
    db, seed, act_as, client = ctx
    _, profile = seed("a@x.com")
    act_as("a@x.com")
    app_row, job = _application(db, profile)
    _planner(monkeypatch, _plan("email"))
    formplans.plan_job(db, job)
    r = client.post("/extension/fill-snapshots", json=_snapshot(app_row.id))
    assert r.status_code == 201, r.text
    snap = db.query(models.FillSnapshot).one()
    assert snap.application_id == app_row.id and snap.plan_version == 1
    assert snap.record["fields"][0] == {"label": "Field 0", "source": "email", "status": "filled", "required": True}


def test_snapshot_for_another_users_application_is_404(ctx):
    db, seed, act_as, client = ctx
    _, owner_profile = seed("a@x.com")
    seed("b@x.com")
    app_row, _ = _application(db, owner_profile)
    act_as("b@x.com")
    assert client.post("/extension/fill-snapshots", json=_snapshot(app_row.id)).status_code == 404
    assert db.query(models.FillSnapshot).count() == 0


def test_snapshot_is_size_capped_and_carries_no_values(ctx):
    db, seed, act_as, client = ctx
    _, profile = seed("a@x.com")
    act_as("a@x.com")
    app_row, _ = _application(db, profile)
    assert client.post("/extension/fill-snapshots", json=_snapshot(app_row.id, n=301)).status_code == 422
    too_long = _snapshot(app_row.id)
    too_long["fields"][0]["label"] = "x" * 1000
    assert client.post("/extension/fill-snapshots", json=too_long).status_code == 422
    with_value = _snapshot(app_row.id)
    with_value["fields"][0]["value"] = "asha@example.com"
    assert client.post("/extension/fill-snapshots", json=with_value).status_code == 422


def test_snapshot_payload_is_small_enough_to_store_every_fill():
    record = _snapshot("00000000-0000-0000-0000-000000000000", n=300)
    for f in record["fields"]:
        f["label"] = "x" * 200
    assert len(json.dumps(record)) < 100_000
