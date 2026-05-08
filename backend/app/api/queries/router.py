"""Queries / stats router — Phase 9 slice 9a (read-only).

Mounted at the legacy ``/api/`` paths so admin.html keeps working
unchanged. admin_console served these without auth; the FastAPI port
adds ``Depends(current_admin)`` (security hardening — same pattern
slice 7b/8c/8d used).

Routes shipped in this slice:
- GET /api/stats              status counts (queries.status aggregated)
- GET /api/queries            filtered + paginated list

Write paths (POST / retry / batch_trigger / cleanup / mark_failed) are
deferred to slice 9b — those mutate the queries table and need
emit_audit + careful audit shape.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.queries import db as queries_db
from app.api.admin.auth.router import current_admin
from app.core.security import _DependsDb

router = APIRouter(tags=["Queries + stats (read-only)"])


@router.get("/stats", response_model=None)
async def stats(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    return await queries_db.fetch_status_stats(session)


@router.get("/queries", response_model=None)
async def queries(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    llm: str | None = Query(None),
    status: str | None = Query(None),
    brand_id: int | None = Query(None),
    topic_id: int | None = Query(None),
    prompt_id: int | None = Query(None),
    id: int | None = Query(None),
    q: str | None = Query(None),
    date: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    sort: str = Query("id_desc"),
    count: str | None = Query(None),
) -> Any:
    """Filtered list. Pagination is page+offset based; ``count=1`` adds
    ``total`` and ``by_status`` to the response (admin_console parity)."""
    include_count = (count or "").strip() == "1"
    rows, total, by_status = await queries_db.list_queries(
        session,
        llm=llm,
        status=status,
        brand_id=brand_id,
        topic_id=topic_id,
        prompt_id=prompt_id,
        query_id=id,
        prompt_q=q,
        date_filter=date,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
        sort=sort,
        include_count=include_count,
    )
    if include_count:
        return {"rows": rows, "total": total, "by_status": by_status}
    return rows


__all__ = ["router"]
