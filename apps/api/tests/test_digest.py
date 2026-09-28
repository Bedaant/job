"""ADR-015 rail: "daily caps + a digest of what went out". The digest is read
from the events outbox + applications over one day window, per user."""
from datetime import datetime, timedelta
from unittest.mock import patch

import digest
import models
import workers.run_scheduler as run_scheduler
from tests.test_activity import _client, _user


def _seed(SessionLocal, email, *, today, yesterday):
    """One user's day: 2 sent (1 unconfirmed), 1 waiting on them, 4 per-job skips
    (3 below_score, 1 already_applied) + a summary row, 1 recruiter reply; plus
    the same kinds of rows yesterday, which must not count."""
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.email == email).one()
    profile = db.query(models.Profile).filter(models.Profile.user_id == user.id).one()
    jobs = []
    for i in range(5):
        job = models.Job(source="remotive", external_id=f"{email}-{i}", canonical_hash=f"{email}-{i}",
                         title=f"Engineer {i}", company="Acme", apply_url="https://x")
        db.add(job)
        jobs.append(job)
    db.flush()
    S = models.ApplicationStatus
    rows = [
        models.Application(profile_id=profile.id, job_id=jobs[0].id, status=S.applied, applied_at=today),
        models.Application(profile_id=profile.id, job_id=jobs[1].id, status=S.submitted_unconfirmed,
                           applied_at=today),
        models.Application(profile_id=profile.id, job_id=jobs[2].id, status=S.applied, applied_at=yesterday),
        models.Application(profile_id=profile.id, job_id=jobs[3].id, status=S.ready_for_review),
        models.Application(profile_id=profile.id, job_id=jobs[4].id, status=S.recruiter),
    ]
    db.add_all(rows)
    db.flush()

    def ev(type_, payload, at):
        db.add(models.Event(user_id=user.id, type=type_, payload=payload, created_at=at))

    for code in ["below_score", "below_score", "below_score", "already_applied"]:
        ev("campaign.skipped", {"campaign_id": "c", "job_id": jobs[0].id, "reason_code": code, "reason": "x"}, today)
    ev("campaign.skipped", {"campaign_id": "c", "reason_code": "checked", "reason": "Checked 9"}, today)
    ev("campaign.skipped", {"campaign_id": "c", "job_id": jobs[0].id, "reason_code": "daily_cap", "reason": "x"},
       yesterday)
    ev("application.status_changed", {"application_id": rows[4].id, "status": "recruiter"}, today)
    ev("application.status_changed", {"application_id": rows[4].id, "status": "submitting"}, today)
    ev("application.status_changed", {"application_id": rows[2].id, "status": "rejected"}, yesterday)
    uid = user.id
    db.commit()
    db.close()
    return uid


def _window():
    end = datetime.utcnow().replace(microsecond=0) + timedelta(minutes=1)
    start = end - timedelta(hours=12)
    return start, end, end - timedelta(hours=1), start - timedelta(hours=1)


def test_build_digest_counts_only_the_users_own_window():
    client, SessionLocal = _client()
    _user(client, "a@example.com")
    _user(client, "b@example.com")
    start, end, today, yesterday = _window()
    uid = _seed(SessionLocal, "a@example.com", today=today, yesterday=yesterday)
    _seed(SessionLocal, "b@example.com", today=today, yesterday=yesterday)  # never leaks into A

    db = SessionLocal()
    user = db.get(models.User, uid)
    d = digest.build_digest(db, user, start, end)

    assert d["sent"] == 2
    assert d["unconfirmed"] == 1
    assert d["needs_you"] == 1
    assert d["ready_to_send"] == 0
    assert d["skipped"] == 4
    assert d["top_skip_reasons"][0] == {"reason_code": "below_score", "label": "Below your minimum score",
                                        "count": 3}
    assert [r["status"] for r in d["replies"]] == ["recruiter"]
    assert d["replies"][0]["job_title"] == "Engineer 4"
    assert d["had_activity"] is True


