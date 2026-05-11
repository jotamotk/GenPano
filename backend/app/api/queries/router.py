"""Queries / stats router — Phase 9 slice 9a + 9b.

Mounted at the legacy ``/api/`` paths so admin.html keeps working
unchanged. admin_console served these without auth; the FastAPI port
adds ``Depends(current_admin)`` (security hardening).

Routes:
- GET    /api/stats                       status counts (slice 9a)
- GET    /api/queries                     filtered + paginated (slice 9a)
- POST   /api/queries                     create + emit_audit (med)
- POST   /api/queries/{id}/retry          retry + emit_audit (med)
- POST   /api/queries/batch_trigger       bulk reset + emit_audit (high)
- DELETE /api/queries/cleanup             orphan delete + emit_audit (high)
- POST   /api/queries/{id}/mark_failed    flip done→failed + emit_audit (med)
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.queries import db as queries_db
from app.admin.queries.analytics import fetch_query_analytics
from app.admin.queries.celery_dispatch import dispatch_execute_query, dispatch_many
from app.admin.queries.lib import (
    QueryValidationError,
    parse_batch_trigger_payload,
    parse_cleanup_query_args,
    parse_create_query_payload,
)
from app.api.admin.auth.router import current_admin
from app.core.errors import not_found
from app.core.security import _DependsDb

router = APIRouter(tags=["Queries + stats"])


def _validation_400(error: QueryValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"success": False, "error": error.code, "message": error.message},
    )


@router.get("/stats", response_model=None)
async def stats(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    return await queries_db.fetch_status_stats(session)


@router.get("/admin/queries/analytics", response_model=None)
async def query_analytics(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
    brand_id: int | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    engine: str | None = Query(None),
) -> Any:
    """Brand query analytics — aggregated metrics over queries JOIN
    llm_responses JOIN response_analyses JOIN brand_mentions JOIN prompts
    JOIN topics. Powers the TopicsPage QueryActivityCard. Default window:
    last 30 days. Empty shape (zeros + empty arrays) when brand_id is
    missing or upstream tables are unavailable."""
    return await fetch_query_analytics(
        session,
        brand_id=brand_id,
        date_from=date_from,
        date_to=date_to,
        engine=engine,
    )


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


# ── write paths (slice 9b) ──────────────────────────────────


@router.post("/queries", response_model=None)
async def create_query(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Create a single pending query and dispatch it to celery."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        normalized = parse_create_query_payload(payload)
    except QueryValidationError as error:
        return _validation_400(error)

    query_id = await queries_db.create_query(
        session,
        target_llm=normalized["target_llm"],
        query_text=normalized["query_text"],
        brand_id=normalized["brand_id"],
        prompt_id=normalized.get("prompt_id"),
    )
    if query_id is None:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "queries_unavailable",
                "message": "queries table is not available; run migrations first.",
            },
        )

    dispatched = dispatch_execute_query(query_id, normalized["target_llm"])
    await emit_audit(
        session,
        operator=operator,
        action="create_query",
        severity="med",
        resource_type="query",
        resource_id=str(query_id),
        after={
            "target_llm": normalized["target_llm"],
            "brand_id": normalized["brand_id"],
            "query_length": len(normalized["query_text"]),
            "dispatched": dispatched,
        },
        reason="create_query",
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "query_id": query_id, "dispatched": dispatched},
    )


@router.post("/queries/{query_id}/retry", response_model=None)
async def retry_query(
    query_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Reset a single query to pending + bump retry_count + re-dispatch."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    retry_reason = str(payload.get("reason") or "").strip() or None

    detail = await queries_db.retry_query(session, query_id=query_id, retry_reason=retry_reason)
    if detail is None:
        raise not_found("Query not found")

    dispatched = dispatch_execute_query(query_id, detail.get("target_llm"))
    await emit_audit(
        session,
        operator=operator,
        action="retry_query",
        severity="med",
        resource_type="query",
        resource_id=str(query_id),
        after={
            "target_llm": detail.get("target_llm"),
            "retry_reason": retry_reason,
            "dispatched": dispatched,
        },
        reason=retry_reason or "retry_query",
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "dispatched": dispatched},
    )


@router.post("/queries/batch_trigger", response_model=None)
async def batch_trigger(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Bulk reset matching queries + re-dispatch. emit_audit HIGH because
    a single click can flip 1000s of rows back to pending."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        normalized = parse_batch_trigger_payload(payload)
    except QueryValidationError as error:
        return _validation_400(error)

    matched, dispatch_items, refused = await queries_db.batch_trigger_queries(
        session, payload=normalized
    )
    if refused:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": (
                    f"matched {matched} rows; over the limit "
                    f"{normalized.get('max_count')} — narrow the filter "
                    "or pass a higher 'max'"
                ),
                "count": matched,
            },
        )
    if normalized.get("dry_run"):
        return JSONResponse(
            status_code=200, content={"success": True, "count": matched, "dry_run": True}
        )
    if not dispatch_items:
        return JSONResponse(status_code=200, content={"success": True, "count": 0, "dispatched": 0})

    dispatched, dispatch_failed = dispatch_many(dispatch_items)
    await emit_audit(
        session,
        operator=operator,
        action="batch_trigger_queries",
        severity="high",
        resource_type="query",
        after={
            "matched": matched,
            "ids_count": len(dispatch_items),
            "dispatched": dispatched,
            "dispatch_failed": dispatch_failed,
            "reason": normalized.get("reason"),
            "filter_keys": sorted(
                k for k in normalized if k not in {"max_count", "dry_run", "reason"}
            ),
        },
        reason=str(normalized.get("reason") or "batch_trigger"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            "count": len(dispatch_items),
            "dispatched": dispatched,
            "dispatch_failed": dispatch_failed,
        },
    )


@router.delete("/queries/cleanup", response_model=None)
async def cleanup(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Delete orphaned queries by type (unqueued / all_pending /
    failed_old). emit_audit HIGH — destructive bulk delete."""
    try:
        normalized = parse_cleanup_query_args(dict(request.query_params))
    except QueryValidationError as error:
        return _validation_400(error)

    matched, deleted = await queries_db.cleanup_queries(
        session,
        cleanup_type=normalized["type"],
        days=normalized["days"],
        dry_run=normalized["dry_run"],
    )
    if normalized["dry_run"]:
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "count": matched,
                "dry_run": True,
                "type": normalized["type"],
            },
        )
    await emit_audit(
        session,
        operator=operator,
        action="cleanup_queries",
        severity="high",
        resource_type="query",
        after={
            "type": normalized["type"],
            "days": normalized["days"],
            "matched": matched,
            "deleted": deleted,
        },
        reason=f"cleanup_queries:{normalized['type']}",
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "deleted": deleted, "type": normalized["type"]},
    )


@router.post("/queries/{query_id}/mark_failed", response_model=None)
async def mark_failed(
    query_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Flip a done query to failed (retroactive QA flagging). Only
    succeeds when the row is currently in ``done`` (admin_console parity)."""
    flipped = await queries_db.mark_query_failed(session, query_id)
    if not flipped:
        return JSONResponse(
            status_code=404,
            content={
                "success": False,
                "error": "Query not found or not in done status",
            },
        )
    await emit_audit(
        session,
        operator=operator,
        action="mark_query_failed",
        severity="med",
        resource_type="query",
        resource_id=str(query_id),
        after={"new_status": "failed"},
        reason="mark_query_failed",
        request=request,
    )
    return JSONResponse(status_code=200, content={"success": True})


__all__ = ["router"]
