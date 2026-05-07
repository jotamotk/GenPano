"""Phase 7 slice 7a-bis — admin/brand-management generate / enrich / import.

Tests mock the LLM service (and brand_db helpers where needed) so the
test suite doesn't require Doubao credentials or a Postgres ``brands``
schema. Pure-python validators in lib.py are tested directly.
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

from app.admin.brand_management.enrich_jobs import (
    execute_brand_enrich_job,
    get_brand_enrich_job,
    set_brand_enrich_job,
)
from app.admin.brand_management.lib import (
    BrandManagementError,
    brand_enrich_context,
    brand_enrich_context_from_payload,
    brand_schema_hint,
    extract_llm_items,
    validate_brand_candidates,
)
from app.admin.brand_management.llm import (
    BrandGenerationResult,
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


def _bm_router_module():
    import app.api.admin.brand_management.router  # noqa: F401

    return sys.modules["app.api.admin.brand_management.router"]


def _valid_brand_draft(idx: int = 1) -> dict:
    return {
        "name": f"Brand {idx}",
        "name_zh": "牌子",
        "name_en": f"Brand {idx}",
        "industry": "Beauty",
        "target_market": "global",
        "description": "summary",
        "positioning": "premium",
        "headquarters": "Shanghai",
        "founded_year": 2010,
        "aliases": [],
        "official_domains": ["example.com"],
        "tags": [],
        "competitors": [],
        "status": "draft",
        "source": "llm",
    }


def _patch_llm(
    monkeypatch,
    *,
    generate_returns=None,
    generate_raises=None,
    enrich_returns=None,
    enrich_raises=None,
):
    """Replace BrandManagementService used by both router + worker."""
    import app.admin.brand_management.enrich_jobs as ej

    bm = _bm_router_module()

    class _StubService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def generate_brands(self, **_kwargs):
            if generate_raises is not None:
                raise generate_raises
            if generate_returns is not None:
                return generate_returns
            return BrandGenerationResult(
                items=[_valid_brand_draft(1)],
                model="stub-doubao",
                prompt="stub-prompt",
                usage={"total_tokens": 10},
                estimated_cost=None,
            )

        async def enrich_brand_by_name(self, **_kwargs):
            if enrich_raises is not None:
                raise enrich_raises
            if enrich_returns is not None:
                return enrich_returns
            return BrandGenerationResult(
                items=[_valid_brand_draft(1)],
                model="stub-doubao",
                prompt="stub-enrich-prompt",
                usage={"total_tokens": 5},
                estimated_cost=None,
            )

    monkeypatch.setattr(bm, "BrandManagementService", _StubService)
    monkeypatch.setattr(ej, "BrandManagementService", _StubService)


def _patch_db_writes(monkeypatch, *, seeds=None, import_result=None):
    bm = _bm_router_module()
    monkeypatch.setattr(
        bm.brand_db,
        "fetch_industry_seeds",
        AsyncMock(return_value=list(seeds or [])),
    )
    # Skip the actual log INSERT in the test (sqlite fixture lacks the table
    # but the route handler awaits this without raising).
    monkeypatch.setattr(
        bm.brand_db,
        "write_brand_generation_log",
        AsyncMock(return_value=None),
    )
    if import_result is not None:
        monkeypatch.setattr(
            bm.brand_db,
            "import_brands_bulk",
            AsyncMock(return_value=import_result),
        )


# ── lib.py: pure helpers ─────────────────────────────────────


def test_brand_schema_hint_shape():
    schema = brand_schema_hint()
    assert "brands" in schema
    assert isinstance(schema["brands"], list)
    assert "name" in schema["brands"][0]


def test_extract_llm_items_root_key():
    out = extract_llm_items({"brands": [{"name": "x"}]}, "brands")
    assert out == [{"name": "x"}]


def test_extract_llm_items_aliases():
    # Falls back to ``brand`` (singular)
    out = extract_llm_items({"brand": [{"name": "x"}]}, "brands")
    assert out == [{"name": "x"}]
    # Single name dict at root
    out2 = extract_llm_items({"name": "y"}, "brands")
    assert out2 == [{"name": "y"}]


def test_extract_llm_items_missing_raises():
    with pytest.raises(BrandManagementError) as exc:
        extract_llm_items({"foo": "bar"}, "brands")
    assert exc.value.code == "llm_schema_invalid"


def test_validate_brand_candidates_dedupes_and_caps():
    items = [
        {"name": "A"},
        {"name": "a"},  # dup case-fold
        {"name": "B"},
        {"name": "C"},
    ]
    out = validate_brand_candidates(items, max_count=10)
    names = [d["name"] for d in out]
    assert names == ["A", "B", "C"]
    assert all(d["source"] == "llm" for d in out)


def test_validate_brand_candidates_empty_raises():
    with pytest.raises(BrandManagementError) as exc:
        validate_brand_candidates([], 5)
    assert exc.value.code == "missing_llm_field"


def test_brand_enrich_context_filters_empties():
    out = brand_enrich_context({"name_zh": "x", "industry": "", "founded_year": 1990})
    assert out == {"name_zh": "x", "founded_year": 1990}


def test_brand_enrich_context_from_payload_merges_top_level_and_nested():
    payload = {
        "name_zh": "X",
        "context": {"name_en": "Y", "industry": "Beauty"},
    }
    out = brand_enrich_context_from_payload(payload)
    assert out == {"name_zh": "X", "name_en": "Y", "industry": "Beauty"}


# ── auth ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_unauth_401(client):
    resp = await client.post("/api/admin/brand-management/generate", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_enrich_unauth_401(client):
    resp = await client.post("/api/admin/brand-management/enrich", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_enrich_job_unauth_401(client):
    resp = await client.get("/api/admin/brand-management/enrich/no-such-job")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_import_unauth_401(client):
    resp = await client.post("/api/admin/brand-management/import", json={"drafts": [{"name": "x"}]})
    assert resp.status_code == 401


# ── POST /generate ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_missing_industry_422(client, admin_operator, monkeypatch):
    _patch_llm(monkeypatch)
    _patch_db_writes(monkeypatch)
    resp = await client.post("/api/admin/brand-management/generate", json={})
    assert resp.status_code == 422
    assert "industry_required" in str(resp.json())


@pytest.mark.asyncio
async def test_generate_returns_drafts_and_audit(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_llm(monkeypatch)
    _patch_db_writes(monkeypatch)
    resp = await client.post(
        "/api/admin/brand-management/generate",
        json={"industry": "Beauty", "count": 5},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["drafts"]) == 1
    assert body["industry"] == "Beauty"
    assert body["model"] == "stub-doubao"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "generate_brands")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_generate_llm_error_503(client, admin_operator, monkeypatch):
    _patch_llm(
        monkeypatch,
        generate_raises=BrandManagementError("llm_call_failed", "Doubao timed out"),
    )
    _patch_db_writes(monkeypatch)
    resp = await client.post(
        "/api/admin/brand-management/generate",
        json={"industry": "Beauty"},
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "llm_call_failed"


# ── POST /enrich (sync) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_enrich_missing_name_422(client, admin_operator, monkeypatch):
    _patch_llm(monkeypatch)
    _patch_db_writes(monkeypatch)
    resp = await client.post("/api/admin/brand-management/enrich", json={})
    assert resp.status_code == 422
    assert "name_required" in str(resp.json())


@pytest.mark.asyncio
async def test_enrich_sync_returns_draft(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_llm(monkeypatch)
    _patch_db_writes(monkeypatch)
    resp = await client.post("/api/admin/brand-management/enrich", json={"name": "Apple"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["draft"]["name"] == "Brand 1"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "enrich_brand")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_enrich_sync_ambiguous_409(client, admin_operator, monkeypatch):
    """Multiple drafts → 409 with ``choices``."""
    multi = BrandGenerationResult(
        items=[_valid_brand_draft(1), _valid_brand_draft(2)],
        model="stub-doubao",
        prompt="stub",
        usage={},
        estimated_cost=None,
    )
    _patch_llm(monkeypatch, enrich_returns=multi)
    _patch_db_writes(monkeypatch)
    resp = await client.post("/api/admin/brand-management/enrich", json={"name": "Apple"})
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"] == "ambiguous_brand"
    assert len(body["choices"]) == 2


@pytest.mark.asyncio
async def test_enrich_sync_llm_error_503(client, admin_operator, monkeypatch):
    _patch_llm(
        monkeypatch,
        enrich_raises=BrandManagementError("llm_call_failed", "boom"),
    )
    _patch_db_writes(monkeypatch)
    resp = await client.post("/api/admin/brand-management/enrich", json={"name": "x"})
    assert resp.status_code == 503
    assert resp.json()["error"] == "llm_call_failed"


# ── POST /enrich (async) + GET /enrich/{job_id} ─────────────


@pytest.mark.asyncio
async def test_enrich_async_returns_202_with_job_id(client, admin_operator, monkeypatch):
    _patch_llm(monkeypatch)
    _patch_db_writes(monkeypatch)
    resp = await client.post(
        "/api/admin/brand-management/enrich",
        json={"name": "Apple", "async_generation": True},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["pending"] is True
    assert body["status"] == "queued"
    snap = await get_brand_enrich_job(body["job_id"])
    assert snap is not None


@pytest.mark.asyncio
async def test_async_worker_completes_job(
    db_session: AsyncSession, admin_operator, monkeypatch, env
):
    _patch_llm(monkeypatch)
    job_id = "00000000-test-bm-0000-completebrand"
    await set_brand_enrich_job(job_id, status="queued", message="queued")
    await execute_brand_enrich_job(
        env.sessionmaker,
        job_id=job_id,
        operator_id=admin_operator.id,
        name="Apple",
        payload={},
    )
    snap = await get_brand_enrich_job(job_id)
    assert snap is not None
    assert snap["status"] == "completed"
    assert snap["pending"] is False
    assert snap["draft"]["name"] == "Brand 1"


@pytest.mark.asyncio
async def test_async_worker_marks_failed_on_llm_error(
    db_session: AsyncSession, admin_operator, monkeypatch, env
):
    _patch_llm(
        monkeypatch,
        enrich_raises=BrandManagementError("llm_call_failed", "boom"),
    )
    job_id = "00000000-test-bm-0000-failedbrand00"
    await set_brand_enrich_job(job_id, status="queued", message="queued")
    await execute_brand_enrich_job(
        env.sessionmaker,
        job_id=job_id,
        operator_id=admin_operator.id,
        name="X",
        payload={},
    )
    snap = await get_brand_enrich_job(job_id)
    assert snap is not None
    assert snap["status"] == "failed"
    assert snap["error"] == "llm_call_failed"
    assert snap["http_status"] == 503


@pytest.mark.asyncio
async def test_get_enrich_job_unknown_404(client, admin_operator):
    resp = await client.get("/api/admin/brand-management/enrich/no-such-job")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_enrich_job_completed_returns_draft(client, admin_operator):
    job_id = "00000000-test-bm-0000-rendered00001"
    await set_brand_enrich_job(
        job_id,
        status="completed",
        message="ok",
        drafts=[_valid_brand_draft(1)],
        draft=_valid_brand_draft(1),
        model="stub",
        usage={"tokens": 5},
    )
    resp = await client.get(f"/api/admin/brand-management/enrich/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pending"] is False
    assert body["draft"]["name"] == "Brand 1"


@pytest.mark.asyncio
async def test_get_enrich_job_ambiguous_409(client, admin_operator):
    job_id = "00000000-test-bm-0000-ambiguous0001"
    await set_brand_enrich_job(
        job_id,
        status="completed",
        message="ok",
        drafts=[_valid_brand_draft(1), _valid_brand_draft(2)],
        draft=None,
        model="stub",
    )
    resp = await client.get(f"/api/admin/brand-management/enrich/{job_id}")
    assert resp.status_code == 409
    assert resp.json()["error"] == "ambiguous_brand"


# ── POST /import ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_missing_drafts_422(client, admin_operator, monkeypatch):
    _patch_llm(monkeypatch)
    _patch_db_writes(
        monkeypatch, import_result={"added": 0, "updated": 0, "skipped": 0, "results": []}
    )
    resp = await client.post("/api/admin/brand-management/import", json={})
    assert resp.status_code == 422
    assert "drafts_required" in str(resp.json())


@pytest.mark.asyncio
async def test_import_calls_db_and_audits(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    result = {
        "added": 2,
        "updated": 1,
        "skipped": 0,
        "results": [
            {"brand_id": 1, "name": "A", "outcome": "added"},
            {"brand_id": 2, "name": "B", "outcome": "added"},
            {"brand_id": 3, "name": "C", "outcome": "updated"},
        ],
    }
    _patch_llm(monkeypatch)
    _patch_db_writes(monkeypatch, import_result=result)
    resp = await client.post(
        "/api/admin/brand-management/import",
        json={
            "drafts": [{"name": "A"}, {"name": "B"}, {"name": "C"}],
            "default_industry": "Beauty",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] == 2
    assert body["updated"] == 1

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "import_brands")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_import_table_missing_500(client, admin_operator, monkeypatch):
    _patch_llm(monkeypatch)
    bm = _bm_router_module()

    async def _raise(*_args, **_kwargs):
        raise BrandManagementError("brands_table_missing", "no brands table")

    monkeypatch.setattr(bm.brand_db, "import_brands_bulk", _raise)
    resp = await client.post(
        "/api/admin/brand-management/import",
        json={"drafts": [{"name": "A"}]},
    )
    assert resp.status_code == 500
    assert resp.json()["error"] == "brands_table_missing"


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice7a_bis():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
