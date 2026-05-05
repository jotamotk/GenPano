"""Service for crawl-requests (Phase 4).

Per PRD §4.6 user-triggered crawl: HIGH priority + daily quota 5/day per user.
Phase 4 ships the persistence + quota check; Celery enqueue wires later
(Phase RP / Tracker integration).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from genpano_models import CrawlRequest, Project, User
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found, rate_limit_exceeded

DAILY_QUOTA_PER_USER = 5  # PRD §4.6 user crawl quota


def _new_id() -> str:
    return str(uuid.uuid4())


async def create_crawl_request(
    session: AsyncSession,
    *,
    project: Project,
    user: User,
    brand_id: int | None,
    scope: dict[str, Any] | None,
) -> CrawlRequest:
    """Create a new crawl request, enforcing per-user daily quota."""
    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    today_end = today_start + timedelta(days=1)

    quota_stmt = select(func.count()).where(
        and_(
            CrawlRequest.created_by == user.id,
            CrawlRequest.created_at >= today_start,
            CrawlRequest.created_at < today_end,
        )
    )
    today_count = int((await session.execute(quota_stmt)).scalar_one() or 0)
    if today_count >= DAILY_QUOTA_PER_USER:
        raise rate_limit_exceeded(retry_after_seconds=86400)

    cr = CrawlRequest(
        id=_new_id(),
        project_id=project.id,
        brand_id=brand_id,
        scope=scope,
        status="queued",
        created_by=user.id,
    )
    session.add(cr)
    await session.commit()
    await session.refresh(cr)
    # TODO Phase 4.celery: enqueue user_triggered crawl task with HIGH priority
    return cr


async def get_crawl_request(
    session: AsyncSession,
    *,
    project: Project,
    crawl_id: str,
) -> CrawlRequest:
    stmt = select(CrawlRequest).where(
        and_(CrawlRequest.id == crawl_id, CrawlRequest.project_id == project.id)
    )
    cr = (await session.execute(stmt)).scalar_one_or_none()
    if cr is None:
        raise not_found("crawl request not found")
    return cr
