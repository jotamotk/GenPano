"""Phase 4 LLM extraction candidates.

Coverage:
- extract brand context payloads into entity / attribute / claim candidates
- backfill from brand_context_snapshots
- review entity / attribute / claim candidates through Admin API
- approved attributes / claims are exposed to the brand context assembler
- Admin HTML exposes the LLM Extraction review surface
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from genpano_models import (
    AdminAuditLog,
    AdminUser,
    BrandContextSnapshot,
    KGEntityAttribute,
    KGEntityClaim,
    LLMAttributeCandidate,
    LLMClaimCandidate,
    LLMEntityCandidate,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def admin_operator(db_session: AsyncSession) -> AsyncGenerator[AdminUser, None]:
    from app.api.admin.auth.router import current_admin
    from app.main import app

    admin = AdminUser(
        id=_new_id(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="$2b$04$dummyhashfortestsdummyhashfortestsdummyhashfortest",
        role="super_admin",
        status="active",
    )
    db_session.add(admin)
    await db_session.commit()

    async def _override_current_admin() -> AdminUser:
        return admin

    app.dependency_overrides[current_admin] = _override_current_admin
    try:
        yield admin
    finally:
        app.dependency_overrides.pop(current_admin, None)


def _context_payload() -> dict[str, object]:
    return {
        "brand": {
            "name": "AcmeVault",
            "industry": "Virtual data room",
            "positioning": "secure deal collaboration",
            "official_domains": ["acmevault.example"],
        },
        "products": [
            {
                "name": "AcmeVault Rooms",
                "category": "VDR",
                "key_features": ["bulk permission review"],
                "use_cases": ["M&A diligence"],
                "target_users": ["legal teams"],
                "price_positioning": "enterprise",
            }
        ],
        "scenarios": [
            {
                "name": "M&A due diligence",
                "pain_points": ["large file permission review"],
                "decision_criteria": ["audit trail"],
                "buying_stage": "shortlist",
            }
        ],
        "competitors": [
            {
                "name": "DealRoom",
                "competitor_type": "direct",
                "overlap_category": "VDR",
                "comparison_axes": ["workflow speed"],
                "relation_reason": "Both support deal-room collaboration.",
            }
        ],
        "audience_hypotheses": [
            {
                "segment_name": "legal operations",
                "needs": ["secure redaction workflow"],
                "regions": ["US"],
                "buying_stage": "evaluation",
            }
        ],
        "claims": {
            "pros": ["easy permission management"],
            "cons": ["enterprise pricing"],
            "best_for": ["mid-market legal teams"],
        },
        "source_notes": [
            {
                "title": "Official product page",
                "url": "https://acmevault.example/product",
                "snippet": "AcmeVault Rooms is a virtual data room.",
            }
        ],
    }


def test_extract_candidates_from_brand_context_payload() -> None:
    from app.admin.llm_extraction.lib import extract_candidates_from_context_payload

    extracted = extract_candidates_from_context_payload(
        brand_id=7,
        brand_context_version="bcx-7-test",
        payload=_context_payload(),
    )

    entity_types = {item["entity_type"] for item in extracted["entities"]}
    assert {"brand", "product", "competitor", "scenario", "segment"}.issubset(entity_types)
    assert any(item["name"] == "DealRoom" for item in extracted["entities"])
    assert any(
        item["entity_kind"] == "product" and item["attribute_key"] == "key_features"
        for item in extracted["attributes"]
    )
    assert {item["claim_type"] for item in extracted["claims"]} >= {
        "pros",
        "cons",
        "best_for",
    }
    all_keys = [
        *(item["candidate_key"] for item in extracted["entities"]),
        *(item["candidate_key"] for item in extracted["attributes"]),
        *(item["candidate_key"] for item in extracted["claims"]),
    ]
    assert len(all_keys) == len(set(all_keys))


@pytest.mark.asyncio
async def test_backfill_from_context_snapshot_creates_reviewable_candidates(
    client,
    admin_operator: AdminUser,
    db_session: AsyncSession,
) -> None:
    db_session.add(
        BrandContextSnapshot(
            id=_new_id(),
            brand_id=7,
            version="bcx-7-backfill",
            payload_json=_context_payload(),
            source_notes_json=[{"title": "Official product page"}],
            search_as_of=_now(),
            status="active",
        )
    )
    await db_session.commit()

    resp = await client.post(
        "/api/admin/llm-extraction/backfill",
        json={"brand_id": 7, "brand_context_version": "bcx-7-backfill"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["summary"]["entities_created"] >= 5
    assert body["summary"]["attributes_created"] >= 4
    assert body["summary"]["claims_created"] == 3

    listed = await client.get(
        "/api/admin/llm-extraction/candidates?entity_type=competitor&status=pending"
    )
    assert listed.status_code == 200
    rows = listed.json()["items"]
    assert any(row["name"] == "DealRoom" for row in rows)
    assert rows[0]["source_notes"]


@pytest.mark.asyncio
async def test_attribute_approval_writes_formal_kg_attribute_and_audit(
    client,
    admin_operator: AdminUser,
    db_session: AsyncSession,
) -> None:
    candidate = LLMAttributeCandidate(
        id=_new_id(),
        brand_id=7,
        brand_context_version="bcx-7-test",
        entity_kind="product",
        entity_id=None,
        entity_name="AcmeVault Rooms",
        attribute_key="key_features",
        attribute_value="bulk permission review",
        normalized_value="bulk permission review",
        candidate_key="attr:product:acmevault rooms:key_features:bulk permission review",
        confidence=0.82,
        evidence_json={"source": "brand_context_pack"},
        source_notes_json=[{"url": "https://acmevault.example/product"}],
        status="pending",
    )
    db_session.add(candidate)
    await db_session.commit()

    resp = await client.post(f"/api/admin/llm-extraction/attributes/{candidate.id}/approve")
    assert resp.status_code == 200
    body = resp.json()
    assert body["item"]["status"] == "approved"

    attr = (
        await db_session.execute(
            select(KGEntityAttribute).where(
                KGEntityAttribute.approved_from_candidate_id == candidate.id
            )
        )
    ).scalar_one()
    assert attr.entity_kind == "product"
    assert attr.attribute_key == "key_features"
    assert attr.attribute_value == "bulk permission review"

    audit = (
        await db_session.execute(
            select(AdminAuditLog).where(AdminAuditLog.action == "llm_attribute_approved")
        )
    ).scalar_one()
    assert audit.operator_id == admin_operator.id


@pytest.mark.asyncio
async def test_claim_approval_writes_formal_kg_claim(
    client,
    admin_operator: AdminUser,
    db_session: AsyncSession,
) -> None:
    candidate = LLMClaimCandidate(
        id=_new_id(),
        brand_id=7,
        brand_context_version="bcx-7-test",
        entity_kind="brand",
        entity_id="7",
        entity_name="AcmeVault",
        claim_type="pros",
        text="easy permission management",
        normalized_text="easy permission management",
        scenario="M&A due diligence",
        candidate_key="claim:brand:7:pros:easy permission management:m&a due diligence",
        confidence=0.79,
        evidence_json={"source": "brand_context_pack"},
        source_notes_json=[{"url": "https://acmevault.example/product"}],
        status="pending",
    )
    db_session.add(candidate)
    await db_session.commit()

    resp = await client.post(f"/api/admin/llm-extraction/claims/{candidate.id}/approve")
    assert resp.status_code == 200
    claim = (
        await db_session.execute(
            select(KGEntityClaim).where(KGEntityClaim.approved_from_candidate_id == candidate.id)
        )
    ).scalar_one()
    assert claim.claim_type == "pros"
    assert claim.text == "easy permission management"
    assert claim.scenario == "M&A due diligence"


@pytest.mark.asyncio
async def test_entity_reject_is_terminal_and_audited(
    client,
    admin_operator: AdminUser,
    db_session: AsyncSession,
) -> None:
    candidate = LLMEntityCandidate(
        id=_new_id(),
        brand_id=7,
        brand_context_version="bcx-7-test",
        entity_type="scenario",
        name="Wrong scenario",
        normalized_name="wrong scenario",
        parent_brand_id=7,
        parent_brand_name="AcmeVault",
        domain="acmevault.example",
        candidate_key="entity:scenario:wrong scenario:7",
        confidence=0.4,
        attributes_json={"pain_points": ["not relevant"]},
        evidence_json={"source": "brand_context_pack"},
        source_notes_json=[],
        status="pending",
    )
    db_session.add(candidate)
    await db_session.commit()

    resp = await client.post(
        f"/api/admin/llm-extraction/candidates/{candidate.id}/reject",
        json={"reason": "not relevant"},
    )
    assert resp.status_code == 200
    assert resp.json()["item"]["status"] == "rejected"

    second = await client.post(f"/api/admin/llm-extraction/candidates/{candidate.id}/approve")
    assert second.status_code == 409

    audit = (
        await db_session.execute(
            select(AdminAuditLog).where(AdminAuditLog.action == "llm_entity_rejected")
        )
    ).scalar_one()
    assert audit.operator_id == admin_operator.id


@pytest.mark.asyncio
async def test_approved_extractions_are_added_to_context_pack(
    db_session: AsyncSession,
) -> None:
    from app.admin.brand_context import enrich_context_pack_with_approved_extractions

    db_session.add_all(
        [
            LLMEntityCandidate(
                id=_new_id(),
                brand_id=7,
                brand_context_version="bcx-7-test",
                entity_type="scenario",
                name="Board reporting",
                normalized_name="board reporting",
                parent_brand_id=7,
                parent_brand_name="AcmeVault",
                candidate_key="entity:scenario:board reporting:7",
                attributes_json={
                    "pain_points": ["permission audit summaries"],
                    "decision_criteria": ["exportable reports"],
                },
                status="approved",
            ),
            KGEntityAttribute(
                id=_new_id(),
                entity_kind="brand",
                entity_id="7",
                entity_name="AcmeVault",
                entity_ref_key="brand:7",
                attribute_key="positioning",
                attribute_value="secure deal collaboration",
                normalized_value="secure deal collaboration",
                source="llm_extraction",
                status="active",
            ),
            KGEntityClaim(
                id=_new_id(),
                entity_kind="brand",
                entity_id="7",
                entity_name="AcmeVault",
                entity_ref_key="brand:7",
                claim_type="best_for",
                text="legal teams that need audit-ready diligence rooms",
                normalized_text="legal teams that need audit-ready diligence rooms",
                scenario="M&A due diligence",
                source="llm_extraction",
                status="active",
            ),
        ]
    )
    await db_session.commit()

    pack = await enrich_context_pack_with_approved_extractions(
        db_session,
        brand_id=7,
        payload={"brand": {"name": "AcmeVault"}, "scenarios": [], "claims": {}},
    )

    assert any(item["name"] == "Board reporting" for item in pack["scenarios"])
    assert "kg_entity_attributes" in pack["source_notes"][0]["source_type"]
    assert "legal teams that need audit-ready diligence rooms" in pack["claims"]["best_for"]


def test_admin_html_exposes_llm_extraction_review_surface() -> None:
    html = (Path(__file__).resolve().parents[1] / "static" / "admin.html").read_text(
        encoding="utf-8"
    )

    assert "planner-llm-extraction" in html
    assert "LLM Extraction" in html
    assert "llmExtractionTab" in html
    assert "/api/admin/llm-extraction/candidates" in html
    assert "/api/admin/llm-extraction/attributes" in html
    assert "/api/admin/llm-extraction/claims" in html
    assert "approveLLMExtractionCandidate" in html
    assert "rejectLLMExtractionCandidate" in html
