"""Centralized password policy.

Policy (configurable via .env):
- minimum length: PASSWORD_MIN_LENGTH (default 10);
- at least one uppercase letter, one lowercase letter and one digit;
- rejection of a small denylist of common weak passwords;
- rejection of passwords containing the username;
- empty passwords are always rejected.

Deliberately avoids exotic complexity rules that harm usability; entropy is
expected to come primarily from length. Hashing (bcrypt) is handled by
core/security.py — this module only validates.
"""

import re

from app.core.config import settings

UPPERCASE_PATTERN = re.compile(r"[A-Z]")
LOWERCASE_PATTERN = re.compile(r"[a-z]")
DIGIT_PATTERN = re.compile(r"\d")

COMMON_WEAK_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "password123",
        "12345678",
        "123456789",
        "1234567890",
        "qwerty123",
        "qwertyuiop",
        "admin123",
        "admin1234",
        "administrator",
        "letmein1",
        "iloveyou1",
        "welcome1",
        "monkey123",
        "dragon123",
        "root1234",
        "changeme1",
    }
)


class WeakPasswordError(Exception):
    """Raised when a password does not comply with the policy."""

    def __init__(self, violations: list[str]) -> None:
        self.violations = violations
        super().__init__("Password does not comply with the policy.")


def validate_password(password: str, username: str | None = None) -> list[str]:
    violations: list[str] = []

    if not password:
        return ["La contraseña no puede estar vacía."]

    if len(password) < settings.PASSWORD_MIN_LENGTH:
        violations.append(
            f"Debe tener al menos {settings.PASSWORD_MIN_LENGTH} caracteres."
        )
    if not UPPERCASE_PATTERN.search(password):
        violations.append("Debe incluir al menos una letra mayúscula.")
    if not LOWERCASE_PATTERN.search(password):
        violations.append("Debe incluir al menos una letra minúscula.")
    if not DIGIT_PATTERN.search(password):
        violations.append("Debe incluir al menos un número.")

    normalized = password.lower()
    if normalized in COMMON_WEAK_PASSWORDS:
        violations.append("Es una contraseña demasiado común.")
    if username and username.lower() in normalized:
        violations.append("No debe contener el nombre de usuario.")

    return violations


def enforce_password_policy(password: str, username: str | None = None) -> None:
    """Raise WeakPasswordError if the password violates the policy."""
    violations = validate_password(password, username=username)
    if violations:
        raise WeakPasswordError(violations)
