"""Audit log — 5 cases.

Verifies success / failure paths each write exactly one row with the
four security fields, that the CHECK constraint on `failure_code`
enforces the four-code allow-list, and that repeated calls accumulate
without collapsing rows.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.auth.audit import record_login_failure, record_login_success
from app.models.admin import AdminLoginAttempt


@pytest.mark.asyncio
async def test_record_login_success_writes_success_row(db_session: AsyncSession) -> None:
    await record_login_success(
        db_session,
        email="frank@example.com",
        ip_address="203.0.113.7",
        user_agent="Mozilla/5.0",
    )
    await db_session.flush()

    rows = (await db_session.execute(select(AdminLoginAttempt))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.email == "frank@example.com"
    assert row.ip_address == "203.0.113.7"
    assert row.success is True
    assert row.failure_code is None
    assert row.user_agent == "Mozilla/5.0"


@pytest.mark.asyncio
async def test_record_login_failure_persists_failure_code(db_session: AsyncSession) -> None:
    await record_login_failure(
        db_session,
        email="frank@example.com",
        ip_address="203.0.113.7",
        user_agent=None,
        failure_code="WRONG_PASSWORD",
    )
    await db_session.flush()

    [row] = (await db_session.execute(select(AdminLoginAttempt))).scalars().all()
    assert row.success is False
    assert row.failure_code == "WRONG_PASSWORD"


@pytest.mark.asyncio
async def test_rate_limited_failure_code_is_accepted(db_session: AsyncSession) -> None:
    await record_login_failure(
        db_session,
        email="frank@example.com",
        ip_address=None,
        user_agent=None,
        failure_code="RATE_LIMITED",
    )
    await db_session.flush()

    [row] = (await db_session.execute(select(AdminLoginAttempt))).scalars().all()
    assert row.failure_code == "RATE_LIMITED"


@pytest.mark.asyncio
async def test_invalid_failure_code_rejected_by_check_constraint(
    db_session: AsyncSession,
) -> None:
    # CHECK enforces the 4-code allow-list. Bypassing the helper directly
    # to confirm the DB-level guard is in place.
    db_session.add(
        AdminLoginAttempt(
            email="x@y.com",
            ip_address=None,
            success=False,
            failure_code="NOT_A_REAL_CODE",
            user_agent=None,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.asyncio
async def test_repeated_attempts_create_distinct_rows(db_session: AsyncSession) -> None:
    for _ in range(3):
        await record_login_failure(
            db_session,
            email="frank@example.com",
            ip_address="203.0.113.7",
            user_agent=None,
            failure_code="WRONG_PASSWORD",
        )
    await db_session.flush()

    rows = (await db_session.execute(select(AdminLoginAttempt))).scalars().all()
    assert len(rows) == 3
    assert all(row.email == "frank@example.com" for row in rows)
