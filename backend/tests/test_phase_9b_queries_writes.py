"""Phase 9 slice 9b — /api/queries write paths."""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, AdminUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.queries.lib import (
    QueryValidationError,
    parse_batch_trigger_payload,
    parse_cleanup_query_args,
    parse_create_query_payload,
)

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def admin_operator(db_session: AsyncSession) -> AsyncGenerator[AdminUser, None]:
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


def _queries_router_module():
    import app.api.queries.router  # noqa: F401

    return sys.modules["app.api.queries.router"]


def _patch_writes(monkeypatch, **overrides):
    a = _queries_router_module()
    monkeypatch.setattr(
        a.queries_db,
        "create_query",
        AsyncMock(return_value=overrides.get("create_query", 42)),
    )
    monkeypatch.setattr(
        a.queries_db,
        "retry_query",
        AsyncMock(
            return_value=overrides.get(
                "retry_query",
                {"id": 1, "target_llm": "doubao", "query_text": "x", "brand_id": None},
            )
        ),
    )
    monkeypatch.setattr(
        a.queries_db,
        "batch_trigger_queries",
        AsyncMock(return_value=overrides.get("batch", (0, [], False))),
    )
    monkeypatch.setattr(
        a.queries_db,
        "cleanup_queries",
        AsyncMock(return_value=overrides.get("cleanup", (0, 0))),
    )
    monkeypatch.setattr(
        a.queries_db,
        "mark_query_failed",
        AsyncMock(return_value=overrides.get("mark_failed", True)),
    )
    monkeypatch.setattr(a, "dispatch_execute_query", MagicMock(return_value=False))
    monkeypatch.setattr(a, "dispatch_many", MagicMock(return_value=(0, 0)))


# ── lib.py ──────────────────────────────────────────────────


def test_parse_create_payload_required():
    with pytest.raises(QueryValidationError) as exc:
        parse_create_query_payload({})
    assert exc.value.code == "missing_required"


def test_parse_create_payload_invalid_brand_id():
    with pytest.raises(QueryValidationError) as exc:
        parse_create_query_payload({"target_llm": "doubao", "query_text": "x", "brand_id": "weird"})
    assert exc.value.code == "invalid_brand_id"


def test_parse_create_payload_ok():
    out = parse_create_query_payload(
        {"target_llm": " Doubao ", "query_text": " hi ", "brand_id": "7"}
    )
    assert out["target_llm"] == "Doubao"
    assert out["query_text"] == "hi"
    assert out["brand_id"] == 7


def test_parse_batch_trigger_with_ids():
    out = parse_batch_trigger_payload({"ids": ["1", 2, "weird", "3"]})
    assert out["ids"] == [1, 2, 3]


def test_parse_batch_trigger_empty_ids_invalid():
    with pytest.raises(QueryValidationError) as exc:
        parse_batch_trigger_payload({"ids": ["weird"]})
    assert exc.value.code == "ids_empty_or_invalid"


def test_parse_batch_trigger_filter_passthrough():
    out = parse_batch_trigger_payload({"brand_id": "1", "topic_id": 2, "llm": "doubao", "q": "hot"})
    assert out["brand_id"] == 1
    assert out["topic_id"] == 2
    assert out["llm"] == "doubao"
    assert out["prompt_q"] == "hot"


def test_parse_batch_trigger_invalid_max():
    with pytest.raises(QueryValidationError) as exc:
        parse_batch_trigger_payload({"max": "weird"})
    assert exc.value.code == "invalid_max"


def test_parse_cleanup_invalid_type():
    with pytest.raises(QueryValidationError) as exc:
        parse_cleanup_query_args({"type": "weird"})
    assert exc.value.code == "invalid_type"


def test_parse_cleanup_args_normalized():
    out = parse_cleanup_query_args({"type": "FAILED_OLD", "days": "45", "dry_run": "1"})
    assert out["type"] == "failed_old"
    assert out["days"] == 45
    assert out["dry_run"] is True


