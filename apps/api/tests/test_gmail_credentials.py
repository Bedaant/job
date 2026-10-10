"""REACH-A — the Gmail OAuth grant and the sender it produces.

Every Google HTTP call is mocked: there is no OAuth client yet (the owner creates it in
the Cloud console), so what is testable now is our side of the contract — that we ask
for the right scope, refuse a grant that is narrower, encrypt what we store, never
return or log the token, and revoke at Google rather than only in our own table.

The one property worth stating as a property rather than a case:
**no code path returns the refresh token or its ciphertext to a caller that could put it
in a response.** `test_gmail_token_never_returned_by_any_endpoint` walks the router's
routes and checks it, because the realistic regression is a one-line response-model
change by someone who has not read ADR-003.
"""
import logging
from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import crypto
import models
from core.config import get_settings
from database import Base, get_db
from outreach import gmail

REFRESH = "1//0g-A-REAL-LOOKING-REFRESH-TOKEN"
SEND = models.GMAIL_SEND_SCOPE


@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    """A working key and OAuth client for every test here. Without the key, every store
    path raises by design — that case is covered in test_crypto.py."""
    get_settings.cache_clear()
    monkeypatch.setenv("ENCRYPTION_KEY", crypto.generate_key())
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "client-secret")
    crypto.reset_cipher_cache()
    yield
    get_settings.cache_clear()
    crypto.reset_cipher_cache()


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user(db, email="a@example.com"):
    u = models.User(email=email, password_hash="x")
    db.add(u)
    db.commit()
    return u


def _token_response(scope=SEND, refresh_token=REFRESH, email="me@gmail.com"):
    """What Google's token endpoint returns. `id_token` carries the address, which is why
    `openid email` is requested alongside the send scope."""
    from jose import jwt
    id_token = jwt.encode({"email": email}, "irrelevant", algorithm="HS256")
    body = {"access_token": "ya29.access", "expires_in": 3599, "scope": scope,
            "token_type": "Bearer", "id_token": id_token}
    if refresh_token is not None:
        body["refresh_token"] = refresh_token
    return body


class _Resp:
    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text

    def json(self):
        return self._json


# ---------- the consent URL ----------

def test_authorize_url_requests_only_the_send_scope(db):
    """Parsed rather than substring-matched: query params are percent-encoded, so `SEND`
    is never a literal substring of the URL. Parsing also makes this test assert what
    its name claims — that the scope is EXACTLY the send scope, not merely that it is
    among them. `gmail.compose` would also work for drafting and grants sending too;
    REACH-A chose `gmail.send` because it cannot read mail or list drafts."""
    from urllib.parse import parse_qs, urlparse

    url = gmail.authorize_url(_user(db).id)
    scopes = parse_qs(urlparse(url).query)["scope"][0].split()

    # `openid` and `email` are also requested, deliberately: the connected address comes
    # from the id_token, and it is what the settings page shows the user so they can see
    # WHICH account is linked before revoking. Neither is a restricted scope and neither
    # grants mailbox access.
    assert [s for s in scopes if "gmail" in s] == [SEND], (
        "exactly one Gmail scope, and it is send-only"
    )
    assert set(scopes) <= {SEND, "openid", "email"}, "no scope beyond send plus identity"


def test_authorize_url_forces_a_refresh_token(db):
    """Without `access_type=offline` and `prompt=consent`, a user who has granted before
    gets a response with no refresh token — a credential that dies in an hour."""
    url = gmail.authorize_url(_user(db).id)
    assert "access_type=offline" in url
    assert "prompt=consent" in url


def test_authorize_state_round_trips_the_user_and_rejects_tampering(db):
    u = _user(db)
    state = gmail._state_for(u.id)
    assert gmail._user_from_state(state) == u.id
    with pytest.raises(ValueError):
        gmail._user_from_state(state[:-3] + "xxx")


