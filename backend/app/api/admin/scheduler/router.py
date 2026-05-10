"""Admin Scheduler router — Phase 8 slice 8c (+ 8c-bis manual_trigger).

Mounted under /api/admin (no segment prefix) so paths register at
``/api/admin/scheduler/...``. Also re-mounted at the legacy
``/api/scheduler/...`` paths in app/main.py — admin.html still hits
those. Both mounts gate every handler with ``Depends(current_admin)``.

Routes:
- GET    /scheduler/config                          read + capacity
- PUT    /scheduler/config                          update + emit_audit (med/high)
- GET    /scheduler/runs                            list (paginated or bare)
- DELETE /scheduler/runs/{run_id}                   delete one + emit_audit (med)
- DELETE /scheduler/runs                            bulk delete + emit_audit (high)
- GET    /scheduler/today                           today's progress
- GET    /scheduler/schedules                       list query plans
- POST   /scheduler/schedules                       create + emit_audit (med)
- PUT    /scheduler/schedules/{id}                  update + emit_audit (med)
- DELETE /scheduler/schedules/{id}                  delete + emit_audit (high)
- GET    /scheduler/upcoming                        N-day projection
- POST   /scheduler/manual_trigger                  inline dispatch + emit_audit (high)
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.scheduler import db as scheduler_db
from app.admin.scheduler.lib import (
    SchedulerValidationError,
    parse_config_payload,
    parse_schedule_payload,
)
from app.admin.scheduler.manual_dispatch import run_manual_dispatch
from app.api.admin.auth.router import current_admin
from app.core.errors import not_found
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin · Scheduler"])


def _validation_400(error: SchedulerValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": error.message, "code": error.code},
    )


def _manual_dispatch_message(result: dict[str, Any]) -> str | None:
    """Operator-facing explanation for 0-dispatch outcomes."""
    if int(result.get("queries_created") or 0) > 0:
        return None

    enabled = int(result.get("schedules_enabled") or 0)
    dispatchable = int(result.get("schedules_dispatchable") or 0)
    quotas = int(result.get("quotas_total") or 0)
    paused = [str(e) for e in (result.get("paused_engines") or []) if e]
    failures = result.get("schedule_failures") or []

    if enabled == 0 and quotas > 0:
        return (
            f"账号容量已配置 ({quotas}/天), 但没有启用的 Query 计划。"
            "请先在下方添加或启用 Query 计划; 只调整账号 quota 不会自动入队。"
        )
    if enabled == 0:
        return "没有启用的 Query 计划。请先添加并启用 Query 计划, 然后再触发调度。"
    if dispatchable == 0 and paused:
        return (
            f"有 {enabled} 条启用的 Query 计划, 但目标 LLM 已暂停: "
            f"{', '.join(paused)}。请先恢复对应 LLM 后再触发。"
        )
    if dispatchable == 0:
        return (
            f"有 {enabled} 条启用的 Query 计划, 但没有可派发计划。"
            "请检查目标 LLM 是否在白名单内, 以及计划是否启用。"
        )
    if failures:
        return (
            f"找到 {dispatchable} 条可派发计划, 但写入队列失败。"
            f"前两条错误: {'; '.join(str(x) for x in failures[:2])}"
        )
    return f"本次没有入队。启用计划 {enabled} 条, 可派发 {dispatchable} 条, 账号容量 {quotas}/天。"


# ── /scheduler/config ────────────────────────────────────────


@router.get("/scheduler/config", response_model=None)
async def scheduler_config_get(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    cfg = await scheduler_db.fetch_scheduler_config(session)
    if not cfg:
        return JSONResponse(
            status_code=500,
            content={"error": "scheduler_config missing"},
        )
    return cfg


@router.put("/scheduler/config", response_model=None)
async def scheduler_config_put(
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
        fields = parse_config_payload(payload)
    except SchedulerValidationError as error:
        return _validation_400(error)

    if not fields:
        return JSONResponse(status_code=200, content={"success": True, "updated": 0})

    updated = await scheduler_db.update_scheduler_config(session, fields=fields)

    severity: Literal["low", "med", "high"] = "med"
    if "mode" in fields and fields["mode"] == "paused":
        severity = "high"

    await emit_audit(
        session,
        operator=operator,
        action="update_scheduler_config",
        severity=severity,
        resource_type="scheduler_config",
        after={
            "fields_changed": sorted(fields.keys()),
            "mode": fields.get("mode"),
            "paused_engines_count": len(fields.get("paused_engines") or [])
            if "paused_engines" in fields
            else None,
            "engine_caps_keys": sorted((fields.get("engine_caps") or {}).keys())
            if "engine_caps" in fields
            else None,
            "temp_global_cap": fields.get("temp_global_cap"),
            "retry_max": fields.get("retry_max"),
            "daily_time": fields.get("daily_time"),
            "timezone": fields.get("timezone"),
        },
        reason=str(payload.get("reason") or "update_scheduler_config"),
        request=request,
    )
    return JSONResponse(
        status_code=200,
        content={"success": True, "updated": updated},
    )


# ── /scheduler/runs ──────────────────────────────────────────


@router.get("/scheduler/runs", response_model=None)
async def scheduler_runs_list(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    """Pagination is opt-in: when neither ``page`` nor ``per_page`` is
    present in the query string, returns the bare list (admin_console
    backwards-compat).
    """
    qs = request.query_params
    paginated = "page" in qs or "per_page" in qs
    try:
        page = max(1, int(qs.get("page") or 1))
    except Exception:
        page = 1
    try:
        per_page = max(1, min(int(qs.get("per_page") or 20), 100))
    except Exception:
        per_page = 20
    try:
        limit = max(1, min(int(qs.get("limit") or per_page), 200))
    except Exception:
        limit = per_page
    offset = (page - 1) * per_page if paginated else 0

    rows, total = await scheduler_db.list_scheduler_runs(
        session,
        limit=per_page if paginated else limit,
        offset=offset,
        paginated=paginated,
    )
    if paginated:
        return {"rows": rows, "total": total, "page": page, "per_page": per_page}
    return rows


@router.delete("/scheduler/runs/{run_id}", response_model=None)
async def scheduler_run_delete(
    run_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    deleted = await scheduler_db.delete_scheduler_run(session, run_id)
    if not deleted:
        raise not_found("run not found")
    await emit_audit(
        session,
        operator=operator,
        action="delete_scheduler_run",
        severity="med",
        resource_type="scheduler_run",
        resource_id=str(run_id),
        after={"deleted": True},
        reason="delete_scheduler_run",
        request=request,
    )
    return JSONResponse(status_code=200, content={"success": True})


@router.delete("/scheduler/runs", response_model=None)
async def scheduler_runs_bulk_delete(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    qs = request.query_params
    body: dict[str, Any]
    try:
        raw_body = await request.json()
    except Exception:
        raw_body = None
    body = raw_body if isinstance(raw_body, dict) else {}

    delete_all = str(qs.get("all") or "").lower() in ("1", "true", "yes")
    delete_empty = str(qs.get("empty") or "").lower() in ("1", "true", "yes")
    raw_ids = qs.get("ids") or body.get("ids") or ""
    if isinstance(raw_ids, list):
        id_list = [str(x).strip() for x in raw_ids if str(x).strip()]
    else:
        id_list = [s.strip() for s in str(raw_ids).split(",") if s.strip()]

    ids: list[int] | None = None
    if not delete_all and not delete_empty:
        clean = [int(x) for x in id_list if str(x).isdigit()]
        if not clean:
            return JSONResponse(
                status_code=400,
                content={"error": "pass ?ids=… , ?empty=1, or ?all=1"},
            )
        ids = clean

    deleted = await scheduler_db.bulk_delete_scheduler_runs(
        session,
        ids=ids,
        delete_empty=delete_empty,
        delete_all=delete_all,
    )
    severity: Literal["low", "med", "high"] = "high" if delete_all else "med"
    await emit_audit(
        session,
        operator=operator,
        action="bulk_delete_scheduler_runs",
        severity=severity,
        resource_type="scheduler_run",
        after={
            "deleted": deleted,
            "all": delete_all,
            "empty_only": delete_empty,
            "ids_count": len(ids) if ids else 0,
        },
        reason="bulk_delete_scheduler_runs",
        request=request,
    )
    return JSONResponse(status_code=200, content={"success": True, "deleted": deleted})


# ── /scheduler/today ─────────────────────────────────────────


@router.get("/scheduler/today", response_model=None)
async def scheduler_today(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    return await scheduler_db.fetch_today_dispatch(session)


# ── /scheduler/schedules ─────────────────────────────────────


@router.get("/scheduler/schedules", response_model=None)
async def schedules_list(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    enabled_only = str(request.query_params.get("enabled_only") or "").lower() in (
        "1",
        "true",
        "yes",
    )
    return await scheduler_db.list_query_schedules(session, enabled_only=enabled_only)


@router.post("/scheduler/schedules", response_model=None)
async def schedule_create(
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
        normalized = parse_schedule_payload(payload, partial=False)
    except SchedulerValidationError as error:
        return _validation_400(error)

    row = await scheduler_db.create_query_schedule(session, payload=normalized)
    if row is None:
        return JSONResponse(
            status_code=503,
            content={"error": "query_schedules table is not available"},
        )
    await emit_audit(
        session,
        operator=operator,
        action="create_query_schedule",
        severity="med",
        resource_type="query_schedule",
        resource_id=str(row["id"]),
        after={
            "target_llm": normalized["target_llm"],
            "cadence_days": normalized.get("cadence_days"),
            "enabled": normalized.get("enabled", True),
            "brand_id": normalized.get("brand_id"),
            "prompt_id": normalized.get("prompt_id"),
        },
        reason=str(payload.get("reason") or "create_query_schedule"),
        request=request,
    )
    return JSONResponse(status_code=200, content=row)


@router.put("/scheduler/schedules/{schedule_id}", response_model=None)
async def schedule_update(
    schedule_id: int,
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
        fields = parse_schedule_payload(payload, partial=True)
    except SchedulerValidationError as error:
        return _validation_400(error)
    if not fields:
        return JSONResponse(status_code=200, content={"success": True, "updated": 0})

    before = await scheduler_db.get_query_schedule(session, schedule_id)
    if before is None:
        raise not_found("Schedule not found")

    row = await scheduler_db.update_query_schedule(session, schedule_id=schedule_id, fields=fields)
    if row is None:
        raise not_found("Schedule not found")

    await emit_audit(
        session,
        operator=operator,
        action="update_query_schedule",
        severity="med",
        resource_type="query_schedule",
        resource_id=str(schedule_id),
        before={k: before.get(k) for k in fields if k in before},
        after={k: row.get(k) for k in fields if k in row},
        reason=str(payload.get("reason") or "update_query_schedule"),
        request=request,
    )
    return JSONResponse(status_code=200, content=row)


@router.delete("/scheduler/schedules/{schedule_id}", response_model=None)
async def schedule_delete(
    schedule_id: int,
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    before = await scheduler_db.get_query_schedule(session, schedule_id)
    if before is None:
        raise not_found("Schedule not found")
    deleted = await scheduler_db.delete_query_schedule(session, schedule_id)
    if not deleted:
        raise not_found("Schedule not found")
    await emit_audit(
        session,
        operator=operator,
        action="delete_query_schedule",
        severity="high",
        resource_type="query_schedule",
        resource_id=str(schedule_id),
        before={
            "target_llm": before.get("target_llm"),
            "cadence_days": before.get("cadence_days"),
            "enabled": before.get("enabled"),
        },
        after={"deleted": True},
        reason="delete_query_schedule",
        request=request,
    )
    return JSONResponse(status_code=200, content={"success": True})


# ── /scheduler/upcoming ──────────────────────────────────────


@router.get("/scheduler/upcoming", response_model=None)
async def scheduler_upcoming(
    operator: Annotated[AdminUser, Depends(current_admin)],
    days: int = Query(7, ge=1, le=60),
    session: AsyncSession = _DependsDb,
) -> Any:
    by_date = await scheduler_db.upcoming_schedule_fires(session, days=days)
    return {"days": days, "by_date": by_date}


# ── /scheduler/manual_trigger (slice 8c-bis) ──────────────────


@router.post("/scheduler/manual_trigger", response_model=None)
async def scheduler_manual_trigger(
    request: Request,
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> JSONResponse:
    """Run the daily dispatch inline — schedules only, no random fill.

    Body (optional): ``{"cap": 100, "note": "manual via UI"}``. ``cap``
    overrides ``scheduler_config.temp_global_cap`` for this dispatch.

    audit severity HIGH: this is a destructive bulk write to the
    ``queries`` table — operators have used it incorrectly in the past
    (94k pending queries from repeated clicks per a previous user
    report).
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    cap_raw = payload.get("cap")
    cap_int: int | None
    if cap_raw is None or cap_raw == "":
        cap_int = None
    else:
        try:
            cap_int = int(cap_raw)
        except (TypeError, ValueError):
            return JSONResponse(
                status_code=400,
                content={"error": "cap must be an integer or null"},
            )
    note = str(payload.get("note") or "manual via UI").strip()

    try:
        result = await run_manual_dispatch(session, cap_override=cap_int, note=note)
    except RuntimeError as error:
        if str(error) == "scheduler_tables_unavailable":
            return JSONResponse(
                status_code=503,
                content={
                    "success": False,
                    "error": "scheduler_tables_unavailable",
                    "message": (
                        "scheduler_config / llm_accounts / queries / query_schedules "
                        "are not all available; run migrations first."
                    ),
                },
            )
        raise
    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(error)[:300]},
        )

    await emit_audit(
        session,
        operator=operator,
        action="scheduler_manual_trigger",
        severity="high",
        resource_type="scheduler_run",
        resource_id=str(result.get("run_id") or ""),
        after={
            "queries_created": int(result.get("queries_created") or 0),
            "target_total": int(result.get("target_total") or 0),
            "schedules_dispatchable": int(result.get("schedules_dispatchable") or 0),
            "cap_override": cap_int,
            "reason": result.get("reason"),
            "schedule_failures_count": len(result.get("schedule_failures") or []),
        },
        reason=note,
        request=request,
    )
    message = _manual_dispatch_message(result)
    return JSONResponse(
        status_code=200,
        content={"success": True, **result, **({"message": message} if message else {})},
    )


__all__ = ["router"]
