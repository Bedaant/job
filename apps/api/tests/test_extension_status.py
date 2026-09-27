"""The web app can tell whether the user's extension is connected.

Under ADR-015 nothing is submitted unless the extension is installed, signed in,
and running the queue — Maggie applies from the user's own browser session. The
web app had no way to know that, so a user finished onboarding believing Maggie
applies while nothing happened. The extension's own calls
(GET /extension/work-queue, POST /extension/map-fields) now stamp
`users.extension_last_seen_at`; GET /extension/status reads it back.
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import main
import models
from tests.test_submission_loop import _auth, _bind, _client, _seed


def test_connected_window_decision():
    now = datetime(2026, 9, 27, 12, 0, 0)
    assert main.extension_connected(None, now) is False
    assert main.extension_connected(now, now) is True
    assert main.extension_connected(now - main.EXTENSION_CONNECTED_WINDOW, now) is True
    assert main.extension_connected(now - main.EXTENSION_CONNECTED_WINDOW - timedelta(seconds=1), now) is False


def test_status_is_disconnected_until_the_extension_calls_in():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "ext-new@example.com")

    body = client.get("/extension/status", headers=headers).json()
    assert body == {"connected": False, "last_seen_at": None, "approved_waiting": 0}


def test_work_queue_poll_marks_the_extension_connected():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "ext-wq@example.com")
    _seed(client, headers, [
        models.ApplicationStatus.approved,
        models.ApplicationStatus.approved,
        models.ApplicationStatus.ready_for_review,
    ])

    # Reading the status is the web app, not the extension: it must not count.
    assert client.get("/extension/status", headers=headers).json()["connected"] is False

    client.get("/extension/work-queue", headers=headers)
    body = client.get("/extension/status", headers=headers).json()
    assert body["connected"] is True
    assert body["last_seen_at"] is not None
    assert body["approved_waiting"] == 2


def test_popup_check_in_with_limit_zero_takes_no_work():
    """The popup checks in on open with ?limit=0: connected, nothing handed out."""
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "ext-ping@example.com")
    _seed(client, headers, [models.ApplicationStatus.approved])

    assert client.get("/extension/work-queue?limit=0", headers=headers).json() == []
    body = client.get("/extension/status", headers=headers).json()
    assert body["connected"] is True
    assert body["approved_waiting"] == 1


def test_map_fields_marks_the_extension_connected():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "ext-mf@example.com")
    pid, _ = _seed(client, headers, [])

    with patch("main.map_form_fields", return_value=[]):
        resp = client.post(
            "/extension/map-fields", headers=headers,
            json={"profile_id": pid, "url": "https://boards.greenhouse.io/acme/jobs/1", "fields": []},
        )
    assert resp.status_code == 200
    assert client.get("/extension/status", headers=headers).json()["connected"] is True


def test_stale_check_in_reads_as_disconnected():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    headers = _auth(client, "ext-stale@example.com")
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.email == "ext-stale@example.com").first()
    user.extension_last_seen_at = datetime.utcnow() - timedelta(hours=1)
    db.commit()
    db.close()

    body = client.get("/extension/status", headers=headers).json()
    assert body["connected"] is False
    assert body["last_seen_at"] is not None


def test_status_never_counts_another_users_approved_work():
    client, SessionLocal = _client()
    _bind(client, SessionLocal)
    theirs = _auth(client, "ext-them@example.com")
    _seed(client, theirs, [models.ApplicationStatus.approved])

    mine = _auth(client, "ext-me@example.com")
    assert client.get("/extension/status", headers=mine).json()["approved_waiting"] == 0


def test_status_requires_auth():
    client, SessionLocal = _client()
    assert client.get("/extension/status").status_code == 401
