"""REACH-E — the unsubscribe link in every outreach email (`docs/PLAN-OUTREACH.md`).

`GET /outreach/unsubscribe/{token}` is **unauthenticated by necessity**: the recipient
has no account here and must never need one to be left alone. So the signature is the
only thing standing between this endpoint and mass-suppression or address enumeration —
an unsigned id would let anyone walk the id space, and anyone who could guess an id
could suppress a stranger.

Signed with the existing `JWT_SECRET`. Stdlib `hmac`, because `itsdangerous` is not
installed and ADR-010 makes adding a dependency an owner decision — this is ~15 lines
either way.

**No expiry, deliberately.** Every other signed link in a product like this wants a TTL;
an opt-out link does not. Someone finding a year-old email and asking not to be
contacted again is exactly who this is for, and "your unsubscribe link has expired" is
a dark pattern.

No Gmail scope and no inbox reading is involved. That is the whole reason this is a link
rather than reply-parsing: honouring an opt-out must not cost a restricted read scope.
"""
import base64
import hmac
import logging
from hashlib import sha256

import models
from core.config import get_settings

logger = logging.getLogger(__name__)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _sign(outreach_id: str) -> str:
    secret = get_settings().jwt_secret.encode()
    return _b64(hmac.new(secret, outreach_id.encode(), sha256).digest())


def make_token(outreach_id: str) -> str:
    """`<outreach_id>.<signature>` — both halves URL-safe, so it drops straight into a
    path segment. The id is a UUID string, which needs no encoding of its own."""
    return f"{outreach_id}.{_sign(outreach_id)}"


def verify_token(token: str | None) -> str | None:
    """Return the outreach id, or None for anything that is not a token we issued.

    Never raises: this is reached by arbitrary internet traffic, including mail clients
    that prefetch links and scanners that mangle them.
    """
    if not token or "." not in token:
        return None
    outreach_id, _, signature = token.rpartition(".")
    if not outreach_id or not signature:
        return None
    # compare_digest, not `==`: constant-time comparison is the one thing worth not
    # being lazy about on a signature check.
    #
    # Compared as BYTES, not str. `compare_digest` RAISES TypeError on a str containing
    # non-ASCII, and this is reached by arbitrary internet traffic — mail scanners and
    # prefetchers mangle links routinely. A raise here is a 500 on the unsubscribe path,
    # so someone trying to be left alone would get an error page instead. Encoding first
    # makes any input comparable and keeps the timing property.
    if not hmac.compare_digest(signature.encode("utf-8", "surrogatepass"),
                               _sign(outreach_id).encode()):
        return None
    return outreach_id


def record_optout(db, outreach_id: str) -> str | None:
    """Suppress the CONTACT's address globally. Returns the address, or None if there was
    nothing to suppress.

    GLOBAL (`profile_id=None`) is the point: someone who asks not to be contacted should
    not have to ask each user of this product separately.

    Suppresses `contact.email`, never the profile's own address — getting that backwards
    would silently suppress our own user and quietly stop their outreach working.

    IDEMPOTENT. Mail clients prefetch links and people click twice; neither may raise or
    write a second row.
    """
    row = db.query(models.Outreach).filter(models.Outreach.id == outreach_id).first()
    if row is None or row.contact is None:
        return None
    email = (row.contact.email or "").strip()
    if not email:
        return None

    # Stored casefolded so the row is stable regardless of which adapter supplied the
    # address; `suppression.is_suppressed` casefolds both sides anyway.
    addr = email.casefold()
    already = (
        db.query(models.Suppression)
        .filter(
            models.Suppression.profile_id.is_(None),
            models.Suppression.email == addr,
        )
        .first()
    )
    if already is not None:
        return addr

    db.add(models.Suppression(profile_id=None, email=addr, reason="opt_out"))
    db.flush()
    logger.info("outreach opt-out recorded for outreach=%s", outreach_id)
    return addr
