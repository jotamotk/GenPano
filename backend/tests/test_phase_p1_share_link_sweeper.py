"""[#1044 P1] B2-14 — share-link sweeper regression test.

The Celery beat task `reports.expire_share_tokens` runs daily to flip
`revoked_at` on expired-but-not-revoked rows so the public read path
returns 410 even if the row is still in the table. Pre-fix the only
coverage was a smoke test (`callable(expire_share_tokens)`); the sweep
logic itself had no regression guard.

This module exercises `expire_share_tokens_in_session` (the inner
async helper the Celery task wraps) directly against the fixture
session, verifying:
  - already-expired tokens get revoked_at set
  - active tokens are left alone
  - already-revoked tokens are not double-flipped
  - sweep is idempotent across consecutive runs
"""

from __future__ import annotations

import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    Project,
    ReportJob,
    ReportShareToken,
    User,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"sw-{uuid.uuid4().hex[:6]}@example.com",
        name="sw",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def report_job(db_session: AsyncSession, user: User) -> ReportJob:
    p = Project(id=_new_id(), user_id=user.id, name="Sweep P", primary_brand_id=42)
    db_session.add(p)
    await db_session.commit()
    job = ReportJob(
        id=_new_id(),
        project_id=p.id,
        type="json",
        scope="{}",
        status="done",
        created_by=user.id,
        finished_at=_now(),
    )
    db_session.add(job)
    await db_session.commit()
    return job


def _share_token(
    *,
    report_id: str,
    user_id: str,
    expires_at: datetime,
    revoked_at: datetime | None = None,
) -> ReportShareToken:
    return ReportShareToken(
        token=secrets.token_urlsafe(16),
        report_id=report_id,
        expires_at=expires_at,
        created_by=user_id,
        revoked_at=revoked_at,
    )


@pytest.mark.asyncio
async def test_b2_14_sweeper_flips_expired_unrevoked_tokens(db_session, user, report_job):
    """Expired + unrevoked → revoked_at gets set, count reflects it."""
    from app.tasks.reports import expire_share_tokens_in_session

    expired = _share_token(
        report_id=report_job.id,
        user_id=user.id,
        expires_at=_now() - timedelta(hours=1),
    )
    db_session.add(expired)
    await db_session.commit()

    result = await expire_share_tokens_in_session(db_session)
    assert result == {"expired_count": 1}

    refreshed = (
        await db_session.execute(
            select(ReportShareToken).where(ReportShareToken.token == expired.token)
        )
    ).scalar_one()
    assert refreshed.revoked_at is not None


@pytest.mark.asyncio
async def test_b2_14_sweeper_leaves_active_tokens_alone(db_session, user, report_job):
    """Future-expiry tokens must not be flipped (active share links remain valid)."""
    from app.tasks.reports import expire_share_tokens_in_session

    active = _share_token(
        report_id=report_job.id,
        user_id=user.id,
        expires_at=_now() + timedelta(hours=24),
    )
    db_session.add(active)
    await db_session.commit()

    result = await expire_share_tokens_in_session(db_session)
    assert result == {"expired_count": 0}

    refreshed = (
        await db_session.execute(
            select(ReportShareToken).where(ReportShareToken.token == active.token)
        )
    ).scalar_one()
    assert refreshed.revoked_at is None


@pytest.mark.asyncio
async def test_b2_14_sweeper_skips_already_revoked(db_session, user, report_job):
    """Already-revoked rows must not be touched — preserves the
    original revoke timestamp so audit trails stay accurate."""
    from app.tasks.reports import expire_share_tokens_in_session

    original_revoke = _now() - timedelta(days=2)
    already_revoked = _share_token(
        report_id=report_job.id,
        user_id=user.id,
        expires_at=_now() - timedelta(hours=1),
        revoked_at=original_revoke,
    )
    db_session.add(already_revoked)
    await db_session.commit()

    result = await expire_share_tokens_in_session(db_session)
    assert result == {"expired_count": 0}

    refreshed = (
        await db_session.execute(
            select(ReportShareToken).where(ReportShareToken.token == already_revoked.token)
        )
    ).scalar_one()
    # Original revoked_at preserved exactly
    assert refreshed.revoked_at == original_revoke


@pytest.mark.asyncio
async def test_b2_14_sweeper_is_idempotent(db_session, user, report_job):
    """Running the sweep twice in a row: second run reports 0 — the
    flipped rows are now filtered out by the revoked_at IS NULL guard."""
    from app.tasks.reports import expire_share_tokens_in_session

    expired = _share_token(
        report_id=report_job.id,
        user_id=user.id,
        expires_at=_now() - timedelta(hours=1),
    )
    db_session.add(expired)
    await db_session.commit()

    first = await expire_share_tokens_in_session(db_session)
    second = await expire_share_tokens_in_session(db_session)
    assert first == {"expired_count": 1}
    assert second == {"expired_count": 0}


@pytest.mark.asyncio
async def test_b2_14_sweeper_handles_mixed_population(db_session, user, report_job):
    """3 expired + 2 active + 1 already-revoked: exactly 3 should flip."""
    from app.tasks.reports import expire_share_tokens_in_session

    for _ in range(3):
        db_session.add(
            _share_token(
                report_id=report_job.id,
                user_id=user.id,
                expires_at=_now() - timedelta(hours=1),
            )
        )
    for _ in range(2):
        db_session.add(
            _share_token(
                report_id=report_job.id,
                user_id=user.id,
                expires_at=_now() + timedelta(hours=12),
            )
        )
    db_session.add(
        _share_token(
            report_id=report_job.id,
            user_id=user.id,
            expires_at=_now() - timedelta(hours=2),
            revoked_at=_now() - timedelta(days=3),
        )
    )
    await db_session.commit()

    result = await expire_share_tokens_in_session(db_session)
    assert result == {"expired_count": 3}

    # Sanity: only 4 of the 6 rows should now have revoked_at set
    # (3 freshly swept + 1 already-revoked).
    rows = list((await db_session.execute(select(ReportShareToken))).scalars().all())
    revoked = [r for r in rows if r.revoked_at is not None]
    assert len(revoked) == 4
