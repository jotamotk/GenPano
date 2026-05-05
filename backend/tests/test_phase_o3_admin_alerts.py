"""Phase O.3.1 — admin alerts sub-router (operator-scope alerts CRUD)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, Alert, User
from sqlalchemy import select
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


@pytest_asyncio.fixture
async def operator_alert(db_session: AsyncSession) -> Alert:
    a = Alert(
        id=_new_id(),
        project_id=None,
        source="engine_health",
        source_ref_id=None,
        severity="P1",
        scope="operator",
        title="Engine success rate < 80%",
        body="ChatGPT engine success rate dropped to 72% in last 24h",
        status="unread",
        triggered_at=_now(),
    )
    db_session.add(a)
    await db_session.commit()
    return a


@pytest_asyncio.fixture
async def user_scope_alert(db_session: AsyncSession) -> Alert:
    """User-scope alert that admin endpoints must NOT see."""
    a = Alert(
        id=_new_id(),
        project_id="proj-x",
        source="diagnostic",
        severity="P1",
        scope="user",
        title="user-scope only",
        status="unread",
        triggered_at=_now(),
    )
    db_session.add(a)
    await db_session.commit()
    return a


# ── list ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_admin_alerts_returns_operator_only(
    client, admin_operator, operator_alert, user_scope_alert
):
    resp = await client.get("/api/admin/alerts/", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    body = resp.json()
    ids = {it["id"] for it in body["items"]}
    assert operator_alert.id in ids
    assert user_scope_alert.id not in ids


@pytest.mark.asyncio
async def test_list_admin_alerts_filters_by_status(client, admin_operator, operator_alert):
    resp = await client.get(
        "/api/admin/alerts/?status=unread",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_list_admin_alerts_non_operator_403(client, regular_user, operator_alert):
    resp = await client.get("/api/admin/alerts/", headers=_bearer(regular_user))
    assert resp.status_code == 403


# ── update ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_alert_status_emits_audit(client, admin_operator, operator_alert, db_session):
    resp = await client.patch(
        f"/api/admin/alerts/{operator_alert.id}",
        headers=_bearer(admin_operator),
        json={"status": "resolved"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"

    # Verify audit log row exists
    rows = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "alert_update",
                    AdminAuditLog.resource_id == operator_alert.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].operator_id == admin_operator.id


@pytest.mark.asyncio
async def test_update_alert_invalid_status_422(client, admin_operator, operator_alert):
    resp = await client.patch(
        f"/api/admin/alerts/{operator_alert.id}",
        headers=_bearer(admin_operator),
        json={"status": "bogus"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_unknown_alert_404(client, admin_operator):
    resp = await client.patch(
        "/api/admin/alerts/no-such-id",
        headers=_bearer(admin_operator),
        json={"status": "resolved"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_user_scope_alert_404(client, admin_operator, user_scope_alert):
    """User-scope alerts must NOT be reachable via admin endpoint."""
    resp = await client.patch(
        f"/api/admin/alerts/{user_scope_alert.id}",
        headers=_bearer(admin_operator),
        json={"status": "resolved"},
    )
    assert resp.status_code == 404


# ── bulk read ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_all_read_updates_unread_only(
    client, admin_operator, operator_alert, db_session
):
    # Create a second unread + a read alert
    second = Alert(
        id=_new_id(),
        source="cost_overrun",
        severity="P0",
        scope="operator",
        title="Daily LLM cost > $500",
        status="unread",
        triggered_at=_now(),
    )
    third = Alert(
        id=_new_id(),
        source="manual",
        severity="P2",
        scope="operator",
        title="Already read",
        status="read",
        triggered_at=_now(),
    )
    db_session.add_all([second, third])
    await db_session.commit()

    resp = await client.post(
        "/api/admin/alerts/mark-all-read",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 200
    assert resp.json()["updated"] == 2  # operator_alert + second; not third


@pytest.mark.asyncio
async def test_admin_alerts_routes_pass_audit_coverage_gate():
    """Phase O.2 gate must accept the new alerts router (PATCH + POST mutations)."""
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
