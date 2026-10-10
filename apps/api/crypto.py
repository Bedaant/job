"""Encryption at rest for the Gmail refresh token (REACH-A, ADR-003).

ADR-003 calls that token "the highest-value secret in the system: KMS-backed encryption,
never logged, never returned by any endpoint". This module is the encryption half.

**The invariant: there is no input for which this returns or stores plaintext.** A
missing key, a blank key, a malformed key, a tampered ciphertext — every one raises. The
failure mode being designed out is a credential written under a silently-empty key, which
would look exactly like success.

ponytail: a local symmetric key from the environment, NOT a KMS. ADR-003 specifies
KMS-backed and GAPS 5.6 records that it is deferred. Ceiling: the key sits in `.env`
beside the database URL, so anyone who can read the environment can decrypt every stored
token, and there is no rotation story — re-encrypting existing rows needs a migration
that reads with the old key and writes with the new one. Upgrade path: move `_fernet()`
behind a KMS decrypt call (AWS KMS / GCP KMS), keeping `encrypt`/`decrypt` signatures
unchanged so no caller moves.

WHY NOT A MODULE-LEVEL RAISE. `PLAN-GMAIL-CREDENTIALS.md` asks to fail closed "at
import/boot, not at first use". Raising during import would brick the entire app and all
950 existing tests today, because `ENCRYPTION_KEY` is genuinely unset (GAPS 5.6) and
nothing else in the system needs it. The intent behind that line — never operate under a
bad key — is met by raising on every use instead, which is what `_fernet()` does.
`is_configured()` exists so a caller can branch rather than catch, and boot-time
verification is one `require_configured()` call in `main.py`'s startup when someone wires
the endpoints up.
"""
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from core.config import get_settings

logger = logging.getLogger(__name__)


class EncryptionUnavailable(RuntimeError):
    """No usable `ENCRYPTION_KEY`. Never downgrade this to a warning: the caller is
    trying to store or read a credential and must not proceed without a key."""


class DecryptionFailed(RuntimeError):
    """Ciphertext did not authenticate — tampered, truncated, or written under a
    different key. Deliberately distinct from `EncryptionUnavailable`, because this one
    means "the key is fine, this row is not" and points at key rotation."""


def generate_key() -> str:
    """A fresh key, for the owner to put in `.env`. Not called by the app."""
    return Fernet.generate_key().decode()


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    """The cipher, or a raise. Cached because Fernet construction derives key material
    and this is on the path of every credential read."""
    key = (get_settings().encryption_key or "").strip()
    if not key:
        raise EncryptionUnavailable(
            "ENCRYPTION_KEY is not set, so the Gmail refresh token cannot be stored or "
            "read. Generate one with: python -c "
            '"from crypto import generate_key; print(generate_key())"'
        )
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        # The key itself is never included in the message — it would land in a traceback,
        # a log aggregator, or an error-reporting service.
        raise EncryptionUnavailable(
            "ENCRYPTION_KEY is not a valid Fernet key (expected 32 url-safe base64 "
            f"bytes): {type(exc).__name__}"
        ) from None


def reset_cipher_cache() -> None:
    """Drop the cached cipher. For tests that change the key, and for key rotation."""
    _fernet.cache_clear()


def is_configured() -> bool:
    """Whether encryption is usable, without raising — so a status endpoint can report
    "not configured" instead of returning a 500."""
    try:
        _fernet()
        return True
    except EncryptionUnavailable:
        return False


def require_configured() -> None:
    """Raise unless encryption is usable. Call from app startup to turn a
    misconfiguration into a boot failure rather than a first-request failure."""
    _fernet()


def encrypt(plaintext: str) -> str:
    """Plaintext -> ciphertext. Raises `EncryptionUnavailable` rather than returning
    anything readable."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Ciphertext -> plaintext. Raises on a bad key or a ciphertext that does not
    authenticate; never returns a partial or garbled value."""
    cipher = _fernet()
    try:
        return cipher.decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError, TypeError) as exc:
        # Type only, and no ciphertext: `digest.smtp_sender` sets this precedent.
        logger.warning("refresh token failed to decrypt: %s", type(exc).__name__)
        raise DecryptionFailed(
            f"ciphertext did not authenticate ({type(exc).__name__}) — written under a "
            "different ENCRYPTION_KEY, or modified"
        ) from None
