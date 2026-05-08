"""Admin Hot Topics router — Phase 8 slice 8b.

Mounted under /api/admin (no segment prefix) so paths register as
``/api/admin/hot-topics`` and ``/api/admin/hot-topics/...``. All handlers
are gated by ``Depends(current_admin)`` and emit_audit fires on every
write (ADR-014).

Routes:
- GET    /api/admin/hot-topics                          list + status counts
- POST   /api/admin/hot-topics                          create + emit_audit (med)
- PUT    /api/admin/hot-topics/{hot_id}                 update + emit_audit (med/high)
- DELETE /api/admin/hot-topics/{hot_id}                 delete + emit_audit (high)
- POST   /api/admin/hot-topics/archive-expired          batch flip + emit_audit (med)
- POST   /api/admin/hot-topics/batch                    bulk + emit_audit (med/high)
- POST   /api/admin/hot-topics/collect                  trigger collect cycle + emit_audit (med)
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.hot_topics import db as hot_topics_db
from app.admin.hot_topics.lib import (
    HotTopicValidationError,
    hot_topic_row_to_dict,
    parse_batch_payload,
    parse_collect_payload,
    parse_create_payload,
    parse_update_payload,
)
from app.admin.products.db import fetch_brand_context
from app.api.admin.auth.router import current_admin
from app.core.errors import not_found
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Hot Topics"])


def _validation_400(error: HotTopicValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"success": False, "error": error.code, "message": error.message},
    )


# ─────────────────────────── GET list ───────────────────────────────


@router.get("/hot-topics", response_model=None)
async def list_hot_topics(
    operator: Annotated[AdminUser, Depends(current_admin)],
    status: str | None = Query(None),
    source: str | None = Query(None),
    industry: str | None = Query(None),
    brand_id: int | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = _DependsDb,
) -> Any:
    rows, counts = await hot_topics_db.list_hot_topics(
        session,
        status=status,
        source=source,
        industry=industry,
        brand_id=brand_id,
        limit=limit,
    )
    return {
        "success": True,
        "hot_topics": [hot_topic_row_to_dict(r) for r in rows],
        "counts": {
            "draft": counts.get("draft", 0),
            "active": counts.get("active", 0),
            "expired": counts.get("expired", 0),
            "rejected": counts.get("rejected", 0),
            "total": sum(counts.values()),
        },
    }


# ─────────────────────────── POST create ────────────────────────────


@router.post("/hot-topics", response_model=None)
async def create_hot_topic(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        normalized = parse_create_payload(payload)
    except HotTopicValidationError as error:
        return _validation_400(error)

    row = await hot_topics_db.create_hot_topic(session, payload=normalized)
    if row is None:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "hot_topics_unavailable",
                "message": "hot_topics table is not available; run migrations first.",
            },
        )
    await emit_audit(
        session,
        operator=operator,
        action="create_hot_topic",
        severity="med",
        resource_type="hot_topic",
        resource_id=str(row["id"]),
        after={
            "title": normalized["title"],
            "source": normalized["source"],
            "industry": normalized["industry"],
            "brand_id": normalized["brand_id"],
            "status": normalized["status"],
            "effective_days": normalized["effective_days"],
        },
        reason=str(payload.get("reason") or "create_hot_topic"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "hot_topic": hot_topic_row_to_dict(row)},
    )


# ─────────────────────────── PUT update ─────────────────────────────


@router.put("/hot-topics/{hot_id}", response_model=None)
async def update_hot_topic(
    hot_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        fields = parse_update_payload(payload)
    except HotTopicValidationError as error:
        return _validation_400(error)
    if not fields:
        return JSONResponse(
            status_code=400,
            content={
                "success": False,
                "error": "no_fields",
                "message": "no updatable fields supplied",
            },
        )

    before = await hot_topics_db.get_hot_topic(session, hot_id)
    if before is None:
        raise not_found("not_found")

    row = await hot_topics_db.update_hot_topic(session, hot_id=hot_id, fields=fields)
    if row is None:
        raise not_found("not_found")

    severity: Literal["low", "med", "high"] = "med"
    new_status = fields.get("status")
    if new_status in {"rejected", "expired"} and new_status != before.get("status"):
        severity = "high"
    await emit_audit(
        session,
        operator=operator,
        action="update_hot_topic",
        severity=severity,
        resource_type="hot_topic",
        resource_id=str(hot_id),
        before={k: before.get(k) for k in fields if k in before},
        after={k: row.get(k) for k in fields if k in row},
        reason=str(payload.get("reason") or "update_hot_topic"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "hot_topic": hot_topic_row_to_dict(row)},
    )


# ─────────────────────────── DELETE ─────────────────────────────────


@router.delete("/hot-topics/{hot_id}", response_model=None)
async def delete_hot_topic(
    hot_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    before = await hot_topics_db.get_hot_topic(session, hot_id)
    if before is None:
        raise not_found("not_found")
    deleted, unlinked = await hot_topics_db.delete_hot_topic(session, hot_id)
    if not deleted:
        raise not_found("not_found")
    await emit_audit(
        session,
        operator=operator,
        action="delete_hot_topic",
        severity="high",
        resource_type="hot_topic",
        resource_id=str(hot_id),
        before={
            "title": before.get("title"),
            "status": before.get("status"),
            "industry": before.get("industry"),
            "brand_id": before.get("brand_id"),
        },
        after={"deleted": True, "unlinked_prompts": unlinked},
        reason=str(payload.get("reason") or "delete_hot_topic"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "unlinked_prompts": unlinked},
    )


# ─────────────────────── POST archive-expired ───────────────────────


@router.post("/hot-topics/archive-expired", response_model=None)
async def archive_expired(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    n = await hot_topics_db.archive_expired(session)
    await emit_audit(
        session,
        operator=operator,
        action="archive_expired_hot_topics",
        severity="med",
        resource_type="hot_topic",
        after={"archived": n},
        reason="archive_expired_hot_topics",
        request=request,
    )
    return JSONResponse(status_code=200, content={"success": True, "archived": n})


# ─────────────────────────── POST batch ─────────────────────────────


@router.post("/hot-topics/batch", response_model=None)
async def batch_hot_topics(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        normalized = parse_batch_payload(payload)
    except HotTopicValidationError as error:
        return _validation_400(error)

    result = await hot_topics_db.batch_update_hot_topics(
        session,
        ids=normalized["ids"],
        action=normalized["action"],
        status=normalized.get("status"),
        industry=normalized.get("industry"),
        brand_id=normalized.get("brand_id"),
    )

    severity: Literal["low", "med", "high"] = "med"
    if normalized["action"] == "delete":
        severity = "high"
    await emit_audit(
        session,
        operator=operator,
        action=f"batch_hot_topics_{normalized['action']}",
        severity=severity,
        resource_type="hot_topic",
        after={
            "ids_count": len(normalized["ids"]),
            "action": normalized["action"],
            **{k: normalized[k] for k in ("status", "industry", "brand_id") if k in normalized},
            **result,
        },
        reason=str(payload.get("reason") or f"batch_{normalized['action']}"),
        request=request,
    )
    return JSONResponse(status_code=200, content={"success": True, **result})


# ─────────────────────────── POST collect ───────────────────────────


@router.post("/hot-topics/collect", response_model=None)
async def collect_hot_topics(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Trigger one collection cycle. Lightweight collectors (baidu /
    zhihu / llm_search) run in-process via admin_console.hotspot_collectors;
    browser collectors (douyin / xhs) are dispatched to celery."""
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        normalized = parse_collect_payload(payload)
    except HotTopicValidationError as error:
        return _validation_400(error)

    brand_context: dict[str, Any] | None = None
    industry_filter = normalized["industry"]
    if normalized["brand_id"] is not None:
        brand_context = await fetch_brand_context(session, brand_id=normalized["brand_id"])
        if brand_context is None:
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "brand_not_found"},
            )
        if not industry_filter:
            industry_filter = (str(brand_context.get("industry") or "")).strip() or None

    # In-process lightweight collectors. admin_console keeps the actual
    # collector module (admin_console.hotspot_collectors). Phase X moves
    # that module into the backend image.
    run_collection_cycle: Any = None
    try:
        import importlib

        run_collection_cycle = importlib.import_module(
            "admin_console.hotspot_collectors"
        ).run_collection_cycle
    except Exception:
        run_collection_cycle = None

    result: dict[str, Any] = {"collected": 0, "inserted": 0, "by_source": {}, "errors": {}}
    queued_sources: list[str] = []
    queued_tasks: list[dict[str, Any]] = []

    if normalized["local_sources"]:
        if run_collection_cycle is None:
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "error": "collectors_unavailable",
                    "message": (
                        "admin_console.hotspot_collectors is not on the backend Python path; "
                        "deploy admin_console alongside the FastAPI service or wait for "
                        "Phase X cleanup which moves collectors into backend."
                    ),
                },
            )
        try:
            # admin_console's run_collection_cycle expects a sync callable
            # returning a psycopg2 connection. Use the same DATABASE_URL the
            # async engine consumes (psycopg2's parser handles both prefixes).
            def _get_db_sync() -> Any:
                import os

                import psycopg2  # type: ignore[import-untyped]

                return psycopg2.connect(os.environ["DATABASE_URL"])

            result = run_collection_cycle(
                sources=normalized["local_sources"],
                industry_filter=industry_filter,
                brand_context=brand_context,
                get_db=_get_db_sync,
            )
        except Exception as error:
            return JSONResponse(
                status_code=502,
                content={
                    "success": False,
                    "error": "collection_failed",
                    "message": str(error)[:200],
                },
            )

    if normalized["browser_sources"]:
        celery_app = None
        try:
            from celery import Celery  # noqa: F401
            from geo_tracker.celery_app import (
                celery_app as _celery,  # type: ignore[import-not-found]
            )

            celery_app = _celery
        except Exception:
            celery_app = None

        for source in normalized["browser_sources"]:
            if celery_app is None:
                result.setdefault("errors", {})[source] = "browser_collection_requires_worker"
                continue
            try:
                task = celery_app.send_task(
                    "geo_tracker.tasks.celery_tasks.collect_hotspot_source",
                    args=[source],
                    kwargs={
                        "industry": industry_filter,
                        "brand_id": normalized["brand_id"],
                        "brand_context": brand_context,
                    },
                    queue="celery",
                )
                queued_sources.append(source)
                queued_tasks.append({"source": source, "task_id": getattr(task, "id", None)})
            except Exception as error:
                result.setdefault("errors", {})[source] = f"queue_failed: {str(error)[:160]}"

    await emit_audit(
        session,
        operator=operator,
        action="collect_hot_topics",
        severity="med",
        resource_type="hot_topic",
        after={
            "sources": normalized["sources"],
            "industry": industry_filter,
            "brand_id": normalized["brand_id"],
            "local_collected": int(result.get("collected") or 0),
            "local_inserted": int(result.get("inserted") or 0),
            "queued_browser_sources": queued_sources,
            "errors_count": len(result.get("errors") or {}),
        },
        reason=str(payload.get("reason") or "collect_hot_topics"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={
            "success": True,
            **result,
            "queued_sources": queued_sources,
            "queued_tasks": queued_tasks,
        },
    )


__all__ = ["router"]
