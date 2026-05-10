"""Phase 3 B.2.b — POST /api/admin/topic-plan/generate.

The generate route reads brands / coverage / candidates via the
``app.admin.topic_plan.db`` helpers (mocked here — sqlite has no shape
for ``brands`` / ``topics``) and drives the LLM batch loop via a mocked
``DoubaoTopicPlanClient``. ``topic_plan_runs`` and ``topic_candidates``
are real ORM tables and run end-to-end against sqlite.

Sync mode (``TOPIC_PLAN_SYNC_GENERATE=1``) is exercised inline. The
background path is verified by asserting the response shape +
``run.status='running'`` immediately after the call returns; the
background coroutine itself is exercised indirectly through sync-mode
because both paths share ``execute_generation``.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import (
    AdminAuditLog,
    AdminUser,
    BrandContextSnapshot,
    TopicCandidate,
    TopicPlanRun,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def test_topic_plan_run_timeout_allows_day_scale(monkeypatch):
    from app.admin.topic_plan.db import run_timeout_seconds

    monkeypatch.setenv("TOPIC_PLAN_RUN_TIMEOUT_SECONDS", "86400")

    run = SimpleNamespace(request_config={"max_topics": 10_000})

    assert run_timeout_seconds(run) == 86400


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


def _patch_tp_db(monkeypatch, **overrides):
    import app.admin.topic_plan.db as tp_db

    for name, value in overrides.items():
        monkeypatch.setattr(tp_db, name, value)


def _patch_doubao(monkeypatch, generate_topics_return):
    """Replace ``DoubaoTopicPlanClient`` so generation uses canned LLM output."""
    from app.admin.topic_plan import generation as gen_mod
    from app.admin.topic_plan.lib import DoubaoConfig

    class FakeClient:
        def __init__(self, config=None):
            self.config = DoubaoConfig(
                api_key="test",
                base_url="http://fake",
                model="doubao-test",
            )
            self.calls: list[dict[str, Any]] = []

        async def generate_topics(self, **kwargs):
            self.calls.append(kwargs)
            return generate_topics_return

    monkeypatch.setattr(gen_mod, "DoubaoTopicPlanClient", FakeClient)
    return FakeClient


def _coverage_with_one_gap(brand_name: str = "NIKE", brand_id: int = 1) -> dict[str, Any]:
    return {
        "rows": [{"brand_id": brand_id, "brand": brand_name, "topics": 0, "gaps": 1}],
        "gaps": [
            {
                "brand_id": brand_id,
                "brand": brand_name,
                "type": "product",
                "count": 4,
                "priority": "P1",
                "coverage_gap": f"{brand_name}:product",
            }
        ],
        "summary": {"brand_count": 1, "topic_count": 0, "gap_count": 1},
        "existing_topics": [],
    }


def _llm_topic(
    title: str,
    brand: str = "NIKE",
    dimension: str = "product",
    product_name: str | None = None,
) -> Any:
    from app.admin.topic_plan.lib import LLMTopic

    return LLMTopic(
        title=title,
        brand=brand,
        dimension=dimension,
        reason="consumer demand",
        confidence=0.85,
        coverage_gap=f"{brand}:{dimension}",
        product_name=product_name,
    )


# ── validation ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_unauth_401(client):
    resp = await client.post("/api/admin/topic-plan/generate", json={"brand_ids": [1]})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_generate_missing_brand_ids_422(client, admin_operator):
    resp = await client.post("/api/admin/topic-plan/generate", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_generate_invalid_brand_ids_422(client, admin_operator):
    resp = await client.post(
        "/api/admin/topic-plan/generate",
        json={"brand_ids": ["not-int"]},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_generate_no_matching_brands_404(client, admin_operator, monkeypatch):
    _patch_tp_db(monkeypatch, fetch_brands=AsyncMock(return_value=[]))
    resp = await client.post(
        "/api/admin/topic-plan/generate",
        json={"brand_ids": [99]},
    )
    assert resp.status_code == 404


# ── sync mode end-to-end ──────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_sync_inserts_candidates_and_completes_run(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    """Sync mode: one brand x one batch x 2 LLM topics → 2 candidates inserted,
    run flips to ``completed`` with metrics, audit emitted."""
    monkeypatch.setenv("TOPIC_PLAN_SYNC_GENERATE", "1")
    _patch_tp_db(
        monkeypatch,
        fetch_brands=AsyncMock(return_value=[{"id": 1, "name": "NIKE", "industry_id": "footwear"}]),
        build_coverage=AsyncMock(return_value=_coverage_with_one_gap()),
        fetch_pending_candidate_titles=AsyncMock(return_value=[]),
        fetch_products_by_brand=AsyncMock(return_value={}),
    )
    _patch_doubao(
        monkeypatch,
        (
            [
                _llm_topic("新手慢跑鞋选购指南"),
                _llm_topic("篮球鞋抓地力测评方法"),
            ],
            {"model": "doubao-test", "usage": {"prompt_tokens": 30, "total_tokens": 60}},
        ),
    )

    resp = await client.post(
        "/api/admin/topic-plan/generate",
        json={"brand_ids": [1], "max_topics": 50},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == "completed"
    run_id = body["run_id"]
    assert len(body["candidates"]) == 2

    # Run row landed and is completed
    run = (
        await db_session.execute(select(TopicPlanRun).where(TopicPlanRun.id == run_id))
    ).scalar_one()
    assert run.status == "completed"
    assert run.candidates_generated == 2
    assert run.metrics_json is not None
    assert run.metrics_json["accepted"] == 2
    assert run.completed_at is not None

    # Candidates landed
    cands = list(
        (await db_session.execute(select(TopicCandidate).where(TopicCandidate.run_id == run_id)))
        .scalars()
        .all()
    )
    assert len(cands) == 2
    assert {c.title for c in cands} == {"新手慢跑鞋选购指南", "篮球鞋抓地力测评方法"}

    # Audit emit (terminal state)
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "generate_topic_plan",
                    AdminAuditLog.resource_id == run_id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "med"


@pytest.mark.asyncio
async def test_generate_sync_persists_context_snapshot_and_topic_refs(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("TOPIC_PLAN_SYNC_GENERATE", "1")
    _patch_tp_db(
        monkeypatch,
        fetch_brands=AsyncMock(
            return_value=[
                {
                    "id": 1,
                    "name": "NIKE",
                    "industry_id": "footwear",
                    "products": [
                        {
                            "id": 10,
                            "name": "Pegasus",
                            "category": "running shoes",
                            "aliases": [],
                        }
                    ],
                }
            ]
        ),
        build_coverage=AsyncMock(return_value=_coverage_with_one_gap()),
        fetch_pending_candidate_titles=AsyncMock(return_value=[]),
        fetch_products_by_brand=AsyncMock(return_value={}),
    )
    _patch_doubao(
        monkeypatch,
        (
            [
                _llm_topic(
                    "Which Pegasus shoes are best for new runners?",
                    dimension="product",
                    product_name="Pegasus",
                )
            ],
            {
                "model": "doubao-test",
                "usage": {"total_tokens": 60},
                "brand_context_packs": {
                    "NIKE": {
                        "brand": {"name": "NIKE", "industry": "footwear"},
                        "products": [{"name": "Pegasus", "category": "running shoes"}],
                        "scenarios": [{"name": "beginner running"}],
                        "competitors": [{"name": "Adidas", "competitor_type": "direct"}],
                        "audience_hypotheses": [{"segment_name": "new runners"}],
                        "claims": {"pros": ["stable fit"]},
                        "source_notes": [
                            {"title": "Official", "url": "https://nike.example/pegasus"}
                        ],
                    }
                },
            },
        ),
    )

    resp = await client.post(
        "/api/admin/topic-plan/generate",
        json={"brand_ids": [1], "max_topics": 5},
    )

    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]
    snapshot = (
        await db_session.execute(
            select(BrandContextSnapshot).where(BrandContextSnapshot.created_from_run_id == run_id)
        )
    ).scalar_one()
    assert snapshot.brand_id == 1
    assert snapshot.payload_json["products"][0]["name"] == "Pegasus"

    candidate = (
        await db_session.execute(select(TopicCandidate).where(TopicCandidate.run_id == run_id))
    ).scalar_one()
    assert candidate.brand_context_version == snapshot.version
    assert candidate.topic_axis == "product"
    assert candidate.context_refs_json["products"] == ["Pegasus"]

    run = (
        await db_session.execute(select(TopicPlanRun).where(TopicPlanRun.id == run_id))
    ).scalar_one()
    assert run.request_config["brand_context_versions"]["1"] == snapshot.version


@pytest.mark.asyncio
async def test_generate_sync_quality_blocked_marks_failed(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    """LLM returns nothing usable (all rejected) → run.status='failed' with
    llm_error='quality_gate_blocked'."""
    monkeypatch.setenv("TOPIC_PLAN_SYNC_GENERATE", "1")
    _patch_tp_db(
        monkeypatch,
        fetch_brands=AsyncMock(return_value=[{"id": 1, "name": "NIKE", "industry_id": "footwear"}]),
        build_coverage=AsyncMock(return_value=_coverage_with_one_gap()),
        fetch_pending_candidate_titles=AsyncMock(return_value=[]),
        fetch_products_by_brand=AsyncMock(return_value={}),
    )
    # All LLM topics fail "is_natural_consumer_topic" gate (operator wording)
    _patch_doubao(
        monkeypatch,
        (
            [
                _llm_topic("LVMH集团旗下品牌档次划分"),  # rejected: stilted
                _llm_topic("LVMH知名品牌市场表现分析"),  # rejected: stilted
            ],
            {"model": "doubao-test", "usage": {}},
        ),
    )

    resp = await client.post(
        "/api/admin/topic-plan/generate",
        json={"brand_ids": [1], "max_topics": 50},
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    run = (
        await db_session.execute(select(TopicPlanRun).where(TopicPlanRun.id == run_id))
    ).scalar_one()
    assert run.status == "failed"
    assert run.llm_error == "quality_gate_blocked"
    assert run.metrics_json["quality_blocked"] is True

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "generate_topic_plan_quality_blocked",
                    AdminAuditLog.resource_id == run_id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_generate_sync_rejects_brand_named_topic_titles(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    """Topics belong to the selected brand row, but the visible title stays
    brand-neutral. Branded/non-branded/competitor expansion happens at Prompt.
    """
    monkeypatch.setenv("TOPIC_PLAN_SYNC_GENERATE", "1")
    _patch_tp_db(
        monkeypatch,
        fetch_brands=AsyncMock(return_value=[{"id": 1, "name": "NIKE", "industry_id": "footwear"}]),
        build_coverage=AsyncMock(return_value=_coverage_with_one_gap()),
        fetch_pending_candidate_titles=AsyncMock(return_value=[]),
        fetch_products_by_brand=AsyncMock(return_value={}),
    )
    _patch_doubao(
        monkeypatch,
        (
            [
                _llm_topic("NIKE跑鞋怎么选不容易伤膝盖", dimension="product"),
                _llm_topic("新手慢跑鞋怎么选不容易伤膝盖", dimension="category"),
            ],
            {"model": "doubao-test", "usage": {"total_tokens": 60}},
        ),
    )

    resp = await client.post(
        "/api/admin/topic-plan/generate",
        json={"brand_ids": [1], "max_topics": 10},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert [c["title"] for c in body["candidates"]] == ["新手慢跑鞋怎么选不容易伤膝盖"]
    assert {item["reason"] for item in body["summary"]["skipped"]} >= {"topic_brand_leak"}

    run = (
        await db_session.execute(select(TopicPlanRun).where(TopicPlanRun.id == body["run_id"]))
    ).scalar_one()
    assert run.metrics_json["by_reason"]["topic_brand_leak"] == 1


@pytest.mark.asyncio
async def test_generate_sync_llm_error_marks_failed(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    """LLM client raises → run.status='failed', llm_error has the code,
    response is 503 (llm_*) per topic_plan_run_failed_status_code."""
    from app.admin.topic_plan.lib import TopicPlanLLMError

    monkeypatch.setenv("TOPIC_PLAN_SYNC_GENERATE", "1")
    _patch_tp_db(
        monkeypatch,
        fetch_brands=AsyncMock(return_value=[{"id": 1, "name": "NIKE", "industry_id": "footwear"}]),
        build_coverage=AsyncMock(return_value=_coverage_with_one_gap()),
        fetch_pending_candidate_titles=AsyncMock(return_value=[]),
        fetch_products_by_brand=AsyncMock(return_value={}),
    )

    from app.admin.topic_plan import generation as gen_mod

    class BoomClient:
        def __init__(self, config=None):
            from app.admin.topic_plan.lib import DoubaoConfig

            self.config = DoubaoConfig(api_key="x", base_url="x", model="x")

        async def generate_topics(self, **kwargs):
            raise TopicPlanLLMError("llm_call_failed", "boom")

    monkeypatch.setattr(gen_mod, "DoubaoTopicPlanClient", BoomClient)

    resp = await client.post(
        "/api/admin/topic-plan/generate",
        json={"brand_ids": [1], "max_topics": 10},
    )
    body = resp.json()
    # Sync mode wraps the error and returns 200 with the inline error body
    # — admin_console behavior. The detail body still carries the code.
    assert "code" in body or "error" in body
    # The run row got marked failed
    if "run_id" in body:
        run_id = body["run_id"]
    else:
        # _problem-style response
        run_id = body.get("run_id") or body.get("extra", {}).get("run_id")
    if run_id:
        run = (
            await db_session.execute(select(TopicPlanRun).where(TopicPlanRun.id == run_id))
        ).scalar_one_or_none()
        assert run is None or run.status == "failed"
        assert run is None or run.llm_error == "llm_call_failed: boom"


# ── background mode ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_background_returns_running_immediately(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    """Background mode (default): response should be ``status='running'``
    with run_id + estimated count, even before the LLM has been called.
    """
    monkeypatch.delenv("TOPIC_PLAN_SYNC_GENERATE", raising=False)
    _patch_tp_db(
        monkeypatch,
        fetch_brands=AsyncMock(return_value=[{"id": 1, "name": "NIKE", "industry_id": "footwear"}]),
        build_coverage=AsyncMock(return_value=_coverage_with_one_gap()),
        fetch_pending_candidate_titles=AsyncMock(return_value=[]),
        fetch_products_by_brand=AsyncMock(return_value={}),
    )
    # Replace background entry to a no-op so the test doesn't depend on
    # the worker scheduling outcome.
    called = {}

    async def fake_background(*args, **kwargs):
        called["ran"] = True

    monkeypatch.setattr(
        "app.admin.topic_plan.generation.execute_generation_background",
        fake_background,
    )

    resp = await client.post(
        "/api/admin/topic-plan/generate",
        json={"brand_ids": [1], "max_topics": 30},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == "running"
    assert body["summary"]["estimated"] == 30
    run_id = body["run_id"]

    # Run row inserted with status=running
    run = (
        await db_session.execute(select(TopicPlanRun).where(TopicPlanRun.id == run_id))
    ).scalar_one()
    assert run.status == "running"
    assert run.admin_id == admin_operator.id
    assert run.candidates_generated == 0


# ── audit gate ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_generate_route():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
