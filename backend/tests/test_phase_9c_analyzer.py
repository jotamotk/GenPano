"""Phase 9 slice 9c — /api/analyzer/* (8 routes)."""

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

from app.admin.analyzer.lib import (
    ANALYZER_TRIGGER_ACTIONS,
    AnalyzerValidationError,
    parse_trigger_payload,
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


def _analyzer_router_module():
    import app.api.analyzer.router  # noqa: F401

    return sys.modules["app.api.analyzer.router"]


def _patch_db(monkeypatch, **overrides):
    a = _analyzer_router_module()
    defaults = {
        "fetch_analyzer_stats": AsyncMock(
            return_value=overrides.get(
                "stats",
                {
                    "total": 0,
                    "done": 0,
                    "pending": 0,
                    "running": 0,
                    "failed": 0,
                    "avg_geo_score": None,
                    "total_brands_tracked": 0,
                },
            )
        ),
        "list_brands": AsyncMock(return_value=overrides.get("brands", [])),
        "list_distinct_llms": AsyncMock(return_value=overrides.get("llms", [])),
        "list_responses": AsyncMock(return_value=overrides.get("responses", [])),
        "fetch_response_detail": AsyncMock(
            return_value=overrides.get("detail", {"error": "Response not found"})
        ),
        "fetch_daily_scores": AsyncMock(return_value=overrides.get("daily", [])),
        "reset_responses_for_date": AsyncMock(return_value=overrides.get("reset_date", 0)),
        "reset_response_for_rerun": AsyncMock(return_value=overrides.get("reset_one", True)),
    }
    for name, mock in defaults.items():
        monkeypatch.setattr(a.analyzer_db, name, mock)
    monkeypatch.setattr(
        a,
        "dispatch_run_daily_analysis",
        MagicMock(return_value=overrides.get("daily_task", "task-123")),
    )
    monkeypatch.setattr(
        a,
        "dispatch_aggregate_daily_scores",
        MagicMock(return_value=overrides.get("agg_task", "task-456")),
    )
    monkeypatch.setattr(
        a,
        "dispatch_analyze_response",
        MagicMock(return_value=overrides.get("response_task", "task-789")),
    )


# ── lib.py ──────────────────────────────────────────────────


def test_constants():
    assert ANALYZER_TRIGGER_ACTIONS == ("analyze", "aggregate", "reanalyze")


def test_parse_trigger_invalid_action():
    with pytest.raises(AnalyzerValidationError) as exc:
        parse_trigger_payload({"action": "weird", "date": "2026-05-08"})
    assert exc.value.code == "invalid_action"


def test_parse_trigger_date_required():
    with pytest.raises(AnalyzerValidationError) as exc:
        parse_trigger_payload({})
    assert exc.value.code == "date_required"


def test_parse_trigger_invalid_date():
    with pytest.raises(AnalyzerValidationError) as exc:
        parse_trigger_payload({"date": "2026/05/08"})
    assert exc.value.code == "invalid_date"


def test_parse_trigger_invalid_brand_id():
    with pytest.raises(AnalyzerValidationError) as exc:
        parse_trigger_payload({"date": "2026-05-08", "brand_id": "weird"})
    assert exc.value.code == "invalid_brand_id"


def test_parse_trigger_default_action():
    out = parse_trigger_payload({"date": "2026-05-08"})
    assert out["action"] == "analyze"
    assert out["brand_id"] is None


# ── auth gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stats_unauth_401(client):
    resp = await client.get("/api/analyzer/stats")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_brands_unauth_401(client):
    resp = await client.get("/api/analyzer/brands")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_llms_unauth_401(client):
    resp = await client.get("/api/analyzer/llms")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_responses_unauth_401(client):
    resp = await client.get("/api/analyzer/responses")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_response_detail_unauth_401(client):
    resp = await client.get("/api/analyzer/response/1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_daily_unauth_401(client):
    resp = await client.get("/api/analyzer/daily")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_trigger_unauth_401(client):
    resp = await client.post("/api/analyzer/trigger", json={"date": "2026-05-08"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rerun_unauth_401(client):
    resp = await client.post("/api/analyzer/rerun/1")
    assert resp.status_code == 401


# ── reads ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stats_returns_full_shape(client, admin_operator, monkeypatch):
    _patch_db(
        monkeypatch,
        stats={
            "total": 100,
            "done": 80,
            "pending": 10,
            "running": 5,
            "failed": 5,
            "avg_geo_score": 0.75,
            "total_brands_tracked": 20,
        },
    )
    resp = await client.get("/api/analyzer/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 100
    assert body["avg_geo_score"] == 0.75
    assert body["total_brands_tracked"] == 20


@pytest.mark.asyncio
async def test_brands_passes_through(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, brands=[{"id": 1, "name": "Apple"}])
    resp = await client.get("/api/analyzer/brands")
    assert resp.status_code == 200
    assert resp.json() == [{"id": 1, "name": "Apple"}]


@pytest.mark.asyncio
async def test_llms_returns_array(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, llms=["doubao", "chatgpt"])
    resp = await client.get("/api/analyzer/llms")
    assert resp.status_code == 200
    assert resp.json() == ["doubao", "chatgpt"]


@pytest.mark.asyncio
async def test_responses_with_filters(client, admin_operator, monkeypatch):
    captured: dict = {}

    async def _capture(session, **kwargs):
        captured.update(kwargs)
        return [{"response_id": 1}]

    a = _analyzer_router_module()
    monkeypatch.setattr(a.analyzer_db, "list_responses", _capture)
    resp = await client.get(
        "/api/analyzer/responses?status=done&brand_id=1&llm=doubao"
        "&date_from=2026-05-01&date_to=2026-05-08&limit=20&offset=10"
    )
    assert resp.status_code == 200
    assert captured["status"] == "done"
    assert captured["brand_id"] == 1
    assert captured["llm"] == "doubao"
    assert captured["date_from"] == "2026-05-01"
    assert captured["date_to"] == "2026-05-08"
    assert captured["limit"] == 20
    assert captured["offset"] == 10


@pytest.mark.asyncio
async def test_response_detail_404_returns_error(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, detail={"error": "Response not found"})
    resp = await client.get("/api/analyzer/response/999")
    assert resp.status_code == 200  # admin_console parity — 200 with error key
    assert resp.json()["error"] == "Response not found"


@pytest.mark.asyncio
async def test_response_detail_with_analysis(client, admin_operator, monkeypatch):
    _patch_db(
        monkeypatch,
        detail={
            "id": 1,
            "geo_score": 0.8,
            "mentions": [],
            "citations": [],
            "features": [],
        },
    )
    resp = await client.get("/api/analyzer/response/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["geo_score"] == 0.8


@pytest.mark.asyncio
async def test_daily_clamps_days(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, daily=[])
    resp = await client.get("/api/analyzer/daily?days=999")
    assert resp.status_code == 422  # FastAPI Query(le=90) validation


# ── trigger / rerun ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_trigger_validation_400(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch)
    resp = await client.post("/api/analyzer/trigger", json={})
    assert resp.status_code == 400
    assert resp.json()["error"] == "date_required"


@pytest.mark.asyncio
async def test_trigger_celery_unavailable_503(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, daily_task=None)
    resp = await client.post(
        "/api/analyzer/trigger",
        json={"action": "analyze", "date": "2026-05-08"},
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "celery_unavailable"


@pytest.mark.asyncio
async def test_trigger_analyze_audit_med(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, daily_task="task-abc")
    resp = await client.post(
        "/api/analyzer/trigger",
        json={"action": "analyze", "date": "2026-05-08", "brand_id": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == "task-abc"
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "analyzer_trigger_analyze")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "med"


@pytest.mark.asyncio
async def test_trigger_aggregate_audit_med(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, agg_task="task-xyz")
    resp = await client.post(
        "/api/analyzer/trigger",
        json={"action": "aggregate", "date": "2026-05-08"},
    )
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "analyzer_trigger_aggregate")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "med"


@pytest.mark.asyncio
async def test_trigger_reanalyze_audit_high(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, reset_date=42, daily_task="task-rean")
    resp = await client.post(
        "/api/analyzer/trigger",
        json={"action": "reanalyze", "date": "2026-05-08"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "Reset 42 responses" in body["message"]
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "analyzer_trigger_reanalyze")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "high"
    assert audit[0].after.get("reset_count") == 42


@pytest.mark.asyncio
async def test_rerun_404_when_missing(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, reset_one=False)
    resp = await client.post("/api/analyzer/rerun/9999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_rerun_celery_unavailable_503_audit_still_emits(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, reset_one=True, response_task=None)
    resp = await client.post("/api/analyzer/rerun/77")
    assert resp.status_code == 503
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "analyzer_rerun_response")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].after.get("celery_unavailable") is True


@pytest.mark.asyncio
async def test_rerun_success_audit_med(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_db(monkeypatch, reset_one=True, response_task="task-rerun")
    resp = await client.post("/api/analyzer/rerun/77")
    assert resp.status_code == 200
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "analyzer_rerun_response")
            )
        )
        .scalars()
        .all()
    )
    assert audit[0].severity == "med"
    assert audit[0].after.get("task_id") == "task-rerun"


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice9c():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
