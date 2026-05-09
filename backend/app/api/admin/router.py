"""Admin API top-level aggregator router.

Mounts at `/api/admin/*`. Sub-routers add deeper paths.

Phase R.4 ships:
- `_meta/routes` — admin route introspection
- `_meta/audit-log` — list audit log (for self-test of `@audit` decorator)
- 13 sub-package skeletons (each empty for now)
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from genpano_models import AdminAuditLog, AdminUser, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.brand_management import db as brand_management_db
from app.admin.security import current_admin_operator
from app.api.admin.accounts import router as accounts_router
from app.api.admin.alerts import router as alerts_router
from app.api.admin.auth.router import current_admin
from app.api.admin.brand_management import router as brand_management_router
from app.api.admin.brand_submissions import router as brand_submissions_router
from app.api.admin.comms import router as comms_router
from app.api.admin.cost import router as cost_router
from app.api.admin.diagnostics import router as diagnostics_router
from app.api.admin.engine_health import router as engine_health_router
from app.api.admin.hot_topics import router as hot_topics_router
from app.api.admin.kg_candidates import router as kg_candidates_router
from app.api.admin.kg_discovery import router as kg_discovery_router
from app.api.admin.leads import router as leads_router
from app.api.admin.llm_extraction import router as llm_extraction_router
from app.api.admin.mcp_ops import router as mcp_ops_router
from app.api.admin.products import router as products_router
from app.api.admin.projects import router as projects_router
from app.api.admin.prompt_matrix import router as prompt_matrix_router
from app.api.admin.proxy_pool import router as proxy_pool_router
from app.api.admin.query_pool import router as query_pool_router
from app.api.admin.scheduler import router as scheduler_router
from app.api.admin.segments import router as segments_router
from app.api.admin.session import router as session_router
from app.api.admin.stats import router as stats_router
from app.api.admin.topic_plan import router as topic_plan_router
from app.api.admin.users import router as users_router
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin"])
router.include_router(accounts_router, prefix="/accounts")
router.include_router(alerts_router, prefix="/alerts")
router.include_router(brand_management_router, prefix="/brand-management")
router.include_router(brand_submissions_router, prefix="/brand-submissions")
router.include_router(comms_router, prefix="/comms")
router.include_router(cost_router, prefix="/cost")
router.include_router(diagnostics_router, prefix="/diagnostics")
router.include_router(engine_health_router, prefix="/engine-health")
router.include_router(hot_topics_router, prefix="")
router.include_router(kg_candidates_router, prefix="/kg-candidates")
router.include_router(kg_discovery_router, prefix="/kg-discovery")
router.include_router(leads_router, prefix="/leads")
router.include_router(llm_extraction_router, prefix="/llm-extraction")
router.include_router(mcp_ops_router, prefix="/mcp-ops")
router.include_router(projects_router, prefix="/projects")
router.include_router(proxy_pool_router, prefix="/proxy-pool")
router.include_router(prompt_matrix_router, prefix="/prompt-matrix")
router.include_router(query_pool_router, prefix="/query-pool")
router.include_router(products_router, prefix="")
router.include_router(scheduler_router, prefix="")
router.include_router(segments_router, prefix="/segments")
router.include_router(session_router, prefix="/session")
router.include_router(stats_router, prefix="/stats")
router.include_router(topic_plan_router, prefix="/topic-plan")
router.include_router(users_router, prefix="/users")


@router.get("/brands", response_model=None)
async def admin_brand_options(
    operator: Annotated[AdminUser, Depends(current_admin)],
    session: AsyncSession = _DependsDb,
) -> Any:
    """Topic-plan brand picker. Returns ``{success, brands}`` with each
    brand enriched with topic_count + primary category. Mirrors
    admin_console line 5886 — final route from Flask, ported in Phase X.

    Auth: cookie-based ``current_admin`` (same as every other admin SPA
    route). ``current_admin_operator`` requires a Bearer JWT and would
    silently 401 the SPA, leaving every brand picker (segments, products,
    LLM auto-add product, LLM 生成 Brand Segment, etc.) empty.
    """
    brands = await brand_management_db.fetch_brand_options_with_topic_count(session)
    return {"success": True, "brands": brands}


@router.get("/_meta/whoami")
async def admin_meta_whoami(request: Request) -> dict[str, object]:
    """Diagnostic: report what backend sees about the caller's session.

    No auth required — that's the point. Use this when 401s land on
    other admin routes to figure out which side of the cookie bridge
    is broken (cookie not received vs. cookie received but session
    decode produced an empty payload).

    Returns:
    - ``cookie_present``: was ``genpano_admin_session`` in Cookie header
    - ``session_keys``: list of keys in ``request.session`` (decrypted)
    - ``admin_user_id``: value of ``request.session['admin_user_id']``
      if present (else ``None``)
    - ``forwarded_proto``: X-Forwarded-Proto header (helps spot HTTP
      vs HTTPS proxy mismatch causing Secure-cookie drop)
    - ``host``: X-Forwarded-Host or Host
    """
    cookie_present = "genpano_admin_session" in request.cookies
    session_keys = sorted(request.session.keys())
    admin_user_id = request.session.get("admin_user_id")
    return {
        "cookie_present": cookie_present,
        "session_keys": session_keys,
        "admin_user_id": admin_user_id,
        "forwarded_proto": request.headers.get("x-forwarded-proto"),
        "host": request.headers.get("x-forwarded-host") or request.headers.get("host"),
    }


@router.get("/_meta/routes")
async def admin_meta_routes(
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
) -> dict[str, object]:
    """List all registered admin routes (operator-only)."""
    items: list[dict[str, object]] = []
    for route in request.app.routes:
        if not (hasattr(route, "methods") and hasattr(route, "path")):
            continue
        path = route.path
        if not path.startswith("/api/admin"):
            continue
        items.append(
            {
                "path": path,
                "methods": sorted(route.methods - {"HEAD", "OPTIONS"}),
                "name": route.name,
            }
        )
    return {"items": items, "count": len(items)}


def _build_audit_query(
    *,
    action: str | None = None,
    severity: str | None = None,
    operator_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> Any:
    """Compose the AdminAuditLog filter chain shared by list + export."""
    stmt = select(AdminAuditLog).order_by(AdminAuditLog.occurred_at.desc())
    if action:
        stmt = stmt.where(AdminAuditLog.action == action)
    if severity:
        stmt = stmt.where(AdminAuditLog.severity == severity)
    if operator_id:
        stmt = stmt.where(AdminAuditLog.operator_id == operator_id)
    if resource_type:
        stmt = stmt.where(AdminAuditLog.resource_type == resource_type)
    if resource_id:
        stmt = stmt.where(AdminAuditLog.resource_id == resource_id)
    if from_date:
        try:
            d = datetime.fromisoformat(from_date)
        except ValueError:
            pass
        else:
            stmt = stmt.where(AdminAuditLog.occurred_at >= d)
    if to_date:
        try:
            d = datetime.fromisoformat(to_date)
        except ValueError:
            pass
        else:
            stmt = stmt.where(AdminAuditLog.occurred_at <= d)
    return stmt


@router.get("/audit-log")
async def admin_audit_log(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    action: str | None = Query(None),
    severity: str | None = Query(None),
    operator_id: str | None = Query(None),
    resource_type: str | None = Query(None),
    resource_id: str | None = Query(None),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, object]:
    """List admin audit log (operator scope, ADR-014).

    Filters: action, severity, operator_id, resource_type, resource_id,
    from / to (ISO datetime). All optional; combined with AND.
    """
    stmt = _build_audit_query(
        action=action,
        severity=severity,
        operator_id=operator_id,
        resource_type=resource_type,
        resource_id=resource_id,
        from_date=from_date,
        to_date=to_date,
    ).limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())
    items = [
        {
            "id": r.id,
            "operator_id": r.operator_id,
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "severity": r.severity,
            "ip": r.ip,
            "reason": r.reason,
            "occurred_at": r.occurred_at.isoformat(),
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


@router.get("/audit-log/export.csv")
async def admin_audit_log_export_csv(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    action: str | None = Query(None),
    severity: str | None = Query(None),
    operator_id: str | None = Query(None),
    resource_type: str | None = Query(None),
    resource_id: str | None = Query(None),
    from_date: str | None = Query(None, alias="from"),
    to_date: str | None = Query(None, alias="to"),
    limit: int = Query(5000, ge=1, le=50000),
) -> Any:
    """Export filtered admin audit log as CSV (ADMIN_PRD §4.4.7)."""
    import csv
    import io

    from fastapi.responses import StreamingResponse

    stmt = _build_audit_query(
        action=action,
        severity=severity,
        operator_id=operator_id,
        resource_type=resource_type,
        resource_id=resource_id,
        from_date=from_date,
        to_date=to_date,
    ).limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "id",
            "occurred_at",
            "operator_id",
            "action",
            "resource_type",
            "resource_id",
            "severity",
            "ip",
            "reason",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r.id,
                r.occurred_at.isoformat(),
                r.operator_id,
                r.action,
                r.resource_type,
                r.resource_id or "",
                r.severity,
                r.ip or "",
                (r.reason or "").replace("\n", " "),
            ]
        )
    buf.seek(0)
    headers = {
        "Content-Disposition": (
            f"attachment; filename=audit_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        )
    }
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers=headers)


# ── Demo: high-risk mutation with @audit decorator ────────────────


@router.post("/_demo/test-mutation")
async def admin_demo_mutation(
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
) -> dict[str, str]:
    """Demo endpoint that emits an audit log entry.

    Used by Phase R.4 self-test to verify emit_audit() works end-to-end.
    Real Phase R.4 sub-router PRs will migrate actual admin_console mutations.
    """
    await emit_audit(
        session,
        operator=operator,
        action="config_change",
        severity="high",
        resource_type="config",
        request=request,
    )
    return {"status": "ok", "ts": datetime.now().isoformat()}


# ── Sub-router migration status (auto-detected from routes) ──────


# Phase R.4 originally listed 13 stubs from admin_console Flask. Phase O
# expanded this with operator-side sub-routers that don't map 1:1 to the
# original Flask routes (cost, comms, mcp_ops, leads, alerts, etc.).
#
# Master list of all expected sub-routers (Phase R.4 originals + Phase O
# additions). Order shown to operator preserves PRD reading order.
SUB_ROUTERS: list[str] = [
    # Phase R.4 originals (admin_console migration targets)
    "session",
    "brands",
    "topic_plan",
    "prompt_matrix",
    "query_pool",
    "scheduler",
    "segments",
    "profiles",
    "accounts",
    "users",
    "analyzer",
    "artifacts",
    "stats",
    # Phase O additions (new operator surfaces)
    "alerts",
    "comms",
    "cost",
    "engine_health",
    "kg_discovery",
    "leads",
    "llm_extraction",
    "mcp_ops",
    "proxy_pool",
]


def _sub_router_path_segments(app_routes: list[object]) -> set[str]:
    """Extract registered sub-router segments from /api/admin/{seg}/... paths."""
    seen: set[str] = set()
    for route in app_routes:
        if not (hasattr(route, "path") and hasattr(route, "methods")):
            continue
        path = getattr(route, "path", "")
        if not path.startswith("/api/admin/"):
            continue
        rest = path[len("/api/admin/") :]
        if not rest or rest.startswith("_"):
            continue
        segment = rest.split("/", 1)[0]
        # Hyphen → underscore so URL `mcp-ops` matches package `mcp_ops`
        seen.add(segment.replace("-", "_"))
    return seen


@router.get("/_meta/sub-routers")
async def admin_sub_routers_status(
    request: Request,
    operator: Annotated[User, Depends(current_admin_operator)],
) -> dict[str, object]:
    """Migration status: which sub-routers are wired vs pending.

    Auto-detects 'wired' from the live FastAPI route table — the moment a
    new sub-router lands and registers any path under /api/admin/<name>/,
    this view flips to 'wired'. No manual list bumps required.
    """
    wired_segments = _sub_router_path_segments(list(request.app.routes))
    items = [
        {
            "name": name,
            "status": "wired" if name in wired_segments else "pending",
        }
        for name in SUB_ROUTERS
    ]
    wired_count = sum(1 for it in items if it["status"] == "wired")
    return {
        "items": items,
        "total": len(items),
        "wired": wired_count,
        "pending": len(items) - wired_count,
        "note": "Status is auto-detected from live FastAPI route table.",
    }
