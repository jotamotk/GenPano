"""Product-user password policy.

The public product PRD keeps the MVP password gate lighter than admin auth:
8+ characters with upper/lower letters and a number. Hashing still goes through
the admin bcrypt helper so cost and malformed-hash handling stay centralized.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.admin.auth.password import hash_password, verify_password

MIN_USER_PASSWORD_LENGTH = 8


@dataclass(frozen=True)
class PasswordPolicyResult:
    ok: bool
    reason: str | None = None


def check_user_password_policy(password: str) -> PasswordPolicyResult:
    if len(password) < MIN_USER_PASSWORD_LENGTH:
        return PasswordPolicyResult(ok=False, reason="too_short")
    if not any(ch.islower() for ch in password):
        return PasswordPolicyResult(ok=False, reason="missing_lowercase")
    if not any(ch.isupper() for ch in password):
        return PasswordPolicyResult(ok=False, reason="missing_uppercase")
    if not any(ch.isdigit() for ch in password):
        return PasswordPolicyResult(ok=False, reason="missing_digit")
    return PasswordPolicyResult(ok=True)


__all__ = [
    "MIN_USER_PASSWORD_LENGTH",
    "PasswordPolicyResult",
    "check_user_password_policy",
    "hash_password",
    "verify_password",
]
