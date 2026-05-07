"""Phase 3 B.1 — admin topic_plan candidate review routes.

Auth: ``current_admin`` (cookie AdminUser) overridden via
``app.dependency_overrides``.

Approve path inserts into the legacy ``topics`` table (upstream stub in
backend's ORM — only ``id`` modeled). Tests for the approve path mock
``_approve_topic_in_topics_table`` because sqlite has no ``brand_id /
text / category / generated_by`` columns to insert into. The reject path
runs end-to-end against sqlite.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import (
    AdminAuditLog,
    AdminUser,
    TopicCandidate,
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


def _candidate(
    *,
    title: str = "测试候选标题",
    brand_name: str = "TestBrand",
    brand_id: int = 1,
    dimension: str = "brand",
    status: str = "pending",
) -> TopicCandidate:
    return TopicCandidate(
        id=_new_id(),
        run_id=None,
        brand_id=brand_id,
        brand_name=brand_name,
        title=title,
        dimension=dimension,
        normalized_title=title,
        status=status,
        confidence=0.8,
        coverage_gap=f"{brand_name}:{dimension}",
        reason="test reason",
    )


# ── single review ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_review_reject_updates_status_and_audits(
    client, admin_operator, db_session: AsyncSession
):
    cand = _candidate()
    db_session.add(cand)
    await db_session.commit()

    resp = await client.post(
        f"/api/admin/topic-plan/candidates/{cand.id}/review",
        json={"status": "rejected", "reason": "off-topic"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["candidate"]["status"] == "rejected"
    assert body["candidate"]["review_reason"] is None or "off-topic" in str(body)

    # DB-side: status flipped, reviewed_by set. Expire the test session's
    # identity-map copy so the next read goes to the DB and sees the
    # request-side commit (request used a different session via the
    # dependency override).
    await db_session.refresh(cand)
    assert cand.status == "rejected"
    assert cand.reviewed_by == admin_operator.id
    assert cand.reviewed_at is not None
    assert cand.review_reason == "off-topic"

    # Audit row written
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "review_topic_candidate",
                    AdminAuditLog.resource_id == cand.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "med"
    assert audit[0].operator_id == admin_operator.id


@pytest.mark.asyncio
async def test_review_already_reviewed_returns_400_with_code(
    client, admin_operator, db_session: AsyncSession
):
    cand = _candidate(status="approved")
    db_session.add(cand)
    await db_session.commit()

    resp = await client.post(
        f"/api/admin/topic-plan/candidates/{cand.id}/review",
        json={"status": "rejected"},
    )
    assert resp.status_code == 400
    body = resp.json()
    # detail is a Problem+JSON body with stable error code
    detail = body["detail"]
    assert detail["code"] == "candidate_already_reviewed"


@pytest.mark.asyncio
async def test_review_invalid_status_422(client, admin_operator, db_session: AsyncSession):
    cand = _candidate()
    db_session.add(cand)
    await db_session.commit()

    resp = await client.post(
        f"/api/admin/topic-plan/candidates/{cand.id}/review",
        json={"status": "merged"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_review_unknown_id_404(client, admin_operator):
    resp = await client.post(
        "/api/admin/topic-plan/candidates/no-such-id/review",
        json={"status": "rejected"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_review_unauth_401(client):
    resp = await client.post(
        "/api/admin/topic-plan/candidates/anything/review",
        json={"status": "rejected"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_review_approve_calls_topics_insert(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    """Approve path inserts into ``topics`` (upstream stub). Mock the helper
    so this test runs on sqlite — production path is exercised by the
    smoke test in the PR description.
    """
    import importlib

    router_mod = importlib.import_module("app.api.admin.topic_plan.router")
    fake_insert = AsyncMock(return_value=999)
    monkeypatch.setattr(router_mod, "_approve_topic_in_topics_table", fake_insert)

    cand = _candidate()
    db_session.add(cand)
    await db_session.commit()

    resp = await client.post(
        f"/api/admin/topic-plan/candidates/{cand.id}/review",
        json={"status": "approved"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["candidate"]["status"] == "approved"
    assert body["candidate"]["approved_topic_id"] == 999
    fake_insert.assert_awaited_once()


# ── bulk review ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_review_all_succeed(client, admin_operator, db_session: AsyncSession):
    cands = [_candidate(title=f"测试候选标题{i}") for i in range(3)]
    for c in cands:
        db_session.add(c)
    await db_session.commit()

    resp = await client.post(
        "/api/admin/topic-plan/candidates/bulk-review",
        json={
            "candidate_ids": [c.id for c in cands],
            "status": "rejected",
            "reason": "noisy batch",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["summary"]["updated_count"] == 3
    assert body["summary"]["failed_count"] == 0
    assert body["summary"]["missing_count"] == 0


@pytest.mark.asyncio
async def test_bulk_review_partial_failure_returns_409(
    client, admin_operator, db_session: AsyncSession
):
    good = _candidate(title="好的候选")
    already = _candidate(title="已经审过的候选", status="approved")
    db_session.add(good)
    db_session.add(already)
    await db_session.commit()

    resp = await client.post(
        "/api/admin/topic-plan/candidates/bulk-review",
        json={
            "candidate_ids": [good.id, already.id, "no-such-id"],
            "status": "rejected",
        },
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert body["summary"]["updated_count"] == 1
    assert body["summary"]["failed_count"] == 1
    assert body["summary"]["missing_count"] == 1
    assert any(f["error"] == "candidate_already_reviewed" for f in body["failed"])
    assert "no-such-id" in body["missing"]


@pytest.mark.asyncio
async def test_bulk_review_too_many_422(client, admin_operator):
    resp = await client.post(
        "/api/admin/topic-plan/candidates/bulk-review",
        json={
            "candidate_ids": [f"id-{i}" for i in range(201)],
            "status": "rejected",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_review_empty_ids_422(client, admin_operator):
    resp = await client.post(
        "/api/admin/topic-plan/candidates/bulk-review",
        json={"candidate_ids": [], "status": "rejected"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_review_invalid_status_422(client, admin_operator):
    resp = await client.post(
        "/api/admin/topic-plan/candidates/bulk-review",
        json={"candidate_ids": ["x"], "status": "merged"},
    )
    assert resp.status_code == 422


# ── audit gate ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_topic_plan_routes():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
