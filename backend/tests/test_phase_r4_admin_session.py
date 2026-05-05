"""Phase R.4 — admin session sub-router (operator identity + dashboard meta)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, Alert, Diagnostic, User
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
        name="Admin Op",
        role="paid",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
        last_login_at=_now() - timedelta(hours=2),
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"u-{uuid.uuid4().hex[:6]}@example.com",
        name="Regular",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


# ── /me ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_me_returns_operator_identity(client, admin_operator):
    resp = await client.get("/api/admin/session/me", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == admin_operator.id
    assert body["email"] == admin_operator.email
    assert body["role"] == "paid"
    assert body["audit_actions_24h"] == 0
    assert body["last_audit_at"] is None
    assert "as_of" in body
    # Password hash is never exposed
    assert "password_hash" not in body


@pytest.mark.asyncio
async def test_me_counts_recent_audits(client, admin_operator, db_session: AsyncSession):
    now = _now()
    db_session.add_all(
        [
            AdminAuditLog(
                id=_new_id(),
                operator_id=admin_operator.id,
                action="config_change",
                resource_type="config",
                severity="med",
                occurred_at=now,
            ),
            AdminAuditLog(
                id=_new_id(),
                operator_id=admin_operator.id,
                action="alert_update",
                resource_type="alert",
                severity="low",
                occurred_at=now - timedelta(hours=2),
            ),
            # Older than 24h - excluded
            AdminAuditLog(
                id=_new_id(),
                operator_id=admin_operator.id,
                action="ancient",
                resource_type="x",
                severity="low",
                occurred_at=now - timedelta(hours=48),
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/session/me", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["audit_actions_24h"] == 2
    assert body["last_audit_at"] is not None


@pytest.mark.asyncio
async def test_me_excludes_other_operators_audits(client, admin_operator, db_session: AsyncSession):
    """audit_actions_24h is per-operator, not global."""
    other_op = User(
        id=_new_id(),
        email=f"other-{uuid.uuid4().hex[:6]}@example.com",
        name="Other",
        role="paid",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(other_op)
    await db_session.commit()

    db_session.add(
        AdminAuditLog(
            id=_new_id(),
            operator_id=other_op.id,
            action="x",
            resource_type="x",
            severity="low",
            occurred_at=_now(),
        )
    )
    await db_session.commit()

    resp = await client.get("/api/admin/session/me", headers=_bearer(admin_operator))
    assert resp.json()["audit_actions_24h"] == 0


@pytest.mark.asyncio
async def test_me_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/session/me", headers=_bearer(regular_user))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_me_unauth_401(client):
    resp = await client.get("/api/admin/session/me")
    assert resp.status_code == 401


# ── /dashboard-meta ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_dashboard_meta_zero_state(client, admin_operator):
    resp = await client.get("/api/admin/session/dashboard-meta", headers=_bearer(admin_operator))
    body = resp.json()
    counters = body["counters"]
    assert counters["unread_operator_alerts"] == 0
    assert counters["open_p0_p1_diagnostics"] == 0
    assert counters["audits_24h_total"] == 0
    assert counters["high_risk_audits_24h"] == 0


@pytest.mark.asyncio
async def test_dashboard_meta_aggregates(client, admin_operator, db_session: AsyncSession):
    now = _now()
    db_session.add_all(
        [
            Alert(
                id=_new_id(),
                scope="operator",
                source="cost_overrun",
                severity="P1",
                title="alert 1",
                status="unread",
                triggered_at=now,
            ),
            Alert(
                id=_new_id(),
                scope="operator",
                source="cost_overrun",
                severity="P0",
                title="alert 2",
                status="unread",
                triggered_at=now,
            ),
            # User-scope alert excluded
            Alert(
                id=_new_id(),
                scope="user",
                source="diagnostic",
                severity="P1",
                title="user-side",
                status="unread",
                triggered_at=now,
            ),
            # Already read excluded
            Alert(
                id=_new_id(),
                scope="operator",
                source="x",
                severity="P2",
                title="read",
                status="read",
                triggered_at=now,
            ),
        ]
    )
    await db_session.commit()

    db_session.add_all(
        [
            Diagnostic(
                id=_new_id(),
                project_id="p1",
                category="visibility_decline",
                severity="P0",
                type="brand",
                title="d1",
                rule_id="r1",
                evidence={},
                reader_hints=["manager"],
                status="open",
            ),
            Diagnostic(
                id=_new_id(),
                project_id="p1",
                category="sentiment_drop",
                severity="P1",
                type="brand",
                title="d2",
                rule_id="r2",
                evidence={},
                reader_hints=["manager"],
                status="open",
            ),
            # P3 excluded
            Diagnostic(
                id=_new_id(),
                project_id="p1",
                category="topic_loss",
                severity="P3",
                type="brand",
                title="d3-low",
                rule_id="r3",
                evidence={},
                reader_hints=["manager"],
                status="open",
            ),
            # Resolved excluded
            Diagnostic(
                id=_new_id(),
                project_id="p1",
                category="x",
                severity="P0",
                type="brand",
                title="d4-resolved",
                rule_id="r4",
                evidence={},
                reader_hints=["manager"],
                status="resolved",
            ),
        ]
    )
    await db_session.commit()

    db_session.add_all(
        [
            AdminAuditLog(
                id=_new_id(),
                operator_id=admin_operator.id,
                action="freeze_user",  # HIGH_RISK_ACTIONS
                resource_type="user",
                severity="high",
                occurred_at=now,
            ),
            AdminAuditLog(
                id=_new_id(),
                operator_id=admin_operator.id,
                action="alert_update",  # not high-risk
                resource_type="alert",
                severity="med",
                occurred_at=now,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/session/dashboard-meta", headers=_bearer(admin_operator))
    counters = resp.json()["counters"]
    assert counters["unread_operator_alerts"] == 2
    assert counters["open_p0_p1_diagnostics"] == 2
    assert counters["audits_24h_total"] == 2
    assert counters["high_risk_audits_24h"] == 1


@pytest.mark.asyncio
async def test_dashboard_meta_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/session/dashboard-meta", headers=_bearer(regular_user))
    assert resp.status_code == 403


# ── audit gate ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_gate_with_session_no_writes():
    """session sub-router has only GET endpoints — gate must still pass."""
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
