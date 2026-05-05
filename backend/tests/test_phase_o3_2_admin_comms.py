"""Phase O.3.2 — admin announcements (comms) sub-router."""

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


# ── create + list ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_announcement_emits_audit(client, admin_operator, db_session: AsyncSession):
    resp = await client.post(
        "/api/admin/comms/",
        headers=_bearer(admin_operator),
        json={
            "title_zh": "系统更新",
            "title_en": "System Update",
            "body_zh": "本周日凌晨维护",
            "body_en": "Maintenance this Sunday",
            "channel": "inapp",
            "audience": "all",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "draft"
    assert body["id"]

    rows = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "comms_create",
                    AdminAuditLog.resource_id == body["id"],
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_list_announcements(client, admin_operator):
    await client.post(
        "/api/admin/comms/",
        headers=_bearer(admin_operator),
        json={"title_zh": "T", "channel": "inapp", "audience": "all"},
    )
    resp = await client.get("/api/admin/comms/", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_list_announcements_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/comms/", headers=_bearer(regular_user))
    assert resp.status_code == 403


# ── validation ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_invalid_channel_422(client, admin_operator):
    resp = await client.post(
        "/api/admin/comms/",
        headers=_bearer(admin_operator),
        json={"channel": "carrier_pigeon", "audience": "all"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_invalid_audience_422(client, admin_operator):
    resp = await client.post(
        "/api/admin/comms/",
        headers=_bearer(admin_operator),
        json={"channel": "inapp", "audience": "moon_settlers"},
    )
    assert resp.status_code == 422


# ── update + state machine ───────────────────────────────────


@pytest.mark.asyncio
async def test_update_draft_announcement(client, admin_operator):
    cid = (
        await client.post(
            "/api/admin/comms/",
            headers=_bearer(admin_operator),
            json={"title_zh": "old", "channel": "inapp", "audience": "all"},
        )
    ).json()["id"]

    resp = await client.patch(
        f"/api/admin/comms/{cid}",
        headers=_bearer(admin_operator),
        json={"title_zh": "new"},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_update_after_send_409(client, admin_operator):
    cid = (
        await client.post(
            "/api/admin/comms/",
            headers=_bearer(admin_operator),
            json={"title_zh": "T", "channel": "inapp", "audience": "all"},
        )
    ).json()["id"]
    await client.post(f"/api/admin/comms/{cid}/send", headers=_bearer(admin_operator))

    resp = await client.patch(
        f"/api/admin/comms/{cid}",
        headers=_bearer(admin_operator),
        json={"title_zh": "tampered"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_send_announcement_emits_audit(client, admin_operator, db_session):
    cid = (
        await client.post(
            "/api/admin/comms/",
            headers=_bearer(admin_operator),
            json={"title_zh": "T", "channel": "inapp", "audience": "all"},
        )
    ).json()["id"]

    resp = await client.post(
        f"/api/admin/comms/{cid}/send",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"

    rows = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "comms_send",
                    AdminAuditLog.resource_id == cid,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].severity == "med"


@pytest.mark.asyncio
async def test_send_already_sent_409(client, admin_operator):
    cid = (
        await client.post(
            "/api/admin/comms/",
            headers=_bearer(admin_operator),
            json={"title_zh": "T", "channel": "inapp", "audience": "all"},
        )
    ).json()["id"]
    await client.post(f"/api/admin/comms/{cid}/send", headers=_bearer(admin_operator))

    resp = await client.post(f"/api/admin/comms/{cid}/send", headers=_bearer(admin_operator))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_cancel_draft(client, admin_operator):
    cid = (
        await client.post(
            "/api/admin/comms/",
            headers=_bearer(admin_operator),
            json={"title_zh": "T", "channel": "inapp", "audience": "all"},
        )
    ).json()["id"]

    resp = await client.post(f"/api/admin/comms/{cid}/cancel", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_after_send_409(client, admin_operator):
    cid = (
        await client.post(
            "/api/admin/comms/",
            headers=_bearer(admin_operator),
            json={"title_zh": "T", "channel": "inapp", "audience": "all"},
        )
    ).json()["id"]
    await client.post(f"/api/admin/comms/{cid}/send", headers=_bearer(admin_operator))

    resp = await client.post(f"/api/admin/comms/{cid}/cancel", headers=_bearer(admin_operator))
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_unknown_id_404(client, admin_operator):
    resp = await client.patch(
        "/api/admin/comms/no-such",
        headers=_bearer(admin_operator),
        json={"title_zh": "x"},
    )
    assert resp.status_code == 404


# ── coverage gate ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_emit_coverage_gate_with_comms_routes():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
