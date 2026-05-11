"""Phase 8 slice 8c-bis — /api/scheduler/manual_trigger.

Async port of admin_console's _run_manual_dispatch. The dispatch logic
itself (350+ lines of raw SQL with SAVEPOINTs over scheduler_config /
llm_accounts / queries / query_schedules / scheduler_runs) doesn't have
a sqlite-friendly path because the upstream tables aren't ORM-managed,
so the route handler is tested with run_manual_dispatch monkeypatched
on the router module. The real dispatch logic is exercised manually
via prod smoke tests (see PR description).
"""

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


def _scheduler_router_module():
    import app.api.admin.scheduler.router  # noqa: F401

    return sys.modules["app.api.admin.scheduler.router"]


class _FakeResult:
    def __init__(self, rows=None):
        self._rows = list(rows or [])

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)


class _ManualDispatchBatchSession:
    def __init__(self):
        self.query_insert_calls = 0
        self.query_insert_rows = 0
        self.inserted_query_rows = []
        self.schedule_update_calls = 0
        self.committed = False
        self.next_query_id = 100
        self.batch_columns = [
            "id",
            "query_text",
            "profile_id",
            "target_llm",
            "cadence_days",
            "brand_id",
            "prompt_id",
            "plan_kind",
            "target_llms_json",
            "query_items_json",
            "item_count",
        ]

    async def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        if "information_schema.tables" in sql:
            return _FakeResult([(1,)])
        if "information_schema.columns" in sql:
            table = params.get("n")
            if table == "query_schedules":
                return _FakeResult([(name,) for name in self.batch_columns])
            return _FakeResult([])
        if "FROM scheduler_config" in sql:
            return _FakeResult(
                [
                    {
                        "id": 1,
                        "mode": "auto",
                        "daily_time": "09:00",
                        "timezone": "Asia/Shanghai",
                        "temp_global_cap": None,
                        "engine_caps": {},
                        "retry_max": 3,
                        "paused_engines": [],
                    }
                ]
            )
        if "COALESCE(apm.profile_id" in sql:
            return _FakeResult(
                [
                    {
                        "account_id": 11,
                        "engine": "chatgpt",
                        "account_cap": 100,
                        "profile_id": "101",
                        "quota": 100,
                    },
                    {
                        "account_id": 12,
                        "engine": "gemini",
                        "account_cap": 100,
                        "profile_id": "101",
                        "quota": 100,
                    },
                ]
            )
        if "SELECT COUNT(*) AS n FROM query_schedules" in sql:
            return _FakeResult([{"n": 1}])
        if "FROM query_schedules qs" in sql and "ORDER BY next_run_at" in sql:
            return _FakeResult(
                [
                    {
                        "id": 7,
                        "query_text": "Query Pool batch (3 queries)",
                        "profile_id": None,
                        "target_llm": "chatgpt",
                        "cadence_days": 1,
                        "brand_id": 42,
                        "prompt_id": None,
                        "plan_kind": "batch",
                        "target_llms_json": ["chatgpt", "gemini"],
                        "query_items_json": [
                            {
                                "query_text": "best running shoes",
                                "profile_id": "101",
                                "brand_id": 42,
                                "prompt_id": 1001,
                                "language": "en",
                            },
                            {
                                "query_text": "best walking shoes",
                                "profile_id": "101",
                                "brand_id": 42,
                                "prompt_id": 1002,
                                "language": "en",
                            },
                            {
                                "query_text": "best trail shoes",
                                "profile_id": "101",
                                "brand_id": 42,
                                "prompt_id": 1003,
                                "language": "en",
                            },
                        ],
                        "item_count": 3,
                    }
                ]
            )
        if "INSERT INTO queries" in sql:
            self.query_insert_calls += 1
            self.query_insert_rows += len(params) if isinstance(params, list) else 1
            if isinstance(params, list):
                self.inserted_query_rows.extend(params)
                ids = [
                    {"id": query_id}
                    for query_id in range(
                        self.next_query_id,
                        self.next_query_id + len(params),
                    )
                ]
                self.next_query_id += len(params)
            else:
                self.inserted_query_rows.append(params)
                ids = [{"id": self.next_query_id}]
                self.next_query_id += 1
            return _FakeResult(ids if "RETURNING" in sql else [])
        if "UPDATE query_schedules" in sql:
            self.schedule_update_calls += 1
            return _FakeResult([])
        if "INSERT INTO scheduler_runs" in sql:
            return _FakeResult([{"id": 99}])
        raise AssertionError(f"unexpected SQL: {sql}")

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_manual_dispatch_batch_plan_uses_bulk_writes_to_avoid_proxy_timeout():
    from app.admin.scheduler.manual_dispatch import run_manual_dispatch

    session = _ManualDispatchBatchSession()

    result = await run_manual_dispatch(
        session,
        note="manual bulk test",
        brand_id=42,
        schedule_limit=50,
    )

    assert result["queries_created"] == 6
    assert result["run_id"] == 99
    assert result["query_ids"] == [100, 101, 102, 103, 104, 105]
    assert session.query_insert_rows == 6
    assert session.query_insert_calls == 1
    assert session.schedule_update_calls == 1
    assert {row["profile_id"] for row in session.inserted_query_rows} == {101}
    assert {row["target_llm"] for row in session.inserted_query_rows} == {"chatgpt", "gemini"}
    assert {(row["target_llm"], row["account_id"]) for row in session.inserted_query_rows} == {
        ("chatgpt", 11),
        ("gemini", 12),
    }
    assert session.committed is True


