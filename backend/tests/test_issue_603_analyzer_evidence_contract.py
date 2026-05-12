"""Issue #603: App APIs must honor #602 analyzer fact packages."""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any

import pytest
import pytest_asyncio
from genpano_models import (
    BrandMention,
    CitationSource,
    GeoScoreDaily,
    Project,
    ResponseAnalysis,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)

DAY = datetime(2026, 5, 12, 8, 0, 0)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"issue603-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue 603 User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


async def _project(db_session: AsyncSession, user: User) -> Project:
    p = Project(
        user_id=user.id,
        name=f"Issue 603 {uuid.uuid4().hex[:6]}",
        primary_brand_id=12,
        industry_id=7,
    )
    db_session.add(p)
    await db_session.commit()
    return p


def _card(body: dict[str, Any], metric_key: str) -> dict[str, Any]:
    return next(card for card in body["kpi_cards"] if card["metric_key"] == metric_key)


def _base_packages(*, response_id: int, status: str = "ok") -> dict[str, Any]:
    return {
        "version": "issue_602_v1",
        "coverage": {
            "status": status,
            "eligible_response_ids": [response_id],
            "analyzed_response_ids": [response_id] if status != "missing_required_inputs" else [],
            "failed_response_ids": [],
            "missing_analyzer_response_ids": [],
            "eligible_count": 1,
            "analyzed_count": 1,
            "failed_count": 0,
            "missing_analyzer_count": 0,
            "reason_codes": [] if status == "ok" else ["partial_analyzer_coverage"],
            "chains": [
                {
                    "response_id": response_id,
                    "query_id": 300 + response_id,
                    "prompt_id": 200 + response_id,
                    "topic_id": 100 + response_id,
                    "project_brand_id": 12,
                    "engine": "chatgpt",
                    "profile_id": None,
                    "collected_at": DAY.isoformat(),
                    "analysis_status": "done",
                    "has_analysis": True,
                }
            ],
        },
        "entities": {
            "status": "ok",
            "target_brand_id": 12,
            "target_brand_name": "Estee Lauder",
            "facts": [],
        },
        "sov": {
            "status": "ok",
            "formula_status": "ok",
            "reason_codes": [],
            "numerator_target_mentions": 1,
            "denominator_competitive_mentions": 2,
            "sov": 0.5,
            "competitors": [{"brand_id": 99, "brand_name": "Clinique", "mention_count": 1}],
            "sample_response_ids": [response_id],
        },
        "sentiment": {
            "status": "ok",
            "formula_status": "ok",
            "reason_codes": [],
            "score_count": 1,
            "label_count": 1,
            "driver_count": 1,
            "quote_count": 1,
            "avg_sentiment_score": 0.8,
            "sample_response_ids": [response_id],
        },
        "citations": {
            "status": "ok",
            "formula_status": "ok",
            "citation_count": 1,
            "attributed_count": 1,
            "unresolved_count": 0,
            "normalized_domains": ["example.com"],
            "source_type_counts": {"publisher": 1},
            "tier_counts": {"2": 1},
            "unresolved_source_type_counts": {},
            "unresolved_tier_counts": {},
            "sample_response_ids": [response_id],
            "reason_codes": [],
        },
        "topic_product": {
            "status": "ok",
            "topic_chain_missing_response_ids": [],
            "topic_chain_count": 1,
            "product_fact_count": 0,
            "product_status": "empty",
            "reason_codes": [],
        },
        "pano_geo": {
            "status": "ok",
            "formula_status": "ok",
            "component_readiness": {
                "coverage": "ok",
                "sov": "ok",
                "sentiment": "ok",
                "citation": "ok",
            },
            "reason_codes": [],
        },
    }


def _analysis(response_id: int, packages: dict[str, Any]) -> ResponseAnalysis:
    return ResponseAnalysis(
        response_id=response_id,
        target_brand_mentioned=True,
        target_brand_rank=1,
        target_brand_sentiment="positive",
        sentiment_score=0.8,
        geo_score=0.8,
        raw_analysis_json={"analyzer_fact_packages": packages},
        created_at=DAY,
    )


