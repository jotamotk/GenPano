"""Issue #486 App analytics API contract coverage."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    BrandMention,
    GeoScoreDaily,
    Project,
    ProjectCompetitor,
    ResponseAnalysis,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"issue486-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue 486 User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


async def _project(
    db_session: AsyncSession,
    user: User,
    *,
    primary_brand_id: int | None = 12,
) -> Project:
    p = Project(
        user_id=user.id,
        name=f"Issue 486 {uuid.uuid4().hex[:6]}",
        primary_brand_id=primary_brand_id,
        industry_id=7,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p


def _daily_row(
    *,
    brand_id: int,
    days_ago: int = 0,
    mention_rate: float = 0.162,
    avg_sov: float = 38.4,
    citation_rate: float = 12.5,
    avg_sentiment: float = 0.25,
) -> GeoScoreDaily:
    d = datetime.now().date() - timedelta(days=days_ago)
    return GeoScoreDaily(
        brand_id=brand_id,
        date=datetime.combine(d, datetime.min.time()),
        target_llm="chatgpt",
        total_queries=100,
        mention_count=16,
        mention_rate=mention_rate,
        avg_sov=avg_sov,
        avg_position_rank=2.0,
        avg_sentiment_score=avg_sentiment,
        citation_rate=citation_rate,
        avg_visibility=72.0,
        avg_sentiment=avg_sentiment,
        avg_sov_score=38.4,
        avg_citation_score=12.5,
        avg_geo_score=80.0,
        industry_rank=3,
        industry_sov_pct=38.4,
    )


@pytest.mark.asyncio
async def test_overview_contract_exposes_units_evidence_and_percent_scale(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user)
    db_session.add(ProjectCompetitor(project_id=p.id, brand_id=99, pinned_by=user.id))
    db_session.add(_daily_row(brand_id=12))
    db_session.add(
        BrandMention(
            response_id=8601,
            brand_id=12,
            brand_name="Estee Lauder",
            mention_count=2,
            position_rank=1,
            sentiment_score=0.25,
            created_at=datetime.now(),
        )
    )
    db_session.add(
        ResponseAnalysis(
            response_id=8601,
            target_brand_mentioned=True,
            target_brand_rank=1,
            sentiment_score=0.25,
            geo_score=80.0,
            raw_analysis_json={"source": "full_analyzer"},
            analyzed_at=datetime.now(),
        )
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{p.id}/overview",
        headers=_bearer(user),
        params={"brand_id": 12},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "ok"
    assert body["state_reason"] == "data_available"
    assert body["formula_diagnostics"]["status"] == "formula_pending_upstream"
    assert "upstream_formula_provenance" in body["missing_sources"]
    assert body["project_scope"] == {
        "exists": True,
        "project_id": p.id,
        "primary_brand_id": 12,
        "requested_brand_id": 12,
        "competitor_brand_ids": [99],
        "missing_reason": None,
    }
    assert body["evidence_counts"]["geo_score_daily_rows"] == 1
    assert body["evidence_counts"]["brand_mention_count"] == 1
    assert body["evidence_counts"]["brand_mentioned_response_count"] == 1
    assert body["evidence_counts"]["response_analysis_count"] == 1

    cards = {card["metric_key"]: card for card in body["kpi_cards"]}
    assert cards["mention_rate"]["value"] == pytest.approx(16.2)
    assert cards["mention_rate"]["unit"] == "percent"
    assert cards["mention_rate"]["value_scale"] == "percent"
    assert cards["mention_rate"]["value_range"] == {"min": 0.0, "max": 100.0}
    assert cards["mention_rate"]["formula_status"] == "formula_pending_upstream"
    assert "eligible" in cards["mention_rate"]["denominator_label"]

    assert cards["sov"]["value"] == pytest.approx(38.4)
    assert cards["sov"]["value_scale"] == "percent"
    assert "competitive" in cards["sov"]["denominator_label"]
    assert cards["sov"]["denominator_label"] != cards["mention_rate"]["denominator_label"]

    assert body["score_components"]["final_geo_score"]["value"] == pytest.approx(80.0)
    assert body["score_components"]["visibility"]["value_scale"] == "score_0_100"


@pytest.mark.asyncio
async def test_geo_score_daily_sentiment_component_is_not_labeled_raw_sentiment(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user)
    db_session.add(ProjectCompetitor(project_id=p.id, brand_id=99, pinned_by=user.id))
    db_session.add(_daily_row(brand_id=12, avg_sentiment=64.0))
    db_session.add(_daily_row(brand_id=99, avg_sentiment=52.0))
    await db_session.commit()

    overview = await client.get(
        f"/api/v1/projects/{p.id}/overview",
        headers=_bearer(user),
        params={"brand_id": 12},
    )
    metrics = await client.get(
        f"/api/v1/projects/{p.id}/metrics",
        headers=_bearer(user),
        params={"series": "sentiment", "brand_id": 12},
    )
    competitor_metrics = await client.get(
        f"/api/v1/projects/{p.id}/competitors/metrics",
        headers=_bearer(user),
        params={"brand_id": 12},
    )
    competitor_trends = await client.get(
        f"/api/v1/projects/{p.id}/competitors/trends",
        headers=_bearer(user),
        params={"brand_id": 12, "metric": "sentiment"},
    )

    assert overview.status_code == 200
    sentiment_card = next(
        card for card in overview.json()["kpi_cards"] if card["label_en"] == "Sentiment"
    )
    assert sentiment_card["metric_key"] == "avg_sentiment"
    assert sentiment_card["value"] == pytest.approx(64.0)
    assert sentiment_card["value_scale"] == "score_0_100"
    assert sentiment_card["value_range"] == {"min": 0.0, "max": 100.0}

    assert metrics.status_code == 200
    sentiment_series = metrics.json()["series"][0]
    assert sentiment_series["metric"] == "sentiment"
    assert sentiment_series["points"][0]["value"] == pytest.approx(64.0)
    assert sentiment_series["value_scale"] == "score_0_100"
    assert sentiment_series["value_range"] == {"min": 0.0, "max": 100.0}

    assert competitor_metrics.status_code == 200
    competitor_metrics_body = competitor_metrics.json()
    avg_sentiment_def = competitor_metrics_body["metric_definitions"]["avg_sentiment"]
    assert avg_sentiment_def["value_scale"] == "score_0_100"
    assert avg_sentiment_def["value_range"] == {"min": 0.0, "max": 100.0}
    assert competitor_metrics_body["primary"]["avg_sentiment"] == pytest.approx(64.0)

    assert competitor_trends.status_code == 200
    trend_definition = competitor_trends.json()["metric_definition"]
    assert trend_definition["metric_key"] == "avg_sentiment"
    assert trend_definition["value_scale"] == "score_0_100"
    assert trend_definition["value_range"] == {"min": 0.0, "max": 100.0}


@pytest.mark.asyncio
async def test_metrics_contract_uses_decimal_values_and_distinct_denominators(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user)
    db_session.add(_daily_row(brand_id=12, avg_sov=38.4, citation_rate=12.5))
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{p.id}/metrics",
        headers=_bearer(user),
        params={"series": "mention_rate,sov,citation", "brand_id": 12},
    )

    assert resp.status_code == 200
    body = resp.json()
    by_metric = {series["metric"]: series for series in body["series"]}
    assert by_metric["mention_rate"]["points"][0]["value"] == pytest.approx(0.162)
    assert by_metric["sov"]["points"][0]["value"] == pytest.approx(0.384)
    assert by_metric["citation"]["points"][0]["value"] == pytest.approx(0.125)

    assert by_metric["mention_rate"]["unit"] == "ratio"
    assert by_metric["mention_rate"]["value_scale"] == "decimal"
    assert by_metric["mention_rate"]["value_range"] == {"min": 0.0, "max": 1.0}
    assert by_metric["mention_rate"]["formula_status"] == "formula_pending_upstream"
    assert "eligible" in by_metric["mention_rate"]["denominator_label"]
    assert "competitive" in by_metric["sov"]["denominator_label"]
    assert by_metric["mention_rate"]["denominator_label"] != by_metric["sov"]["denominator_label"]
    assert body["state_reason"] == "data_available"
    assert body["formula_diagnostics"]["status"] == "formula_pending_upstream"


@pytest.mark.asyncio
async def test_overview_partial_alias_repair_metadata_surfaces_missing_sources(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user)
    db_session.add(
        BrandMention(
            response_id=8701,
            brand_id=12,
            brand_name="Estee Lauder",
            mention_count=1,
            position_rank=None,
            sentiment_score=None,
            created_at=datetime.now(),
        )
    )
    db_session.add(
        ResponseAnalysis(
            response_id=8701,
            target_brand_mentioned=True,
            raw_analysis_json={
                "canonical_alias_repairs": [
                    {
                        "state": "partial",
                        "brand_id": 12,
                        "brand_name": "Estee Lauder",
                        "owner_brand_id": 2,
                        "matched_terms": ["Estee Lauder"],
                        "mention_count": 1,
                        "missing_sources": [
                            "llm_brand_position",
                            "llm_brand_sentiment",
                        ],
                    }
                ]
            },
            analyzed_at=datetime.now(),
        )
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{p.id}/overview",
        headers=_bearer(user),
        params={"brand_id": 12},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "partial"
    assert body["state_reason"] == "partial_analyzer_data"
    assert "llm_brand_position" in body["missing_sources"]
    assert "llm_brand_sentiment" in body["missing_sources"]
    assert body["identity_diagnostics"]["canonical_alias_repair_count"] == 1
    assert body["identity_diagnostics"]["raw_text_owner_brand_ids"] == [2]


@pytest.mark.asyncio
async def test_empty_project_contract_includes_project_scope_and_state_reason(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user, primary_brand_id=None)

    overview = await client.get(f"/api/v1/projects/{p.id}/overview", headers=_bearer(user))
    metrics = await client.get(f"/api/v1/projects/{p.id}/metrics", headers=_bearer(user))

    assert overview.status_code == 200
    overview_body = overview.json()
    assert overview_body["state"] == "empty"
    assert overview_body["state_reason"] == "no_primary_brand"
    assert overview_body["project_scope"]["exists"] is True
    assert overview_body["project_scope"]["missing_reason"] == "no_primary_brand"
    assert overview_body["missing_sources"] == ["project.primary_brand_id"]

    assert metrics.status_code == 200
    metrics_body = metrics.json()
    assert metrics_body["state"] == "empty"
    assert metrics_body["state_reason"] == "no_primary_brand"
    assert metrics_body["project_scope"]["missing_reason"] == "no_primary_brand"


@pytest.mark.asyncio
async def test_competitor_chart_endpoints_expose_contract_metadata(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user)
    db_session.add(ProjectCompetitor(project_id=p.id, brand_id=99, pinned_by=user.id))
    db_session.add(_daily_row(brand_id=12, avg_sov=38.4))
    db_session.add(_daily_row(brand_id=99, avg_sov=21.6))
    await db_session.commit()

    metrics = await client.get(
        f"/api/v1/projects/{p.id}/competitors/metrics",
        headers=_bearer(user),
        params={"brand_id": 12},
    )
    trends = await client.get(
        f"/api/v1/projects/{p.id}/competitors/trends",
        headers=_bearer(user),
        params={"brand_id": 12, "metric": "sov"},
    )

    assert metrics.status_code == 200
    metrics_body = metrics.json()
    assert metrics_body["state_reason"] == "data_available"
    assert metrics_body["metric_definitions"]["avg_sov"]["unit"] == "ratio"
    assert metrics_body["metric_definitions"]["avg_sov"]["value_scale"] == "decimal"
    assert (
        metrics_body["metric_definitions"]["avg_sov"]["formula_status"]
        == "formula_pending_upstream"
    )
    assert metrics_body["primary"]["avg_sov"] == pytest.approx(0.384)
    assert metrics_body["competitors"][0]["avg_sov"] == pytest.approx(0.216)
    assert metrics_body["evidence_counts"]["competitor_brand_count"] == 1

    assert trends.status_code == 200
    trends_body = trends.json()
    assert trends_body["metric_definition"]["metric_key"] == "sov"
    assert trends_body["metric_definition"]["unit"] == "ratio"
    primary_series = next(series for series in trends_body["series"] if series["is_primary"])
    assert primary_series["points"][0]["value"] == pytest.approx(0.384)
