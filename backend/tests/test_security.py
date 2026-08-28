"""Unit tests for password hashing and JWT handling."""

import datetime
import time

import jwt as pyjwt
import pytest

from app.core.config import settings
from app.core.security import (
    ACCESS_TOKEN_TYPE,
    TOKEN_TYPE_CLAIM,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_password_roundtrip():
    hashed = hash_password("my-secret-password")
    assert hashed != "my-secret-password"
    assert verify_password("my-secret-password", hashed) is True


def test_verify_password_rejects_wrong_password():
    hashed = hash_password("correct-password")
    assert verify_password("wrong-password", hashed) is False


def test_hash_is_salted_each_time():
    first = hash_password("same-password")
    second = hash_password("same-password")
    assert first != second


def test_decode_valid_token_contains_expected_claims():
    token, expires_in = create_access_token(subject="42", extra_claims={"username": "admin"})
    payload = decode_token(token)

    assert payload["sub"] == "42"
    assert payload["username"] == "admin"
    assert payload[TOKEN_TYPE_CLAIM] == ACCESS_TOKEN_TYPE
    assert expires_in == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


def test_decode_rejects_tampered_token():
    token, _ = create_access_token(subject="42")
    tampered = token[:-3] + ("aaa" if not token.endswith("aaa") else "bbb")

    with pytest.raises(pyjwt.PyJWTError):
        decode_token(tampered)


def test_decode_rejects_expired_token():
    expired_delta = datetime.timedelta(seconds=-10)
    token, _ = create_access_token(subject="42", expires_delta=expired_delta)

    with pytest.raises(pyjwt.ExpiredSignatureError):
        decode_token(token)


def test_bcrypt_verification_timing_reasonable():
    start = time.perf_counter()
    verify_password("password", hash_password("password"))
    elapsed = time.perf_counter() - start
    # bcrypt cost must be non-trivial but bounded.  With BCRYPT_ROUNDS=4
    # in tests the hash is fast; with production rounds (12+) it takes ≥ 0.25s.
    assert elapsed < 2.0