# ── auth gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_manual_trigger_unauth_401(client):
    resp = await client.post("/api/admin/scheduler/manual_trigger", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_manual_trigger_legacy_alias_unauth_401(client):
    resp = await client.post("/api/scheduler/manual_trigger", json={})
    assert resp.status_code == 401


# ── input validation ───────────────────────────────────────


@pytest.mark.asyncio
async def test_manual_trigger_invalid_cap_400(client, admin_operator, monkeypatch):
    a = _scheduler_router_module()
    monkeypatch.setattr(a, "run_manual_dispatch", AsyncMock(return_value={}))
    resp = await client.post("/api/admin/scheduler/manual_trigger", json={"cap": "not-int"})
    assert resp.status_code == 400
    assert resp.json()["error"] == "cap must be an integer or null"


# ── 503 path when upstream tables aren't on the DB ─────────


@pytest.mark.asyncio
async def test_manual_trigger_returns_503_when_tables_missing(client, admin_operator, monkeypatch):
    """sqlite test fixture has no scheduler tables; the route surfaces
    503 with a stable error code rather than 500."""
    a = _scheduler_router_module()

    async def _raise_unavailable(*args, **kwargs):
        raise RuntimeError("scheduler_tables_unavailable")

    monkeypatch.setattr(a, "run_manual_dispatch", _raise_unavailable)
    resp = await client.post("/api/admin/scheduler/manual_trigger", json={})
    assert resp.status_code == 503
    assert resp.json()["error"] == "scheduler_tables_unavailable"


@pytest.mark.asyncio
async def test_manual_trigger_returns_500_on_unexpected_error(client, admin_operator, monkeypatch):
    """Anything other than the known scheduler_tables_unavailable code
    surfaces as 500 with a truncated error string (admin_console parity)."""
    a = _scheduler_router_module()

    async def _raise_other(*args, **kwargs):
        raise ValueError("unexpected boom")

    monkeypatch.setattr(a, "run_manual_dispatch", _raise_other)
    resp = await client.post("/api/admin/scheduler/manual_trigger", json={})
    assert resp.status_code == 500
    assert "unexpected boom" in resp.json()["error"]


# ── happy path + audit ─────────────────────────────────────


@pytest.mark.asyncio
async def test_manual_trigger_success_audit_high(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    a = _scheduler_router_module()
    monkeypatch.setattr(a, "dispatch_many", MagicMock(return_value=(3, 0)))
    fake_result = {
        "target_total": 5,
        "queries_created": 3,
        "query_ids": [101, 102, 103],
        "run_id": 42,
        "reason": "ok",
        "schedules_enabled": 5,
        "schedules_dispatchable": 3,
        "paused_engines": [],
        "quotas_total": 0,
        "schedule_failures": [],
    }
    monkeypatch.setattr(a, "run_manual_dispatch", AsyncMock(return_value=fake_result))
    resp = await client.post(
        "/api/admin/scheduler/manual_trigger",
        json={"cap": 50, "note": "smoke test", "brand_id": 42, "limit": 1200},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["queries_created"] == 3
    assert body["dispatched"] == 3
    assert body["dispatch_failed"] == 0
    assert body["run_id"] == 42
    a.run_manual_dispatch.assert_awaited_once()
    a.dispatch_many.assert_called_once_with([101, 102, 103])
    dispatch_kwargs = a.run_manual_dispatch.await_args.kwargs
    assert dispatch_kwargs["brand_id"] == 42
    assert dispatch_kwargs["schedule_limit"] == 1200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "scheduler_manual_trigger")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "high"
    after = audit[0].after or {}
    assert after.get("queries_created") == 3
    assert after.get("cap_override") == 50
    assert after.get("brand_id") == 42
    assert after.get("schedule_limit") == 1200
    assert after.get("reason") == "ok"
    assert after.get("dispatched") == 3
    assert after.get("dispatch_failed") == 0


@pytest.mark.asyncio
async def test_manual_trigger_zero_dispatched_reason_propagates(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    """When 0 queries are created the audit row still fires and the
    ``reason`` field tells the operator why (admin_console line 10408)."""
    a = _scheduler_router_module()
    fake_result = {
        "target_total": 0,
        "queries_created": 0,
        "run_id": None,
        "reason": "all_engines_paused",
        "schedules_enabled": 5,
        "schedules_dispatchable": 0,
        "paused_engines": ["doubao", "deepseek", "chatgpt", "gemini"],
        "quotas_total": 0,
        "schedule_failures": [],
    }
    monkeypatch.setattr(a, "run_manual_dispatch", AsyncMock(return_value=fake_result))
    resp = await client.post("/api/admin/scheduler/manual_trigger", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["queries_created"] == 0
    assert body["reason"] == "all_engines_paused"
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "scheduler_manual_trigger")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].after.get("reason") == "all_engines_paused"
    assert audit[0].after.get("queries_created") == 0


@pytest.mark.asyncio
async def test_manual_trigger_returns_operator_message_for_quota_without_schedules(
    client, admin_operator, monkeypatch
):
    a = _scheduler_router_module()
    fake_result = {
        "target_total": 0,
        "queries_created": 0,
        "run_id": None,
        "reason": "no_schedules_only_bindings_no_prompts",
        "schedules_enabled": 0,
        "schedules_dispatchable": 0,
        "paused_engines": [],
        "quotas_total": 125,
        "schedule_failures": [],
    }
    monkeypatch.setattr(a, "run_manual_dispatch", AsyncMock(return_value=fake_result))

    resp = await client.post("/api/admin/scheduler/manual_trigger", json={})

    assert resp.status_code == 200
    body = resp.json()
    assert body["queries_created"] == 0
    assert "账号容量已配置" in body["message"]
    assert "125" in body["message"]
    assert "没有启用的 Query 计划" in body["message"]


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice8c_bis():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
