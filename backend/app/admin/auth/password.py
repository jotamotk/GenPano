"""BCrypt password hashing + zxcvbn strength gate.

`hash_password()` is the single-source entry to bcrypt (Harness D9 will reject
literal `bcrypt.hashpw(..., <12)` anywhere outside this module). Cost factor
comes from `BCRYPT_COST` constant — never inlined.

`verify_password()` swallows malformed-hash exceptions and returns False;
this matches the master decision #24.B contract that callers should treat any
verify failure as "wrong password" without leaking which.

`check_password_strength()` is the gate used by /change-password and
/reset-password. Returns `(ok, reason?)` where reason is one of
`'too_short'` or `'too_weak'` so the API can surface a code without leaking
the zxcvbn raw score.

We use the `bcrypt` library directly rather than passlib's CryptContext —
passlib 1.7.4 (last release 2020) crashes on its internal version probe when
paired with bcrypt ≥ 4.0 (the probe hashes a 240-byte secret, which modern
bcrypt rejects per the 72-byte spec limit).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import bcrypt
from zxcvbn import zxcvbn  # type: ignore[import-untyped]

from app.admin.auth.constants import (
    BCRYPT_COST,
    MIN_PASSWORD_LENGTH,
    MIN_ZXCVBN_SCORE,
)

# bcrypt ≥ 4.0 caps secrets at 72 bytes (the original spec). We enforce the
# same cap here so callers get a clear error before bcrypt raises.
_BCRYPT_MAX_BYTES = 72


@dataclass(frozen=True)
class PasswordStrengthResult:
    ok: bool
    reason: str | None = None  # 'too_short' | 'too_weak' | None


def hash_password(plaintext: str) -> str:
    """Hash with bcrypt at cost = `BCRYPT_COST`.

    Encodes plaintext as UTF-8; refuses payloads > 72 bytes (bcrypt limit).
    Returns the standard `$2b$<cost>$<22 salt><31 hash>` ASCII form.
    """

    payload = plaintext.encode("utf-8")
    if len(payload) > _BCRYPT_MAX_BYTES:
        raise ValueError(
            f"password exceeds bcrypt 72-byte limit ({len(payload)} bytes)"
        )
    salt = bcrypt.gensalt(rounds=BCRYPT_COST)
    return bcrypt.hashpw(payload, salt).decode("ascii")


def verify_password(plaintext: str, stored_hash: str) -> bool:
    """Constant-time verify; any structural failure → False (no leak)."""

    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), stored_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def check_password_strength(
    plaintext: str,
    user_inputs: Sequence[str] | None = None,
) -> PasswordStrengthResult:
    """Gate length first (deterministic), then zxcvbn.

    `user_inputs` should include the email + any obvious vocabulary (admin
    name, company name) so zxcvbn can penalise dictionary-style passwords
    woven from the user's own profile — see decision #24.B.
    """

    if len(plaintext) < MIN_PASSWORD_LENGTH:
        return PasswordStrengthResult(ok=False, reason="too_short")
    result = zxcvbn(plaintext, user_inputs=list(user_inputs) if user_inputs else None)
    score = int(result.get("score", 0))
    if score < MIN_ZXCVBN_SCORE:
        return PasswordStrengthResult(ok=False, reason="too_weak")
    return PasswordStrengthResult(ok=True, reason=None)
