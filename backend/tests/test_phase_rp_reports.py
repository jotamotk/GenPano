"""Phase RP — ReportSchedule + ReportShareToken ORM tests."""

from __future__ import annotations

import os
import secrets
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import Project, ReportSchedule, ReportShareToken, User
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    u = User(
        id=_new_id(),
        email=f"r-{uuid.uuid4().hex[:6]}@example.com",
        name="Report User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    p = Project(user_id=u.id, name="Report Test", primary_brand_id=42)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p


@pytest.mark.asyncio
async def test_create_report_schedule(db_session: AsyncSession, project: Project) -> None:
    sched = ReportSchedule(
        project_id=project.id,
        report_type="weekly",
        cron="0 8 * * 1",
        recipients=["operator@example.com"],
        next_run_at=datetime.now() + timedelta(days=1),
    )
    db_session.add(sched)
    await db_session.commit()
    assert sched.id is not None
    assert sched.enabled is True


@pytest.mark.asyncio
async def test_share_token_lifecycle(db_session: AsyncSession, project: Project) -> None:
    token = secrets.token_urlsafe(32)
    share = ReportShareToken(
        token=token,
        report_id=_new_id(),
        expires_at=datetime.now() + timedelta(days=30),
        created_by="user-1",
    )
    db_session.add(share)
    await db_session.commit()
    assert share.view_count == 0
    assert share.revoked_at is None
    share.revoked_at = datetime.now()
    await db_session.commit()
    assert share.revoked_at is not None


@pytest.mark.asyncio
async def test_schedule_next_run_query(db_session: AsyncSession, project: Project) -> None:
    """Index `(next_run_at, enabled)` enables Celery beat scan query."""
    from sqlalchemy import select

    now = datetime.now()
    db_session.add(
        ReportSchedule(
            project_id=project.id,
            report_type="weekly",
            cron="0 9 * * 1",
            next_run_at=now + timedelta(hours=1),
            enabled=True,
        )
    )
    db_session.add(
        ReportSchedule(
            project_id=project.id,
            report_type="monthly",
            cron="0 9 1 * *",
            next_run_at=now + timedelta(days=5),
            enabled=False,
        )
    )
    db_session.add(
        ReportSchedule(
            project_id=project.id,
            report_type="weekly",
            cron="0 9 * * 1",
            next_run_at=now + timedelta(hours=2),
            enabled=True,
        )
    )
    await db_session.commit()

    stmt = select(ReportSchedule).where(
        ReportSchedule.enabled.is_(True),
        ReportSchedule.next_run_at <= now + timedelta(days=1),
    )
    rows = list((await db_session.execute(stmt)).scalars().all())
    assert len(rows) == 2
