"""Product-user password policy."""

from __future__ import annotations

import os
from dataclasses import dataclass

import bcrypt

MIN_USER_PASSWORD_LENGTH = 8
_BCRYPT_MAX_BYTES = 72
_BCRYPT_COST = int(os.getenv("BCRYPT_COST", "12"))


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


def hash_password(plaintext: str) -> str:
    payload = plaintext.encode("utf-8")
    if len(payload) > _BCRYPT_MAX_BYTES:
        raise ValueError(f"password exceeds bcrypt 72-byte limit ({len(payload)} bytes)")
    return bcrypt.hashpw(payload, bcrypt.gensalt(rounds=_BCRYPT_COST)).decode("ascii")


def verify_password(plaintext: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), stored_hash.encode("ascii"))
    except (TypeError, ValueError):
        return False


__all__ = [
    "MIN_USER_PASSWORD_LENGTH",
    "PasswordPolicyResult",
    "check_user_password_policy",
    "hash_password",
    "verify_password",
]
