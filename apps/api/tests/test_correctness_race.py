"""Two workers at once, on real Postgres: no double send, and the cap holds.

`with_for_update()` is a no-op on SQLite, so this only means something on the Postgres
lane (TEST_DATABASE_URL). Rows are committed for real (two connections must see them),
then deleted.
"""
import threading
import time
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

import apply_email
import models
from tests.conftest import TEST_DATABASE_URL

pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="needs the Postgres lane")


def _seed(Session, n_apps):
    db = Session()
    user = models.User(email=f"race-{time.time_ns()}@example.com", password_hash="x")
    db.add(user)
    db.flush()
    profile = models.Profile(user_id=user.id, full_name="Race Test")
    db.add(profile)
    db.flush()
    fact = models.ResumeFact(profile_id=profile.id, category="experience", achievement="Built a ledger")
    db.add(fact)
    db.flush()
    app_ids, job_ids = [], []
    for i in range(n_apps):
        job = models.Job(source="race", external_id=f"{user.id}-{i}", canonical_hash=f"{user.id}-{i}",
                         title="Engineer", company="Acme", apply_url=f"mailto:hr{i}@acme.com")
        db.add(job)
        db.flush()
        a = models.Application(profile_id=profile.id, job_id=job.id, status=models.ApplicationStatus.approved,
                               tailored_resume_json={"bullets": [{"text": "Built a ledger",
                                                                  "source_fact_ids": [fact.id]}]})
        db.add(a)
        db.flush()
        app_ids.append(a.id)
        job_ids.append(job.id)
    db.commit()
    user_id = user.id
    db.close()
    return user_id, app_ids, job_ids


def _cleanup(Session, user_id, job_ids):
    db = Session()
    db.query(models.User).filter(models.User.id == user_id).delete(synchronize_session=False)
    db.query(models.Job).filter(models.Job.id.in_(job_ids)).delete(synchronize_session=False)
    db.commit()
    db.close()


def _race(Session, app_ids):
    sent, barrier, lock = [], threading.Barrier(len(app_ids)), threading.Lock()

    def sender(to, subject, body, attachments=None):
        time.sleep(0.3)  # widen the window between claim and record
        with lock:
            sent.append(to)
        return "msg"

    def worker(app_id):
        db = Session()
        try:
            barrier.wait()
            apply_email.send_application_email(db, app_id)
        finally:
            db.close()

    with patch("apply_email._sender_for", return_value=sender), patch("workers.jobs.get_queue"):
        threads = [threading.Thread(target=worker, args=(a,)) for a in app_ids]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
    return sent


def test_two_workers_on_one_application_send_once(_pg_engine):
    Session = sessionmaker(bind=_pg_engine)
    user_id, (app_id,), job_ids = _seed(Session, 1)
    try:
        assert len(_race(Session, [app_id, app_id])) == 1
    finally:
        _cleanup(Session, user_id, job_ids)


def test_two_workers_at_the_cap_send_only_one(_pg_engine, monkeypatch):
    monkeypatch.setattr(apply_email, "DAILY_CAP", 1)
    Session = sessionmaker(bind=_pg_engine)
    user_id, app_ids, job_ids = _seed(Session, 2)
    try:
        assert len(_race(Session, app_ids)) == 1
    finally:
        _cleanup(Session, user_id, job_ids)
