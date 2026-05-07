"""Phase 5 slice 3b-i — POST /api/admin/query-pool/preflight.

Mocks the three DB-touching helpers
(``fetch_prompt_ids_from_selection`` / ``fetch_query_pool_prompt_rows`` /
``fetch_query_pool_profile_pool``) so the test doesn't need a real
postgres ``prompts`` / ``segments`` / ``profiles`` schema.

Coverage:
- 401 unauth
- 422 on invalid config enum (desired_engine_policy)
- 422 on prompt_selection_required (no prompts resolve from filter)
- 422 on profile_pool_empty
- 422 on candidate_cap_exceeded (overflow=hold)
- 200 happy path returns ``{success, run: {status='preview', ...,
  preflight_summary}}``; no DB writes
- legacy alias /admin/api/v1/pipeline/query-pool/preflight reaches same handler
- audit gate: preflight is exempt; verify path is in EXEMPT_PATHS
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from genpano_models import AdminUser
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


def _qp_router_module():
    """Resolve the router *module* (not the APIRouter exported by __init__)."""
    import app.api.admin.query_pool.router  # noqa: F401

    return sys.modules["app.api.admin.query_pool.router"]


def _patch_db(monkeypatch, *, prompt_ids=None, prompt_rows=None, profile_pool=None):
    """Helper: monkeypatch the qp_db helpers on the router module."""
    from unittest.mock import AsyncMock

    qp = _qp_router_module()
    monkeypatch.setattr(
        qp.qp_db,
        "fetch_prompt_ids_from_selection",
        AsyncMock(return_value=list(prompt_ids or [])),
    )
    monkeypatch.setattr(
        qp.qp_db, "fetch_query_pool_prompt_rows", AsyncMock(return_value=list(prompt_rows or []))
    )
    monkeypatch.setattr(
        qp.qp_db,
        "fetch_query_pool_profile_pool",
        AsyncMock(return_value=list(profile_pool or [])),
    )


# ── auth + validation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preflight_unauth_401(client):
    resp = await client.post("/api/admin/query-pool/preflight", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_preflight_invalid_engine_policy_422(client, admin_operator):
    resp = await client.post(
        "/api/admin/query-pool/preflight",
        json={"desired_engine_policy": "bogus"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_preflight_no_prompts_returns_422(client, admin_operator, monkeypatch):
    _patch_db(monkeypatch, prompt_ids=[])
    resp = await client.post("/api/admin/query-pool/preflight", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert "prompt_selection_required" in str(body)


@pytest.mark.asyncio
async def test_preflight_empty_profile_pool_returns_422(client, admin_operator, monkeypatch):
    _patch_db(
        monkeypatch,
        prompt_ids=["1"],
        prompt_rows=[{"id": "1", "text": "hi", "topic_id": None, "topic_text": None}],
        profile_pool=[],
    )
    resp = await client.post("/api/admin/query-pool/preflight", json={})
    assert resp.status_code == 422
    assert "query_pool_profile_pool_empty" in str(resp.json())


@pytest.mark.asyncio
async def test_preflight_overflow_hold_raises_422(client, admin_operator, monkeypatch):
    _patch_db(
        monkeypatch,
        prompt_ids=[str(i) for i in range(5)],
        prompt_rows=[
            {"id": str(i), "text": f"p{i}", "topic_id": None, "topic_text": None} for i in range(5)
        ],
        profile_pool=[
            {
                "segment_id": "s1",
                "segment_name": "seg-one",
                "segment_weight": 5,
                "profile_id": "p1",
                "profile_name": "name",
                "profile_demographic": "demo",
                "profile_need": "need",
                "profile_weight": 5,
            }
        ],
    )
    resp = await client.post(
        "/api/admin/query-pool/preflight",
        json={
            "profiles_per_prompt": 5,
            "max_candidates": 3,
            "overflow_policy": "hold",
        },
    )
    assert resp.status_code == 422
    assert "query_pool_candidate_cap_exceeded" in str(resp.json())


# ── happy path ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preflight_happy_returns_preview_run(client, admin_operator, monkeypatch):
    _patch_db(
        monkeypatch,
        prompt_ids=["1", "2"],
        prompt_rows=[
            {"id": "1", "text": "Q1?", "topic_id": "t1", "topic_text": "topic-1"},
            {"id": "2", "text": "Q2?", "topic_id": "t1", "topic_text": "topic-1"},
        ],
        profile_pool=[
            {
                "segment_id": "s1",
                "segment_name": "seg-one",
                "segment_weight": 5,
                "profile_id": "p1",
                "profile_name": "alpha",
                "profile_demographic": "30F",
                "profile_need": "trust",
                "profile_weight": 5,
            },
            {
                "segment_id": "s2",
                "segment_name": "seg-two",
                "segment_weight": 4,
                "profile_id": "p2",
                "profile_name": "beta",
                "profile_demographic": "25M",
                "profile_need": "speed",
                "profile_weight": 4,
            },
        ],
    )
    resp = await client.post(
        "/api/admin/query-pool/preflight",
        json={"profiles_per_prompt": 2},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    run = body["run"]
    assert run["id"] is None
    assert run["status"] == "preview"
    assert run["candidates_estimated"] == 4  # 2 prompts x 2 profiles_per_prompt
    assert run["candidates_assembled"] == 0
    summary = run["preflight_summary"]
    assert summary["scheduler_intake"] == "ready"
    assert summary["raw_candidates_estimated"] == 4
    assert summary["accepted"] == 4
    assert summary["generation_method"] == "llm_estimate"


@pytest.mark.asyncio
async def test_preflight_via_legacy_alias(client, admin_operator, monkeypatch):
    _patch_db(
        monkeypatch,
        prompt_ids=["1"],
        prompt_rows=[{"id": "1", "text": "hi", "topic_id": None, "topic_text": None}],
        profile_pool=[
            {
                "segment_id": "s1",
                "segment_name": "n",
                "segment_weight": 1,
                "profile_id": "p1",
                "profile_name": "n",
                "profile_demographic": "d",
                "profile_need": "x",
                "profile_weight": 1,
            }
        ],
    )
    resp = await client.post(
        "/admin/api/v1/pipeline/query-pool/preflight", json={"profiles_per_prompt": 1}
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ── audit gate ───────────────────────────────────────────────────


def test_preflight_path_is_audit_exempt():
    """Preflight is registered in EXEMPT_PATHS — read-only dry-run."""
    from tests.test_audit_emit_coverage import EXEMPT_PATHS

    assert "/api/admin/query-pool/preflight" in EXEMPT_PATHS


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice3b_i():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
