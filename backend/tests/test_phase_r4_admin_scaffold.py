"""Phase R.4 — admin scaffold (audit decorator + admin auth + meta routes)."""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def admin_operator(db_session: AsyncSession) -> User:
    """User with role='paid' (treated as admin during R.4 migration)."""
    u = User(
        id=_new_id(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        name="Admin",
        role="paid",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"user-{uuid.uuid4().hex[:6]}@example.com",
        name="User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest.mark.asyncio
async def test_admin_meta_requires_admin_role(client, regular_user):
    """Non-admin user → 403."""
    resp = await client.get("/api/admin/_meta/routes", headers=_bearer(regular_user))
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "forbidden"


@pytest.mark.asyncio
async def test_admin_meta_with_operator(client, admin_operator):
    """Admin operator can access; sees admin routes."""
    resp = await client.get("/api/admin/_meta/routes", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] >= 3
    paths = {it["path"] for it in body["items"]}
    assert "/api/admin/_meta/routes" in paths
    assert "/api/admin/audit-log" in paths


@pytest.mark.asyncio
async def test_admin_no_auth_returns_401(client):
    resp = await client.get("/api/admin/_meta/routes")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_sub_routers_status_lists_originals_and_phase_o(client, admin_operator):
    """Sub-router status list includes Phase R.4 originals + Phase O additions."""
    resp = await client.get("/api/admin/_meta/sub-routers", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    body = resp.json()
    # Phase R.4 originals (13) + Phase O operator surfaces
    assert body["total"] >= 13
    actual = {it["name"] for it in body["items"]}
    # All 13 Phase R.4 originals must remain in the list
    originals = {
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
    }
    assert originals.issubset(actual)


@pytest.mark.asyncio
async def test_admin_sub_routers_auto_detect_wired_status(client, admin_operator):
    """Wired sub-routers (e.g. users) are flipped to status='wired' automatically."""
    resp = await client.get("/api/admin/_meta/sub-routers", headers=_bearer(admin_operator))
    body = resp.json()
    by_name = {it["name"]: it["status"] for it in body["items"]}
    # users sub-router was migrated in PR #247
    assert by_name["users"] == "wired"
    # session sub-router was migrated in subsequent PR (admin /me + dashboard meta)
    assert by_name["session"] == "wired"
    # topic_plan candidate review wired in Phase 3 B.1; B.2/B.3 add the
    # remaining 8 routes (config / coverage / topics / runs / generate / delete)
    assert by_name["topic_plan"] == "wired"
    # wired count matches what we see
    assert body["wired"] == sum(1 for it in body["items"] if it["status"] == "wired")
    assert body["pending"] == sum(1 for it in body["items"] if it["status"] == "pending")


@pytest.mark.asyncio
async def test_audit_decorator_emits_log_on_success(client, admin_operator, db_session):
    """Calling a @audit-wrapped admin endpoint inserts admin_audit_log row."""
    resp = await client.post("/api/admin/_demo/test-mutation", headers=_bearer(admin_operator))
    assert resp.status_code == 200

    stmt = select(AdminAuditLog).where(
        AdminAuditLog.operator_id == admin_operator.id,
        AdminAuditLog.action == "config_change",
    )
    rows = list((await db_session.execute(stmt)).scalars().all())
    assert len(rows) == 1
    assert rows[0].severity == "high"
    assert rows[0].resource_type == "config"


@pytest.mark.asyncio
async def test_audit_log_endpoint_lists_recent(client, admin_operator):
    """GET /api/admin/audit-log returns recent rows after a mutation."""
    # Trigger a mutation
    await client.post("/api/admin/_demo/test-mutation", headers=_bearer(admin_operator))

    resp = await client.get("/api/admin/audit-log", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert any(it["action"] == "config_change" for it in body["items"])


@pytest.mark.asyncio
async def test_high_risk_actions_constant_completeness():
    """HIGH_RISK_ACTIONS list has 13 entries per PRD addendum §5.7."""
    from app.admin.audit import HIGH_RISK_ACTIONS

    assert len(HIGH_RISK_ACTIONS) == 13
    assert "freeze_user" in HIGH_RISK_ACTIONS
    assert "brand_merge" in HIGH_RISK_ACTIONS
    assert "config_change" in HIGH_RISK_ACTIONS
