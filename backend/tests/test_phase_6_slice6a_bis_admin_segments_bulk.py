"""Phase 6 slice 6a-bis — segments bulk import + LLM generate.

Tests:
- POST /import: end-to-end against sqlite (segments ORM model is real)
- POST /generate: mocks the SegmentProfileGenerationService so we
  exercise the route handler (brand resolution, error mapping, audit
  emission) without making a real LLM call.

Plus pure-Python validators in app/admin/segments/llm.py.
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
    SegmentProfileGenerationService,
    validate_profile_candidates,
    validate_segment_candidates,
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


def _valid_segment_draft(idx: int = 1) -> dict:
    return {
        "id": f"SEG-DRAFT-{idx:03d}",
        "name": f"Draft Segment {idx}",
        "industry": "Beauty",
        "status": "draft",
        "weight": 0.15,
        "age_range": "24-38",
        "income": "mid",
        "regions": "tier 1",
        "sampling_rate": "10%",
        "note": "ok",
    }


# ── validators (pure) ────────────────────────────────────────


def test_validate_segment_candidates_passes_clean():
    rows = validate_segment_candidates([_valid_segment_draft()], 5)
    assert len(rows) == 1
    assert rows[0]["id"] == "SEG-DRAFT-001"


def test_validate_segment_candidates_rejects_duplicate_names():
    a = _valid_segment_draft()
    b = dict(a)
    b["id"] = "SEG-DRAFT-002"
    with pytest.raises(SegmentProfileGenerationError) as exc:
        validate_segment_candidates([a, b], 5)
    assert exc.value.code == "duplicate_segment_name"


def test_validate_segment_candidates_rejects_invalid_status():
    bad = dict(_valid_segment_draft())
    bad["status"] = "weird"
    with pytest.raises(SegmentProfileGenerationError) as exc:
        validate_segment_candidates([bad], 5)
    assert exc.value.code == "invalid_segment_status"


def test_validate_segment_candidates_clamps_to_max_count():
    drafts = [_valid_segment_draft(i) for i in range(1, 11)]
    rows = validate_segment_candidates(drafts, 3)
    assert len(rows) == 3


def test_validate_segment_candidates_accepts_common_llm_aliases_and_defaults():
    rows = validate_segment_candidates(
        [
            {
                "name": "Ingredient proof seekers",
                "description": "Researches ingredients, efficacy proof, and expert reviews.",
                "audience_share": "18%",
                "ageGroup": "25-34",
                "incomeLevel": "mid-high",
                "region": "tier 1 cities",
                "sampleRatio": "18%",
            }
        ],
        3,
    )

    assert rows[0]["id"] == "SEG-DRAFT-001"
    assert rows[0]["status"] == "draft"
    assert rows[0]["weight"] == 0.18
    assert rows[0]["age_range"] == "25-34"
    assert rows[0]["income"] == "mid-high"
    assert rows[0]["regions"] == "tier 1 cities"
    assert rows[0]["sampling_rate"] == "18%"
    assert rows[0]["note"] == "Researches ingredients, efficacy proof, and expert reviews."


@pytest.mark.asyncio
async def test_segment_generation_prompt_anchors_brand_industry(monkeypatch):
    """Segment prompts should force the model to follow the selected brand context."""

    captured: dict[str, str] = {}

    async def fake_call_llm_json(self, prompt: str, root_key: str, max_count: int):
        captured["prompt"] = prompt
        return [_valid_segment_draft()], "gpt-test", {"prompt_tokens": 1}

    monkeypatch.setattr(
        SegmentProfileGenerationService,
        "_call_llm_json",
        fake_call_llm_json,
    )

    service = SegmentProfileGenerationService(config={"default_model": "gpt-test"})
    await service.generate_segments(
        brand_name="bestCoffer",
        industry="数据安全",
        count=1,
        status="active",
        positioning="面向企业的数据安全与合规产品线",
        goal="覆盖数据保护、合规审计和竞品替换场景",
        constraints="禁止生成与数据安全无关的人群",
    )

    prompt = captured["prompt"]
    assert "bestCoffer" in prompt
    assert "数据安全" in prompt
    assert "必须围绕" in prompt
    assert "不要套用" in prompt
    assert "默认使用中文" in prompt


@pytest.mark.asyncio
async def test_segment_generation_prompt_includes_product_context(monkeypatch):
    """Brand-level Segment generation should vary by the chosen product."""

    captured: dict[str, str] = {}

    async def fake_call_llm_json(self, prompt: str, root_key: str, max_count: int):
        captured["prompt"] = prompt
        return [_valid_segment_draft()], "gpt-test", {"prompt_tokens": 1}

    monkeypatch.setattr(
        SegmentProfileGenerationService,
        "_call_llm_json",
        fake_call_llm_json,
    )

    service = SegmentProfileGenerationService(config={"default_model": "gpt-test"})
    await service.generate_segments(
        brand_name="bestCoffer",
        industry="数据安全",
        count=1,
        status="active",
        positioning="面向企业的数据安全与合规产品线",
        product_id="42",
        product_name="bestCoffer DLP",
        product_category="数据防泄漏",
        product_description="识别敏感数据流转并阻断外发风险",
    )

    prompt = captured["prompt"]
    assert "bestCoffer DLP" in prompt
    assert "数据防泄漏" in prompt
    assert "识别敏感数据流转" in prompt
    assert "不同产品" in prompt


@pytest.mark.asyncio
async def test_generate_route_passes_product_context_to_service(
    client, admin_operator, monkeypatch
):
    captured: dict[str, object] = {}

    async def _capture(**kwargs):
        captured.update(kwargs)
        return GenerationResult(
            items=[_valid_segment_draft(1)],
            model="stub-doubao",
            prompt="stub-prompt",
            usage={"total_tokens": 5},
            estimated_cost=None,
        )

    _patch_llm_service(monkeypatch, generate=_capture)
    resp = await client.post(
        "/api/admin/segments/generate",
        json={
            "brand_name": "TestBrand",
            "industry": "数据安全",
            "product_id": "42",
            "product_name": "DLP",
            "product_category": "数据防泄漏",
            "product_description": "阻断敏感数据外发",
        },
    )

    assert resp.status_code == 200
    assert captured["product_id"] == "42"
    assert captured["product_name"] == "DLP"
    assert captured["product_category"] == "数据防泄漏"
    assert captured["product_description"] == "阻断敏感数据外发"


def test_validate_profile_candidates_skips_silent_invalid():
    """admin_console silently skips profile drafts missing demographic /
    need / name (rather than raising) — preserve that contract."""
    drafts = [
        {"id": "P-1", "name": "ok", "demographic": "30F", "need": "trust"},
        {"id": "P-2", "name": "missing_demo", "need": "x"},  # silently dropped
        {"id": "P-3"},  # silently dropped
    ]
    rows = validate_profile_candidates(drafts, 10)
    assert len(rows) == 1
    assert rows[0]["id"] == "P-1"


def test_validate_profile_candidates_empty_raises():
    with pytest.raises(SegmentProfileGenerationError) as exc:
        validate_profile_candidates([], 10)
    assert exc.value.code == "missing_llm_field"


# ── POST /import ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_import_unauth_401(client):
    resp = await client.post("/api/admin/segments/import", json={"rows": []})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_import_invalid_rows_422(client, admin_operator):
    resp = await client.post("/api/admin/segments/import", json={"rows": "nope"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_import_added_updated_skipped(client, admin_operator, db_session: AsyncSession):
    # Pre-existing segment to test the "updated" path.
    db_session.add(
        Segment(
            id="SEG-EXIST",
            code="SEG-EXIST",
            name="Old name",
            industry="Beauty",
            status="active",
            weight=0.1,
            is_deleted=False,
            created_at=_now(),
            updated_at=_now(),
        )
    )
    await db_session.commit()

    resp = await client.post(
        "/api/admin/segments/import",
        json={
            "rows": [
                {"id": "SEG-NEW", "name": "Brand new", "status": "active"},
                {"id": "SEG-EXIST", "name": "Renamed", "status": "active"},
                {"name": "missing weight is fine but"},  # will succeed (default weight 0)
                {"id": "SEG-BAD", "status": "weird"},  # invalid status -> skipped
            ]
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["added"] >= 2  # SEG-NEW + the missing-id one (auto-generated)
    assert body["updated"] == 1
    # at least 1 skipped (SEG-BAD)
    assert body["skipped"] >= 1

    # Audit row written:
    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "import_segments")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_import_via_legacy_alias(client, admin_operator):
    resp = await client.post(
        "/api/segments/import",
        json={"rows": [{"id": "SEG-LEG-IMP", "name": "x", "status": "active"}]},
    )
    assert resp.status_code == 200
    assert resp.json()["added"] == 1


# ── POST /generate ───────────────────────────────────────────


def _patch_llm_service(monkeypatch, *, generate=None):
    """Replace the LLM service class so handler tests don't need a real
    Doubao key. ``generate`` is the awaitable that ``generate_segments``
    is replaced by; default is a happy-path stub returning 1 draft."""
    qp = _segments_router_module()

    class _StubService:
        def __init__(self, *_args, **_kwargs):
            pass

        async def generate_segments(self, **_kwargs):
            if generate is not None:
                return await generate(**_kwargs)
            return GenerationResult(
                items=[_valid_segment_draft(1)],
                model="stub-doubao",
                prompt="stub-prompt",
                usage={"total_tokens": 5},
                estimated_cost=None,
            )

    monkeypatch.setattr(qp, "SegmentProfileGenerationService", _StubService)


@pytest.mark.asyncio
async def test_generate_unauth_401(client):
    resp = await client.post("/api/admin/segments/generate", json={})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_generate_missing_brand_name_422(client, admin_operator, monkeypatch):
    _patch_llm_service(monkeypatch)
    resp = await client.post("/api/admin/segments/generate", json={})
    assert resp.status_code == 422
    assert "brand_name_required" in str(resp.json())


@pytest.mark.asyncio
async def test_generate_happy_returns_drafts_and_audit(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    _patch_llm_service(monkeypatch)
    resp = await client.post(
        "/api/admin/segments/generate",
        json={"brand_name": "TestBrand", "industry": "Beauty", "count": 3},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["drafts"]) == 1
    assert body["drafts"][0]["brand_name"] == "TestBrand"
    assert body["model"] == "stub-doubao"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "generate_segments")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_generate_llm_call_failed_returns_503_and_audit(
    client, admin_operator, monkeypatch, db_session: AsyncSession
):
    async def _raise(**_kwargs):
        raise SegmentProfileGenerationError("llm_call_failed", "Doubao timed out")

    _patch_llm_service(monkeypatch, generate=_raise)
    resp = await client.post(
        "/api/admin/segments/generate",
        json={"brand_name": "TestBrand"},
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "llm_call_failed"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "generate_segments_failed")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_generate_schema_invalid_returns_502(client, admin_operator, monkeypatch):
    async def _raise(**_kwargs):
        raise SegmentProfileGenerationError("llm_schema_invalid", "wrong shape")

    _patch_llm_service(monkeypatch, generate=_raise)
    resp = await client.post(
        "/api/admin/segments/generate",
        json={"brand_name": "TestBrand"},
    )
    assert resp.status_code == 502
    assert resp.json()["error"] == "llm_schema_invalid"


@pytest.mark.asyncio
async def test_generate_via_legacy_alias(client, admin_operator, monkeypatch):
    _patch_llm_service(monkeypatch)
    resp = await client.post(
        "/api/segments/generate",
        json={"brand_name": "TestBrand", "count": 2},
    )
    assert resp.status_code == 200


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice6a_bis():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
