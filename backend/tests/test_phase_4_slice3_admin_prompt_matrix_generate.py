"""Phase 4 slice 3 — POST /api/admin/prompt-matrix/generate.

Mirrors topic_plan B.2.b: sync mode (PROMPT_MATRIX_SYNC_GENERATE=1) runs
the full LLM loop end-to-end with a mocked PromptMatrixClient; background
mode just verifies the response shape + run row landed.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import (
    AdminAuditLog,
    AdminUser,
    PromptCandidate,
    PromptGenerationRun,
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


def _patch_db(monkeypatch, **overrides):
    import app.admin.prompt_matrix.db as pm_db

    for name, value in overrides.items():
        monkeypatch.setattr(pm_db, name, value)


def _patch_client(monkeypatch, generate_batches_returns):
    """Replace PromptMatrixClient with a fake whose generate_prompt_batches
    yields canned (candidates, meta) tuples."""
    from app.admin.prompt_matrix import generation as gen_mod
    from app.admin.topic_plan.lib import DoubaoConfig

    class FakeClient:
        def __init__(self, config=None):
            self.config = DoubaoConfig(api_key="test", base_url="http://fake", model="doubao-test")

        async def generate_prompt_batches(self, **kwargs):
            for batch in generate_batches_returns:
                if isinstance(batch, Exception):
                    raise batch
                yield batch

    monkeypatch.setattr(gen_mod, "PromptMatrixClient", FakeClient)


def _llm_prompt(
    text: str,
    topic_id: int = 1,
    intent: str = "informational",
    prompt_scope: str = "branded",
    language: str = "zh-CN",
    competitive_type: str | None = None,
    tags_extra: dict[str, Any] | None = None,
) -> Any:
    from app.admin.prompt_matrix.lib import LLMPromptCandidate

    return LLMPromptCandidate(
        topic_id=topic_id,
        intent=intent,
        language=language,
        text=text,
        confidence=0.85,
        reason="r",
        template_strategy="latest",
        template_version="v1",
        tags={
            "prompt_scope": prompt_scope,
            **({"competitive_type": competitive_type} if competitive_type else {}),
            **(tags_extra or {}),
        },
    )


def _topic(*, raw_id: int = 1, brand_id: int = 1, brand: str = "NIKE") -> dict[str, Any]:
    return {
        "id": f"T-{raw_id}",
        "raw_id": raw_id,
        "title": "beginner running shoes",
        "brand": brand,
        "brand_id": brand_id,
        "industry": "footwear",
        "industry_id": "footwear",
        "dimension": "品牌",
        "dimension_key": "brand",
        "coverage": "gap",
        "coverageLabel": "No Prompt",
        "priority": "P1",
        "updatedAt": "",
        "prompt_count": 0,
        "prompt_intents": [],
        "prompt_languages": [],
        "missing_intents": [],
        "missing_languages": [],
        "brand_leak_count": 0,
        "selected": False,
    }


# ── validation ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_unauth_401(client):
    resp = await client.post("/api/admin/prompt-matrix/generate", json={"topic_ids": [1]})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_generate_missing_topic_ids_422(client, admin_operator):
    resp = await client.post("/api/admin/prompt-matrix/generate", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_generate_unknown_topics_404(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, fetch_topic_rows_by_ids=AsyncMock(return_value=[]))
    resp = await client.post("/api/admin/prompt-matrix/generate", json={"topic_ids": [99]})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_generate_rejects_max_prompts_above_dynamic_cap(client, admin_operator, monkeypatch):
    """One topic with 4 raw combinations has cap max(10, 4 * 2) == 10."""

    monkeypatch.delenv("PROMPT_MATRIX_SYNC_GENERATE", raising=False)
    _patch_db(
        monkeypatch,
        fetch_topic_rows_by_ids=AsyncMock(return_value=[_topic()]),
        fetch_brand_rows=AsyncMock(return_value=[]),
        fetch_existing_prompt_texts=AsyncMock(return_value=[]),
    )

    async def fake_background(*args, **kwargs):
        pass

    monkeypatch.setattr(
        "app.admin.prompt_matrix.generation.execute_generation_background",
        fake_background,
    )

    resp = await client.post(
        "/api/admin/prompt-matrix/generate",
        json={"topic_ids": [1], "max_prompts": 11},
    )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["field"] == "max_prompts"
    assert detail["reason"] == "must be <= 10"


# ── sync mode ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_sync_inserts_candidates_and_completes(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    """1 topic * 2 LLM prompts -> 2 candidates inserted, run flips to
    completed, audit emitted."""
    monkeypatch.setenv("PROMPT_MATRIX_SYNC_GENERATE", "1")
    _patch_db(
        monkeypatch,
        fetch_topic_rows_by_ids=AsyncMock(return_value=[_topic()]),
        fetch_brand_rows=AsyncMock(
            return_value=[{"id": 1, "name": "NIKE", "industry_id": "footwear", "aliases": []}]
        ),
        fetch_existing_prompt_texts=AsyncMock(return_value=[]),
    )
    _patch_client(
        monkeypatch,
        [
            (
                [
                    _llm_prompt("帮我推荐一双 NIKE 跑鞋"),
                    _llm_prompt("NIKE 跑鞋适合新手吗"),
                ],
                {"model": "doubao-test", "usage": {"prompt_tokens": 30}},
            )
        ],
    )

    resp = await client.post(
        "/api/admin/prompt-matrix/generate",
        json={
            "topic_ids": [1],
            "intent_count": 4,
            "language_count": 2,
            "max_per_topic": 4,
            "max_prompts": 10,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == "completed"
    run_id = body["run_id"]
    assert len(body["candidates"]) == 2

    # Run row landed
    run = (
        await db_session.execute(
            select(PromptGenerationRun).where(PromptGenerationRun.id == run_id)
        )
    ).scalar_one()
    assert run.status == "completed"
    assert run.candidates_generated == 2
    assert run.metrics_json is not None
    assert run.completed_at is not None

    # Candidates landed
    cands = list(
        (await db_session.execute(select(PromptCandidate).where(PromptCandidate.run_id == run_id)))
        .scalars()
        .all()
    )
    assert len(cands) == 2
    assert {c.tags["prompt_scope"] for c in cands} == {"branded"}

    # Audit emit
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "generate_prompt_matrix",
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
async def test_generate_sync_quality_blocked_candidates_remain_reviewable(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    """LLM quality failures are still visible as reviewable candidates."""
    monkeypatch.setenv("PROMPT_MATRIX_SYNC_GENERATE", "1")
    _patch_db(
        monkeypatch,
        fetch_topic_rows_by_ids=AsyncMock(return_value=[_topic()]),
        fetch_brand_rows=AsyncMock(
            return_value=[{"id": 1, "name": "NIKE", "industry_id": "footwear", "aliases": []}]
        ),
        fetch_existing_prompt_texts=AsyncMock(return_value=[]),
    )
    # All prompts fail is_natural_user_prompt
    _patch_client(
        monkeypatch,
        [
            (
                [_llm_prompt("nikenike")],  # too short / unnatural
                {"model": "doubao-test", "usage": {}},
            )
        ],
    )

    resp = await client.post(
        "/api/admin/prompt-matrix/generate",
        json={"topic_ids": [1], "max_prompts": 10},
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]

    run = (
        await db_session.execute(
            select(PromptGenerationRun).where(PromptGenerationRun.id == run_id)
        )
    ).scalar_one()
    assert run.status == "completed"
    assert run.llm_error is None
    assert run.candidates_generated == 1
    assert run.metrics_json["accepted"] == 0
    assert run.metrics_json["reviewable_blocked"] == 1
    assert run.metrics_json["hard_rejected"] == 0
    assert run.metrics_json["rejected_total"] == 1

    candidate = (
        await db_session.execute(select(PromptCandidate).where(PromptCandidate.run_id == run_id))
    ).scalar_one()
    assert candidate.status == "pending"
    assert candidate.tags["quality_gate_status"] == "blocked"
    assert candidate.tags["quality_gate_reason"] == "prompt_not_natural"


@pytest.mark.asyncio
async def test_generate_sync_blocks_competitive_prompt_missing_named_competitor(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("PROMPT_MATRIX_SYNC_GENERATE", "1")
    _patch_db(
        monkeypatch,
        fetch_topic_rows_by_ids=AsyncMock(return_value=[_topic()]),
        fetch_brand_rows=AsyncMock(
            return_value=[
                {"id": 1, "name": "NIKE", "industry_id": "footwear", "aliases": []},
                {"id": 2, "name": "Adidas", "industry_id": "footwear", "aliases": []},
            ]
        ),
        fetch_existing_prompt_texts=AsyncMock(return_value=[]),
    )
    _patch_client(
        monkeypatch,
        [
            (
                [
                    _llm_prompt(
                        "Is NIKE a better alternative for beginner running shoes?",
                        language="en-US",
                        prompt_scope="competitive",
                        competitive_type="direct_comparison",
                        tags_extra={
                            "competitor_name": "Adidas",
                            "competitor_brand_id": 2,
                            "scenario_axis": "comfort",
                        },
                    )
                ],
                {"model": "doubao-test", "usage": {}},
            )
        ],
    )

    resp = await client.post(
        "/api/admin/prompt-matrix/generate",
        json={"topic_ids": [1], "max_prompts": 1, "max_per_topic": 1},
    )

    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]
    candidate = (
        await db_session.execute(select(PromptCandidate).where(PromptCandidate.run_id == run_id))
    ).scalar_one()
    assert candidate.status == "pending"
    assert candidate.tags["quality_gate_status"] == "blocked"
    assert candidate.tags["quality_gate_reason"] == "competitive_competitor_missing"


@pytest.mark.asyncio
async def test_generate_sync_blocks_competitive_prompt_without_competitor_metadata(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("PROMPT_MATRIX_SYNC_GENERATE", "1")
    _patch_db(
        monkeypatch,
        fetch_topic_rows_by_ids=AsyncMock(return_value=[_topic()]),
        fetch_brand_rows=AsyncMock(
            return_value=[
                {"id": 1, "name": "NIKE", "industry_id": "footwear", "aliases": []},
                {"id": 2, "name": "Adidas", "industry_id": "footwear", "aliases": []},
            ]
        ),
        fetch_existing_prompt_texts=AsyncMock(return_value=[]),
    )
    _patch_client(
        monkeypatch,
        [
            (
                [
                    _llm_prompt(
                        "Is NIKE better than similar products for beginner running shoes?",
                        language="en-US",
                        prompt_scope="competitive",
                        competitive_type="direct_comparison",
                    )
                ],
                {"model": "doubao-test", "usage": {}},
            )
        ],
    )

    resp = await client.post(
        "/api/admin/prompt-matrix/generate",
        json={"topic_ids": [1], "max_prompts": 1, "max_per_topic": 1},
    )

    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]
    candidate = (
        await db_session.execute(select(PromptCandidate).where(PromptCandidate.run_id == run_id))
    ).scalar_one()
    assert candidate.status == "pending"
    assert candidate.tags["quality_gate_status"] == "blocked"
    assert candidate.tags["quality_gate_reason"] == "competitive_competitor_missing"


@pytest.mark.asyncio
async def test_generate_sync_blocks_competitive_prompt_missing_topic_brand(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    monkeypatch.setenv("PROMPT_MATRIX_SYNC_GENERATE", "1")
    _patch_db(
        monkeypatch,
        fetch_topic_rows_by_ids=AsyncMock(return_value=[_topic()]),
        fetch_brand_rows=AsyncMock(
            return_value=[
                {"id": 1, "name": "NIKE", "industry_id": "footwear", "aliases": []},
                {"id": 2, "name": "Adidas", "industry_id": "footwear", "aliases": []},
            ]
        ),
        fetch_existing_prompt_texts=AsyncMock(return_value=[]),
    )
    _patch_client(
        monkeypatch,
        [
            (
                [
                    _llm_prompt(
                        "Is Adidas better than other options for beginner running shoes?",
                        language="en-US",
                        prompt_scope="competitive",
                        competitive_type="direct_comparison",
                        tags_extra={
                            "competitor_name": "Adidas",
                            "competitor_brand_id": 2,
                            "scenario_axis": "comfort",
                        },
                    )
                ],
                {"model": "doubao-test", "usage": {}},
            )
        ],
    )

    resp = await client.post(
        "/api/admin/prompt-matrix/generate",
        json={"topic_ids": [1], "max_prompts": 1, "max_per_topic": 1},
    )

    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]
    candidate = (
        await db_session.execute(select(PromptCandidate).where(PromptCandidate.run_id == run_id))
    ).scalar_one()
    assert candidate.status == "pending"
    assert candidate.tags["quality_gate_status"] == "blocked"
    assert candidate.tags["quality_gate_reason"] == "competitive_brand_anchor_missing"


@pytest.mark.asyncio
async def test_generate_sync_persists_discovered_competitors_in_run_config(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    from app.admin.prompt_matrix import generation as gen_mod
    from app.admin.topic_plan.lib import DoubaoConfig

    monkeypatch.setenv("PROMPT_MATRIX_SYNC_GENERATE", "1")
    _patch_db(
        monkeypatch,
        fetch_topic_rows_by_ids=AsyncMock(return_value=[_topic()]),
        fetch_brand_rows=AsyncMock(return_value=[{"id": 1, "name": "NIKE", "aliases": []}]),
        fetch_existing_prompt_texts=AsyncMock(return_value=[]),
    )

    class FakeClient:
        def __init__(self, config=None):
            self.config = DoubaoConfig(api_key="test", base_url="http://fake", model="doubao-test")

        async def generate_prompt_batches(self, **kwargs):
            kwargs["config"]["competitors_by_topic"] = {
                "1": [
                    {
                        "name": "Adidas",
                        "brand_id": 2,
                        "source": "llm",
                        "scenario_axes": ["daily training"],
                    }
                ]
            }
            yield (
                [
                    _llm_prompt(
                        "Is NIKE better than Adidas for beginner running shoes?",
                        language="en-US",
                        prompt_scope="competitive",
                        competitive_type="direct_comparison",
                        tags_extra={
                            "competitor_name": "Adidas",
                            "competitor_brand_id": 2,
                            "scenario_axis": "daily training",
                        },
                    )
                ],
                {"model": "doubao-test", "usage": {}},
            )

    monkeypatch.setattr(gen_mod, "PromptMatrixClient", FakeClient)

    resp = await client.post(
        "/api/admin/prompt-matrix/generate",
        json={"topic_ids": [1], "max_prompts": 1, "max_per_topic": 1},
    )

    assert resp.status_code == 200, resp.text
    run_id = resp.json()["run_id"]
    run = (
        await db_session.execute(
            select(PromptGenerationRun).where(PromptGenerationRun.id == run_id)
        )
    ).scalar_one()
    assert run.request_config["competitors_by_topic"]["1"][0]["name"] == "Adidas"
    assert run.request_config["competitors_by_topic"]["1"][0]["source"] == "llm"


@pytest.mark.asyncio
async def test_generate_sync_surfaces_reviewable_quality_blocks_for_full_estimate(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    """Estimated 80 can produce 24 clean + 56 quality-blocked candidates."""
    monkeypatch.setenv("PROMPT_MATRIX_SYNC_GENERATE", "1")
    brands = ["NIKE", "Adidas", "Puma", "Asics"]
    topics = [_topic(raw_id=i, brand_id=i, brand=brand) for i, brand in enumerate(brands, start=1)]
    _patch_db(
        monkeypatch,
        fetch_topic_rows_by_ids=AsyncMock(return_value=topics),
        fetch_brand_rows=AsyncMock(
            return_value=[
                {"id": i, "name": brand, "industry_id": "footwear", "aliases": []}
                for i, brand in enumerate(brands, start=1)
            ]
        ),
        fetch_existing_prompt_texts=AsyncMock(return_value=[]),
    )
    prompts = []
    valid_templates = [
        "Is {brand} a good beginner running shoes choice for wet road jogging?",
        "Should wide feet runners consider {brand} beginner running shoes?",
        "Can {brand} beginner running shoes handle light gym training?",
        "Are {brand} beginner running shoes practical for daily school commute?",
        "Do {brand} beginner running shoes feel soft on treadmill runs?",
        "Would {brand} beginner running shoes work for long weekend errands?",
    ]
    blocked_templates = [
        "Could {brand} beginner running shoes handle rainy park jogging?",
        "Are flat feet support needs okay with {brand} beginner running shoes?",
        "Would {brand} beginner running shoes be useful on airport travel days?",
        "Can someone standing at work wear {brand} beginner running shoes?",
        "Do {brand} beginner running shoes feel stable on city pavement walks?",
        "Are {brand} beginner running shoes soft enough for easy recovery runs?",
        "Could outdoor stair workouts damage {brand} beginner running shoes?",
        "Should I pack {brand} beginner running shoes for a summer holiday?",
        "Are morning dog walks comfortable in {brand} beginner running shoes?",
        "Can {brand} beginner running shoes match casual denim outfits?",
        "Would a beginner half marathon be too much for {brand} beginner running shoes?",
        "Are {brand} beginner running shoes discreet enough for office lunch breaks?",
        "Could {brand} beginner running shoes survive light hiking paths?",
        "Do evening neighborhood laps feel cushioned in {brand} beginner running shoes?",
    ]
    for topic in topics:
        topic_id = int(topic["raw_id"])
        brand = str(topic["brand"])
        for template in valid_templates:
            prompts.append(
                _llm_prompt(
                    template.format(brand=brand),
                    topic_id=topic_id,
                    language="en-US",
                )
            )
        for template in blocked_templates:
            prompts.append(
                _llm_prompt(
                    template.format(brand=brand),
                    topic_id=topic_id,
                    language="zh-CN",
                )
            )
    _patch_client(monkeypatch, [(prompts, {"model": "doubao-test", "usage": {}})])

    resp = await client.post(
        "/api/admin/prompt-matrix/generate",
        json={
            "topic_ids": [1, 2, 3, 4],
            "intent_count": 4,
            "language_count": 2,
            "max_per_topic": 20,
            "max_prompts": 80,
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    run_id = body["run_id"]
    assert body["summary"]["estimated"] == 80
    assert len(body["candidates"]) == 80

    run = (
        await db_session.execute(
            select(PromptGenerationRun).where(PromptGenerationRun.id == run_id)
        )
    ).scalar_one()
    assert run.status == "completed"
    assert run.candidates_generated == 80
    assert run.metrics_json["accepted"] == 24
    assert run.metrics_json["reviewable_blocked"] == 56
    assert run.metrics_json["hard_rejected"] == 0
    assert run.metrics_json["rejected_total"] == 56

    cands = list(
        (await db_session.execute(select(PromptCandidate).where(PromptCandidate.run_id == run_id)))
        .scalars()
        .all()
    )
    assert len(cands) == 80
    assert sum(1 for cand in cands if cand.tags.get("quality_gate_status") == "blocked") == 56


@pytest.mark.asyncio
async def test_generate_sync_completes_with_partial_results_after_batch_error(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    from app.admin.prompt_matrix.lib import PromptMatrixError

    monkeypatch.setenv("PROMPT_MATRIX_SYNC_GENERATE", "1")
    _patch_db(
        monkeypatch,
        fetch_topic_rows_by_ids=AsyncMock(return_value=[_topic()]),
        fetch_brand_rows=AsyncMock(
            return_value=[{"id": 1, "name": "NIKE", "industry_id": "footwear", "aliases": []}]
        ),
        fetch_existing_prompt_texts=AsyncMock(return_value=[]),
    )
    _patch_client(
        monkeypatch,
        [
            (
                [_llm_prompt("Is NIKE good for beginner running shoes?", language="en-US")],
                {"model": "doubao-test", "usage": {"prompt_tokens": 30}},
            ),
            PromptMatrixError(
                "llm_call_failed",
                "Prompt Matrix generation failed: HTTP 429: quota exhausted",
            ),
        ],
    )

    resp = await client.post(
        "/api/admin/prompt-matrix/generate",
        json={"topic_ids": [1], "max_prompts": 10},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    run_id = body["run_id"]
    run = (
        await db_session.execute(
            select(PromptGenerationRun).where(PromptGenerationRun.id == run_id)
        )
    ).scalar_one()
    assert run.status == "completed"
    assert run.candidates_generated == 1
    assert run.llm_error is None
    assert run.metrics_json["partial_failure"] is True
    assert run.metrics_json["partial_completion"] is True
    assert "HTTP 429" in run.metrics_json["batch_error_message"]


# ── background mode ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_background_returns_running_immediately(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    monkeypatch.delenv("PROMPT_MATRIX_SYNC_GENERATE", raising=False)
    _patch_db(
        monkeypatch,
        fetch_topic_rows_by_ids=AsyncMock(return_value=[_topic()]),
        fetch_brand_rows=AsyncMock(return_value=[]),
        fetch_existing_prompt_texts=AsyncMock(return_value=[]),
    )

    async def fake_background(*args, **kwargs):
        pass

    monkeypatch.setattr(
        "app.admin.prompt_matrix.generation.execute_generation_background",
        fake_background,
    )

    resp = await client.post(
        "/api/admin/prompt-matrix/generate",
        json={"topic_ids": [1], "max_prompts": 10},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["status"] == "running"
    assert body["summary"]["estimated"] > 0

    run = (
        await db_session.execute(
            select(PromptGenerationRun).where(PromptGenerationRun.id == body["run_id"])
        )
    ).scalar_one()
    assert run.status == "running"
    assert run.admin_id == admin_operator.id


# ── audit gate ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_generate_route():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
