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
                yield batch

    monkeypatch.setattr(gen_mod, "PromptMatrixClient", FakeClient)


def _llm_prompt(text: str, topic_id: int = 1, intent: str = "informational") -> Any:
    from app.admin.prompt_matrix.lib import LLMPromptCandidate

    return LLMPromptCandidate(
        topic_id=topic_id,
        intent=intent,
        language="zh-CN",
        text=text,
        confidence=0.85,
        reason="r",
        template_strategy="latest",
        template_version="v1",
        tags={},
    )


def _topic(*, raw_id: int = 1, brand_id: int = 1, brand: str = "NIKE") -> dict[str, Any]:
    return {
        "id": f"T-{raw_id}",
        "raw_id": raw_id,
        "title": "Test topic",
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
            "max_prompts": 50,
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
async def test_generate_sync_quality_blocked_marks_failed(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    """LLM returns only rejected items -> run.status='failed' /
    llm_error='quality_gate_blocked'."""
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
    assert run.status == "failed"
    assert run.llm_error == "quality_gate_blocked"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "generate_prompt_matrix_quality_blocked",
                    AdminAuditLog.resource_id == run_id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


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
        json={"topic_ids": [1], "max_prompts": 30},
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
