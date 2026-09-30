"""Password reset (2026-09-30): the owner asked what happens if they lose their password.

POST /auth/forgot-password answers the same whether or not the email has an account
(no enumeration) and emails a one-hour link. POST /auth/reset-password sets the new
password. The token carries a fingerprint of the current password hash, so it works
once: after the reset, or any other password change, it is dead. No table needed.
"""
from unittest.mock import patch

from tests.test_campaigns import _auth, _client

PASSWORD = "correct horse battery staple"


def _login(client, email, password):
    return client.post("/auth/login", data={"username": email, "password": password})


def _link_sent(client, email):
    with patch("auth.router.send_reset_email") as send:
        resp = client.post("/auth/forgot-password", json={"email": email})
    assert resp.status_code == 202 and resp.json() == {"ok": True}
    return send.call_args.args[1] if send.called else None


def test_forgot_then_reset_changes_the_password():
    client, _ = _client()
    _auth(client, "reset@example.com")
    link = _link_sent(client, "reset@example.com")
    assert link.startswith("http://localhost:3000/reset-password?token=")
    token = link.split("token=", 1)[1]

    resp = client.post("/auth/reset-password", json={"token": token, "password": "a new long password"})
    assert resp.status_code == 200
    assert _login(client, "reset@example.com", PASSWORD).status_code == 401
    assert _login(client, "reset@example.com", "a new long password").status_code == 200


def test_unknown_email_gets_the_same_answer_and_no_email():
    client, _ = _client()
    assert _link_sent(client, "nobody@example.com") is None


def test_a_reset_link_works_once():
    client, _ = _client()
    _auth(client, "once@example.com")
    token = _link_sent(client, "once@example.com").split("token=", 1)[1]
    assert client.post("/auth/reset-password", json={"token": token, "password": "first new password"}).status_code == 200
    again = client.post("/auth/reset-password", json={"token": token, "password": "second new password"})
    assert again.status_code == 400
    assert "invalid or has expired" in again.json()["detail"]


def test_a_login_token_is_not_a_reset_token():
    client, _ = _client()
    headers = _auth(client, "jwt@example.com")
    login_token = headers["Authorization"].split(" ", 1)[1]
    assert client.post("/auth/reset-password", json={"token": login_token, "password": "hijacked password"}).status_code == 400
    assert client.post("/auth/reset-password", json={"token": "garbage", "password": "hijacked password"}).status_code == 400


def test_new_password_must_not_be_trivially_short():
    client, _ = _client()
    _auth(client, "short@example.com")
    token = _link_sent(client, "short@example.com").split("token=", 1)[1]
    assert client.post("/auth/reset-password", json={"token": token, "password": "abc"}).status_code == 422
