"""Password hashing (Argon2id), password strength checks, and session/CSRF token helpers."""

import hashlib
import secrets

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


class Argon2PasswordHasher:
    """Argon2id password hasher with constant-work dummy verification support."""

    def __init__(self) -> None:
        self._hasher = PasswordHasher(type=Type.ID)
        self._dummy_hash = self._hasher.hash("vcraft-dummy-timing-guard")

    def hash(self, password: str) -> str:
        """Hash a plaintext password using Argon2id."""
        return self._hasher.hash(password)

    def verify(self, stored_hash: str, password: str) -> bool:
        """Verify a plaintext password against a stored Argon2id hash."""
        try:
            return self._hasher.verify(stored_hash, password)
        except (VerifyMismatchError, InvalidHashError, VerificationError):
            return False

    def verify_dummy(self, password: str) -> None:
        """Run Argon2id verification against a dummy hash to equalize unknown-email timing."""
        self.verify(self._dummy_hash, password)

    def needs_rehash(self, stored_hash: str) -> bool:
        """Return True when a stored hash should be upgraded to current parameters."""
        return self._hasher.check_needs_rehash(stored_hash)


def generate_session_token() -> str:
    """Generate a high-entropy opaque session token for HTTP cookie transport."""
    return secrets.token_urlsafe(32)


def generate_csrf_token() -> str:
    """Generate a high-entropy opaque CSRF token bound to a session or anonymous visitor."""
    return secrets.token_urlsafe(32)


def verify_csrf_token(expected: str | None, provided: str | None) -> bool:
    """Compare expected and provided CSRF tokens in constant time."""
    if not expected or not provided:
        return False
    return secrets.compare_digest(expected, provided)


def hash_session_token(raw_token: str) -> str:
    """Derive a SHA-256 hex digest for storing session tokens safely at rest."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def validate_password_strength(password: str) -> str | None:
    """Validate password policy and return a translation key on failure, else None."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return "auth.errors.password_too_short"
    if len(password) > PASSWORD_MAX_LENGTH:
        return "auth.errors.password_too_long"
    has_letter = any(ch.isalpha() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    if not (has_letter and has_digit):
        return "auth.errors.password_weak"
    return None
