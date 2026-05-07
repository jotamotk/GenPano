"""Phase 3 B.2.a — admin topic_plan read paths + run lifecycle.

Read paths (config / coverage / candidates / topics) hit the
``brands`` / ``topics`` / ``prompts`` / ``queries`` upstream stub tables
in production via raw SQL in ``app/admin/topic_plan/db.py``. Sqlite has
no shape for those tables, so this test mocks the db helpers and
exercises the route layer (auth, query parsing, validation, response
shape). The real DB path is exercised by the production smoke test.

``GET /runs/{run_id}`` and ``POST /runs/{run_id}/stop`` use the
``TopicPlanRun`` ORM and run end-to-end against sqlite.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, AdminUser, TopicPlanRun
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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


def _patch_tp_db(monkeypatch, **overrides):
    """Helper to monkeypatch ``app.admin.topic_plan.db`` callables."""
    import app.admin.topic_plan.db as tp_db

    for name, value in overrides.items():
        monkeypatch.setattr(tp_db, name, value)


# ── GET /config ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_config_returns_brands_industries_categories(client, admin_operator, monkeypatch):
    _patch_tp_db(
        monkeypatch,
        fetch_brands=AsyncMock(
            return_value=[
                {"id": 1, "name": "NIKE", "industry_id": "footwear", "topic_count": 3},
                {"id": 2, "name": "Adidas", "industry_id": "footwear", "topic_count": 1},
                {"id": 3, "name": "Coke", "industry_id": "beverage", "topic_count": 0},
            ]
        ),
        fetch_categories=AsyncMock(return_value=[{"id": "running", "name": "running"}]),
        pending_summary=AsyncMock(return_value={"pending": 5, "low_confidence": 2}),
    )
    resp = await client.get("/api/admin/topic-plan/config")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert {it["id"] for it in body["industries"]} == {"footwear", "beverage"}
    assert body["categories"] == [{"id": "running", "name": "running"}]
    assert len(body["brands"]) == 3
    # default_industry should pick first sorted (alphabetical)
    assert body["defaults"]["industryId"] in {"beverage", "footwear"}
    assert body["summary"]["pending_candidates"] == 5
    assert body["summary"]["low_confidence"] == 2
    # llm_configured is False because no env vars in test
    assert body["summary"]["llm_configured"] is False


@pytest.mark.asyncio
async def test_get_config_unauth_401(client):
    resp = await client.get("/api/admin/topic-plan/config")
    assert resp.status_code == 401


# ── GET /coverage ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_coverage_returns_rows_gaps_summary(client, admin_operator, monkeypatch):
    _patch_tp_db(
        monkeypatch,
        fetch_brands=AsyncMock(
            return_value=[
                {"id": 1, "name": "NIKE", "industry_id": "footwear", "topic_count": 5},
                {"id": 2, "name": "Adidas", "industry_id": "footwear", "topic_count": 1},
            ]
        ),
        build_coverage=AsyncMock(
            return_value={
                "rows": [{"brand_id": 1, "brand": "NIKE", "topics": 5}],
                "gaps": [{"brand": "NIKE", "type": "product", "count": 3}],
                "summary": {"brand_count": 2, "topic_count": 6},
                "existing_topics": [],
            }
        ),
    )
    resp = await client.get("/api/admin/topic-plan/coverage?industry_id=footwear")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["rows"][0]["brand"] == "NIKE"
    assert body["gaps"][0]["count"] == 3


@pytest.mark.asyncio
async def test_get_coverage_invalid_brand_ids_422(client, admin_operator):
    resp = await client.get("/api/admin/topic-plan/coverage?brand_ids=not-an-int")
    assert resp.status_code == 422


# ── GET /candidates ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_candidates_returns_rows_and_summary(client, admin_operator, monkeypatch):
    _patch_tp_db(
        monkeypatch,
        fetch_candidates=AsyncMock(
            return_value=[
                {"id": "cand-1", "title": "Test", "status": "pending"},
                {"id": "cand-2", "title": "Test2", "status": "pending"},
            ]
        ),
        pending_summary=AsyncMock(return_value={"pending": 2, "low_confidence": 0}),
    )
    resp = await client.get("/api/admin/topic-plan/candidates?status=pending&limit=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["rows"]) == 2
    assert body["summary"]["pending_candidates"] == 2


@pytest.mark.asyncio
async def test_get_candidates_invalid_status_422(client, admin_operator):
    resp = await client.get("/api/admin/topic-plan/candidates?status=merged")
    assert resp.status_code == 422


# ── GET /topics ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_topics_returns_rows_and_summary(client, admin_operator, monkeypatch):
    _patch_tp_db(
        monkeypatch,
        fetch_topics=AsyncMock(
            return_value=(
                [{"id": "T-1", "title": "x", "dimension_key": "brand"}],
                {"totalTopics": 1, "promptCoverageLabel": "100%"},
            )
        ),
    )
    resp = await client.get("/api/admin/topic-plan/topics?limit=50")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["rows"][0]["id"] == "T-1"
    assert body["summary"]["totalTopics"] == 1


@pytest.mark.asyncio
async def test_get_topics_invalid_dimension_422(client, admin_operator):
    resp = await client.get("/api/admin/topic-plan/topics?dimension=weather")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_topics_invalid_status_422(client, admin_operator):
    resp = await client.get("/api/admin/topic-plan/topics?status=zombie")
    assert resp.status_code == 422


# ── GET /runs/{run_id} ────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_run_returns_run(client, admin_operator, db_session: AsyncSession):
    run = TopicPlanRun(
        id=_new_id(),
        admin_id=admin_operator.id,
        industry_id="footwear",
        category_id=None,
        brand_ids=[1, 2],
        status="completed",
        request_config={"max_topics": 50},
        candidates_generated=10,
        started_at=_now() - timedelta(seconds=30),
        completed_at=_now(),
    )
    db_session.add(run)
    await db_session.commit()

    resp = await client.get(f"/api/admin/topic-plan/runs/{run.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["run"]["id"] == run.id
    assert body["run"]["status"] == "completed"
    assert body["run"]["estimated_topics"] == 50
    assert body["run"]["candidates_generated"] == 10
    assert body["run"]["elapsed_seconds"] >= 0


@pytest.mark.asyncio
async def test_get_run_marks_stale_running_as_failed(
    client, admin_operator, db_session: AsyncSession
):
    """Running run with last update older than the configured timeout
    flips to ``failed`` with ``llm_error='topic_plan_run_timeout'``."""
    very_old = _now() - timedelta(hours=4)
    run = TopicPlanRun(
        id=_new_id(),
        admin_id=admin_operator.id,
        brand_ids=[1],
        status="running",
        request_config={"max_topics": 30},
        started_at=very_old,
        created_at=very_old,
        updated_at=very_old,
    )
    db_session.add(run)
    await db_session.commit()

    resp = await client.get(f"/api/admin/topic-plan/runs/{run.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run"]["status"] == "failed"
    assert body["run"]["llm_error"] == "topic_plan_run_timeout"


@pytest.mark.asyncio
async def test_get_run_unknown_404(client, admin_operator):
    resp = await client.get("/api/admin/topic-plan/runs/no-such-id")
    assert resp.status_code == 404


# ── POST /runs/{run_id}/stop ──────────────────────────────────


@pytest.mark.asyncio
async def test_stop_run_cancels_running_and_audits(
    client, admin_operator, db_session: AsyncSession
):
    run = TopicPlanRun(
        id=_new_id(),
        admin_id=admin_operator.id,
        brand_ids=[1],
        status="running",
        request_config={"max_topics": 30},
        started_at=_now(),
    )
    db_session.add(run)
    await db_session.commit()

    resp = await client.post(f"/api/admin/topic-plan/runs/{run.id}/stop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["run"]["status"] == "cancelled"
    assert body["run"]["completed_at"] is not None

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "topic_plan_run_cancelled",
                    AdminAuditLog.resource_id == run.id,
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
async def test_stop_run_already_finalized_no_op(client, admin_operator, db_session: AsyncSession):
    run = TopicPlanRun(
        id=_new_id(),
        admin_id=admin_operator.id,
        brand_ids=[1],
        status="completed",
        request_config={"max_topics": 30},
        started_at=_now() - timedelta(seconds=10),
        completed_at=_now(),
    )
    db_session.add(run)
    await db_session.commit()

    resp = await client.post(f"/api/admin/topic-plan/runs/{run.id}/stop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["already_finalized"] is True
    assert body["run"]["status"] == "completed"

    # No audit row for already-finalized stop
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "topic_plan_run_cancelled",
                    AdminAuditLog.resource_id == run.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert audit == []


@pytest.mark.asyncio
async def test_stop_run_unknown_404(client, admin_operator):
    resp = await client.post("/api/admin/topic-plan/runs/no-such-id/stop")
    assert resp.status_code == 404


# ── audit gate ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_b2a_routes():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
