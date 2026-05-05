"""Phase R.4 — admin users sub-router (list / detail / force-password-reset)."""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, User, UserAuthToken
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
async def test_list_users_returns_admin_and_user(client, admin_operator, regular_user):
    resp = await client.get("/api/admin/users/", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    body = resp.json()
    ids = {it["id"] for it in body["items"]}
    assert admin_operator.id in ids
    assert regular_user.id in ids


@pytest.mark.asyncio
async def test_list_users_search_email(client, admin_operator, regular_user):
    fragment = regular_user.email.split("@")[0][:6]
    resp = await client.get(f"/api/admin/users/?q={fragment}", headers=_bearer(admin_operator))
    body = resp.json()
    ids = {it["id"] for it in body["items"]}
    assert regular_user.id in ids


@pytest.mark.asyncio
async def test_list_users_search_name(client, admin_operator, regular_user):
    resp = await client.get("/api/admin/users/?q=bob", headers=_bearer(admin_operator))
    body = resp.json()
    ids = {it["id"] for it in body["items"]}
    assert regular_user.id in ids


@pytest.mark.asyncio
async def test_list_users_role_filter(client, admin_operator, regular_user):
    resp = await client.get("/api/admin/users/?role=free", headers=_bearer(admin_operator))
    body = resp.json()
    for it in body["items"]:
        assert it["role"] == "free"


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

    resp = await client.get("/api/admin/users/?limit=2", headers=_bearer(admin_operator))
    assert resp.json()["returned"] == 2


@pytest.mark.asyncio
async def test_list_users_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/users/", headers=_bearer(regular_user))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_users_unauth_401(client):
    resp = await client.get("/api/admin/users/")
    assert resp.status_code == 401


# ── detail ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_user_detail(client, admin_operator, regular_user):
    resp = await client.get(f"/api/admin/users/{regular_user.id}", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == regular_user.id
    assert body["email"] == regular_user.email
    assert body["name"] == "Bob"
    assert body["company"] == "Acme"
    # Password hash never returned
    assert "password_hash" not in body


@pytest.mark.asyncio
async def test_get_user_unknown_404(client, admin_operator):
    resp = await client.get("/api/admin/users/no-such-id", headers=_bearer(admin_operator))
    assert resp.status_code == 404


# ── force-password-reset ──────────────────────────────────────


@pytest.mark.asyncio
async def test_force_password_reset_creates_token_and_audits_high(
    client, admin_operator, regular_user, db_session: AsyncSession
):
    resp = await client.post(
        f"/api/admin/users/{regular_user.id}/force-password-reset",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == regular_user.id
    assert body["token"]  # plaintext returned ONCE
    assert body["ttl_hours"] == 1

    # UserAuthToken row exists with type=password_reset
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

    # Audit row written with severity=high (HIGH_RISK_ACTIONS)
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
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_force_password_reset_non_admin_403(client, regular_user):
    """Non-admin user must NOT be able to force reset on themselves either."""
    resp = await client.post(
        f"/api/admin/users/{regular_user.id}/force-password-reset",
        headers=_bearer(regular_user),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_force_password_reset_high_risk_in_allowlist():
    from app.admin.audit import HIGH_RISK_ACTIONS

    assert "force_password_reset" in HIGH_RISK_ACTIONS


# ── audit coverage gate re-run ────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_with_users_router():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
