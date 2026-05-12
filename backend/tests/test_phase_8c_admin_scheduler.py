"""Phase 8 slice 8c — admin/scheduler (config + runs + schedules + today + upcoming).

Pure-python validators tested directly. DB helpers mocked since the
scheduler tables (scheduler_config, scheduler_runs, query_schedules,
queries) live in the prod admin_console schema and aren't created in
sqlite test fixtures.

manual_trigger is intentionally not part of this slice — it ports
``_run_manual_dispatch`` (350+ lines) and lands in slice 8c-bis. This
test file therefore omits manual_trigger coverage.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, AdminUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.scheduler.lib import (
    ALLOWED_LLM_ENGINES,
    LLM_DEFAULT_GEO,
    SCHEDULER_MODES,
    SchedulerValidationError,
    account_engine_geo,
    is_query_engine,
    normalize_engine_caps,
    normalize_engine_name,
    normalize_paused_engines,
    parse_config_payload,
    parse_schedule_payload,
    schedule_item_target_llms,
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


def _scheduler_router_module():
    import app.api.admin.scheduler.router  # noqa: F401

    return sys.modules["app.api.admin.scheduler.router"]


def _patch_db(monkeypatch, **overrides):
    """Patch every db-layer helper on the scheduler db module."""
    a = _scheduler_router_module()
    defaults = {
        "fetch_scheduler_config": AsyncMock(
            return_value=overrides.get(
                "config",
                {
                    "id": 1,
                    "mode": "auto",
                    "daily_time": "08:00",
                    "timezone": "Asia/Shanghai",
                    "temp_global_cap": None,
                    "engine_caps": {},
                    "retry_max": 2,
                    "paused_engines": [],
                    "updated_at": "2026-05-07T10:00:00",
                    "capacity": [],
                    "capacity_total": 0,
                },
            )
        ),
        "update_scheduler_config": AsyncMock(return_value=overrides.get("config_rowcount", 1)),
        "list_scheduler_runs": AsyncMock(return_value=overrides.get("runs", ([], None))),
        "delete_scheduler_run": AsyncMock(return_value=overrides.get("delete_run", True)),
        "bulk_delete_scheduler_runs": AsyncMock(return_value=overrides.get("bulk_runs_deleted", 0)),
        "fetch_today_dispatch": AsyncMock(
            return_value=overrides.get(
                "today",
                {
                    "engines": [],
                    "total": {"target": 0, "done": 0, "failed": 0, "running": 0, "pending": 0},
                },
            )
        ),
        "list_query_schedules": AsyncMock(return_value=overrides.get("schedules", [])),
        "get_query_schedule": AsyncMock(return_value=overrides.get("schedule_detail", None)),
        "create_query_schedule": AsyncMock(
            return_value=overrides.get("create_schedule", _schedule_row(7))
        ),
        "update_query_schedule": AsyncMock(
            return_value=overrides.get("update_schedule", _schedule_row(7))
        ),
        "delete_query_schedule": AsyncMock(return_value=overrides.get("delete_schedule", True)),
        "upcoming_schedule_fires": AsyncMock(return_value=overrides.get("upcoming", {})),
    }
    for name, mock in defaults.items():
        monkeypatch.setattr(a.scheduler_db, name, mock)


def _schedule_row(schedule_id: int = 1) -> dict:
    return {
        "id": schedule_id,
        "query_text": "Test plan",
        "profile_id": None,
        "target_llm": "doubao",
        "cadence_days": 1,
        "next_run_at": "2026-05-08T00:00:00",
        "last_run_at": None,
        "enabled": True,
        "note": None,
        "brand_id": None,
        "prompt_id": None,
        "created_at": "2026-05-07T00:00:00",
        "updated_at": "2026-05-07T00:00:00",
    }


# ── lib.py: pure helpers ─────────────────────────────────────


def test_constants():
    assert SCHEDULER_MODES == ("auto", "manual", "paused")
    assert ALLOWED_LLM_ENGINES == frozenset({"doubao", "deepseek", "chatgpt", "gemini"})


def test_account_engine_geo():
    assert account_engine_geo("doubao") == "CN"
    assert account_engine_geo("CHATGPT") == "US"
    assert account_engine_geo("") is None
    assert account_engine_geo(None) is None
    assert account_engine_geo("unknown") is None
    assert LLM_DEFAULT_GEO["doubao"] == "CN"


def test_is_query_engine_filters_hots_suffix():
    assert is_query_engine("doubao")
    assert is_query_engine("chatgpt")
    assert not is_query_engine("doubao_hots")  # excluded
    assert not is_query_engine("")
    assert not is_query_engine(None)


def test_normalize_engine_name():
    assert normalize_engine_name("  Doubao  ") == "doubao"
    assert normalize_engine_name(None) == ""


def test_normalize_paused_engines_dedupe_and_filter():
    assert normalize_paused_engines(["doubao", "DOUBAO", "hot_hots", "deepseek"]) == [
        "doubao",
        "deepseek",
    ]
    assert normalize_paused_engines(None) == []
    assert normalize_paused_engines("not a list") == []


def test_normalize_engine_caps_strict_mode():
    out = normalize_engine_caps({"doubao": 100, "deepseek": "200", "chatgpt": None})
    assert out == {"doubao": 100, "deepseek": 200, "chatgpt": None}


def test_normalize_engine_caps_strict_rejects_negative():
    with pytest.raises(SchedulerValidationError) as exc:
        normalize_engine_caps({"doubao": -1})
    assert exc.value.code == "engine_caps_invalid"


def test_normalize_engine_caps_non_strict_drops_invalid():
    out = normalize_engine_caps({"doubao": -1, "chatgpt": "weird"}, strict=False)
    assert out == {}


def test_parse_config_invalid_mode():
    with pytest.raises(SchedulerValidationError) as exc:
        parse_config_payload({"mode": "weird"})
    assert exc.value.code == "mode_invalid"


def test_parse_config_invalid_daily_time():
    with pytest.raises(SchedulerValidationError) as exc:
        parse_config_payload({"daily_time": "not-time"})
    assert exc.value.code == "daily_time_invalid"


def test_parse_config_invalid_temp_global_cap():
    with pytest.raises(SchedulerValidationError) as exc:
        parse_config_payload({"temp_global_cap": -1})
    assert exc.value.code == "temp_global_cap_invalid"


def test_parse_config_paused_engines_normalized():
    out = parse_config_payload({"paused_engines": ["doubao", "doubao", "weird_hots"]})
    assert out["paused_engines"] == ["doubao"]


def test_parse_config_engine_caps_dropped_invalid_keys():
    out = parse_config_payload({"engine_caps": {"doubao": 100, "weird_hots": 50}})
    assert "weird_hots" not in out["engine_caps"]
    assert out["engine_caps"]["doubao"] == 100


def test_parse_config_paused_engines_must_be_list():
    with pytest.raises(SchedulerValidationError) as exc:
        parse_config_payload({"paused_engines": "doubao"})
    assert exc.value.code == "paused_engines_invalid"


def test_parse_config_empty_returns_empty():
    assert parse_config_payload({}) == {}


def test_parse_schedule_create_required():
    with pytest.raises(SchedulerValidationError) as exc:
        parse_schedule_payload({"target_llm": "doubao"}, partial=False)
    assert exc.value.code == "query_text_required"


def test_parse_schedule_create_batch_plan():
    out = parse_schedule_payload(
        {
            "target_llms": [" Doubao ", "deepseek", "chatgpt", "doubao"],
            "query_items": [
                {
                    "query_text": "中文 Query",
                    "profile_id": "SEG-1-P1",
                    "prompt_id": "42",
                    "brand_id": "7",
                    "language": "zh",
                },
                {
                    "query_text": "English query",
                    "profile_id": "",
                    "language": "en",
                },
            ],
            "cadence_days": 2,
        },
        partial=False,
    )

    assert out["plan_kind"] == "batch"
    assert out["query_text"] == "Query Pool batch (2 queries)"
    assert out["target_llm"] == "doubao"
    assert out["target_llms"] == ["doubao", "deepseek", "chatgpt"]
    assert out["item_count"] == 2
    assert out["query_items"][0]["prompt_id"] == 42
    assert out["query_items"][0]["brand_id"] == 7
    assert out["query_items"][1]["profile_id"] is None


def test_schedule_item_target_llms_skip_english_for_cn_engines():
    assert schedule_item_target_llms(
        {"query_text": "Is bestCoffer accurate?", "language": "en"},
        ["doubao", "deepseek", "chatgpt"],
    ) == ["chatgpt"]
    assert schedule_item_target_llms(
        {"query_text": "bestCoffer 准确率怎么样?", "language": "zh"},
        ["doubao", "deepseek", "chatgpt"],
    ) == ["doubao", "deepseek", "chatgpt"]


def test_parse_schedule_create_target_llm_required():
    with pytest.raises(SchedulerValidationError) as exc:
        parse_schedule_payload({"query_text": "x"}, partial=False)
    assert exc.value.code == "target_llm_invalid"


def test_parse_schedule_create_target_llm_must_be_in_allowlist():
    with pytest.raises(SchedulerValidationError) as exc:
        parse_schedule_payload({"query_text": "x", "target_llm": "claude"}, partial=False)
    assert exc.value.code == "target_llm_invalid"


def test_parse_schedule_create_cadence_must_be_positive():
    with pytest.raises(SchedulerValidationError) as exc:
        parse_schedule_payload(
            {"query_text": "x", "target_llm": "doubao", "cadence_days": 0},
            partial=False,
        )
    assert exc.value.code == "cadence_days_invalid"


def test_parse_schedule_next_run_at_iso_string_to_datetime():
    out = parse_schedule_payload(
        {
            "query_text": "x",
            "target_llm": "doubao",
            "next_run_at": "2026-05-10T11:51:00.000Z",
        },
        partial=False,
    )

    assert out["next_run_at"].isoformat() == "2026-05-10T11:51:00"


def test_parse_schedule_next_run_at_invalid():
    with pytest.raises(SchedulerValidationError) as exc:
        parse_schedule_payload(
            {"query_text": "x", "target_llm": "doubao", "next_run_at": "not-a-date"},
            partial=False,
        )
    assert exc.value.code == "next_run_at_invalid"


def test_parse_schedule_partial_returns_only_changes():
    out = parse_schedule_payload({"enabled": False}, partial=True)
    assert out == {"enabled": False}


def test_parse_schedule_partial_invalid_target_llm():
    with pytest.raises(SchedulerValidationError) as exc:
        parse_schedule_payload({"target_llm": "weird"}, partial=True)
    assert exc.value.code == "target_llm_invalid"


def test_parse_schedule_brand_id_invalid():
    with pytest.raises(SchedulerValidationError) as exc:
        parse_schedule_payload({"brand_id": "not-int"}, partial=True)
    assert exc.value.code == "brand_id_invalid"


# ── auth gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_get_unauth_401(client):
    resp = await client.get("/api/admin/scheduler/config")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_config_legacy_alias_unauth_401(client):
    resp = await client.get("/api/scheduler/config")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_config_put_unauth_401(client):
    resp = await client.put("/api/admin/scheduler/config", json={"mode": "auto"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_runs_unauth_401(client):
    resp = await client.get("/api/admin/scheduler/runs")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_runs_delete_one_unauth_401(client):
    resp = await client.delete("/api/admin/scheduler/runs/1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_runs_bulk_delete_unauth_401(client):
    resp = await client.delete("/api/admin/scheduler/runs?all=1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_today_unauth_401(client):
    resp = await client.get("/api/admin/scheduler/today")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_schedules_list_unauth_401(client):
    resp = await client.get("/api/admin/scheduler/schedules")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_schedule_create_unauth_401(client):
    resp = await client.post(
        "/api/admin/scheduler/schedules",
        json={"query_text": "x", "target_llm": "doubao"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_schedule_update_unauth_401(client):
    resp = await client.put("/api/admin/scheduler/schedules/1", json={"enabled": False})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_schedule_delete_unauth_401(client):
    resp = await client.delete("/api/admin/scheduler/schedules/1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_upcoming_unauth_401(client):
    resp = await client.get("/api/admin/scheduler/upcoming")
    assert resp.status_code == 401


# ── /scheduler/config ───────────────────────────────────────


@pytest.mark.asyncio
async def test_config_get_returns_500_when_missing(client, admin_operator, monkeypatch):
    a = _scheduler_router_module()
    monkeypatch.setattr(a.scheduler_db, "fetch_scheduler_config", AsyncMock(return_value=None))
    resp = await client.get("/api/admin/scheduler/config")
    assert resp.status_code == 500
    assert resp.json()["error"] == "scheduler_config missing"


@pytest.mark.asyncio
async def test_config_get_returns_capacity(client, admin_operator, monkeypatch):
    _patch_db(
        monkeypatch,
        config={
            "id": 1,
            "mode": "auto",
            "daily_time": "08:00",
            "timezone": "UTC",
            "paused_engines": ["chatgpt"],
            "engine_caps": {"doubao": 100},
            "retry_max": 2,
            "temp_global_cap": None,
            "updated_at": "2026-05-07T10:00:00",
            "capacity": [{"engine": "doubao", "daily_capacity": 200}],
            "capacity_total": 200,
        },
    )
    resp = await client.get("/api/admin/scheduler/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "auto"
    assert body["paused_engines"] == ["chatgpt"]
    assert body["capacity_total"] == 200


@pytest.mark.asyncio
async def test_config_put_validation_400(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch)
    resp = await client.put("/api/admin/scheduler/config", json={"mode": "weird"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "mode_invalid"


@pytest.mark.asyncio
async def test_config_put_no_fields_returns_zero(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch)
    resp = await client.put("/api/admin/scheduler/config", json={})
    assert resp.status_code == 200
    assert resp.json()["updated"] == 0


@pytest.mark.asyncio
async def test_config_put_paused_severity_high(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch)
    resp = await client.put("/api/admin/scheduler/config", json={"mode": "paused"})
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_scheduler_config")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "high"


@pytest.mark.asyncio
async def test_config_put_normal_change_severity_med(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch)
    resp = await client.put("/api/admin/scheduler/config", json={"daily_time": "10:00"})
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_scheduler_config")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "med"


# ── /scheduler/runs ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_runs_bare_list_when_no_pagination(client, admin_operator, monkeypatch):
    rows = [
        {
            "id": 1,
            "started_at": "2026-05-01T00:00:00",
            "finished_at": "2026-05-01T00:05:00",
            "mode": "auto",
            "target_total": 10,
            "queries_created": 8,
            "note": "ok",
        }
    ]
    _patch_db(monkeypatch, runs=(rows, None))
    resp = await client.get("/api/admin/scheduler/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert body[0]["id"] == 1


@pytest.mark.asyncio
async def test_runs_paginated_when_query_present(client, admin_operator, monkeypatch):
    rows = [
        {
            "id": 1,
            "started_at": "2026-05-01T00:00:00",
            "finished_at": None,
            "mode": "auto",
            "target_total": 10,
            "queries_created": 0,
            "note": None,
        }
    ]
    _patch_db(monkeypatch, runs=(rows, 33))
    resp = await client.get("/api/admin/scheduler/runs?page=2&per_page=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 33
    assert body["page"] == 2
    assert body["per_page"] == 10


@pytest.mark.asyncio
async def test_runs_delete_one_404(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, delete_run=False)
    resp = await client.delete("/api/admin/scheduler/runs/999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_runs_delete_one_success_audit_med(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, delete_run=True)
    resp = await client.delete("/api/admin/scheduler/runs/77")
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "delete_scheduler_run")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "med"


@pytest.mark.asyncio
async def test_runs_bulk_delete_400_when_no_filter(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch)
    resp = await client.delete("/api/admin/scheduler/runs")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_runs_bulk_delete_all_audit_high(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, bulk_runs_deleted=12)
    resp = await client.delete("/api/admin/scheduler/runs?all=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["deleted"] == 12
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "bulk_delete_scheduler_runs")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "high"
    assert audit[0].after.get("all") is True


@pytest.mark.asyncio
async def test_runs_bulk_delete_empty_filter(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, bulk_runs_deleted=3)
    resp = await client.delete("/api/admin/scheduler/runs?empty=1")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 3


@pytest.mark.asyncio
async def test_runs_bulk_delete_ids_filter(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, bulk_runs_deleted=2)
    resp = await client.delete("/api/admin/scheduler/runs?ids=1,2,3")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 2


# ── /scheduler/today ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_today_returns_grouped(client, admin_operator, monkeypatch):
    _patch_db(
        monkeypatch,
        today={
            "engines": [
                {
                    "engine": "doubao",
                    "done": 3,
                    "failed": 0,
                    "running": 1,
                    "pending": 1,
                    "target": 5,
                },
            ],
            "total": {"target": 5, "done": 3, "failed": 0, "running": 1, "pending": 1},
        },
    )
    resp = await client.get("/api/admin/scheduler/today")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"]["target"] == 5
    assert body["engines"][0]["engine"] == "doubao"


# ── /scheduler/schedules ─────────────────────────────────────


@pytest.mark.asyncio
async def test_reconcile_stale_running_queries_marks_old_rows_failed(monkeypatch):
    from app.admin.scheduler import db as scheduler_db

    class Result:
        rowcount = 3

    class Session:
        def __init__(self):
            self.sql: list[str] = []
            self.params: list[dict] = []
            self.commits = 0

        async def execute(self, stmt, params=None):
            self.sql.append(str(stmt))
            self.params.append(params or {})
            return Result()

        async def commit(self):
            self.commits += 1

    monkeypatch.setattr(scheduler_db, "_table_exists", AsyncMock(return_value=True))

    session = Session()
    changed = await scheduler_db.reconcile_stale_running_queries(
        session,
        max_age_seconds=600,
    )

    assert changed == 3
    assert session.commits == 1
    assert session.params == [{"seconds": 600}]
    sql = session.sql[0]
    assert "LOWER(status) = 'running'" in sql
    assert "retry_reason = 'stale_running_timeout'" in sql
    assert "finished_at = NOW()" in sql
    assert "NOT EXISTS" in sql
    assert "FROM llm_responses" in sql


@pytest.mark.asyncio
async def test_schedules_list(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, schedules=[_schedule_row(7)])
    resp = await client.get("/api/admin/scheduler/schedules?enabled_only=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["id"] == 7


@pytest.mark.asyncio
async def test_schedules_list_paginated_brand_filter(client, admin_operator, monkeypatch):
    _patch_db(
        monkeypatch,
        schedules={"rows": [_schedule_row(7)], "total": 61, "page": 2, "per_page": 25},
    )
    a = _scheduler_router_module()

    resp = await client.get("/api/admin/scheduler/schedules?brand_id=42&page=2&per_page=25")

    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"][0]["id"] == 7
    assert body["total"] == 61
    kwargs = a.scheduler_db.list_query_schedules.await_args.kwargs
    assert kwargs["brand_id"] == 42
    assert kwargs["page"] == 2
    assert kwargs["per_page"] == 25


@pytest.mark.asyncio
async def test_schedule_create_validation_400(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch)
    resp = await client.post("/api/admin/scheduler/schedules", json={})
    assert resp.status_code == 400
    assert resp.json()["code"] == "query_text_required"


@pytest.mark.asyncio
async def test_schedule_create_success_audit_med(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, create_schedule=_schedule_row(99))
    resp = await client.post(
        "/api/admin/scheduler/schedules",
        json={"query_text": "Hot test", "target_llm": "doubao", "cadence_days": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 99
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "create_query_schedule")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "med"
    assert audit[0].after.get("target_llm") == "doubao"


@pytest.mark.asyncio
async def test_schedule_create_batch_plan_success_audit_med(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    row = {
        **_schedule_row(501),
        "query_text": "Query Pool batch (2 queries)",
        "target_llm": "doubao",
        "plan_kind": "batch",
        "target_llms": ["doubao", "chatgpt"],
        "query_items": [
            {"query_text": "中文 Query", "profile_id": "P1", "language": "zh"},
            {"query_text": "English query", "profile_id": None, "language": "en"},
        ],
        "item_count": 2,
    }
    _patch_db(monkeypatch, create_schedule=row)
    a = _scheduler_router_module()

    resp = await client.post(
        "/api/admin/scheduler/schedules",
        json={
            "target_llms": ["doubao", "chatgpt"],
            "query_items": [
                {"query_text": "中文 Query", "profile_id": "P1", "language": "zh"},
                {"query_text": "English query", "language": "en"},
            ],
            "cadence_days": 3,
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 501
    assert body["item_count"] == 2
    create_payload = a.scheduler_db.create_query_schedule.await_args.kwargs["payload"]
    assert create_payload["plan_kind"] == "batch"
    assert create_payload["target_llms"] == ["doubao", "chatgpt"]
    assert len(create_payload["query_items"]) == 2
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "create_query_schedule")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "med"
    assert audit[0].after.get("target_llms") == ["doubao", "chatgpt"]
    assert audit[0].after.get("item_count") == 2


@pytest.mark.asyncio
async def test_schedule_update_404_when_missing(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, schedule_detail=None)
    resp = await client.put("/api/admin/scheduler/schedules/999", json={"enabled": False})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_schedule_update_no_fields_returns_zero(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, schedule_detail=_schedule_row(1))
    resp = await client.put("/api/admin/scheduler/schedules/1", json={})
    assert resp.status_code == 200
    assert resp.json()["updated"] == 0


@pytest.mark.asyncio
async def test_schedule_update_target_llm_invalid_400(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, schedule_detail=_schedule_row(1))
    resp = await client.put("/api/admin/scheduler/schedules/1", json={"target_llm": "claude"})
    assert resp.status_code == 400
    assert resp.json()["code"] == "target_llm_invalid"


@pytest.mark.asyncio
async def test_schedule_update_audit_med(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(
        monkeypatch,
        schedule_detail=_schedule_row(7),
        update_schedule={**_schedule_row(7), "cadence_days": 5},
    )
    resp = await client.put("/api/admin/scheduler/schedules/7", json={"cadence_days": 5})
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "update_query_schedule")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "med"


@pytest.mark.asyncio
async def test_schedule_delete_404_when_missing(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, schedule_detail=None)
    resp = await client.delete("/api/admin/scheduler/schedules/999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_schedule_delete_audit_high(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, schedule_detail=_schedule_row(11), delete_schedule=True)
    resp = await client.delete("/api/admin/scheduler/schedules/11")
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "delete_query_schedule")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "high"


# ── /scheduler/upcoming ──────────────────────────────────────


@pytest.mark.asyncio
async def test_upcoming_returns_by_date(client, admin_operator, monkeypatch):
    _patch_db(
        monkeypatch,
        upcoming={
            "2026-05-08": [{"id": 1, "fires_at": "2026-05-08T00:00:00"}],
            "2026-05-09": [],
        },
    )
    resp = await client.get("/api/admin/scheduler/upcoming?days=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["days"] == 2
    assert "2026-05-08" in body["by_date"]


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice8c():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
