"""Phase 4 — admin prompt_matrix routes (initial slice).

Mirrors topic_plan B.1 + B.2.a runs/stop tests. The 6 heavier routes
(config / topics / gaps / prompts / candidates list / generate) ship in
follow-up PRs once db.py + generation.py are vendored.

Both candidate review routes use ``PromptCandidate`` ORM end-to-end
against sqlite. ``GET /runs/{id}`` and ``POST /runs/{id}/stop`` use
``PromptGenerationRun`` ORM the same way. No upstream stub queries here.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

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


def _candidate(
    *, status: str = "pending", text: str = "test prompt", topic_id: int = 1
) -> PromptCandidate:
    return PromptCandidate(
        id=_new_id(),
        run_id=None,
        topic_id=topic_id,
        topic_text="Topic text",
        brand_id=1,
        brand_name="NIKE",
        dimension="brand",
        intent="informational",
        language="zh-CN",
        text=text,
        status=status,
        confidence=0.85,
        tags={},
    )


def test_build_prompt_matrix_messages_frontloads_quality_rules():
    from app.admin.prompt_matrix.lib import build_prompt_matrix_messages

    messages = build_prompt_matrix_messages(
        topics=[
            {
                "raw_id": 1,
                "title": "新手慢跑鞋怎么选不容易伤膝盖",
                "brand": "NIKE",
                "brand_id": 1,
                "dimension_key": "category",
            }
        ],
        config={"intent_count": 1, "language_count": 1, "max_per_topic": 1, "max_prompts": 1},
        known_brands=[{"name": "NIKE", "aliases": ["耐克"]}],
        existing_prompts=[],
    )
    combined = "\n".join(message["content"] for message in messages)

    assert "前置质检规则" in combined
    assert "不要依赖后端丢弃" in combined
    assert "prompt_not_natural" in combined
    assert "category_brand_leak" in combined
    assert "Topic layer" in combined
    assert "Prompt layer" in combined
    assert "Query layer" in combined
    assert "prompt_scope" in combined
    assert "non_branded" in combined
    assert "branded" in combined
    assert "competitor" in combined


def test_parse_llm_prompt_candidates_persists_prompt_scope():
    from app.admin.prompt_matrix.lib import parse_llm_prompt_candidates

    parsed = parse_llm_prompt_candidates(
        {
            "prompts": [
                {
                    "topic_id": 1,
                    "intent": "informational",
                    "language": "en-US",
                    "text": "How should I choose running shoes for knee pain?",
                    "confidence": 0.8,
                    "tags": {"prompt_scope": "branded"},
                },
                {
                    "topic_id": 1,
                    "intent": "commercial",
                    "language": "en-US",
                    "text": "Which running shoes are best for knee pain?",
                    "confidence": 0.75,
                    "tags": {},
                },
            ]
        },
        topics_by_id={
            1: {
                "id": 1,
                "title": "running shoes for knee pain",
                "dimension": "product",
                "brand": "NIKE",
            }
        },
        known_brands=[{"name": "NIKE", "aliases": []}],
    )

    assert parsed[0].tags["prompt_scope"] == "branded"
    assert parsed[1].tags["prompt_scope"] == "non_branded"


def test_parse_llm_prompt_candidates_accepts_common_llm_shapes():
    from app.admin.prompt_matrix.lib import parse_llm_prompt_candidates

    item = {
        "topic_id": 1,
        "intent": "informational",
        "language": "en-US",
        "text": "How should I choose running shoes for knee pain?",
        "confidence": 0.8,
        "prompt_scope": "branded",
    }
    topics_by_id = {
        1: {
            "id": 1,
            "title": "running shoes for knee pain",
            "dimension": "product",
            "brand": "NIKE",
        }
    }
    known_brands = [{"name": "NIKE", "aliases": []}]

    assert parse_llm_prompt_candidates(
        [item],
        topics_by_id=topics_by_id,
        known_brands=known_brands,
    )[0].text.startswith("How should")
    assert (
        parse_llm_prompt_candidates(
            {"items": [item]},
            topics_by_id=topics_by_id,
            known_brands=known_brands,
        )[0].tags["prompt_scope"]
        == "branded"
    )
    assert (
        parse_llm_prompt_candidates(
            {"prompt": item},
            topics_by_id=topics_by_id,
            known_brands=known_brands,
        )[0].intent
        == "informational"
    )


def test_parse_llm_prompt_candidates_allows_branded_scope_for_category_topic():
    from app.admin.prompt_matrix.lib import parse_llm_prompt_candidates

    parsed = parse_llm_prompt_candidates(
        {
            "prompts": [
                {
                    "topic_id": 1,
                    "intent": "commercial",
                    "language": "en-US",
                    "text": "Is NIKE good for beginner running shoes?",
                    "confidence": 0.8,
                    "prompt_scope": "branded",
                }
            ]
        },
        topics_by_id={
            1: {
                "id": 1,
                "title": "beginner running shoes",
                "dimension": "category",
                "brand": "NIKE",
            }
        },
        known_brands=[{"name": "NIKE", "aliases": []}],
    )

    assert parsed[0].tags["prompt_scope"] == "branded"


def test_parse_llm_prompt_candidates_rejects_invalid_prompt_scope():
    from app.admin.prompt_matrix.lib import PromptMatrixError, parse_llm_prompt_candidates

    with pytest.raises(PromptMatrixError) as exc_info:
        parse_llm_prompt_candidates(
            {
                "prompts": [
                    {
                        "topic_id": 1,
                        "intent": "informational",
                        "language": "en-US",
                        "text": "How should I choose running shoes for knee pain?",
                        "confidence": 0.8,
                        "prompt_scope": "mixed",
                    }
                ]
            },
            topics_by_id={
                1: {
                    "id": 1,
                    "title": "running shoes for knee pain",
                    "dimension": "product",
                    "brand": "NIKE",
                }
            },
            known_brands=[{"name": "NIKE", "aliases": []}],
        )

    assert exc_info.value.code == "llm_schema_invalid"
    assert "prompt_scope" in exc_info.value.message


# ── single review ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_review_unauth_401(client):
    resp = await client.post(
        "/api/admin/prompt-matrix/candidates/x/review",
        json={"status": "rejected"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_review_reject_updates_status_and_audits(
    client, admin_operator, db_session: AsyncSession
):
    cand = _candidate()
    db_session.add(cand)
    await db_session.commit()

    resp = await client.post(
        f"/api/admin/prompt-matrix/candidates/{cand.id}/review",
        json={"status": "rejected", "reason": "off-topic"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["candidate"]["status"] == "rejected"

    await db_session.refresh(cand)
    assert cand.status == "rejected"
    assert cand.reviewed_by == admin_operator.id
    assert cand.review_reason == "off-topic"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "review_prompt_candidate",
                    AdminAuditLog.resource_id == cand.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "med"


@pytest.mark.asyncio
async def test_review_approve_updates_status(client, admin_operator, db_session: AsyncSession):
    """Prompt Matrix approve does NOT cross to a `prompts` insert (unlike
    topic_plan); it just flips status. SPA's "promote to prompt" is a
    separate Phase 5 (query_pool) flow."""
    cand = _candidate()
    db_session.add(cand)
    await db_session.commit()

    resp = await client.post(
        f"/api/admin/prompt-matrix/candidates/{cand.id}/review",
        json={"status": "approved"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["candidate"]["status"] == "approved"


@pytest.mark.asyncio
async def test_review_already_reviewed_returns_400(
    client, admin_operator, db_session: AsyncSession
):
    cand = _candidate(status="approved")
    db_session.add(cand)
    await db_session.commit()

    resp = await client.post(
        f"/api/admin/prompt-matrix/candidates/{cand.id}/review",
        json={"status": "rejected"},
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body["detail"]["code"] == "candidate_already_reviewed"


@pytest.mark.asyncio
async def test_review_invalid_status_422(client, admin_operator, db_session: AsyncSession):
    cand = _candidate()
    db_session.add(cand)
    await db_session.commit()
    resp = await client.post(
        f"/api/admin/prompt-matrix/candidates/{cand.id}/review",
        json={"status": "merged"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_review_unknown_404(client, admin_operator):
    resp = await client.post(
        "/api/admin/prompt-matrix/candidates/no-such-id/review",
        json={"status": "rejected"},
    )
    assert resp.status_code == 404


# ── bulk review ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_review_all_succeed(client, admin_operator, db_session: AsyncSession):
    cands = [_candidate(text=f"prompt {i}") for i in range(3)]
    for c in cands:
        db_session.add(c)
    await db_session.commit()

    resp = await client.post(
        "/api/admin/prompt-matrix/candidates/bulk-review",
        json={
            "candidate_ids": [c.id for c in cands],
            "status": "rejected",
            "reason": "noisy batch",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["updated_count"] == 3
    assert body["summary"]["failed_count"] == 0


@pytest.mark.asyncio
async def test_bulk_review_partial_failure_returns_409(
    client, admin_operator, db_session: AsyncSession
):
    good = _candidate(text="ok")
    already = _candidate(status="approved", text="already")
    db_session.add(good)
    db_session.add(already)
    await db_session.commit()

    resp = await client.post(
        "/api/admin/prompt-matrix/candidates/bulk-review",
        json={
            "candidate_ids": [good.id, already.id, "no-such-id"],
            "status": "rejected",
        },
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["summary"]["updated_count"] == 1
    assert body["summary"]["failed_count"] == 1
    assert body["summary"]["missing_count"] == 1


@pytest.mark.asyncio
async def test_bulk_review_too_many_422(client, admin_operator):
    resp = await client.post(
        "/api/admin/prompt-matrix/candidates/bulk-review",
        json={
            "candidate_ids": [f"id-{i}" for i in range(201)],
            "status": "rejected",
        },
    )
    assert resp.status_code == 422


# ── runs ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_run_returns_run(client, admin_operator, db_session: AsyncSession):
    run = PromptGenerationRun(
        id=_new_id(),
        admin_id=admin_operator.id,
        status="completed",
        request_config={"max_prompts": 100},
        selected_topic_ids=[1, 2],
        estimated_prompts=100,
        candidates_generated=42,
        started_at=_now() - timedelta(seconds=30),
        completed_at=_now(),
    )
    db_session.add(run)
    await db_session.commit()

    resp = await client.get(f"/api/admin/prompt-matrix/runs/{run.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run"]["id"] == run.id
    assert body["run"]["status"] == "completed"
    assert body["run"]["estimated_prompts"] == 100
    assert body["run"]["candidates_generated"] == 42
    assert body["run"]["elapsed_seconds"] >= 0


@pytest.mark.asyncio
async def test_get_run_marks_stale_running_as_failed(
    client, admin_operator, db_session: AsyncSession
):
    very_old = _now() - timedelta(hours=8)
    run = PromptGenerationRun(
        id=_new_id(),
        admin_id=admin_operator.id,
        status="running",
        request_config={"max_prompts": 100},
        started_at=very_old,
        created_at=very_old,
        updated_at=very_old,
    )
    db_session.add(run)
    await db_session.commit()

    resp = await client.get(f"/api/admin/prompt-matrix/runs/{run.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run"]["status"] == "failed"
    assert body["run"]["llm_error"] == "prompt_matrix_run_timeout"


@pytest.mark.asyncio
async def test_get_run_unknown_404(client, admin_operator):
    resp = await client.get("/api/admin/prompt-matrix/runs/no-such-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stop_run_cancels_and_audits(client, admin_operator, db_session: AsyncSession):
    run = PromptGenerationRun(
        id=_new_id(),
        admin_id=admin_operator.id,
        status="running",
        request_config={"max_prompts": 100},
        started_at=_now(),
    )
    db_session.add(run)
    await db_session.commit()

    resp = await client.post(f"/api/admin/prompt-matrix/runs/{run.id}/stop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run"]["status"] == "cancelled"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "prompt_matrix_run_cancelled",
                    AdminAuditLog.resource_id == run.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_stop_run_already_finalized_no_op(client, admin_operator, db_session: AsyncSession):
    run = PromptGenerationRun(
        id=_new_id(),
        admin_id=admin_operator.id,
        status="completed",
        request_config={},
        started_at=_now() - timedelta(seconds=10),
        completed_at=_now(),
    )
    db_session.add(run)
    await db_session.commit()

    resp = await client.post(f"/api/admin/prompt-matrix/runs/{run.id}/stop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["already_finalized"] is True


@pytest.mark.asyncio
async def test_stop_run_unknown_404(client, admin_operator):
    resp = await client.post("/api/admin/prompt-matrix/runs/no-such-id/stop")
    assert resp.status_code == 404


# ── audit gate ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_phase_4_routes():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
