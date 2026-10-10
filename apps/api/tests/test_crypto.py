"""REACH-A — encryption at rest for the Gmail refresh token.

ADR-003 calls that token "the highest-value secret in the system". The property these
tests exist to defend is narrow and absolute: **there is no input for which this module
returns or stores plaintext.** A missing key, a malformed key, a truncated ciphertext —
every one of them raises. None of them degrade.
"""
import logging

import pytest

import crypto


@pytest.fixture(autouse=True)
def _clear_key_cache():
    """The Fernet instance is cached, so a test that changes the key must invalidate it."""
    crypto.reset_cipher_cache()
    yield
    crypto.reset_cipher_cache()


def _with_key(monkeypatch, key):
    """Point `get_settings()` at a specific key, genuinely bypassing `.env`.

    It used to claim that and not do it: clearing `os.environ` leaves pydantic-settings
    free to keep supplying the value from `apps/api/.env`, so `key=None` meant "no key"
    only on a machine where none was configured. The moment a real `ENCRYPTION_KEY` was
    added, both fail-closed tests started failing.

    **This is the third time the same trap has fired** — after `APIFY_TOKEN` and
    `GOOGLE_CLIENT_ID`. The rule it implies: a test asserting a credential is ABSENT must
    blank it on the Settings object too, not just in the environment, or it is really
    asserting "absent on this developer's machine".
    """
    from core.config import get_settings

    get_settings.cache_clear()
    if key is None:
        monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    else:
        monkeypatch.setenv("ENCRYPTION_KEY", key)
    # Overriding the attribute is what actually defeats the `.env` source.
    monkeypatch.setattr(get_settings(), "encryption_key", key, raising=False)
    crypto.reset_cipher_cache()
    return get_settings().encryption_key


def test_round_trip(monkeypatch):
    _with_key(monkeypatch, crypto.generate_key())
    assert crypto.decrypt(crypto.encrypt("hunter2")) == "hunter2"


def test_ciphertext_does_not_contain_the_plaintext(monkeypatch):
    _with_key(monkeypatch, crypto.generate_key())
    secret = "1//0g-REFRESH-TOKEN-abc123"
    assert secret not in crypto.encrypt(secret)


def test_encryption_is_non_deterministic(monkeypatch):
    """Fernet embeds a random IV. Two identical tokens must not produce identical
    ciphertext, or the column leaks which users share a value."""
    _with_key(monkeypatch, crypto.generate_key())
    assert crypto.encrypt("same") != crypto.encrypt("same")


def test_missing_encryption_key_fails_closed(monkeypatch):
    """The failure this exists to prevent: a credential written under a silently-empty
    key. Nothing is encrypted and nothing is decrypted without a key."""
    _with_key(monkeypatch, None)
    with pytest.raises(crypto.EncryptionUnavailable):
        crypto.encrypt("secret")
    with pytest.raises(crypto.EncryptionUnavailable):
        crypto.decrypt("anything")


def test_blank_encryption_key_fails_closed(monkeypatch):
    """An empty string in .env is the likeliest way this gets misconfigured."""
    _with_key(monkeypatch, "   ")
    with pytest.raises(crypto.EncryptionUnavailable):
        crypto.encrypt("secret")


def test_malformed_encryption_key_fails_closed(monkeypatch):
    """Fernet needs 32 url-safe base64 bytes. "hunter2" is not a key."""
    _with_key(monkeypatch, "hunter2")
    with pytest.raises(crypto.EncryptionUnavailable):
        crypto.encrypt("secret")


def test_tampered_ciphertext_is_rejected(monkeypatch):
    """Fernet is authenticated encryption, so a modified ciphertext must not decrypt to
    anything — least of all to a partially-correct token."""
    _with_key(monkeypatch, crypto.generate_key())
    token = crypto.encrypt("secret")
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt(tampered)


def test_ciphertext_from_another_key_is_rejected(monkeypatch):
    """Rotating the key must not silently yield garbage for old rows."""
    _with_key(monkeypatch, crypto.generate_key())
    token = crypto.encrypt("secret")
    _with_key(monkeypatch, crypto.generate_key())
    with pytest.raises(crypto.DecryptionFailed):
        crypto.decrypt(token)


def test_is_configured_reports_without_raising(monkeypatch):
    """Lets a caller branch on availability instead of catching — the status endpoint
    needs to say "not configured" rather than 500."""
    _with_key(monkeypatch, None)
    assert crypto.is_configured() is False
    _with_key(monkeypatch, crypto.generate_key())
    assert crypto.is_configured() is True


def test_the_key_is_never_logged(monkeypatch, caplog):
    """`digest.smtp_sender` sets the precedent: log the error TYPE, never the secret."""
    key = crypto.generate_key()
    _with_key(monkeypatch, key)
    with caplog.at_level(logging.DEBUG):
        crypto.decrypt(crypto.encrypt("a-secret-value"))
        with pytest.raises(crypto.DecryptionFailed):
            crypto.decrypt("not-a-valid-token")
    assert key not in caplog.text
    assert "a-secret-value" not in caplog.text


def test_generate_key_produces_a_usable_key(monkeypatch):
    _with_key(monkeypatch, crypto.generate_key())
    assert crypto.decrypt(crypto.encrypt("x")) == "x"
