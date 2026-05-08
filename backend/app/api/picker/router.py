"""Topics + Prompts read-only endpoints for SPA pickers (Phase 8 slice 8d).

Mounted at the legacy paths ``/api/topics`` and ``/api/prompts`` in
``app/main.py``. admin.html's attempt-tracker filter dropdowns hit
these directly (cascading brand → topic → prompt selectors).

admin_console served these without auth; the FastAPI port adds
``Depends(current_admin)`` (security hardening, mirroring slice 7b's
treatment of /api/accounts).
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from genpano_models import AdminUser
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.auth.router import current_admin
from app.core.security import _DependsDb

router = APIRouter(tags=["Topics + Prompts pickers"])


async def _table_exists(session: AsyncSession, name: str) -> bool:
    try:
        row = (
            await session.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = :n LIMIT 1"
                ),
                {"n": name},
            )
        ).first()
    except Exception:
        return False
    return row is not None


@router.get("/topics", response_model=None)
async def list_topics(
    operator: Annotated[AdminUser, Depends(current_admin)],
    brand_id: int | None = Query(None),
    session: AsyncSession = _DependsDb,
) -> Any:
    """Topics filtered by brand_id (optional). Used by the attempt-tracker
    filter dropdown which cascades from the brand selector."""
    if not await _table_exists(session, "topics"):
        return []
    if brand_id is not None:
        sql = text(
            "SELECT id, brand_id, text, category FROM topics WHERE brand_id = :brand_id ORDER BY id"
        )
        rows = (await session.execute(sql, {"brand_id": brand_id})).mappings().all()
    else:
        sql = text("SELECT id, brand_id, text, category FROM topics ORDER BY brand_id, id")
        rows = (await session.execute(sql)).mappings().all()
    return [dict(r) for r in rows]


@router.get("/prompts", response_model=None)
async def list_prompts(
    operator: Annotated[AdminUser, Depends(current_admin)],
    brand_id: int | None = Query(None),
    topic_id: int | None = Query(None),
    session: AsyncSession = _DependsDb,
) -> Any:
    """Prompts filtered by brand_id and/or topic_id. Used by the attempt
    tracker's searchable prompt picker — client filters in-memory by text."""
    if not await _table_exists(session, "prompts"):
        return []
    where: list[str] = []
    params: dict[str, Any] = {}
    if brand_id is not None:
        where.append("t.brand_id = :brand_id")
        params["brand_id"] = brand_id
    if topic_id is not None:
        where.append("pr.topic_id = :topic_id")
        params["topic_id"] = topic_id
    where_clause = " AND ".join(where) if where else "1=1"
    sql = text(
        f"""
        SELECT pr.id, pr.topic_id, pr.text, t.text AS topic_text
        FROM prompts pr
        LEFT JOIN topics t ON pr.topic_id = t.id
        WHERE {where_clause}
        ORDER BY pr.topic_id, pr.id
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows]


__all__ = ["router"]
