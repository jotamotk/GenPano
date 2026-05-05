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
from app.api.admin.leads import router as leads_router
from app.api.admin.mcp_ops import router as mcp_ops_router
from app.api.admin.stats import router as stats_router
from app.api.admin.users import router as users_router
from app.core.security import _DependsDb

router = APIRouter(tags=["Admin"])
router.include_router(alerts_router, prefix="/alerts")
router.include_router(comms_router, prefix="/comms")
router.include_router(cost_router, prefix="/cost")
router.include_router(leads_router, prefix="/leads")
router.include_router(mcp_ops_router, prefix="/mcp-ops")
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


# ── Sub-router stubs (Phase R.4 follow-up PRs migrate each) ───────


# These are intentionally empty so each sub-router can be opened in
# its own PR migrating routes from admin_console/app.py one by one.
# When migrating, each PR adds: app/api/admin/<name>/router.py + tests.
SUB_ROUTERS: list[str] = [
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
]


@router.get("/_meta/sub-routers")
async def admin_sub_routers_status(
    operator: Annotated[User, Depends(current_admin_operator)],
) -> dict[str, object]:
    """Migration status: which Phase R.4 sub-routers are wired vs pending."""
    return {
        "items": [{"name": name, "status": "pending"} for name in SUB_ROUTERS],
        "total": len(SUB_ROUTERS),
        "note": "Each sub-router migrated in dedicated PR; see docs/ADR/001.",
    }