def _geo_score() -> GeoScoreDaily:
    return GeoScoreDaily(
        brand_id=12,
        date=datetime.combine(DAY.date(), datetime.min.time()),
        target_llm="chatgpt",
        total_queries=10,
        mention_count=8,
        mention_rate=0.8,
        avg_sov=1.0,
        avg_position_rank=1.0,
        avg_sentiment_score=0.8,
        citation_rate=0.5,
        avg_visibility=0.8,
        avg_sentiment=0.8,
        avg_sov_score=1.0,
        avg_citation_score=0.5,
        avg_geo_score=0.88,
    )


@pytest.mark.asyncio
async def test_sov_package_blocks_legacy_target_only_values_across_overview_and_metrics(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    packages = _base_packages(response_id=6001)
    packages["sov"].update(
        {
            "status": "missing_required_inputs",
            "formula_status": "missing_required_inputs",
            "reason_codes": ["target_only_sov"],
            "denominator_competitive_mentions": 1,
            "sov": None,
            "competitors": [],
        }
    )
    packages["pano_geo"].update(
        {
            "status": "missing_required_inputs",
            "formula_status": "missing_required_inputs",
            "component_readiness": {
                "coverage": "ok",
                "sov": "missing_required_inputs",
                "sentiment": "ok",
                "citation": "ok",
            },
            "reason_codes": ["sov_missing_required_inputs"],
        }
    )
    db_session.add(_geo_score())
    db_session.add_all(
        [
            BrandMention(
                response_id=6001,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=2,
                position_rank=1,
                sentiment="positive",
                sentiment_score=0.8,
                created_at=DAY,
            ),
            BrandMention(
                response_id=6002,
                brand_id=99,
                brand_name="Clinique",
                mention_count=1,
                position_rank=2,
                sentiment="negative",
                sentiment_score=0.2,
                created_at=DAY,
            ),
            _analysis(6001, packages),
        ]
    )
    await db_session.commit()

    overview = await client.get(
        f"/api/v1/projects/{project.id}/overview",
        headers=_bearer(user),
        params={"brand_id": 12, "from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )
    metrics = await client.get(
        f"/api/v1/projects/{project.id}/metrics",
        headers=_bearer(user),
        params={
            "brand_id": 12,
            "series": "sov",
            "from": DAY.date().isoformat(),
            "to": DAY.date().isoformat(),
        },
    )

    assert overview.status_code == 200, overview.text
    overview_body = overview.json()
    assert overview_body["formula_status"] == "partial"
    assert "target_only_sov" in overview_body["missing_reasons"]
    assert overview_body["evidence_counts"]["analyzer_sov_denominator_competitive_mentions"] == 1
    assert overview_body["metric_formula_evidence"]["sov"]["formula_status"] == (
        "missing_required_inputs"
    )
    assert _card(overview_body, "sov")["value"] is None
    assert _card(overview_body, "sov")["formula_status"] == "missing_required_inputs"
    assert _card(overview_body, "geo_score")["value"] is None
    assert _card(overview_body, "geo_score")["formula_status"] == "missing_required_inputs"

    assert metrics.status_code == 200, metrics.text
    sov_series = metrics.json()["series"][0]
    assert sov_series["points"] == []
    assert sov_series["formula_status"] == "missing_required_inputs"
    assert "target_only_sov" in sov_series["missing_inputs"]


@pytest.mark.asyncio
async def test_missing_analyzer_rows_mark_coverage_partial_not_zero_or_ok(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    db_session.add(_geo_score())
    db_session.add_all(
        [
            BrandMention(
                response_id=6101,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=1,
                sentiment="positive",
                sentiment_score=0.7,
                created_at=DAY,
            ),
            BrandMention(
                response_id=6102,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=1,
                sentiment="positive",
                sentiment_score=0.6,
                created_at=DAY,
            ),
            _analysis(6101, _base_packages(response_id=6101)),
        ]
    )
    await db_session.commit()

    overview = await client.get(
        f"/api/v1/projects/{project.id}/overview",
        headers=_bearer(user),
        params={"brand_id": 12, "from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert overview.status_code == 200, overview.text
    body = overview.json()
    assert body["formula_status"] == "partial"
    assert "missing_analyzer_rows" in body["missing_reasons"]
    assert body["evidence_counts"]["analyzer_missing_response_count"] == 1
    assert body["evidence_counts"]["analyzer_package_count"] == 1
    assert body["metric_formula_evidence"]["coverage"]["formula_status"] == "partial"


@pytest.mark.asyncio
async def test_sentiment_package_score_only_keeps_explanatory_endpoint_partial(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    packages = _base_packages(response_id=6201)
    packages["sentiment"].update(
        {
            "status": "partial",
            "formula_status": "partial",
            "reason_codes": ["missing_sentiment_driver_quote"],
            "driver_count": 0,
            "quote_count": 0,
        }
    )
    packages["pano_geo"].update(
        {
            "status": "missing_required_inputs",
            "formula_status": "missing_required_inputs",
            "component_readiness": {
                "coverage": "ok",
                "sov": "ok",
                "sentiment": "partial",
                "citation": "ok",
            },
            "reason_codes": ["sentiment_partial"],
        }
    )
    db_session.add_all(
        [
            BrandMention(
                response_id=6201,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=1,
                sentiment="positive",
                sentiment_score=0.8,
                created_at=DAY,
            ),
            _analysis(6201, packages),
        ]
    )
    await db_session.commit()

    sentiment = await client.get(
        f"/api/v1/projects/{project.id}/sentiment",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert sentiment.status_code == 200, sentiment.text
    body = sentiment.json()
    assert body["distribution"]["positive_count"] == 1
    assert body["formula_status"] == "partial"
    assert "missing_sentiment_driver_quote" in body["missing_reasons"]
    assert body["evidence_counts"]["analyzer_sentiment_driver_count"] == 0
    assert body["metric_formula_evidence"]["sentiment"]["formula_status"] == "partial"


@pytest.mark.asyncio
async def test_citations_expose_attributed_and_unresolved_package_counts_separately(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    packages = _base_packages(response_id=6301)
    packages["citations"].update(
        {
            "status": "partial",
            "formula_status": "partial",
            "citation_count": 2,
            "attributed_count": 1,
            "unresolved_count": 1,
            "unresolved_source_type_counts": {"social": 1},
            "unresolved_tier_counts": {"4": 1},
            "reason_codes": ["unresolved_citation_attribution"],
        }
    )
    mention = BrandMention(
        response_id=6301,
        brand_id=12,
        brand_name="Estee Lauder",
        mention_count=1,
        sentiment="positive",
        sentiment_score=0.7,
        created_at=DAY,
    )
    db_session.add(mention)
    await db_session.flush()
    db_session.add_all(
        [
            CitationSource(
                response_id=6301,
                mention_id=mention.id,
                url="https://example.com/target",
                domain="example.com",
                title="Target evidence",
                source_type="publisher",
                created_at=DAY,
            ),
            CitationSource(
                response_id=6301,
                mention_id=None,
                url="https://social.example/unresolved",
                domain="social.example",
                title="Unresolved evidence",
                source_type="social",
                created_at=DAY,
            ),
            _analysis(6301, packages),
        ]
    )
    await db_session.commit()

    citations = await client.get(
        f"/api/v1/projects/{project.id}/citations",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert citations.status_code == 200, citations.text
    body = citations.json()
    assert body["total"] == 1
    assert body["by_domain_top"][0]["domain"] == "example.com"
    assert body["formula_status"] == "partial"
    assert "unresolved_citation_attribution" in body["missing_reasons"]
    assert body["evidence_counts"]["analyzer_attributed_citation_count"] == 1
    assert body["evidence_counts"]["analyzer_unresolved_citation_count"] == 1
    assert body["metric_formula_evidence"]["citation"]["unresolved_tier_counts"] == {"4": 1}
