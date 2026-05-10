"""Phase 3 B.3 — admin topic_plan topic delete (FK-aware).

Both routes call ``app.admin.topic_plan.db.delete_topic_plan_topics`` which
runs raw SQL against the legacy ``topics`` / ``prompts`` / ``queries``
upstream stub tables. Sqlite has no shape for those, so the helper is
mocked here. The route layer (validation, audit emit, status code
mapping) runs end-to-end against sqlite via the AdminAuditLog ORM.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, AdminUser
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


def _patch_delete(monkeypatch, return_value):
    import app.admin.topic_plan.db as tp_db

    monkeypatch.setattr(tp_db, "delete_topic_plan_topics", AsyncMock(return_value=return_value))


def _result(deleted=None, blocked=None, missing=None) -> dict[str, list[Any]]:
    return {
        "deleted": deleted or [],
        "blocked": blocked or [],
        "missing": missing or [],
    }


# ── parse_topic_id / parse_topic_ids (pure-Python) ────────────


def test_parse_topic_id_accepts_int():
    from app.admin.topic_plan.db import parse_topic_id

    assert parse_topic_id(42) == 42
    assert parse_topic_id("42") == 42
    assert parse_topic_id("T-42") == 42
    assert parse_topic_id("t-42") == 42


def test_parse_topic_id_rejects_garbage():
    from app.admin.topic_plan.db import parse_topic_id

    with pytest.raises(ValueError):
        parse_topic_id("not-an-int")
    with pytest.raises(ValueError):
        parse_topic_id("")


def test_parse_topic_ids_dedupes_and_normalizes():
    from app.admin.topic_plan.db import parse_topic_ids

    assert parse_topic_ids([1, "T-1", "2", 3]) == [1, 2, 3]


def test_parse_topic_ids_rejects_non_list():
    from app.admin.topic_plan.db import parse_topic_ids

    with pytest.raises(ValueError):
        parse_topic_ids("1,2,3")
    with pytest.raises(ValueError):
        parse_topic_ids(None)


@pytest.mark.asyncio
async def test_topic_dependency_counts_without_query_prompt_link_counts_prompts_only(monkeypatch):
    import app.admin.topic_plan.db as tp_db

    async def _fake_table_exists(_session, name: str) -> bool:
        return name in {"prompts", "queries"}

    async def _fake_table_columns(_session, name: str) -> set[str]:
        if name == "prompts":
            return {"id", "topic_id"}
        if name == "queries":
            return {"id"}
        return set()

    class _FakeResult:
        def mappings(self):
            return self

        def all(self):
            return [{"topic_id": 7, "prompt_count": 2, "query_count": 0}]

    class _FakeSession:
        async def execute(self, statement, _params=None):
            sql = str(statement)
            assert "LEFT JOIN queries" not in sql
            assert "FROM prompts p" in sql
            return _FakeResult()

    monkeypatch.setattr(tp_db, "_table_exists", _fake_table_exists)
    monkeypatch.setattr(tp_db, "_table_columns", _fake_table_columns)

    counts = await tp_db.topic_dependency_counts(_FakeSession(), [7])

    assert counts[7] == {"prompt_count": 2, "query_count": 0}


@pytest.mark.asyncio
async def test_delete_topic_plan_topics_does_not_require_candidate_updated_at(monkeypatch):
    import app.admin.topic_plan.db as tp_db

    async def _fake_table_exists(_session, name: str) -> bool:
        return name in {"topics", "brands", "topic_candidates"}

    async def _fake_table_columns(_session, name: str) -> set[str]:
        if name == "topics":
            return {"id", "brand_id", "text"}
        if name == "brands":
            return {"id", "name"}
        if name == "topic_candidates":
            return {"approved_topic_id"}
        return set()

    class _FakeResult:
        def __init__(self, rows=None, tuples=None):
            self.rows = rows or []
            self.tuples = tuples or []

        def mappings(self):
            return self

        def all(self):
            return self.rows

        def fetchall(self):
            return self.tuples

    class _FakeSession:
        def __init__(self):
            self.sql: list[str] = []
            self.committed = False

        async def execute(self, statement, _params=None):
            sql = " ".join(str(statement).split())
            self.sql.append(sql)
            if "SELECT t.id" in sql:
                assert "t.category" not in sql
                assert "t.status" not in sql
                assert "b.industry" not in sql
                return _FakeResult(
                    rows=[
                        {
                            "id": 7,
                            "brand_id": 1,
                            "text": "Disposable test topic",
                            "category": None,
                            "status": "active",
                            "brand_name": "TestBrand",
                            "industry": "Uncategorized",
                        }
                    ]
                )
            if "UPDATE topic_candidates" in sql:
                assert "updated_at" not in sql
                return _FakeResult()
            if "DELETE FROM topics" in sql:
                return _FakeResult(tuples=[(7,)])
            raise AssertionError(f"unexpected SQL: {sql}")

        async def commit(self):
            self.committed = True

    monkeypatch.setattr(tp_db, "_table_exists", _fake_table_exists)
    monkeypatch.setattr(tp_db, "_table_columns", _fake_table_columns)

    session = _FakeSession()
    result = await tp_db.delete_topic_plan_topics(session, [7])

    assert result["deleted"][0]["raw_id"] == 7
    assert result["blocked"] == []
    assert result["missing"] == []
    assert session.committed is True


# ── POST /topics/bulk-delete ──────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_delete_unauth_401(client):
    resp = await client.post("/api/admin/topic-plan/topics/bulk-delete", json={"topic_ids": [1]})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_bulk_delete_missing_topic_ids_422(client, admin_operator):
    resp = await client.post("/api/admin/topic-plan/topics/bulk-delete", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_delete_invalid_topic_ids_422(client, admin_operator):
    resp = await client.post(
        "/api/admin/topic-plan/topics/bulk-delete",
        json={"topic_ids": "1,2,3"},  # must be a list
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_delete_all_succeed_emits_audit(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    _patch_delete(
        monkeypatch,
        _result(
            deleted=[
                {"id": "T-1", "raw_id": 1, "title": "x", "brand": "NIKE", "industry": "footwear"},
                {"id": "T-2", "raw_id": 2, "title": "y", "brand": "NIKE", "industry": "footwear"},
            ]
        ),
    )
    resp = await client.post(
        "/api/admin/topic-plan/topics/bulk-delete",
        json={"topic_ids": [1, "T-2"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["summary"] == {"deleted_count": 2, "blocked_count": 0, "missing_count": 0}

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "delete_topic_plan_topics",
                    AdminAuditLog.resource_id == "bulk",
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
async def test_bulk_delete_partial_blocked_returns_200_when_any_deleted(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    _patch_delete(
        monkeypatch,
        _result(
            deleted=[{"id": "T-1", "raw_id": 1, "title": "x", "brand": "NIKE"}],
            blocked=[
                {
                    "id": "T-2",
                    "raw_id": 2,
                    "title": "y",
                    "brand": "NIKE",
                    "prompt_count": 3,
                    "query_count": 5,
                    "reason": "has_downstream_dependencies",
                }
            ],
        ),
    )
    resp = await client.post(
        "/api/admin/topic-plan/topics/bulk-delete",
        json={"topic_ids": [1, 2]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["summary"]["deleted_count"] == 1
    assert body["summary"]["blocked_count"] == 1


@pytest.mark.asyncio
async def test_bulk_delete_all_blocked_returns_409(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    _patch_delete(
        monkeypatch,
        _result(
            blocked=[
                {
                    "id": "T-1",
                    "raw_id": 1,
                    "title": "x",
                    "brand": "NIKE",
                    "prompt_count": 5,
                    "query_count": 10,
                    "reason": "has_downstream_dependencies",
                }
            ]
        ),
    )
    resp = await client.post(
        "/api/admin/topic-plan/topics/bulk-delete",
        json={"topic_ids": [1]},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert body["summary"]["blocked_count"] == 1

    # No audit row when nothing was deleted
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "delete_topic_plan_topics")
            )
        )
        .scalars()
        .all()
    )
    assert audit == []


@pytest.mark.asyncio
async def test_bulk_delete_all_missing_returns_200_no_blocked(client, admin_operator, monkeypatch):
    """Per admin_console behavior: if all ids are missing (none blocked,
    none deleted), success=True (nothing to do)."""
    _patch_delete(monkeypatch, _result(missing=[99]))
    resp = await client.post(
        "/api/admin/topic-plan/topics/bulk-delete",
        json={"topic_ids": [99]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["summary"]["missing_count"] == 1


# ── DELETE /topics/{topic_id} ─────────────────────────────────


@pytest.mark.asyncio
async def test_single_delete_unauth_401(client):
    resp = await client.delete("/api/admin/topic-plan/topics/1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_single_delete_invalid_id_422(client, admin_operator):
    resp = await client.delete("/api/admin/topic-plan/topics/not-a-number")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_single_delete_unknown_404(client, admin_operator, monkeypatch):
    _patch_delete(monkeypatch, _result(missing=[42]))
    resp = await client.delete("/api/admin/topic-plan/topics/42")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_single_delete_blocked_409(client, admin_operator, monkeypatch):
    _patch_delete(
        monkeypatch,
        _result(
            blocked=[
                {
                    "id": "T-42",
                    "raw_id": 42,
                    "title": "x",
                    "brand": "NIKE",
                    "prompt_count": 2,
                    "query_count": 0,
                    "reason": "has_downstream_dependencies",
                }
            ]
        ),
    )
    resp = await client.delete("/api/admin/topic-plan/topics/42")
    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert body["error"] == "topic_has_downstream_dependencies"


@pytest.mark.asyncio
async def test_single_delete_success_emits_audit(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    _patch_delete(
        monkeypatch,
        _result(deleted=[{"id": "T-42", "raw_id": 42, "title": "x", "brand": "NIKE"}]),
    )
    resp = await client.delete("/api/admin/topic-plan/topics/T-42")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["deleted"]) == 1

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "delete_topic_plan_topic",
                    AdminAuditLog.resource_id == "42",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "med"


# ── audit gate ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_b3_routes():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
