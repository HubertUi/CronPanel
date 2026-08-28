"""Tests for the password policy validator."""

import pytest

from app.core.password_policy import validate_password


def test_too_short():
    violations = validate_password("A1b")
    assert any("caracteres" in v or "longitud" in v.lower() for v in violations)


def test_no_uppercase():
    violations = validate_password("alllowercase1")
    assert any("mayúscula" in v for v in violations)


def test_no_lowercase():
    violations = validate_password("ALLUPPERCASE1")
    assert any("minúscula" in v for v in violations)


def test_no_digit():
    violations = validate_password("NoDigitsHere!")
    assert any("número" in v for v in violations)


def test_common_weak_password():
    violations = validate_password("password123")
    assert any("común" in v for v in violations)


def test_contains_username():
    violations = validate_password("MyPass123admin", username="admin")
    assert any("usuario" in v for v in violations)


def test_empty_password():
    violations = validate_password("", username="admin")
    assert len(violations) >= 1


def test_strong_password_passes():
    violations = validate_password("V4lidPassw0rd!", username="alice")
    assert violations == []
