"""Phase K.5 — admin KG candidates review queue."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, KgRelationCandidate, User
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
async def candidate(db_session: AsyncSession) -> KgRelationCandidate:
    c = KgRelationCandidate(
        id=_new_id(),
        entity_kind="brand",
        a_id=1,
        b_id=2,
        type="COMPETES_WITH",
        confidence=0.85,
        evidence={"text_snippet": "Acme vs Beta", "pattern_type": "COMPETES_WITH"},
        status="pending",
        llm_model="deterministic_v1",
    )
    db_session.add(c)
    await db_session.commit()
    return c


# ── /list ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_returns_pending_candidates(client, admin_operator, candidate):
    resp = await client.get("/api/admin/kg-candidates/", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    body = resp.json()
    assert body["returned"] == 1
    assert body["items"][0]["id"] == candidate.id


@pytest.mark.asyncio
async def test_list_filter_by_status(client, admin_operator, db_session: AsyncSession):
    db_session.add_all(
        [
            KgRelationCandidate(
                id=_new_id(),
                entity_kind="brand",
                a_id=1,
                b_id=2,
                type="COMPETES_WITH",
                confidence=0.8,
                status="pending",
            ),
            KgRelationCandidate(
                id=_new_id(),
                entity_kind="brand",
                a_id=3,
                b_id=4,
                type="SAME_GROUP",
                confidence=0.85,
                status="approved",
                reviewed_by=admin_operator.id,
                reviewed_at=_now(),
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get(
        "/api/admin/kg-candidates/?status=pending",
        headers=_bearer(admin_operator),
    )
    assert resp.json()["returned"] == 1


@pytest.mark.asyncio
async def test_list_filter_by_type(client, admin_operator, db_session: AsyncSession):
    db_session.add_all(
        [
            KgRelationCandidate(
                id=_new_id(),
                entity_kind="brand",
                a_id=1,
                b_id=2,
                type="COMPETES_WITH",
                confidence=0.8,
                status="pending",
            ),
            KgRelationCandidate(
                id=_new_id(),
                entity_kind="brand",
                a_id=3,
                b_id=4,
                type="SAME_GROUP",
                confidence=0.85,
                status="pending",
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get(
        "/api/admin/kg-candidates/?type=COMPETES_WITH",
        headers=_bearer(admin_operator),
    )
    assert resp.json()["returned"] == 1
    assert resp.json()["items"][0]["type"] == "COMPETES_WITH"


@pytest.mark.asyncio
async def test_list_filter_by_min_confidence(client, admin_operator, db_session: AsyncSession):
    db_session.add_all(
        [
            KgRelationCandidate(
                id=_new_id(),
                entity_kind="brand",
                a_id=1,
                b_id=2,
                type="COMPETES_WITH",
                confidence=0.5,
                status="pending",
            ),
            KgRelationCandidate(
                id=_new_id(),
                entity_kind="brand",
                a_id=3,
                b_id=4,
                type="COMPETES_WITH",
                confidence=0.95,
                status="pending",
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get(
        "/api/admin/kg-candidates/?min_confidence=0.8",
        headers=_bearer(admin_operator),
    )
    assert resp.json()["returned"] == 1


@pytest.mark.asyncio
async def test_list_invalid_status_422(client, admin_operator):
    resp = await client.get(
        "/api/admin/kg-candidates/?status=bogus",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/kg-candidates/", headers=_bearer(regular_user))
    assert resp.status_code == 403


# ── /counts ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_counts_zero_state(client, admin_operator):
    resp = await client.get("/api/admin/kg-candidates/counts", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["by_status"] == {}
    assert body["pending_by_type"] == {}


@pytest.mark.asyncio
async def test_counts_aggregates(client, admin_operator, db_session: AsyncSession):
    db_session.add_all(
        [
            KgRelationCandidate(
                id=_new_id(),
                entity_kind="brand",
                a_id=1,
                b_id=2,
                type="COMPETES_WITH",
                confidence=0.8,
                status="pending",
            ),
            KgRelationCandidate(
                id=_new_id(),
                entity_kind="brand",
                a_id=3,
                b_id=4,
                type="COMPETES_WITH",
                confidence=0.85,
                status="pending",
            ),
            KgRelationCandidate(
                id=_new_id(),
                entity_kind="brand",
                a_id=5,
                b_id=6,
                type="SAME_GROUP",
                confidence=0.9,
                status="pending",
            ),
            KgRelationCandidate(
                id=_new_id(),
                entity_kind="product",
                a_id=10,
                b_id=20,
                type="UPGRADES_TO",
                confidence=0.8,
                status="approved",
                reviewed_by=admin_operator.id,
                reviewed_at=_now(),
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get("/api/admin/kg-candidates/counts", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["by_status"]["pending"] == 3
    assert body["by_status"]["approved"] == 1
    assert body["pending_by_type"]["COMPETES_WITH"] == 2
    assert body["pending_by_type"]["SAME_GROUP"] == 1
    assert body["pending_by_entity_kind"]["brand"] == 3


# ── /{id} detail ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_detail_returns_full_evidence(client, admin_operator, candidate):
    resp = await client.get(
        f"/api/admin/kg-candidates/{candidate.id}",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert body["id"] == candidate.id
    assert body["evidence"]["text_snippet"] == "Acme vs Beta"


@pytest.mark.asyncio
async def test_get_unknown_404(client, admin_operator):
    resp = await client.get("/api/admin/kg-candidates/no-such", headers=_bearer(admin_operator))
    assert resp.status_code == 404


# ── approve / reject / mark-merged ────────────────────────


@pytest.mark.asyncio
async def test_approve_emits_audit(client, admin_operator, candidate, db_session: AsyncSession):
    resp = await client.post(
        f"/api/admin/kg-candidates/{candidate.id}/approve",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "approved"
    assert body["reviewer_id"] == admin_operator.id

    audits = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "kg_candidate_approved",
                    AdminAuditLog.resource_id == candidate.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_reject_emits_audit(client, admin_operator, candidate, db_session: AsyncSession):
    resp = await client.post(
        f"/api/admin/kg-candidates/{candidate.id}/reject",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"

    audits = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "kg_candidate_rejected")
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_approve_then_approve_409(client, admin_operator, candidate):
    await client.post(
        f"/api/admin/kg-candidates/{candidate.id}/approve",
        headers=_bearer(admin_operator),
    )
    resp = await client.post(
        f"/api/admin/kg-candidates/{candidate.id}/approve",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_mark_merged_with_relation_id(
    client, admin_operator, candidate, db_session: AsyncSession
):
    resp = await client.post(
        f"/api/admin/kg-candidates/{candidate.id}/mark-merged",
        headers=_bearer(admin_operator),
        json={"relation_id": "rel-001"},
    )
    body = resp.json()
    assert body["status"] == "merged"
    assert body["merged_into_relation_id"] == "rel-001"

    audits = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "kg_candidate_merged")
            )
        )
        .scalars()
        .all()
    )
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_mark_merged_missing_relation_id_422(client, admin_operator, candidate):
    resp = await client.post(
        f"/api/admin/kg-candidates/{candidate.id}/mark-merged",
        headers=_bearer(admin_operator),
        json={},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_approve_unknown_404(client, admin_operator):
    resp = await client.post(
        "/api/admin/kg-candidates/no-such/approve",
        headers=_bearer(admin_operator),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_approve_non_admin_403(client, regular_user, candidate):
    resp = await client.post(
        f"/api/admin/kg-candidates/{candidate.id}/approve",
        headers=_bearer(regular_user),
    )
    assert resp.status_code == 403


# ── audit gate ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_gate_with_kg_candidates_writes():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
