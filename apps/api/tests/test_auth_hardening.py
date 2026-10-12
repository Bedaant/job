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


# ---------- P1 #12: rate limits, password minimum, case-insensitive email ----------

class _FakeRedis:
    """Just the two commands the limiter uses; `no_real_redis` blocks the real one."""
    def __init__(self):
        self.data = {}

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.data:
            return None
        self.data[key] = int(value)
        return True

    def incr(self, key):
        self.data[key] = self.data.get(key, 0) + 1
        return self.data[key]


@pytest.fixture()
def fake_redis():
    r = _FakeRedis()
    with patch("auth.router._redis", return_value=r):
        yield r


def _login(client, email, password="correct horse battery staple"):
    return client.post("/auth/login", data={"username": email, "password": password})


def test_login_is_rate_limited_per_email(fake_redis):
    from auth.router import EMAIL_LIMIT
    client, _ = _client()
    _auth(client, "brute@example.com")  # one successful login already counted
    codes = [_login(client, "brute@example.com", "wrong guess").status_code for _ in range(EMAIL_LIMIT)]
    assert codes[:EMAIL_LIMIT - 1] == [401] * (EMAIL_LIMIT - 1) and codes[-1] == 429
    blocked = _login(client, "BRUTE@example.com")  # right password, other casing: still blocked
    assert blocked.status_code == 429 and "retry-after" in blocked.headers


def test_signup_is_rate_limited_per_ip(fake_redis):
    from auth.router import IP_LIMIT
    client, _ = _client()
    codes = [client.post("/auth/signup", json={"email": f"s{i}@example.com", "password": "long enough pw"}).status_code
             for i in range(IP_LIMIT + 1)]
    assert codes[:IP_LIMIT] == [201] * IP_LIMIT and codes[-1] == 429


def test_password_reset_endpoints_are_rate_limited(fake_redis):
    from auth.router import EMAIL_LIMIT, IP_LIMIT
    client, _ = _client()
    with patch("auth.router.send_reset_email"):
        codes = [client.post("/auth/forgot-password", json={"email": "r@example.com"}).status_code
                 for _ in range(EMAIL_LIMIT + 1)]
    assert codes[-1] == 429
    codes = [client.post("/auth/reset-password", json={"token": "garbage", "password": "long enough pw"}).status_code
             for _ in range(IP_LIMIT + 1)]
    assert codes[-1] == 429


def test_auth_still_works_when_redis_is_down():
    # The autouse no_real_redis guard makes every Redis call raise: fail open, like providers/guard.py.
    client, _ = _client()
    assert client.get("/auth/me", headers=_auth(client, "noredis@example.com")).status_code == 200


def test_signup_password_must_be_at_least_8_characters():
    client, _ = _client()
    assert client.post("/auth/signup", json={"email": "p@example.com", "password": "1234567"}).status_code == 422
    assert client.post("/auth/signup", json={"email": "p@example.com", "password": "12345678"}).status_code == 201


def test_email_is_case_insensitive():
    client, _ = _client()
    created = client.post("/auth/signup", json={"email": "Foo@X.com", "password": "correct horse battery staple"})
    assert created.status_code == 201 and created.json()["email"] == "foo@x.com"
    assert client.post("/auth/signup", json={"email": "foo@x.com", "password": "another long pw"}).status_code == 409
    assert _login(client, "foo@x.com").status_code == 200
    assert _login(client, "FOO@X.COM").status_code == 200
    with patch("auth.router.send_reset_email") as send:
        client.post("/auth/forgot-password", json={"email": "Foo@X.Com"})
    assert send.called


def test_an_existing_mixed_case_row_still_matches():
    import models
    from core.security import hash_password
    client, Session = _client()
    with Session() as db:
        db.add(models.User(email="Old@Example.com", password_hash=hash_password("correct horse battery staple")))
        db.commit()
    assert _login(client, "old@example.com").status_code == 200
    assert client.post("/auth/signup", json={"email": "old@example.com", "password": "another long pw"}).status_code == 409
