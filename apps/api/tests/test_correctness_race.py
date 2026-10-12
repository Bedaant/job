"""Two workers at once, on real Postgres: no double send, and the cap holds.

`with_for_update()` is a no-op on SQLite, so this only means something on the Postgres
lane (TEST_DATABASE_URL). Rows are committed for real (two connections must see them),
then deleted.
"""
import threading
import time
from datetime import datetime
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


def test_two_users_racing_to_one_recipient_at_cap_minus_one_claim_only_once(_pg_engine, monkeypatch):
    """RECIPIENT_DAILY_CAP spans users, so the per-user row lock cannot serialise this."""
    from core.config import get_settings
    from outreach.send import RECIPIENT_DAILY_CAP, claim_outreach
    from tests.test_outreach_send import _outreach, _profile

    monkeypatch.setattr(get_settings(), "api_base_url", "https://api.applyscout.in", raising=False)
    Session = sessionmaker(bind=_pg_engine)
    db = Session()
    tag = time.time_ns()
    users, jobs, racers = [], [], []
    for i in range(RECIPIENT_DAILY_CAP + 1):  # cap-1 already sent, then two racers
        p = _profile(db, f"r{i}-{tag}@example.com")
        if i < RECIPIENT_DAILY_CAP - 1:
            o = _outreach(db, p, status=models.OutreachStatus.sent, email=f"r-{tag}@acme.com",
                          sent_at=datetime.utcnow())
        else:
            # same address in a different case: the job external_id embeds the email, so it must differ
            o = _outreach(db, p, email=f"R-{tag}@Acme.com" if not racers else f"r-{tag}@ACME.com")
            racers.append((o.id, p.id))
        users.append(p.user_id)
        jobs.append(db.get(models.Application, o.application_id).job_id)
    db.commit()
    db.close()

    results, barrier = [], threading.Barrier(2)

    def worker(outreach_id, profile_id):
        s = Session()
        try:
            barrier.wait()
            results.append(claim_outreach(s, outreach_id, profile_id))
            time.sleep(0.3)  # hold the transaction across the other worker's count
            s.commit()
        finally:
            s.close()

    try:
        threads = [threading.Thread(target=worker, args=r) for r in racers]
        for t in threads:
            t.start()
        for t in threads:
            t.join(30)
        assert sorted(results, key=str) == [None, "recipient_cap"]
    finally:
        for u in users:  # jobs go with the last user: earlier users' applications still reference them
            _cleanup(Session, u, jobs if u == users[-1] else [])
