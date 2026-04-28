"""Append-only login audit — `admin_login_attempts`.

Decision #24.B contract: each row records exactly four security-relevant
fields plus the user agent: `email / ip_address / success / failure_code
/ user_agent`. **Passwords and tokens MUST NOT be persisted** under any
circumstance — the `record_*` helpers accept only the four fields, so a
caller that wants to leak a token literally cannot.

`failure_code` is constrained to one of four codes (CHECK constraint in
the migration). `success=True` rows omit the code (it is NULL).
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import AdminLoginAttempt

FailureCode = Literal[
    "WRONG_PASSWORD",
    "USER_SUSPENDED",
    "RATE_LIMITED",
    "UNKNOWN_EMAIL",
]


async def record_login_success(
    db: AsyncSession,
    *,
    email: str,
    ip_address: str | None,
    user_agent: str | None,
) -> AdminLoginAttempt:
    row = AdminLoginAttempt(
        email=email,
        ip_address=ip_address,
        success=True,
        failure_code=None,
        user_agent=user_agent,
    )
    db.add(row)
    await db.flush()
    return row


async def record_login_failure(
    db: AsyncSession,
    *,
    email: str,
    ip_address: str | None,
    user_agent: str | None,
    failure_code: FailureCode,
) -> AdminLoginAttempt:
    row = AdminLoginAttempt(
        email=email,
        ip_address=ip_address,
        success=False,
        failure_code=failure_code,
        user_agent=user_agent,
    )
    db.add(row)
    await db.flush()
    return row
