"""Brand context snapshots and assembly helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
from genpano_models import BrandContextSnapshot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def test_assemble_brand_context_pack_maps_search_attributes():
    from app.admin.brand_context import assemble_brand_context_pack

    pack = assemble_brand_context_pack(
        brand={
            "id": 7,
            "name": "Acme",
            "industry": "VDR",
            "description": "Secure document collaboration",
            "aliases": ["Acme VDR"],
            "products": [
                {
                    "name": "Acme Rooms",
                    "category": "virtual data room",
                    "description": "Due diligence workspace",
                    "aliases": ["Rooms"],
                }
            ],
        },
        search_context={
            "name": "Acme",
            "industry": "Virtual data room",
            "positioning": "secure deal collaboration platform",
            "products": [
                {
                    "name": "Acme Redaction",
                    "category": "AI redaction",
                    "key_features": ["PII detection"],
                    "use_cases": ["M&A diligence"],
                    "target_users": ["legal teams"],
                    "price_positioning": "enterprise",
                }
            ],
            "scenarios": [
                {
                    "name": "M&A due diligence",
                    "pain_points": ["large file review"],
                    "decision_criteria": ["permission controls"],
                    "buying_stage": "shortlist",
                }
            ],
            "competitors": [
                {
                    "name": "DealRoom",
                    "competitor_type": "direct",
                    "overlap_category": "VDR",
                    "comparison_axes": ["workflow speed"],
                }
            ],
            "audience_hypotheses": [
                {"segment_name": "legal ops", "needs": ["redaction"], "regions": ["US"]}
            ],
            "claims": {"pros": ["easy permissions"], "cons": ["enterprise pricing"]},
            "source_notes": [{"title": "Official", "url": "https://example.com/acme"}],
        },
    )

    assert pack["brand"]["name"] == "Acme"
    assert pack["brand"]["positioning"] == "secure deal collaboration platform"
    assert {p["name"] for p in pack["products"]} >= {"Acme Rooms", "Acme Redaction"}
    assert pack["scenarios"][0]["name"] == "M&A due diligence"
    assert pack["competitors"][0]["name"] == "DealRoom"
    assert pack["audience_hypotheses"][0]["segment_name"] == "legal ops"
    assert pack["claims"]["pros"] == ["easy permissions"]
    assert pack["source_notes"][0]["url"] == "https://example.com/acme"


@pytest.mark.asyncio
async def test_persist_brand_context_snapshot_returns_version(db_session: AsyncSession):
    from app.admin.brand_context import persist_brand_context_snapshot

    version = await persist_brand_context_snapshot(
        db_session,
        brand_id=7,
        payload={
            "brand": {"name": "Acme"},
            "products": [],
            "scenarios": [],
            "competitors": [],
            "audience_hypotheses": [],
            "claims": {},
            "source_notes": [{"title": "Official", "url": "https://example.com"}],
        },
        created_from_run_id="run-1",
    )

    row = (
        await db_session.execute(
            select(BrandContextSnapshot).where(BrandContextSnapshot.brand_id == 7)
        )
    ).scalar_one()

    assert row.version == version
    assert row.status == "active"
    assert row.payload_json["brand"]["name"] == "Acme"
    assert row.source_notes_json[0]["title"] == "Official"


def test_admin_topic_candidates_show_context_metadata():
    html = (Path(__file__).resolve().parents[1] / "static" / "admin.html").read_text(
        encoding="utf-8"
    )

    assert "topicPlanContextRefsLabel" in html
    assert "topicPlanCandidateContextSearchBlob" in html
    assert "item.brand_context_version" in html
    assert "item.topic_axis" in html
    assert "item.context_refs" in html
