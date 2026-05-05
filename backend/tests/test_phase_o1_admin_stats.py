"""Phase O.1 — admin stats sub-router (read-only operator KPI counters)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from genpano_models import (
    AdminAuditLog,
    Alert,
    Diagnostic,
    Project,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def admin_operator(db_session: AsyncSession) -> User:
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


# ── overview ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_overview_zero_state(client, admin_operator):
    """Fresh DB returns zero counters (except the admin user itself)."""
    resp = await client.get("/api/admin/stats/overview", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    body = resp.json()
    counters = body["counters"]
    assert counters["total_users"] == 1  # admin operator counts
    assert counters["active_projects"] == 0
    assert counters["open_diagnostics"] == 0
    assert counters["unread_operator_alerts"] == 0
    assert "as_of" in body


@pytest.mark.asyncio
async def test_overview_counts_real_data(
    client, admin_operator, regular_user, db_session: AsyncSession
):
    """Counters reflect real fixture state."""
    p = Project(user_id=regular_user.id, name="P", primary_brand_id=1)
    db_session.add(p)
    await db_session.commit()

    diag = Diagnostic(
        id=_new_id(),
        project_id=p.id,
        category="visibility_decline",
        severity="P1",
        type="brand",
        title="visibility down",
        rule_id="visibility_decline_v1",
        evidence={},
        reader_hints=["manager"],
        status="open",
    )
    a = Alert(
        id=_new_id(),
        scope="operator",
        source="engine_health",
        severity="P0",
        title="engine down",
        status="unread",
        triggered_at=_now(),
    )
    db_session.add_all([diag, a])
    await db_session.commit()

    resp = await client.get("/api/admin/stats/overview", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    counters = resp.json()["counters"]
    assert counters["total_users"] == 2  # admin + regular
    assert counters["active_projects"] == 1
    assert counters["open_diagnostics"] == 1
    assert counters["unread_operator_alerts"] == 1


@pytest.mark.asyncio
async def test_overview_excludes_soft_deleted_projects(
    client, admin_operator, regular_user, db_session: AsyncSession
):
    p = Project(user_id=regular_user.id, name="P", primary_brand_id=1, deleted_at=_now())
    db_session.add(p)
    await db_session.commit()

    resp = await client.get("/api/admin/stats/overview", headers=_bearer(admin_operator))
    assert resp.json()["counters"]["active_projects"] == 0


@pytest.mark.asyncio
async def test_overview_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/stats/overview", headers=_bearer(regular_user))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_overview_unauth_401(client):
    resp = await client.get("/api/admin/stats/overview")
    assert resp.status_code == 401


# ── audit-summary ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_summary_aggregates_by_severity(
    client, admin_operator, db_session: AsyncSession
):
    rows = [
        AdminAuditLog(
            id=_new_id(),
            operator_id=admin_operator.id,
            action=f"a{i}",
            resource_type="x",
            severity=sev,
            occurred_at=_now(),
        )
        for i, sev in enumerate(["high", "high", "med", "low", "low", "low"])
    ]
    db_session.add_all(rows)
    await db_session.commit()

    resp = await client.get("/api/admin/stats/audit-summary", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    body = resp.json()
    assert body["window_hours"] == 24
    assert body["total"] == 6
    assert body["by_severity"]["high"] == 2
    assert body["by_severity"]["med"] == 1
    assert body["by_severity"]["low"] == 3


@pytest.mark.asyncio
async def test_audit_summary_window_excludes_old_rows(
    client, admin_operator, db_session: AsyncSession
):
    """Rows older than 24h should not appear."""
    from datetime import timedelta

    old = AdminAuditLog(
        id=_new_id(),
        operator_id=admin_operator.id,
        action="ancient",
        resource_type="x",
        severity="high",
        occurred_at=_now() - timedelta(hours=48),
    )
    fresh = AdminAuditLog(
        id=_new_id(),
        operator_id=admin_operator.id,
        action="recent",
        resource_type="x",
        severity="med",
        occurred_at=_now(),
    )
    db_session.add_all([old, fresh])
    await db_session.commit()

    resp = await client.get("/api/admin/stats/audit-summary", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["total"] == 1
    assert body["by_severity"] == {"med": 1}


@pytest.mark.asyncio
async def test_audit_summary_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/stats/audit-summary", headers=_bearer(regular_user))
    assert resp.status_code == 403


# ── coverage gate ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_with_stats_router_no_writes():
    """Stats router has only GET endpoints — gate must still pass."""
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
