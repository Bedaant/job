"""REACH-A — the Gmail OAuth grant, and the sender it produces (ADR-003).

Outreach sends from the user's own Gmail rather than a platform domain, because a
referral ask from a real personal address lands and the same text from
`noreply@ourdomain.com` does not. This module holds the grant and hands
`outreach.send.send_outreach` a `sender(to, subject, body)` callable, matching the
contract `digest.py` already established.

SCOPE. `gmail.send` only — it can send and nothing else: it cannot read the mailbox,
list drafts, or touch anything already there. `gmail.compose`, which an earlier design
would have needed to write drafts, grants draft management PLUS sending, so sending from
the dashboard is the LOWER-privilege design. `openid email` is requested alongside it
purely to learn which address was connected, so the UI can show it; neither is a
sensitive scope and neither grants mailbox access.

Google's consent screen stays in **Testing** mode: 100 explicitly-listed test users, no
verification review. Past ~80 users that ceiling needs revisiting, and it is worth
knowing in advance because hitting it presents as "OAuth suddenly broke" rather than
"we outgrew Testing mode".

THE SECRET. ADR-003: "never logged, never returned by any endpoint". Nothing here
returns the refresh token or its ciphertext — `status()` is the whole public read
surface and is a fixed, hand-built dict. Errors log the exception TYPE only, because a
provider's reply body can echo what was sent.
"""
import base64
import logging
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from jose import JWTError, jwt
from sqlalchemy.orm import Session

import crypto
import models
from core.config import get_settings
from core.deps import get_current_user
from database import get_db

logger = logging.getLogger(__name__)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# `openid email` only identifies the account; `gmail.send` is the one that does work.
SCOPES = ("openid", "email", models.GMAIL_SEND_SCOPE)
TIMEOUT = 20
_STATE_PURPOSE = "gmail_oauth"
_STATE_MINUTES = 15


class GmailNotConfigured(RuntimeError):
    """No OAuth client. The owner creates it in the Cloud console; it cannot come from
    code, so this is a configuration error rather than a user-facing failure."""


class GmailConnectFailed(RuntimeError):
    """The consent round trip did not produce a storable credential."""


class GmailNotConnected(RuntimeError):
    """No live, sufficiently-scoped grant for this user. Raised BEFORE any send is
    attempted, so a narrowed grant never surfaces as a mid-send 500."""


class GmailReauthRequired(RuntimeError):
    """Google rejected the refresh token — revoked at their end, or a password change.
    The credential is marked revoked and the user notified; this is terminal, never
    retried. Retrying an `invalid_grant` cannot succeed and only burns quota."""


# ---------- configuration ----------

def _client() -> tuple[str, str]:
    s = get_settings()
    if not s.google_client_id or not s.google_client_secret:
        raise GmailNotConfigured(
            "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are unset. Create an OAuth client "
            "in the Google Cloud console (consent screen in Testing mode) and add them "
            "to apps/api/.env — see docs/PLAN-GMAIL-CREDENTIALS.md."
        )
    return s.google_client_id, s.google_client_secret


def _redirect_uri() -> str:
    """Where Google sends the user back, and it must name a route that EXISTS.

    This pointed at `web_base_url` + `/settings/gmail/callback` — a Next.js page that was
    never built. Google would have redirected to a 404 and the authorization code would
    never have reached the API, while `/gmail/callback` sat mounted and tested one port
    over. `tests/test_gmail_credentials.py::test_the_redirect_uri_points_at_a_mounted_route`
    now pins the two together.

    `api_base_url`, not `web_base_url`: this endpoint is served by the API. A nicer flow
    would land the user on a web page that forwards the code, but that page has to exist
    first, and swapping back is one line plus the console entry.
    """
    return f"{get_settings().api_base_url.rstrip('/')}/gmail/callback"


# ---------- the signed state parameter ----------

def _state_for(user_id: str) -> str:
    """Signed, short-lived, and purpose-tagged, reusing the JWT discipline in
    `core/security.py`: a login token must not be usable as an OAuth state and vice
    versa. Signing it is what stops someone attaching their own Google account to
    another user's row."""
    s = get_settings()
    return jwt.encode(
        {
            "sub": user_id,
            "purpose": _STATE_PURPOSE,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=_STATE_MINUTES),
        },
        s.jwt_secret,
        algorithm=s.jwt_algorithm,
    )


