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


async def _table_columns(session: AsyncSession, name: str) -> set[str]:
    try:
        result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :n"
            ),
            {"n": name},
        )
    except Exception:
        return set()
    return {row[0] for row in result.all()}


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
    cols = await _table_columns(session, "topics")
    if "id" not in cols:
        return []
    brand_expr = "brand_id" if "brand_id" in cols else "NULL AS brand_id"
    text_expr = "text" if "text" in cols else "'' AS text"
    category_expr = "category" if "category" in cols else "NULL AS category"
    if brand_id is not None:
        if "brand_id" not in cols:
            return []
        sql = text(
            f"""
            SELECT id, {brand_expr}, {text_expr}, {category_expr}
            FROM topics
            WHERE brand_id = :brand_id
            ORDER BY id
            """
        )
        rows = (await session.execute(sql, {"brand_id": brand_id})).mappings().all()
    else:
        order_expr = "brand_id, id" if "brand_id" in cols else "id"
        sql = text(
            f"""
            SELECT id, {brand_expr}, {text_expr}, {category_expr}
            FROM topics
            ORDER BY {order_expr}
            """
        )
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
    prompt_cols = await _table_columns(session, "prompts")
    if "id" not in prompt_cols:
        return []
    has_prompt_topic_id = "topic_id" in prompt_cols
    if topic_id is not None and not has_prompt_topic_id:
        return []
    topic_cols = await _table_columns(session, "topics") if has_prompt_topic_id else set()
    can_join_topics = (
        has_prompt_topic_id and await _table_exists(session, "topics") and "id" in topic_cols
    )
    can_filter_brand = can_join_topics and "brand_id" in topic_cols
    if brand_id is not None and not can_filter_brand:
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
    topic_join = "LEFT JOIN topics t ON pr.topic_id = t.id" if can_join_topics else ""
    topic_id_expr = "pr.topic_id" if has_prompt_topic_id else "NULL AS topic_id"
    text_expr = "pr.text" if "text" in prompt_cols else "'' AS text"
    topic_text_expr = (
        "t.text AS topic_text" if can_join_topics and "text" in topic_cols else "NULL AS topic_text"
    )
    order_expr = "pr.topic_id, pr.id" if has_prompt_topic_id else "pr.id"
    sql = text(
        f"""
        SELECT pr.id, {topic_id_expr}, {text_expr}, {topic_text_expr}
        FROM prompts pr
        {topic_join}
        WHERE {where_clause}
        ORDER BY {order_expr}
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    return [dict(r) for r in rows]


__all__ = ["router"]