# ── auth gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_query_unauth_401(client):
    resp = await client.post("/api/queries", json={"target_llm": "x", "query_text": "y"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_retry_unauth_401(client):
    resp = await client.post("/api/queries/1/retry", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_batch_trigger_unauth_401(client):
    resp = await client.post("/api/queries/batch_trigger", json={"ids": [1]})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_cleanup_unauth_401(client):
    resp = await client.delete("/api/queries/cleanup?type=unqueued")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mark_failed_unauth_401(client):
    resp = await client.post("/api/queries/1/mark_failed")
    assert resp.status_code == 401


# ── POST /api/queries ───────────────────────────────────────


@pytest.mark.asyncio
async def test_create_validation_400(client, admin_operator, monkeypatch):
    _patch_writes(monkeypatch)
    resp = await client.post("/api/queries", json={})
    assert resp.status_code == 400
    assert resp.json()["error"] == "missing_required"


@pytest.mark.asyncio
async def test_create_503_when_table_missing(client, admin_operator, monkeypatch):
    _patch_writes(monkeypatch, create_query=None)
    resp = await client.post("/api/queries", json={"target_llm": "doubao", "query_text": "hi"})
    assert resp.status_code == 503
    assert resp.json()["error"] == "queries_unavailable"


@pytest.mark.asyncio
async def test_create_audit_med(client, admin_operator, monkeypatch, db_session: AsyncSession):
    _patch_writes(monkeypatch, create_query=99)
    resp = await client.post(
        "/api/queries",
        json={"target_llm": "doubao", "query_text": "hello", "brand_id": 7},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["query_id"] == 99
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "create_query")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "med"
    assert audit[0].after.get("target_llm") == "doubao"


# ── retry / batch / cleanup / mark_failed ───────────────────


@pytest.mark.asyncio
async def test_retry_404_when_missing(client, admin_operator, monkeypatch):
    _patch_writes(monkeypatch, retry_query=None)
    resp = await client.post("/api/queries/9999/retry", json={})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_retry_audit_med(client, admin_operator, monkeypatch, db_session: AsyncSession):
    _patch_writes(monkeypatch)
    resp = await client.post("/api/queries/1/retry", json={"reason": "manual qa"})
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "retry_query")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "med"
    assert audit[0].after.get("retry_reason") == "manual qa"


@pytest.mark.asyncio
async def test_batch_trigger_dry_run(client, admin_operator, monkeypatch):
    _patch_writes(monkeypatch, batch=(15, [], False))
    resp = await client.post("/api/queries/batch_trigger", json={"ids": [1, 2, 3], "dry_run": True})
    assert resp.status_code == 200
    assert resp.json()["count"] == 15


@pytest.mark.asyncio
async def test_batch_trigger_refused_when_over_cap(client, admin_operator, monkeypatch):
    _patch_writes(monkeypatch, batch=(5000, [], True))
    resp = await client.post("/api/queries/batch_trigger", json={"ids": [1, 2, 3], "max": 100})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_batch_trigger_audit_high(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_writes(monkeypatch, batch=(3, [10, 11, 12], False))
    a = _queries_router_module()
    a.dispatch_many.return_value = (3, 0)
    resp = await client.post("/api/queries/batch_trigger", json={"ids": [10, 11, 12]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 3
    assert body["dispatched"] == 3
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "batch_trigger_queries")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "high"


@pytest.mark.asyncio
async def test_cleanup_invalid_type_400(client, admin_operator):
    resp = await client.delete("/api/queries/cleanup?type=weird")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cleanup_dry_run_no_audit(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_writes(monkeypatch, cleanup=(7, 0))
    resp = await client.delete("/api/queries/cleanup?type=unqueued&dry_run=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 7
    assert body["dry_run"] is True
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "cleanup_queries")
            )
        )
        .scalars()
        .all()
    )
    assert audit == []


@pytest.mark.asyncio
async def test_cleanup_audit_high(client, admin_operator, monkeypatch, db_session: AsyncSession):
    _patch_writes(monkeypatch, cleanup=(20, 20))
    resp = await client.delete("/api/queries/cleanup?type=unqueued")
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "cleanup_queries")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "high"
    assert audit[0].after.get("deleted") == 20


@pytest.mark.asyncio
async def test_mark_failed_404_when_not_done(client, admin_operator, monkeypatch):
    _patch_writes(monkeypatch, mark_failed=False)
    resp = await client.post("/api/queries/1/mark_failed")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_failed_audit_med(client, admin_operator, monkeypatch, db_session: AsyncSession):
    _patch_writes(monkeypatch, mark_failed=True)
    resp = await client.post("/api/queries/1/mark_failed")
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "mark_query_failed")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "med"


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice9b():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