def _user_from_state(state: str) -> str:
    s = get_settings()
    try:
        payload = jwt.decode(state, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("invalid or expired OAuth state") from exc
    if payload.get("purpose") != _STATE_PURPOSE:
        raise ValueError("not an OAuth state token")
    return payload["sub"]


# ---------- connect ----------

def authorize_url(user_id: str) -> str:
    client_id, _ = _client()
    return AUTH_URL + "?" + urlencode({
        "client_id": client_id,
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        # Both are load-bearing. Without them, a user who has granted before gets a
        # response with NO refresh token, and we would be storing a credential that dies
        # in an hour with no way to renew it.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": _state_for(user_id),
    })


def _email_from_id_token(id_token: str | None) -> str | None:
    """The connected address, from the `email` scope's id_token.

    Claims are read WITHOUT signature verification, deliberately: this token came
    straight back from Google's token endpoint over TLS in a server-to-server exchange,
    not from the browser, so there is no untrusted party in the path. It is used only as
    a display label, never for authorization.
    """
    if not id_token:
        return None
    try:
        return jwt.get_unverified_claims(id_token).get("email")
    except JWTError:
        return None


def handle_callback(db: Session, state: str, code: str) -> models.GmailCredential:
    """Exchange the code, encrypt the refresh token, record the GRANTED scopes."""
    user_id = _user_from_state(state)
    client_id, client_secret = _client()

    try:
        resp = httpx.post(TOKEN_URL, data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": _redirect_uri(),
            "grant_type": "authorization_code",
        }, timeout=TIMEOUT)
    except Exception as exc:
        logger.warning("gmail token exchange failed: %s", type(exc).__name__)
        raise GmailConnectFailed(f"could not reach Google ({type(exc).__name__})") from None

    if resp.status_code != 200:
        # `error` is a short Google error code ("access_denied", "invalid_grant") and is
        # safe to surface; the body is not logged.
        code_str = (resp.json() or {}).get("error", resp.status_code)
        logger.warning("gmail token exchange rejected: %s", code_str)
        raise GmailConnectFailed(f"Google rejected the authorization ({code_str})")

    payload = resp.json() or {}
    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        # Storing an access-token-only grant would look like success and stop working in
        # an hour, recoverable only by the user consenting again.
        raise GmailConnectFailed(
            "Google returned no refresh token. Re-run the consent flow; the request "
            "must carry access_type=offline and prompt=consent."
        )

    granted = [s for s in (payload.get("scope") or "").split() if s]
    cred = db.query(models.GmailCredential).filter_by(user_id=user_id).first()
    if cred is None:
        cred = models.GmailCredential(user_id=user_id)
        db.add(cred)
    cred.refresh_token_encrypted = crypto.encrypt(refresh_token)
    cred.email_address = _email_from_id_token(payload.get("id_token"))
    cred.scopes = granted
    cred.connected_at = datetime.utcnow()
    cred.revoked_at = None  # reconnecting clears an earlier revocation
    db.commit()
    db.refresh(cred)

    if cred.missing_scopes:
        # Not an exception: the grant is real and worth keeping so the UI can say which
        # permission is missing. `gmail_sender` refuses it, which is the actual gate.
        logger.warning(
            "gmail grant for user %s is missing %s — unusable for outreach",
            user_id, cred.missing_scopes,
        )
    return cred


# ---------- revoke ----------

def revoke(db: Session, user_id: str) -> bool:
    """ADR-003's "revocable in one click". Returns whether Google confirmed it.

    The local row is marked revoked EITHER WAY. A network failure must not leave a user
    unable to disconnect — a grant that is stale at Google but unusable by us is a far
    better outcome than a user who cannot turn it off.
    """
    cred = db.query(models.GmailCredential).filter_by(user_id=user_id).first()
    if cred is None:
        return False

    reached_google = False
    try:
        token = crypto.decrypt(cred.refresh_token_encrypted)
        resp = httpx.post(REVOKE_URL, data={"token": token}, timeout=TIMEOUT)
        reached_google = resp.status_code == 200
    except Exception as exc:
        # Includes a decrypt failure: the row is still revoked locally.
        logger.warning("gmail revoke at Google failed: %s", type(exc).__name__)

    cred.revoked_at = datetime.utcnow()
    db.commit()
    return reached_google


# ---------- status ----------

def status(db: Session, user_id: str) -> dict:
    """The entire public read surface. Hand-built rather than serialised from the model,
    so no column can be added into a response by accident."""
    cred = db.query(models.GmailCredential).filter_by(user_id=user_id).first()
    if cred is None or cred.revoked_at is not None:
        return {"connected": False, "email_address": None, "connected_at": None,
                "usable": False, "missing_scopes": []}
    return {
        "connected": True,
        "email_address": cred.email_address,
        "connected_at": cred.connected_at.isoformat() if cred.connected_at else None,
        "usable": cred.is_usable,
        "missing_scopes": cred.missing_scopes,
    }


# ---------- the sender ----------