def test_authorize_url_without_a_client_is_a_clear_error(db, monkeypatch):
    """Isolated from Settings, not just from `os.environ`.

    `delenv` alone was enough only while no OAuth client existed. Once a real
    `GOOGLE_CLIENT_ID` landed in `apps/api/.env`, pydantic-settings kept supplying it and
    this test started failing — the same trap the Apify token sprang. A test asserting
    "unconfigured" has to blank the `.env` source too, or it only passes on machines where
    the thing genuinely is not set up.
    """
    get_settings.cache_clear()
    monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
    monkeypatch.setattr(get_settings(), "google_client_id", None, raising=False)
    with pytest.raises(gmail.GmailNotConfigured):
        gmail.authorize_url(_user(db).id)
    get_settings.cache_clear()


# ---------- the callback ----------

def test_callback_stores_an_encrypted_token_and_the_granted_scopes(db):
    u = _user(db)
    with patch("outreach.gmail.httpx.post", return_value=_Resp(json_body=_token_response())):
        cred = gmail.handle_callback(db, gmail._state_for(u.id), "auth-code")
    assert cred.scopes == [SEND]
    assert cred.email_address == "me@gmail.com"
    assert cred.is_usable is True


def test_token_is_encrypted_at_rest(db):
    """The raw column must not contain the token. This is the whole point of crypto.py."""
    u = _user(db)
    with patch("outreach.gmail.httpx.post", return_value=_Resp(json_body=_token_response())):
        gmail.handle_callback(db, gmail._state_for(u.id), "auth-code")
    stored = db.execute(
        models.GmailCredential.__table__.select()
    ).mappings().one()["refresh_token_encrypted"]
    assert REFRESH not in stored
    assert crypto.decrypt(stored) == REFRESH


def test_partial_scope_grant_is_marked_unusable(db):
    """Google permits narrowing a grant. Detected now, not at send time — otherwise it
    surfaces as a 500 after the user has already approved an email."""
    u = _user(db)
    narrowed = _token_response(scope="openid email")
    with patch("outreach.gmail.httpx.post", return_value=_Resp(json_body=narrowed)):
        cred = gmail.handle_callback(db, gmail._state_for(u.id), "auth-code")
    assert cred.is_usable is False
    assert cred.missing_scopes == [SEND]


def test_a_response_with_no_refresh_token_is_a_hard_failure(db):
    """Storing an access-token-only grant would look like success and stop working in an
    hour, with no way to recover without the user re-consenting."""
    u = _user(db)
    with patch("outreach.gmail.httpx.post",
               return_value=_Resp(json_body=_token_response(refresh_token=None))):
        with pytest.raises(gmail.GmailConnectFailed, match="refresh token"):
            gmail.handle_callback(db, gmail._state_for(u.id), "auth-code")
    assert db.query(models.GmailCredential).count() == 0, "nothing half-stored"


def test_a_denied_consent_is_not_stored(db):
    u = _user(db)
    with patch("outreach.gmail.httpx.post",
               return_value=_Resp(status_code=400, json_body={"error": "access_denied"})):
        with pytest.raises(gmail.GmailConnectFailed):
            gmail.handle_callback(db, gmail._state_for(u.id), "auth-code")
    assert db.query(models.GmailCredential).count() == 0


def test_reconnecting_replaces_the_existing_grant(db):
    """`user_id` is unique, so a second connect must update rather than raise."""
    u = _user(db)
    with patch("outreach.gmail.httpx.post", return_value=_Resp(json_body=_token_response())):
        gmail.handle_callback(db, gmail._state_for(u.id), "code-1")
    with patch("outreach.gmail.httpx.post",
               return_value=_Resp(json_body=_token_response(refresh_token="1//0g-SECOND"))):
        cred = gmail.handle_callback(db, gmail._state_for(u.id), "code-2")
    assert db.query(models.GmailCredential).count() == 1
    assert crypto.decrypt(cred.refresh_token_encrypted) == "1//0g-SECOND"
    assert cred.revoked_at is None, "reconnecting clears a previous revocation"


# ---------- revoke ----------