def test_quiet_day_has_no_activity_and_text_says_so():
    client, SessionLocal = _client()
    _user(client, "q@example.com")
    db = SessionLocal()
    user = db.query(models.User).one()
    start, end, _, _ = _window()
    d = digest.build_digest(db, user, start, end)
    assert d["had_activity"] is False
    assert "Nothing went out" in digest.render_text(d)


def test_render_text_names_every_bucket():
    text = digest.render_text({
        "sent": 3, "unconfirmed": 1, "needs_you": 2, "ready_to_send": 1, "skipped": 4,
        "top_skip_reasons": [{"reason_code": "below_score", "label": "Below your minimum score", "count": 3}],
        "replies": [{"status": "interview", "job_title": "Engineer", "company": "Acme"}],
        "had_activity": True,
    })
    assert "Sent 3 applications" in text
    assert "1 couldn't be confirmed" in text
    assert "2 need you" in text
    assert "1 ready to send" in text
    assert "Skipped 4" in text and "Below your minimum score (3)" in text
    assert "Engineer at Acme: interview" in text


def test_preview_endpoint_returns_json_and_text_for_the_caller_only():
    client, SessionLocal = _client()
    headers_a, _ = _user(client, "a@example.com")
    _user(client, "b@example.com")
    _, _, today, yesterday = _window()
    _seed(SessionLocal, "b@example.com", today=today, yesterday=yesterday)

    res = client.get("/digest/preview", headers=headers_a, params={"tz": "Asia/Kolkata"})
    assert res.status_code == 200
    body = res.json()
    assert body["sent"] == 0 and body["skipped"] == 0
    assert "Nothing went out" in body["text"]
    assert client.get("/digest/preview").status_code == 401


def test_daily_task_writes_one_notification_per_active_user_and_is_idempotent():
    client, SessionLocal = _client()
    _user(client, "a@example.com")
    _user(client, "quiet@example.com")
    end = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    uid = _seed(SessionLocal, "a@example.com", today=end - timedelta(hours=2), yesterday=end - timedelta(hours=30))
    sent = []

    def sender(to, subject, body):
        sent.append((to, subject, body))
        return False  # log-only: nothing actually delivered

    with patch("digest.session_scope") as scope:
        db = SessionLocal()
        scope.return_value.__enter__.return_value = db
        scope.return_value.__exit__.return_value = False
        assert digest.daily_digest_task(sender=sender) == {"notified": 1}
        db.commit()
        assert digest.daily_digest_task(sender=sender) == {"notified": 0}
        db.commit()

    rows = SessionLocal().query(models.Notification).all()
    assert len(rows) == 1
    n = rows[0]
    assert (n.user_id, n.trigger, n.channel, n.template) == (uid, "daily_digest", "email", "daily_digest_v1")
    assert n.status == "skipped" and n.error == "no email sender configured"
    assert n.payload["sent"] == 2 and "Sent 2 applications" in n.payload["text"]
    assert [s[0] for s in sent] == ["a@example.com"]


def test_a_real_sender_marks_the_notification_sent():
    client, SessionLocal = _client()
    _user(client, "a@example.com")
    end = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    _seed(SessionLocal, "a@example.com", today=end - timedelta(hours=2), yesterday=end - timedelta(hours=30))
    with patch("digest.session_scope") as scope:
        db = SessionLocal()
        scope.return_value.__enter__.return_value = db
        scope.return_value.__exit__.return_value = False
        digest.daily_digest_task(sender=lambda *a: True)
        db.commit()
    n = SessionLocal().query(models.Notification).one()
    assert n.status == "sent" and n.sent_at is not None


