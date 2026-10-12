"""NEXT-WORK-PLAN P0 #3 and P1 #12: auth hardening.

API routes take only access tokens; the Gmail OAuth callback only completes in the
browser that started it; the app refuses to boot on a weak JWT secret.
"""
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import ValidationError

import crypto
from core.config import Settings, get_settings
from core.security import create_reset_token
from outreach import gmail
from tests.test_campaigns import _auth, _client
from tests.test_gmail_credentials import _Resp, _token_response


# ---------- only access tokens authenticate ----------

def test_a_password_reset_token_is_not_an_api_token():
    client, Session = _client()
    _auth(client, "typ@example.com")
    with Session() as db:
        import models
        user = db.query(models.User).filter_by(email="typ@example.com").one()
        reset = create_reset_token(user.id, user.password_hash)
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {reset}"}).status_code == 401


def test_an_oauth_state_token_is_not_an_api_token():
    client, Session = _client()
    headers = _auth(client, "state@example.com")
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    state = gmail._state_for(user_id)
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {state}"}).status_code == 401


def test_a_login_token_still_works():
    client, _ = _client()
    assert client.get("/auth/me", headers=_auth(client, "ok@example.com")).status_code == 200


# ---------- weak JWT secret fails boot ----------

_BASE = dict(database_url="sqlite://", anthropic_api_key="x")


@pytest.mark.parametrize("secret", [
    "short",
    "x" * 31,
    "change-me-to-a-random-64-char-string-in-every-real-environment",  # .env.example
    "ci-placeholder-not-a-real-secret",  # ci.yml
])
def test_boot_refuses_a_weak_jwt_secret(secret):
    with pytest.raises(ValidationError):
        Settings(**_BASE, jwt_secret=secret)


def test_boot_accepts_a_strong_jwt_secret():
    assert Settings(**_BASE, jwt_secret="k3Jx9Qm2Vb7Lr5Tz8Wc1Nh4Pf6Sd0GaY").jwt_secret


# ---------- Gmail OAuth state is bound to the starting browser ----------

@pytest.fixture()
def gmail_env(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("ENCRYPTION_KEY", crypto.generate_key())
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    crypto.reset_cipher_cache()
    yield monkeypatch
    get_settings.cache_clear()
    crypto.reset_cipher_cache()


def _start(client, email):
    resp = client.get("/gmail/authorize", headers=_auth(client, email))
    assert resp.status_code == 200
    state = parse_qs(urlparse(resp.json()["authorize_url"]).query)["state"][0]
    return resp, state


def _callback(client, state):
    with patch("outreach.gmail.httpx.post", return_value=_Resp(json_body=_token_response())):
        return client.get("/gmail/callback", params={"state": state, "code": "auth-code"})


def test_authorize_sets_a_short_lived_httponly_lax_nonce_cookie(gmail_env):
    client, _ = _client()
    resp, _ = _start(client, "cookie@example.com")
    cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "max-age=" in cookie
    assert "secure" not in cookie  # localhost dev has no TLS


def test_the_nonce_cookie_is_secure_off_localhost(gmail_env):
    gmail_env.setenv("API_BASE_URL", "https://api.example.com")
    client, _ = _client()
    resp, _ = _start(client, "secure@example.com")
    assert "secure" in resp.headers["set-cookie"].lower()


def test_callback_in_the_starting_browser_connects(gmail_env):
    client, _ = _client()
    _, state = _start(client, "same@example.com")
    resp = _callback(client, state)
    assert resp.status_code == 200 and resp.json()["connected"] is True


def test_callback_without_the_cookie_is_refused(gmail_env):
    client, _ = _client()
    _, state = _start(client, "nocookie@example.com")
    client.cookies.clear()
    resp = _callback(client, state)
    assert resp.status_code == 400
    assert "connected" not in resp.json()


def test_callback_with_another_browsers_cookie_is_refused(gmail_env):
    client, _ = _client()
    _, victim_state = _start(client, "victim@example.com")
    _start(client, "attacker@example.com")  # overwrites the cookie with a different nonce
    assert _callback(client, victim_state).status_code == 400