def test_revoke_calls_google_then_marks_revoked(db):
    """Clearing our row alone would leave a live grant the user believes is gone."""
    u = _user(db)
    with patch("outreach.gmail.httpx.post", return_value=_Resp(json_body=_token_response())):
        gmail.handle_callback(db, gmail._state_for(u.id), "auth-code")
    with patch("outreach.gmail.httpx.post", return_value=_Resp()) as posted:
        assert gmail.revoke(db, u.id) is True
    assert gmail.REVOKE_URL in posted.call_args[0][0]
    cred = db.query(models.GmailCredential).one()
    assert cred.revoked_at is not None
    assert cred.is_usable is False


def test_revoke_still_marks_revoked_when_google_is_unreachable(db):
    """A network failure must not leave the user unable to disconnect. We record the
    local revocation; the grant at Google is then stale but unusable by us."""
    u = _user(db)
    with patch("outreach.gmail.httpx.post", return_value=_Resp(json_body=_token_response())):
        gmail.handle_callback(db, gmail._state_for(u.id), "auth-code")
    with patch("outreach.gmail.httpx.post", side_effect=RuntimeError("network down")):
        assert gmail.revoke(db, u.id) is False
    assert db.query(models.GmailCredential).one().revoked_at is not None


# ---------- the sender ----------

def test_sender_sends_and_returns_the_message_id(db):
    u = _user(db)
    with patch("outreach.gmail.httpx.post", return_value=_Resp(json_body=_token_response())):
        gmail.handle_callback(db, gmail._state_for(u.id), "auth-code")

    calls = []

    def fake_post(url, **kw):
        calls.append((url, kw))
        if gmail.TOKEN_URL in url:
            return _Resp(json_body={"access_token": "ya29.fresh", "expires_in": 3599})
        return _Resp(json_body={"id": "18ff00112233", "threadId": "t1"})

    with patch("outreach.gmail.httpx.post", side_effect=fake_post):
        send = gmail.gmail_sender(db, u.id)
        assert send("x@acme.com", "Subject", "Body text") == "18ff00112233"
    assert any(gmail.SEND_URL in url for url, _ in calls)


def test_sender_refuses_an_unusable_grant(db):
    """A narrowed grant must fail before any mail is attempted."""
    u = _user(db)
    with patch("outreach.gmail.httpx.post",
               return_value=_Resp(json_body=_token_response(scope="openid email"))):
        gmail.handle_callback(db, gmail._state_for(u.id), "auth-code")
    with pytest.raises(gmail.GmailNotConnected):
        gmail.gmail_sender(db, u.id)


def test_sender_refuses_when_there_is_no_credential(db):
    with pytest.raises(gmail.GmailNotConnected):
        gmail.gmail_sender(db, _user(db).id)


def test_an_invalid_grant_revokes_and_notifies_once(db):
    """User revoked at Google, or changed their password. ADR-003's rule: set revoked_at,
    tell the user to reconnect, and stop — never retry-loop on an invalid grant."""
    u = _user(db)
    with patch("outreach.gmail.httpx.post", return_value=_Resp(json_body=_token_response())):
        gmail.handle_callback(db, gmail._state_for(u.id), "auth-code")

    bad = _Resp(status_code=400, json_body={"error": "invalid_grant"}, text="invalid_grant")
    with patch("outreach.gmail.httpx.post", return_value=bad):
        send = gmail.gmail_sender(db, u.id)
        with pytest.raises(gmail.GmailReauthRequired):
            send("x@acme.com", "S", "B")

    assert db.query(models.GmailCredential).one().revoked_at is not None
    notes = db.query(models.Notification).filter_by(user_id=u.id).all()
    assert len(notes) == 1 and notes[0].trigger == "gmail_reauth_required"


def test_the_sender_matches_the_digest_contract(db):
    """`outreach.send.send_outreach` calls `sender(to, subject, body)` and treats a
    truthy return as delivered. The signature is the integration point."""
    import inspect
    u = _user(db)
    with patch("outreach.gmail.httpx.post", return_value=_Resp(json_body=_token_response())):
        gmail.handle_callback(db, gmail._state_for(u.id), "auth-code")
    send = gmail.gmail_sender(db, u.id)
    params = inspect.signature(send).parameters
    assert list(params)[:3] == ["to", "subject", "body"]
    # apply-by-email added `attachments`; it must stay optional for every 3-arg caller.
    assert all(p.default is not inspect.Parameter.empty for p in list(params.values())[3:])