@patch("workers.run_scheduler.get_redis_connection")
@patch("workers.run_scheduler.Scheduler")
def test_scheduler_registers_the_digest_daily_just_after_utc_midnight(mock_scheduler_cls, _redis):
    scheduler = mock_scheduler_cls.return_value
    scheduler.get_jobs.return_value = []

    run_scheduler.start_scheduler()

    call = next(c for c in scheduler.schedule.call_args_list if c.kwargs["func"] is digest.daily_digest_task)
    assert call.kwargs["interval"] == 24 * 60 * 60
    first = call.kwargs["scheduled_time"]
    assert first > datetime.utcnow() and (first.hour, first.minute) == (0, 5)


class _FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.calls, self.sent = host, port, [], []
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.sent.append(msg)


def _smtp_settings(**kw):
    s = dict(smtp_host="smtp.example.com", smtp_port=587, smtp_user="me@example.com",
             smtp_password="app-pass", smtp_from="Maggie <digest@example.com>")
    s.update(kw)
    return type("S", (), s)()


def test_smtp_sender_starttls_logs_in_and_sends_the_message():
    _FakeSMTP.instances = []
    with patch("digest.get_settings", return_value=_smtp_settings()), \
            patch("digest.smtplib.SMTP", _FakeSMTP):
        assert digest.smtp_sender("a@example.com", "Your digest", "Sent 2 applications.") is True
    smtp = _FakeSMTP.instances[0]
    assert (smtp.host, smtp.port) == ("smtp.example.com", 587)
    assert smtp.calls == ["starttls", ("login", "me@example.com", "app-pass")]
    msg = smtp.sent[0]
    assert msg["To"] == "a@example.com" and msg["Subject"] == "Your digest"
    assert msg["From"] == "Maggie <digest@example.com>"
    assert msg.get_content().strip() == "Sent 2 applications."


def test_smtp_sender_port_465_uses_ssl_and_from_defaults_to_user():
    _FakeSMTP.instances = []
    with patch("digest.get_settings", return_value=_smtp_settings(smtp_port=465, smtp_from=None)), \
            patch("digest.smtplib.SMTP_SSL", _FakeSMTP):
        assert digest.smtp_sender("a@example.com", "s", "b") is True
    smtp = _FakeSMTP.instances[0]
    assert "starttls" not in smtp.calls
    assert smtp.sent[0]["From"] == "me@example.com"


def test_smtp_sender_failure_returns_false_without_logging_the_password(caplog):
    class Boom(_FakeSMTP):
        def login(self, user, password):
            raise digest.smtplib.SMTPAuthenticationError(535, b"bad credentials app-pass")

    with patch("digest.get_settings", return_value=_smtp_settings()), \
            patch("digest.smtplib.SMTP", Boom):
        assert digest.smtp_sender("a@example.com", "s", "b") is False
    assert "SMTPAuthenticationError" in caplog.text and "app-pass" not in caplog.text


def _run_task(SessionLocal):
    with patch("digest.session_scope") as scope:
        db = SessionLocal()
        scope.return_value.__enter__.return_value = db
        scope.return_value.__exit__.return_value = False
        digest.daily_digest_task()
        db.commit()
    return SessionLocal().query(models.Notification).one()


def _seeded_client():
    client, SessionLocal = _client()
    _user(client, "a@example.com")
    end = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    _seed(SessionLocal, "a@example.com", today=end - timedelta(hours=2), yesterday=end - timedelta(hours=30))
    return SessionLocal


def test_scheduled_task_uses_smtp_when_host_is_set_and_records_failures():
    SessionLocal = _seeded_client()
    with patch("digest.get_settings", return_value=_smtp_settings()), \
            patch("digest.smtp_sender", return_value=False) as smtp:
        n = _run_task(SessionLocal)
    assert smtp.call_args.args[0] == "a@example.com"
    assert n.status == "failed" and n.error == "email send failed"


def test_scheduled_task_without_smtp_host_stays_log_only():
    SessionLocal = _seeded_client()
    with patch("digest.get_settings", return_value=_smtp_settings(smtp_host=None)), \
            patch("digest.smtp_sender") as smtp:
        n = _run_task(SessionLocal)
    smtp.assert_not_called()
    assert n.status == "skipped" and n.error == "no email sender configured"
