"""Phase 6 slice 6b-bis — admin/segments/{seg}/profiles/generate (LLM async).

Coverage:
- POST /generate sync path: 401 / 422 missing brand / 200 with drafts +
  audit row / 502 / 503 LLM error mapping / 404 segment_not_found
- POST /generate async path: 202 with job_id; subsequent
  ``await execute_profile_generation_job`` finalises the job
- GET /generate/{job_id}: 404 unknown / mismatched segment, 200
  pending / completed / failed snapshot
- legacy alias /api/segments/.../generate works

The LLM service is mocked so tests don't require Doubao credentials.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from genpano_models import AdminAuditLog, AdminUser, Segment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.segments.llm import (
    GenerationResult,
    SegmentProfileGenerationError,
)
from app.admin.segments.profile_generation import (
    execute_profile_generation_job,
    get_profile_generation_job,
    set_profile_generation_job,
)

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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


def _segments_router_module():
    import app.api.admin.segments.router  # noqa: F401

    return sys.modules["app.api.admin.segments.router"]


def _segment(seg_id: str = "SEG-A") -> Segment:
    return Segment(
        id=seg_id,
        code=seg_id,
        brand_id="brand-1",
        brand_name="Brand One",
        name="Young Pros",
        industry="Beauty",
        status="active",
        weight=1.0,
        is_deleted=False,
        created_at=_now(),
        updated_at=_now(),
    )


def _valid_profile_draft() -> dict:
    return {
        "id": "P-DRAFT-1",
        "name": "Anna",
        "demographic": "30F",
        "need": "trust",
        "weight": 1.0,
        "status": "draft",
        "persona_json": {"summary": "x"},
    }


def _patch_llm_service(monkeypatch, *, generate=None):
    """Replace SegmentProfileGenerationService used by both the sync
    route handler and the async job worker."""
    import app.admin.segments.profile_generation as pg

    qp = _segments_router_module()

    class _StubService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def generate_profiles(self, **_kwargs):
            if generate is not None:
                return await generate(**_kwargs)
            return GenerationResult(
                items=[_valid_profile_draft()],
                model="stub-doubao",
                prompt="stub-prompt",
                usage={"total_tokens": 5},
                estimated_cost=None,
            )

    monkeypatch.setattr(qp, "SegmentProfileGenerationService", _StubService)
    monkeypatch.setattr(pg, "SegmentProfileGenerationService", _StubService)


# ── auth + validation ────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_unauth_401(client):
    resp = await client.post("/api/admin/segments/SEG-X/profiles/generate", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_generate_missing_brand_name_422(client, admin_operator, monkeypatch):
    _patch_llm_service(monkeypatch)
    resp = await client.post("/api/admin/segments/SEG-A/profiles/generate", json={})
    assert resp.status_code == 422
    assert "brand_name_required" in str(resp.json())


@pytest.mark.asyncio
async def test_generate_segment_missing_404(client, admin_operator, monkeypatch):
    _patch_llm_service(monkeypatch)
    resp = await client.post(
        "/api/admin/segments/SEG-NONE/profiles/generate",
        json={"brand_name": "TestBrand"},
    )
    assert resp.status_code == 404


# ── sync path ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_sync_returns_drafts_and_audit(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    db_session.add(_segment("SEG-A"))
    await db_session.commit()
    _patch_llm_service(monkeypatch)
    resp = await client.post(
        "/api/admin/segments/SEG-A/profiles/generate",
        json={"brand_name": "TestBrand", "count": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["drafts"]) == 1
    assert body["drafts"][0]["segment_id"] == "SEG-A"
    assert body["drafts"][0]["brand_name"] == "Brand One"  # from segment
    assert body["model"] == "stub-doubao"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "generate_profiles")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_generate_sync_llm_call_failed_503(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    db_session.add(_segment("SEG-B"))
    await db_session.commit()

    async def _raise(**_kwargs):
        raise SegmentProfileGenerationError("llm_call_failed", "Doubao timed out")

    _patch_llm_service(monkeypatch, generate=_raise)
    resp = await client.post(
        "/api/admin/segments/SEG-B/profiles/generate",
        json={"brand_name": "TestBrand"},
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "llm_call_failed"


@pytest.mark.asyncio
async def test_generate_sync_schema_invalid_502(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    db_session.add(_segment("SEG-C"))
    await db_session.commit()

    async def _raise(**_kwargs):
        raise SegmentProfileGenerationError("llm_schema_invalid", "wrong shape")

    _patch_llm_service(monkeypatch, generate=_raise)
    resp = await client.post(
        "/api/admin/segments/SEG-C/profiles/generate",
        json={"brand_name": "TestBrand"},
    )
    assert resp.status_code == 502
    assert resp.json()["error"] == "llm_schema_invalid"


# ── async path ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_generate_async_returns_202_with_job_id(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    db_session.add(_segment("SEG-AS"))
    await db_session.commit()
    _patch_llm_service(monkeypatch)

    resp = await client.post(
        "/api/admin/segments/SEG-AS/profiles/generate",
        json={"brand_name": "TestBrand", "async_generation": True},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["pending"] is True
    assert body["status"] == "queued"
    job_id = body["job_id"]

    # Verify job snapshot exists
    snap = await get_profile_generation_job(job_id)
    assert snap is not None
    assert snap["segment_id"] == "SEG-AS"


@pytest.mark.asyncio
async def test_async_worker_completes_job_with_drafts(
    db_session: AsyncSession, admin_operator, monkeypatch, env
):
    """End-to-end: schedule a job + drive the worker via direct
    execute_profile_generation_job call (bypass the async scheduler so
    the test is deterministic)."""
    db_session.add(_segment("SEG-W"))
    await db_session.commit()
    _patch_llm_service(monkeypatch)

    job_id = "00000000-test-1234-0000-aaaaaaaaaaaa"
    await set_profile_generation_job(
        job_id,
        status="queued",
        segment_id="SEG-W",
        message="queued",
    )

    await execute_profile_generation_job(
        env.sessionmaker,
        job_id=job_id,
        operator_id=admin_operator.id,
        segment_id="SEG-W",
        payload={"brand_name": "Brand One"},
    )

    snap = await get_profile_generation_job(job_id)
    assert snap is not None
    assert snap["status"] == "completed"
    assert snap["pending"] is False
    assert len(snap["drafts"]) == 1
    assert snap["drafts"][0]["segment_id"] == "SEG-W"


@pytest.mark.asyncio
async def test_async_worker_marks_failed_on_llm_error(
    db_session: AsyncSession, admin_operator, monkeypatch, env
):
    db_session.add(_segment("SEG-WF"))
    await db_session.commit()

    async def _raise(**_kwargs):
        raise SegmentProfileGenerationError("llm_call_failed", "boom")

    _patch_llm_service(monkeypatch, generate=_raise)

    job_id = "00000000-test-1234-0000-fffffffffff1"
    await set_profile_generation_job(job_id, status="queued", segment_id="SEG-WF", message="queued")
    await execute_profile_generation_job(
        env.sessionmaker,
        job_id=job_id,
        operator_id=admin_operator.id,
        segment_id="SEG-WF",
        payload={"brand_name": "Brand One"},
    )
    snap = await get_profile_generation_job(job_id)
    assert snap is not None
    assert snap["status"] == "failed"
    assert snap["error"] == "llm_call_failed"
    assert snap["http_status"] == 503


# ── GET /{job_id} ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_job_unknown_returns_404(client, admin_operator):
    resp = await client.get("/api/admin/segments/SEG-X/profiles/generate/no-such-job")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_job_segment_mismatch_returns_404(
    client, admin_operator, db_session: AsyncSession
):
    db_session.add(_segment("SEG-OW"))
    await db_session.commit()
    job_id = "00000000-test-9999-0000-mismatchseg00"
    await set_profile_generation_job(job_id, status="queued", segment_id="SEG-OW", message="x")
    # request comes in with a different segment_id
    resp = await client.get(f"/api/admin/segments/SEG-OTHER/profiles/generate/{job_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_job_completed_returns_drafts(client, admin_operator):
    job_id = "00000000-test-9999-0000-completed00"
    await set_profile_generation_job(
        job_id,
        status="completed",
        segment_id="SEG-DONE",
        message="ok",
        drafts=[{"id": "P-DONE-1", "segment_id": "SEG-DONE"}],
        model="stub",
        usage={"tokens": 9},
    )
    resp = await client.get(f"/api/admin/segments/SEG-DONE/profiles/generate/{job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["pending"] is False
    assert body["status"] == "completed"
    assert body["drafts"][0]["id"] == "P-DONE-1"


@pytest.mark.asyncio
async def test_get_job_failed_returns_http_status(client, admin_operator):
    job_id = "00000000-test-9999-0000-failedstatus"
    await set_profile_generation_job(
        job_id,
        status="failed",
        segment_id="SEG-F",
        error="llm_call_failed",
        message="boom",
        http_status=503,
    )
    resp = await client.get(f"/api/admin/segments/SEG-F/profiles/generate/{job_id}")
    assert resp.status_code == 503
    assert resp.json()["error"] == "llm_call_failed"


# ── legacy alias ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_legacy_alias_generate_sync(
    client, admin_operator, db_session: AsyncSession, monkeypatch
):
    db_session.add(_segment("SEG-LEG"))
    await db_session.commit()
    _patch_llm_service(monkeypatch)
    resp = await client.post(
        "/api/segments/SEG-LEG/profiles/generate",
        json={"brand_name": "TestBrand"},
    )
    assert resp.status_code == 200


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice6b_bis():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
