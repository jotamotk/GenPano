"""Phase 4 slice 2 — admin prompt_matrix read paths.

The 5 read routes (config / topics / gaps / prompts / candidates) hit
the legacy `brands` / `topics` / `prompts` upstream stub tables in
production. Sqlite has no shape for those, so this test mocks the
``app.admin.prompt_matrix.db`` helpers and exercises the route layer
(auth / query parsing / validation / response shape).

The candidates list uses the real PromptCandidate ORM (it's a backend
model), so the candidate-list test runs end-to-end against sqlite.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import AdminUser, PromptCandidate
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


def _patch(monkeypatch, **overrides):
    import app.admin.prompt_matrix.db as pm_db

    for name, value in overrides.items():
        monkeypatch.setattr(pm_db, name, value)


# ── /config ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_config_unauth_401(client):
    resp = await client.get("/api/admin/prompt-matrix/config")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_config_returns_brands_industries_stats(client, admin_operator, monkeypatch):
    _patch(
        monkeypatch,
        fetch_brand_rows=AsyncMock(
            return_value=[
                {"id": 1, "name": "NIKE", "industry_id": "footwear", "aliases": []},
                {"id": 2, "name": "Coke", "industry_id": "beverage", "aliases": []},
            ]
        ),
        compute_stats=AsyncMock(
            return_value={
                "topicsTotal": 10,
                "topicsWithPrompt": 5,
                "topicsNoPrompt": 5,
                "topicsPartialIntent": 0,
                "coveragePct": 50.0,
                "totalPrompts": 25,
                "intentDist": [],
                "langDist": [],
                "categoryPromptPurity": {"total": 0, "brandLeaks": 0, "status": "pass"},
                "lastRunAt": "Never",
            }
        ),
        candidate_status_counts=AsyncMock(
            return_value={"pending": 3, "approved": 1, "rejected": 0, "all": 4}
        ),
    )

    # mock the inline duplicate-count text() query — it runs through the
    # session, not pm_db, so we patch the session.execute path with a fake
    # mappings().one() return.
    from unittest.mock import MagicMock, patch

    fake_result = MagicMock()
    fake_mappings = MagicMock()
    fake_mappings.one.return_value = {"cnt": 0}
    fake_result.mappings.return_value = fake_mappings

    real_execute = AsyncSession.execute

    async def patched_execute(self, statement, params=None, **kwargs):
        sql = str(statement)
        if "duplicate_of IS NOT NULL" in sql:
            return fake_result
        return await real_execute(self, statement, params, **kwargs)

    with patch.object(AsyncSession, "execute", patched_execute):
        resp = await client.get("/api/admin/prompt-matrix/config")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert {it["id"] for it in body["industries"]} == {"footwear", "beverage"}
    assert len(body["brands"]) == 2
    assert body["summary"]["pending_candidates"] == 3
    assert body["summary"]["llm_configured"] is False
    assert body["stats"]["topicsTotal"] == 10
    assert len(body["qualityGates"]) == 4


# ── /topics ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_topics_returns_paged_rows(client, admin_operator, monkeypatch):
    _patch(
        monkeypatch,
        fetch_topics=AsyncMock(
            return_value=(
                [
                    {
                        "id": "T-1",
                        "raw_id": 1,
                        "title": "x",
                        "dimension_key": "brand",
                        "coverage": "covered",
                    }
                ],
                1,
                {"topicsTotal": 1, "matchingTopics": 1},
            )
        ),
    )
    resp = await client.get("/api/admin/prompt-matrix/topics?per_page=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["rows"][0]["id"] == "T-1"
    assert body["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_topics_invalid_dimension_422(client, admin_operator):
    resp = await client.get("/api/admin/prompt-matrix/topics?dimension=weather")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_topics_invalid_coverage_422(client, admin_operator):
    resp = await client.get("/api/admin/prompt-matrix/topics?coverage=zombie")
    assert resp.status_code == 422


# ── /gaps ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_gaps_returns_rows(client, admin_operator, monkeypatch):
    _patch(
        monkeypatch,
        gaps_for_topics=AsyncMock(
            return_value=[
                {
                    "id": "PG-1",
                    "topic_id": 1,
                    "topic": "Test",
                    "gap": "No Prompt",
                    "priority": "P1",
                    "estimate": 8,
                }
            ]
        ),
    )
    resp = await client.get("/api/admin/prompt-matrix/gaps")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["rows"]) == 1
    assert body["summary"]["estimated_prompts"] == 8


@pytest.mark.asyncio
async def test_gaps_invalid_topic_ids_422(client, admin_operator):
    resp = await client.get("/api/admin/prompt-matrix/gaps?topic_ids=not-an-int")
    assert resp.status_code == 422


# ── /prompts ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prompts_returns_paged(client, admin_operator, monkeypatch):
    _patch(
        monkeypatch,
        fetch_prompts=AsyncMock(
            return_value=(
                [{"id": "P-1", "raw_id": 1, "text": "x", "intent": "informational"}],
                1,
            )
        ),
        compute_stats=AsyncMock(return_value={"topicsTotal": 0, "totalPrompts": 1}),
    )
    resp = await client.get("/api/admin/prompt-matrix/prompts?per_page=20")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["rows"][0]["id"] == "P-1"
    assert body["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_prompts_invalid_intent_422(client, admin_operator):
    resp = await client.get("/api/admin/prompt-matrix/prompts?intent=spam")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_prompts_invalid_language_422(client, admin_operator):
    resp = await client.get("/api/admin/prompt-matrix/prompts?language=fr-FR")
    assert resp.status_code == 422


# ── /candidates (paged list — ORM-backed, end-to-end) ────────


@pytest.mark.asyncio
async def test_candidates_list_real_orm(client, admin_operator, db_session: AsyncSession):
    """Uses the real PromptCandidate ORM table — runs end-to-end against
    sqlite. Three candidates: 2 pending, 1 approved."""
    cands = [
        PromptCandidate(
            id=_new_id(),
            run_id=None,
            topic_id=i + 1,
            topic_text="t",
            brand_id=1,
            brand_name="NIKE",
            dimension="brand",
            intent="informational",
            language="zh-CN",
            text=f"prompt {i}",
            status="pending" if i < 2 else "approved",
            confidence=0.8,
            tags={},
        )
        for i in range(3)
    ]
    for c in cands:
        db_session.add(c)
    await db_session.commit()

    resp = await client.get("/api/admin/prompt-matrix/candidates?status=pending")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["pagination"]["total"] == 2
    assert body["summary"]["pending_candidates"] == 2
    assert body["summary"]["approved_candidates"] == 1
    assert body["summary"]["rejected_candidates"] == 0


@pytest.mark.asyncio
async def test_candidates_list_filter_status_all(client, admin_operator, db_session: AsyncSession):
    for i, st in enumerate(["pending", "approved", "rejected"]):
        db_session.add(
            PromptCandidate(
                id=_new_id(),
                run_id=None,
                topic_id=i + 1,
                topic_text="t",
                brand_id=1,
                brand_name="NIKE",
                dimension="brand",
                intent="informational",
                language="zh-CN",
                text=f"p{i}",
                status=st,
                confidence=0.8,
                tags={},
            )
        )
    await db_session.commit()

    resp = await client.get("/api/admin/prompt-matrix/candidates?status=all")
    assert resp.status_code == 200
    assert resp.json()["pagination"]["total"] == 3


@pytest.mark.asyncio
async def test_candidates_invalid_status_422(client, admin_operator):
    resp = await client.get("/api/admin/prompt-matrix/candidates?status=merged")
    assert resp.status_code == 422


# ── audit gate ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice2_routes():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
