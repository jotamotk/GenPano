"""Phase K — Celery task for KG candidate promotion.

Wraps `app.kg.promote.promote_approved_candidates` so the work runs on
the existing 6-queue topology (routes to `beat` like other housekeeping
tasks) and can be scheduled via Celery Beat.

The actual promotion logic stays in `app.kg.promote` so the same code
path is reachable from:

  - the periodic Celery task here
  - the one-shot CLI script (`backend/scripts/promote_kg_candidates.py`)
  - admin trigger endpoints (future)

All three call the same async function, just with different drivers.
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.celery_app import celery_app
from app.core.config import get_settings


def _run_async(coro: Any) -> dict[str, Any]:  # pragma: no cover — thin wrapper
    result: dict[str, Any] = asyncio.run(coro)
    return result


@celery_app.task(name="app.tasks.kg.promote_candidates", queue="beat")  # type: ignore[untyped-decorator]
def promote_candidates(limit: int = 500) -> dict[str, Any]:
    """Promote approved kg_relation_candidates to canonical relation tables.

    Args:
        limit: max candidates per run (default 500). Multi-batch is
            handled by repeated scheduling rather than a single huge
            transaction.

    Returns the summary dict from `promote_approved_candidates`.
    """

    async def _do() -> dict[str, Any]:
        from app.kg.promote import promote_approved_candidates

        settings = get_settings()
        engine = create_async_engine(settings.database_url, future=True)
        sm = async_sessionmaker(engine, expire_on_commit=False)
        async with sm() as session:
            summary = await promote_approved_candidates(session, limit=limit)
        await engine.dispose()
        return summary

    return _run_async(_do())