def _access_token(db: Session, cred: models.GmailCredential) -> str:
    """Trade the refresh token for a short-lived access token.

    An `invalid_grant` here is terminal: the user revoked at Google or changed their
    password. ADR-003's rule is to mark it revoked, tell them to reconnect, and stop —
    retrying cannot succeed.
    """
    client_id, client_secret = _client()
    resp = httpx.post(TOKEN_URL, data={
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": crypto.decrypt(cred.refresh_token_encrypted),
        "grant_type": "refresh_token",
    }, timeout=TIMEOUT)

    if resp.status_code != 200:
        error = (resp.json() or {}).get("error", "")
        if error == "invalid_grant" or resp.status_code in (400, 401):
            cred.revoked_at = datetime.utcnow()
            db.add(models.Notification(
                user_id=cred.user_id,
                trigger="gmail_reauth_required",
                channel="in_app",
                template="gmail_reauth_required",
                payload={"email_address": cred.email_address},
            ))
            db.commit()
            logger.warning("gmail grant for user %s rejected (%s)", cred.user_id, error)
            raise GmailReauthRequired(
                "Google rejected the saved Gmail permission. Reconnect Gmail in settings."
            )
        logger.warning("gmail token refresh failed: HTTP %s", resp.status_code)
        raise RuntimeError(f"Gmail token refresh failed (HTTP {resp.status_code})")

    token = (resp.json() or {}).get("access_token")
    if not token:
        raise RuntimeError("Gmail token refresh returned no access token")
    return token


def gmail_sender(db: Session, user_id: str):
    """Return `sender(to, subject, body) -> message_id | None`.

    Matches the contract `digest.py` established and `outreach.send.send_outreach`
    already calls: a truthy return means mail left. Raises `GmailNotConnected` up front
    rather than at send time, so an unusable grant is caught before an email is claimed.
    """
    cred = db.query(models.GmailCredential).filter_by(user_id=user_id).first()
    if cred is None or cred.revoked_at is not None:
        raise GmailNotConnected("Gmail is not connected for this user.")
    if cred.missing_scopes:
        raise GmailNotConnected(
            f"The Gmail permission is missing {cred.missing_scopes}. Reconnect to grant it."
        )

    def sender(to: str, subject: str, body: str, attachments=None) -> str | None:
        """`attachments`: optional `[(filename, bytes, mime_type)]`."""
        access_token = _access_token(db, cred)
        msg = EmailMessage()
        msg["To"], msg["Subject"] = to, subject
        if cred.email_address:
            msg["From"] = cred.email_address
        msg.set_content(body)
        for name, data, mime in attachments or ():
            msg.add_attachment(data, *mime.split("/", 1), filename=name)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        resp = httpx.post(
            SEND_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
            timeout=TIMEOUT,
        )
        if resp.status_code not in (200, 202):
            # Status only. Gmail's error body can quote the message that was sent.
            logger.warning("gmail send failed: HTTP %s", resp.status_code)
            raise RuntimeError(f"Gmail send failed (HTTP {resp.status_code})")
        return (resp.json() or {}).get("id")

    return sender


# ---------- router ----------

def current_user_id(user: models.User = Depends(get_current_user)) -> str:
    """Indirection so tests can override the identity without a real JWT."""
    return user.id


router = APIRouter(prefix="/gmail", tags=["gmail"])


@router.get("/authorize")
def gmail_authorize(user_id: str = Depends(current_user_id)):
    """Returns the consent URL, and the redirect URI it was built with.

    The redirect URI is reported deliberately (DEPLOY-A.5): it is derived from
    `api_base_url`, so it CHANGES on deploy, and Google requires an exact match — a
    mismatch surfaces as `redirect_uri_mismatch` only when a real user first tries to
    connect, long after the console entry was typed. Returning the exact string makes
    that self-diagnosing instead of a reconstruction exercise.
    """
    try:
        return {"authorize_url": authorize_url(user_id), "redirect_uri": _redirect_uri()}
    except GmailNotConfigured as exc:
        raise HTTPException(503, str(exc)) from None


@router.get("/callback")
def gmail_callback(
    state: str = Query(...),
    code: str | None = Query(None),
    error: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """A denied consent is a clean outcome, not an error to retry — the user said no."""
    if error:
        return {"connected": False, "message": f"Gmail was not connected ({error})."}
    if not code:
        raise HTTPException(400, "Missing authorization code.")
    try:
        cred = handle_callback(db, state, code)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    except (GmailConnectFailed, GmailNotConfigured, crypto.EncryptionUnavailable) as exc:
        raise HTTPException(503, str(exc)) from None
    return {"connected": True, "email_address": cred.email_address,
            "usable": cred.is_usable, "missing_scopes": cred.missing_scopes}


@router.get("/status")
def gmail_status(user_id: str = Depends(current_user_id), db: Session = Depends(get_db)):
    return status(db, user_id)


@router.delete("/connection")
def gmail_disconnect(user_id: str = Depends(current_user_id), db: Session = Depends(get_db)):
    return {"revoked": revoke(db, user_id)}
