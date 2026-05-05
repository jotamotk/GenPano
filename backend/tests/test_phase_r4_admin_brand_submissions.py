"""Phase R.4 — admin brand submissions moderation queue."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, BrandSubmission, User
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


@pytest_asyncio.fixture
async def submission(db_session: AsyncSession, regular_user: User) -> BrandSubmission:
    s = BrandSubmission(
        id=_new_id(),
        user_id=regular_user.id,
        proposed_name="Acme",
        proposed_industry_id=1,
        proposed_aliases={"alt": ["Acme Corp"]},
        notes="Looking to track this brand",
        status="pending",
    )
    db_session.add(s)
    await db_session.commit()
    return s


# ── list / detail ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_empty(client, admin_operator):
    resp = await client.get("/api/admin/brand-submissions/", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    assert resp.json()["items"] == []


@pytest.mark.asyncio
async def test_list_returns_seeded(client, admin_operator, submission):
    resp = await client.get("/api/admin/brand-submissions/", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["returned"] == 1
    assert body["items"][0]["id"] == submission.id
    assert body["items"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_list_filter_by_status(client, admin_operator, submission, db_session: AsyncSession):
    db_session.add(
        BrandSubmission(
            id=_new_id(),
            user_id=submission.user_id,
            proposed_name="Other",
            status="approved",
        )
    )
    await db_session.commit()

    resp = await client.get(
        "/api/admin/brand-submissions/?status=pending",
        headers=_bearer(admin_operator),
    )
    assert resp.json()["returned"] == 1
    assert resp.json()["items"][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_list_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/brand-submissions/", headers=_bearer(regular_user))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_submission_detail(client, admin_operator, submission):
    resp = await client.get(
        f"/api/admin/brand-submissions/{submission.id}",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert body["id"] == submission.id
    assert body["proposed_name"] == "Acme"
    assert body["proposed_aliases"] == {"alt": ["Acme Corp"]}


@pytest.mark.asyncio
async def test_get_unknown_404(client, admin_operator):
    resp = await client.get("/api/admin/brand-submissions/no-such", headers=_bearer(admin_operator))
    assert resp.status_code == 404


# ── approve ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_pending_emits_audit(
    client, admin_operator, submission, db_session: AsyncSession
):
    resp = await client.post(
        f"/api/admin/brand-submissions/{submission.id}/approve",
        headers=_bearer(admin_operator),
        json={"resulting_brand_id": 42},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["reviewer_id"] == admin_operator.id
    assert body["resulting_brand_id"] == 42
    assert body["reviewed_at"] is not None

    audits = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "brand_submission_approved",
                    AdminAuditLog.resource_id == submission.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1
    assert audits[0].severity == "med"


@pytest.mark.asyncio
async def test_approve_already_approved_409(client, admin_operator, submission):
    await client.post(
        f"/api/admin/brand-submissions/{submission.id}/approve",
        headers=_bearer(admin_operator),
        json={},
    )
    resp = await client.post(
        f"/api/admin/brand-submissions/{submission.id}/approve",
        headers=_bearer(admin_operator),
        json={},
    )
    assert resp.status_code == 409


# ── reject ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reject_pending_emits_audit(
    client, admin_operator, submission, db_session: AsyncSession
):
    resp = await client.post(
        f"/api/admin/brand-submissions/{submission.id}/reject",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    audits = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "brand_submission_rejected",
                    AdminAuditLog.resource_id == submission.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_reject_unknown_404(client, admin_operator):
    resp = await client.post(
        "/api/admin/brand-submissions/no-such/reject",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reject_after_approve_409(client, admin_operator, submission):
    await client.post(
        f"/api/admin/brand-submissions/{submission.id}/approve",
        headers=_bearer(admin_operator),
        json={},
    )
    resp = await client.post(
        f"/api/admin/brand-submissions/{submission.id}/reject",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 409


# ── mark-duplicate ────────────────────────────────────────


@pytest.mark.asyncio
async def test_mark_duplicate_with_canonical_id(
    client, admin_operator, submission, db_session: AsyncSession
):
    resp = await client.post(
        f"/api/admin/brand-submissions/{submission.id}/mark-duplicate",
        headers=_bearer(admin_operator),
        json={"resulting_brand_id": 7},
    )
    body = resp.json()
    assert body["status"] == "duplicate"
    assert body["resulting_brand_id"] == 7

    audits = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "brand_submission_duplicate",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1


# ── auth ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_non_admin_403(client, regular_user, submission):
    resp = await client.post(
        f"/api/admin/brand-submissions/{submission.id}/approve",
        headers=_bearer(regular_user),
        json={},
    )
    assert resp.status_code == 403


# ── audit gate ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_gate_with_brand_submissions_writes():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