# ---------- the secret never escapes ----------

def test_gmail_token_never_returned_by_any_endpoint(db):
    """ADR-003: "never returned by any endpoint". Walks the Gmail router's routes and
    asserts no response body contains the token or its ciphertext."""
    app = FastAPI()
    app.include_router(gmail.router)

    u = _user(db)
    with patch("outreach.gmail.httpx.post", return_value=_Resp(json_body=_token_response())):
        cred = gmail.handle_callback(db, gmail._state_for(u.id), "auth-code")
    ciphertext = cred.refresh_token_encrypted

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[gmail.current_user_id] = lambda: u.id
    client = TestClient(app)

    checked = 0
    for route in app.routes:
        path, methods = getattr(route, "path", ""), getattr(route, "methods", set())
        if "{" in path:
            continue
        for method in methods & {"GET", "DELETE", "POST"}:
            with patch("outreach.gmail.httpx.post", return_value=_Resp()):
                body = client.request(method, path).text
            assert REFRESH not in body, f"{method} {path} leaked the refresh token"
            assert ciphertext not in body, f"{method} {path} leaked the ciphertext"
            checked += 1
    assert checked, "no routes were exercised — the guard would be vacuous"


def test_status_reports_connection_without_the_secret(db):
    u = _user(db)
    with patch("outreach.gmail.httpx.post", return_value=_Resp(json_body=_token_response())):
        gmail.handle_callback(db, gmail._state_for(u.id), "auth-code")
    status = gmail.status(db, u.id)
    assert status["connected"] is True
    assert status["email_address"] == "me@gmail.com"
    assert not any(REFRESH in str(v) for v in status.values())
    assert "refresh_token_encrypted" not in status


def test_token_is_never_logged(db, caplog):
    """Across connect, send and failure. `digest.smtp_sender` sets the precedent: log
    the error type, never the secret."""
    u = _user(db)
    with caplog.at_level(logging.DEBUG):
        with patch("outreach.gmail.httpx.post", return_value=_Resp(json_body=_token_response())):
            gmail.handle_callback(db, gmail._state_for(u.id), "auth-code")
        bad = _Resp(status_code=400, json_body={"error": "invalid_grant"}, text="invalid_grant")
        with patch("outreach.gmail.httpx.post", return_value=bad):
            with pytest.raises(gmail.GmailReauthRequired):
                gmail.gmail_sender(db, u.id)("x@acme.com", "S", "B")
    assert REFRESH not in caplog.text
    assert "client-secret" not in caplog.text


def test_the_redirect_uri_points_at_a_mounted_route():
    """Google requires an EXACT match on the redirect URI, and a wrong one fails only at
    the moment a real user tries to connect — after the console entry is already typed.

    This caught a real break: `_redirect_uri` pointed at `web_base_url` +
    `/settings/gmail/callback`, a Next.js page that was never built, while
    `/gmail/callback` sat mounted and tested one port over. Google would have redirected
    to a 404 and the authorization code would never have reached the API. Nothing else in
    the suite noticed, because every other test calls `handle_callback` directly.
    """
    from urllib.parse import urlparse

    from main import app
    from outreach.gmail import _redirect_uri

    path = urlparse(_redirect_uri()).path
    assert path in app.openapi()["paths"], (
        f"the OAuth redirect points at {path}, which is not a mounted route — Google "
        "would send the user to a 404 and the code would never arrive"
    )


def test_the_authorize_response_names_the_uri_that_must_be_registered(db):
    """DEPLOY-A.5. `_redirect_uri` is built from `api_base_url`, so it CHANGES on deploy —
    and Google requires an exact match, failing with `redirect_uri_mismatch` only when a
    real user first tries to connect, long after the console entry was typed.

    Returning it alongside the consent URL makes the mismatch self-diagnosing: the
    operator can read the exact string to paste into the OAuth client rather than
    reconstructing it from config.
    """
    from outreach import gmail as g

    out = g.gmail_authorize(user_id=_user(db).id)
    assert out["redirect_uri"] == g._redirect_uri()
    assert out["authorize_url"].startswith("https://accounts.google.com/")
