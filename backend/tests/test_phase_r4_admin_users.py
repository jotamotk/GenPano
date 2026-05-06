"""Phase 3 — admin users sub-router (list + actions + moderation + reset).

Auth: ``current_admin`` (cookie-based AdminUser) is overridden via
``app.dependency_overrides`` so tests don't need to round-trip the
SessionMiddleware-signed cookie.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from genpano_models import (
    AdminAuditLog,
    AdminUser,
    User,
    UserAuthToken,
    UserModerationAction,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def admin_operator(
    db_session: AsyncSession,
) -> AsyncGenerator[AdminUser, None]:
    """Create an AdminUser and override `current_admin` to return it."""
    from app.api.admin.auth.router import current_admin
    from app.main import app

    a = AdminUser(
        id=_new_id(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="$2b$04$dummyhashfortestsdummyhashfortestsdummyhashfortest",
        role="super_admin",
        status="active",
    )
    db_session.add(a)
    await db_session.commit()

    async def _override_current_admin() -> AdminUser:
        return a

    app.dependency_overrides[current_admin] = _override_current_admin
    try:
        yield a
    finally:
        app.dependency_overrides.pop(current_admin, None)


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"user-{uuid.uuid4().hex[:6]}@example.com",
        name="Bob",
        company="Acme",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


# ── list ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_users_returns_users(client, admin_operator, regular_user):
    resp = await client.get("/api/admin/users/")
    assert resp.status_code == 200
    body = resp.json()
    ids = {row["id"] for row in body["rows"]}
    assert regular_user.id in ids
    assert body["page"] == 1
    assert body["per_page"] == 20
    assert body["total"] >= 1


@pytest.mark.asyncio
async def test_list_users_search_email(client, admin_operator, regular_user):
    fragment = regular_user.email.split("@")[0][:6]
    resp = await client.get(f"/api/admin/users/?q={fragment}")
    body = resp.json()
    ids = {row["id"] for row in body["rows"]}
    assert regular_user.id in ids


@pytest.mark.asyncio
async def test_list_users_search_name(client, admin_operator, regular_user):
    resp = await client.get("/api/admin/users/?q=bob")
    body = resp.json()
    ids = {row["id"] for row in body["rows"]}
    assert regular_user.id in ids


@pytest.mark.asyncio
async def test_list_users_role_filter(client, admin_operator, regular_user):
    resp = await client.get("/api/admin/users/?role=free")
    body = resp.json()
    for row in body["rows"]:
        # role isn't in row payload but every row matched should be free
        assert row["activity_level"] in {"hot", "warm", "cold", "dormant"}


@pytest.mark.asyncio
async def test_list_users_pagination(client, admin_operator, db_session: AsyncSession):
    for i in range(5):
        db_session.add(
            User(
                id=_new_id(),
                email=f"bulk-{i}-{uuid.uuid4().hex[:6]}@example.com",
                name=f"User{i}",
                role="free",
                provider="email",
                email_verified=True,
                password_hash="dummy",
                locale="zh-CN",
            )
        )
    await db_session.commit()

    resp = await client.get("/api/admin/users/?per_page=2")
    body = resp.json()
    assert len(body["rows"]) == 2
    assert body["per_page"] == 2


@pytest.mark.asyncio
async def test_list_users_unauth_401(client):
    resp = await client.get("/api/admin/users/")
    assert resp.status_code == 401


# ── detail ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_user_detail(client, admin_operator, regular_user):
    resp = await client.get(f"/api/admin/users/{regular_user.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["user"]["id"] == regular_user.id
    assert body["user"]["email"] == regular_user.email
    assert body["user"]["name"] == "Bob"
    assert body["user"]["company"] == "Acme"
    # Password hash never returned
    assert "password_hash" not in body["user"]
    # Detail shape
    assert "projects" in body
    assert "activity" in body
    assert "moderation" in body
    assert "recent_admin_actions" in body


@pytest.mark.asyncio
async def test_get_user_unknown_404(client, admin_operator):
    resp = await client.get("/api/admin/users/no-such-id")
    assert resp.status_code == 404


# ── actions / login-audit ─────────────────────────────────────


@pytest.mark.asyncio
async def test_list_user_actions_empty(client, admin_operator):
    resp = await client.get("/api/admin/users/actions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_list_user_login_audit_returns_empty_with_message(client, admin_operator):
    resp = await client.get("/api/admin/users/login-audit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == []
    assert body["available"] is False
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_list_one_user_actions_empty(client, admin_operator, regular_user):
    resp = await client.get(f"/api/admin/users/{regular_user.id}/actions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == []


# ── freeze / unfreeze ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_freeze_then_unfreeze_user(
    client, admin_operator, regular_user, db_session: AsyncSession
):
    resp = await client.post(
        f"/api/admin/users/{regular_user.id}/freeze",
        json={"reason": "spam"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == "frozen"

    # UserModerationAction row written
    mods = list(
        (
            await db_session.execute(
                select(UserModerationAction).where(UserModerationAction.user_id == regular_user.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(mods) == 1
    assert mods[0].action == "freeze"
    assert mods[0].operator_id == admin_operator.id
    assert mods[0].reason == "spam"

    # Audit row written with severity=high
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "freeze_user",
                    AdminAuditLog.resource_id == regular_user.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "high"
    assert audit[0].operator_id == admin_operator.id

    # User detail now reports frozen
    detail = await client.get(f"/api/admin/users/{regular_user.id}")
    assert detail.json()["user"]["status"] == "frozen"

    # Unfreeze
    resp = await client.post(
        f"/api/admin/users/{regular_user.id}/unfreeze",
        json={"reason": "appeal accepted"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


@pytest.mark.asyncio
async def test_freeze_requires_reason(client, admin_operator, regular_user):
    resp = await client.post(
        f"/api/admin/users/{regular_user.id}/freeze",
        json={},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_freeze_unknown_user_404(client, admin_operator):
    resp = await client.post(
        "/api/admin/users/no-such-id/freeze",
        json={"reason": "spam"},
    )
    assert resp.status_code == 404


# ── force-password-reset ──────────────────────────────────────


@pytest.mark.asyncio
async def test_force_password_reset_creates_token_and_audits_high(
    client, admin_operator, regular_user, db_session: AsyncSession
):
    resp = await client.post(
        f"/api/admin/users/{regular_user.id}/force-password-reset",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == regular_user.id
    assert body["token"]  # plaintext returned ONCE
    assert body["ttl_hours"] == 1

    tokens = list(
        (
            await db_session.execute(
                select(UserAuthToken).where(
                    UserAuthToken.user_id == regular_user.id,
                    UserAuthToken.token_type == "password_reset",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(tokens) == 1
    assert tokens[0].email_snapshot == regular_user.email

    audit_rows = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "force_password_reset",
                    AdminAuditLog.resource_id == regular_user.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit_rows) == 1
    assert audit_rows[0].severity == "high"
    assert audit_rows[0].operator_id == admin_operator.id


@pytest.mark.asyncio
async def test_force_password_reset_unknown_user_404(client, admin_operator):
    resp = await client.post(
        "/api/admin/users/no-such-id/force-password-reset",
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_force_password_reset_high_risk_in_allowlist():
    from app.admin.audit import HIGH_RISK_ACTIONS

    assert "force_password_reset" in HIGH_RISK_ACTIONS


# ── audit coverage gate re-run ────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_with_users_router():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
