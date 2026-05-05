"""Phase O.3.3 — admin commercial leads sub-router."""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, CommercialLead, User
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
        email=f"u-{uuid.uuid4().hex[:6]}@example.com",
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
async def lead(db_session: AsyncSession, regular_user: User) -> CommercialLead:
    led = CommercialLead(
        id=_new_id(),
        user_id=regular_user.id,
        source="contact_form",
        context={"phone": "+86 13800000000", "message": "Want a demo"},
        status="new",
    )
    db_session.add(led)
    await db_session.commit()
    return led


# ── list ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_leads_empty(client, admin_operator):
    resp = await client.get("/api/admin/leads/", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    assert resp.json()["items"] == []


@pytest.mark.asyncio
async def test_list_leads_returns_seeded(client, admin_operator, lead):
    resp = await client.get("/api/admin/leads/", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["returned"] == 1
    assert body["items"][0]["id"] == lead.id
    assert body["items"][0]["source"] == "contact_form"


@pytest.mark.asyncio
async def test_list_leads_filter_by_status(client, admin_operator, db_session: AsyncSession):
    db_session.add_all(
        [
            CommercialLead(id=_new_id(), source="form", status="new"),
            CommercialLead(id=_new_id(), source="form", status="contacted"),
            CommercialLead(id=_new_id(), source="form", status="closed"),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/leads/?status=contacted", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["returned"] == 1
    assert body["items"][0]["status"] == "contacted"


@pytest.mark.asyncio
async def test_list_leads_filter_by_source(client, admin_operator, db_session: AsyncSession):
    db_session.add_all(
        [
            CommercialLead(id=_new_id(), source="contact_form", status="new"),
            CommercialLead(id=_new_id(), source="referral", status="new"),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/leads/?source=referral", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["returned"] == 1
    assert body["items"][0]["source"] == "referral"


@pytest.mark.asyncio
async def test_list_leads_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/leads/", headers=_bearer(regular_user))
    assert resp.status_code == 403


# ── detail ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_lead_detail(client, admin_operator, lead):
    resp = await client.get(f"/api/admin/leads/{lead.id}", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == lead.id
    assert body["context"]["phone"] == "+86 13800000000"


@pytest.mark.asyncio
async def test_get_lead_unknown_404(client, admin_operator):
    resp = await client.get("/api/admin/leads/no-such-id", headers=_bearer(admin_operator))
    assert resp.status_code == 404


# ── update ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_lead_status_emits_audit(
    client, admin_operator, lead, db_session: AsyncSession
):
    resp = await client.patch(
        f"/api/admin/leads/{lead.id}",
        headers=_bearer(admin_operator),
        json={"status": "contacted"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "contacted"

    rows = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "lead_status_update",
                    AdminAuditLog.resource_id == lead.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].severity == "med"
    assert rows[0].operator_id == admin_operator.id


@pytest.mark.asyncio
async def test_update_lead_invalid_status_422(client, admin_operator, lead):
    resp = await client.patch(
        f"/api/admin/leads/{lead.id}",
        headers=_bearer(admin_operator),
        json={"status": "magic"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_lead_unknown_404(client, admin_operator):
    resp = await client.patch(
        "/api/admin/leads/no-such",
        headers=_bearer(admin_operator),
        json={"status": "contacted"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_lead_non_admin_403(client, regular_user, lead):
    resp = await client.patch(
        f"/api/admin/leads/{lead.id}",
        headers=_bearer(regular_user),
        json={"status": "contacted"},
    )
    assert resp.status_code == 403


# ── coverage gate ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_gate_with_leads_router_writes():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
