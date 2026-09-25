import pytest

from core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_is_not_plaintext():
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"


def test_verify_password_accepts_correct_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("correct horse battery staple")
    assert verify_password("wrong password", hashed) is False


def test_access_token_round_trips_subject():
    token = create_access_token(subject="user-123")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"


def test_decode_rejects_tampered_token():
    token = create_access_token(subject="user-123")
    # Flip a character in the middle of the signature segment, not the last
    # character — base64url's final group has redundant padding bits, so
    # flipping the literal last char doesn't always change the decoded bytes
    # (this was a real bug: the test passed or failed depending on which byte
    # the token happened to end on).
    mid = len(token) // 2
    flipped_char = "A" if token[mid] != "A" else "B"
    tampered = token[:mid] + flipped_char + token[mid + 1:]
    with pytest.raises(Exception):
        decode_access_token(tampered)
