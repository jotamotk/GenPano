"""Password module — 8 cases.

Covers bcrypt cost factor, hash format, verify success/failure, malformed
hash safety, and every branch of `check_password_strength()`.
"""

from __future__ import annotations

from app.admin.auth.constants import BCRYPT_COST
from app.admin.auth.password import (
    check_password_strength,
    hash_password,
    verify_password,
)


def test_hash_uses_bcrypt_with_configured_cost() -> None:
    digest = hash_password("a-strong-pwd-1234")
    # passlib bcrypt format: $2b$<cost>$...
    parts = digest.split("$")
    assert parts[1] in {"2a", "2b"}
    assert int(parts[2]) == BCRYPT_COST


def test_verify_password_succeeds_on_match() -> None:
    pwd = "Long-Enough-Pwd-99!"
    digest = hash_password(pwd)
    assert verify_password(pwd, digest) is True


def test_verify_password_fails_on_mismatch() -> None:
    digest = hash_password("Long-Enough-Pwd-99!")
    assert verify_password("wrong-password-xyz", digest) is False


def test_verify_password_safe_on_malformed_hash() -> None:
    # passlib raises ValueError on garbage; module must swallow → False.
    assert verify_password("anything", "not-a-real-bcrypt-hash") is False


def test_check_strength_too_short() -> None:
    result = check_password_strength("Aa1!Aa1!")  # 8 chars, < 12
    assert result.ok is False
    assert result.reason == "too_short"


def test_check_strength_too_weak() -> None:
    # 12+ chars but trivially crackable: passes length, fails zxcvbn score.
    result = check_password_strength("password1234")
    assert result.ok is False
    assert result.reason == "too_weak"


def test_check_strength_ok_on_strong_pwd() -> None:
    result = check_password_strength("Tg9$mLp2qXv8nR4z!Ks")
    assert result.ok is True
    assert result.reason is None


def test_check_strength_at_exact_min_length() -> None:
    # The length gate is strictly `<`: at exactly MIN_PASSWORD_LENGTH the
    # length check must NOT fire, so a strong 12-char password should pass.
    pwd = "Tg9$mLp2qXv8"
    assert len(pwd) == 12  # MIN_PASSWORD_LENGTH (canary)
    result = check_password_strength(pwd)
    assert result.reason != "too_short"
    # Also confirm user_inputs parameter is accepted without raising.
    result_with_inputs = check_password_strength(pwd, user_inputs=["foo", "bar"])
    assert result_with_inputs.reason != "too_short"
