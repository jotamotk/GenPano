"""Admin API top-level aggregator router.

Mounts at `/api/admin/*`. Sub-routers add deeper paths.

Phase R.4 ships:
- `_meta/routes` — admin route introspection
- `_meta/audit-log` — list audit log (for self-test of `@audit` decorator)
- 13 sub-package skeletons (each empty for now)
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from genpano_models import AdminAuditLog, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.audit import emit_audit
from app.admin.security import current_admin_operator
from app.api.admin.alerts import router as alerts_router
from app.api.admin.comms import router as comms_router
from app.api.admin.cost import router as cost_router
from app.api.admin.engine_health import router as engine_health_router
from app.api.admin.kg_discovery import router as kg_discovery_router
from app.api.admin.leads import router as leads_router
from app.api.admin.mcp_ops import router as mcp_ops_router
from app.api.admin.proxy_pool import router as proxy_pool_router
from app.api.admin.stats import router as stats_router
from app.api.admin.users import router as users_router
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin"])
router.include_router(alerts_router, prefix="/alerts")
router.include_router(comms_router, prefix="/comms")
router.include_router(cost_router, prefix="/cost")
router.include_router(engine_health_router, prefix="/engine-health")
router.include_router(kg_discovery_router, prefix="/kg-discovery")
router.include_router(leads_router, prefix="/leads")
router.include_router(mcp_ops_router, prefix="/mcp-ops")
router.include_router(proxy_pool_router, prefix="/proxy-pool")
router.include_router(stats_router, prefix="/stats")
router.include_router(users_router, prefix="/users")


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


@router.get("/audit-log")
async def admin_audit_log(
    operator: Annotated[User, Depends(current_admin_operator)],
    session: AsyncSession = _DependsDb,
    action: str | None = Query(None),
    severity: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, object]:
    """List admin audit log (operator scope, ADR-014)."""
    stmt = select(AdminAuditLog).order_by(AdminAuditLog.occurred_at.desc()).limit(limit)
    if action:
        stmt = stmt.where(AdminAuditLog.action == action)
    if severity:
        stmt = stmt.where(AdminAuditLog.severity == severity)
    rows = list((await session.execute(stmt)).scalars().all())
    items = [
        {
            "id": r.id,
            "operator_id": r.operator_id,
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "severity": r.severity,
            "occurred_at": r.occurred_at.isoformat(),
        }
        for r in rows
    ]
    return {"items": items, "total": len(items)}


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
