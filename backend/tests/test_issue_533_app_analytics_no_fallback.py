"""Issue #533: App analytics API must expose no-fallback formula states."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from genpano_models import (
    BrandMention,
    GeoScoreDaily,
    Project,
    ProjectCompetitor,
    User,
)
from sqlalchemy import text
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
        email=f"issue533-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue 533 User",
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
    competitor_brand_ids: tuple[int, ...] = (),
    competitor_brand_names: tuple[str, ...] = (),
    industry: str = "Beauty",
) -> Project:
    # Issue #1185 / #1192: the /competitors/metrics endpoint now fails
    # closed when ``brands.industry`` is NULL for the primary brand.
    # Seed primary + named competitors with the same industry so the
    # behavior under test (no fallback, name-only competitor evidence,
    # etc.) is still observable in this fixture.
    if primary_brand_id is not None:
        for col in ("industry", "name_zh", "name_en", "name", "primary_name"):
            try:
                await db_session.execute(text(f"ALTER TABLE brands ADD COLUMN {col} TEXT"))
            except Exception:
                pass
        await db_session.execute(
            text("INSERT INTO brands (id, industry, name_en) VALUES (:id, :ind, :name)"),
            {"id": primary_brand_id, "ind": industry, "name": "Estee Lauder"},
        )
        for bid in competitor_brand_ids:
            await db_session.execute(
                text("INSERT INTO brands (id, industry) VALUES (:id, :ind)"),
                {"id": bid, "ind": industry},
            )
        for bname in competitor_brand_names:
            await db_session.execute(
                text("INSERT INTO brands (industry, name_en) VALUES (:ind, :name)"),
                {"ind": industry, "name": bname},
            )

    p = Project(
        user_id=user.id,
        name=f"Issue 533 {uuid.uuid4().hex[:6]}",
        primary_brand_id=primary_brand_id,
        industry_id=7,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p


def _card_by_key(body: dict[str, Any], key: str) -> dict[str, Any]:
    return next(card for card in body["kpi_cards"] if card["metric_key"] == key)


@pytest.mark.asyncio
async def test_computed_overview_and_metrics_values_report_formula_status_ok(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user)
    now = datetime.now()
    db_session.add(
        GeoScoreDaily(
            brand_id=12,
            date=datetime.combine(now.date(), datetime.min.time()),
            target_llm="chatgpt",
            total_queries=20,
            mention_count=8,
            mention_rate=0.4,
            avg_sov=0.5,
            avg_position_rank=1.4,
            avg_sentiment_score=0.6,
            citation_rate=0.25,
            avg_visibility=0.7,
            avg_sentiment=0.6,
            avg_sov_score=0.5,
            avg_citation_score=0.25,
            avg_geo_score=0.76,
        )
    )
    db_session.add_all(
        [
            BrandMention(
                response_id=9401,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=1,
                position_rank=1,
                sentiment="positive",
                sentiment_score=0.6,
                created_at=now,
            ),
            BrandMention(
                response_id=9401,
                brand_id=99,
                brand_name="Clinique",
                mention_count=1,
                position_rank=2,
                sentiment="negative",
                sentiment_score=0.2,
                created_at=now,
            ),
        ]
    )
    await db_session.commit()

    overview = await client.get(
        f"/api/v1/projects/{p.id}/overview",
        headers=_bearer(user),
        params={"brand_id": 12},
    )
    metrics = await client.get(
        f"/api/v1/projects/{p.id}/metrics",
        headers=_bearer(user),
        params={"brand_id": 12, "series": "mention_rate,sov"},
    )

    assert overview.status_code == 200, overview.text
    overview_body = overview.json()
    assert overview_body["state"] == "ok"
    assert overview_body["formula_status"] == "ok"
    assert overview_body["missing_inputs"] == []
    for key in ("geo_score", "mention_rate", "sov", "avg_sentiment"):
        card = _card_by_key(overview_body, key)
        assert card["value"] is not None
        assert card["formula_status"] == "ok"

    assert metrics.status_code == 200, metrics.text
    metrics_body = metrics.json()
    assert metrics_body["state"] == "ok"
    assert metrics_body["formula_status"] == "ok"
    assert metrics_body["missing_inputs"] == []
    by_metric = {series["metric"]: series for series in metrics_body["series"]}
    assert by_metric["mention_rate"]["points"]
    assert by_metric["mention_rate"]["formula_status"] == "ok"
    assert by_metric["sov"]["points"]
    assert by_metric["sov"]["formula_status"] == "ok"


@pytest.mark.asyncio
async def test_empty_overview_without_primary_brand_returns_null_kpi_values(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user, primary_brand_id=None)

    resp = await client.get(
        f"/api/v1/projects/{p.id}/overview",
        headers=_bearer(user),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "empty"
    assert body["state_reason"] == "no_primary_brand"
    assert body["formula_status"] == "no_evidence"
    assert [card["value"] for card in body["kpi_cards"]] == [None, None, None, None]


@pytest.mark.asyncio
async def test_name_only_competitor_mentions_count_as_competitive_evidence(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    # Issue #1185 / #1192: same-industry seed for the name-only competitor
    # so the unified industry filter keeps the bucket alive.
    p = await _project(db_session, user, competitor_brand_names=("Clinique",))
    now = datetime.now()
    db_session.add(
        GeoScoreDaily(
            brand_id=12,
            date=datetime.combine(now.date(), datetime.min.time()),
            target_llm="chatgpt",
            total_queries=10,
            mention_count=5,
            mention_rate=0.5,
            avg_sov=0.5,
            avg_position_rank=1.0,
            avg_sentiment_score=0.4,
            citation_rate=0.0,
            avg_visibility=0.5,
            avg_sentiment=0.4,
            avg_sov_score=0.5,
            avg_citation_score=0.0,
            avg_geo_score=0.64,
        )
    )
    db_session.add_all(
        [
            BrandMention(
                response_id=9501,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=1,
                position_rank=1,
                sentiment="positive",
                sentiment_score=0.5,
                created_at=now,
            ),
            BrandMention(
                response_id=9501,
                brand_id=None,
                brand_name="Clinique",
                mention_count=1,
                position_rank=2,
                sentiment="negative",
                sentiment_score=0.2,
                created_at=now,
            ),
        ]
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{p.id}/competitors/metrics",
        headers=_bearer(user),
        params={"brand_id": 12},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "ok"
    assert body["formula_status"] == "ok"
    assert body["evidence_counts"]["competitive_mention_count"] == 1
    assert "brand_mentions.competitive_set" not in body["missing_inputs"]
    assert body["primary"]["avg_sov"] == pytest.approx(0.5)
    assert body["competitors"][0]["brand_id"] is None
    assert body["competitors"][0]["brand_name"] == "Clinique"


@pytest.mark.asyncio
async def test_overview_and_metrics_do_not_use_brand_mentions_as_denominator_fallback(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user)
    db_session.add(
        BrandMention(
            response_id=9101,
            brand_id=12,
            brand_name="Estee Lauder",
            mention_count=1,
            position_rank=1,
            sentiment_score=0.4,
            created_at=datetime.now(),
        )
    )
    await db_session.commit()

    overview = await client.get(
        f"/api/v1/projects/{p.id}/overview",
        headers=_bearer(user),
        params={"brand_id": 12},
    )
    metrics = await client.get(
        f"/api/v1/projects/{p.id}/metrics",
        headers=_bearer(user),
        params={"brand_id": 12, "series": "mention_rate,sov"},
    )

    assert overview.status_code == 200
    overview_body = overview.json()
    assert overview_body["state"] == "partial"
    assert overview_body["formula_status"] == "missing_required_inputs"
    assert "eligible_response_denominator" in overview_body["missing_inputs"]
    assert "brand_mentions.competitive_set" in overview_body["missing_inputs"]
    assert _card_by_key(overview_body, "mention_rate")["value"] is None
    assert _card_by_key(overview_body, "sov")["value"] is None
    assert overview_body["evidence_counts"]["brand_mention_count"] == 1

    assert metrics.status_code == 200
    metrics_body = metrics.json()
    assert metrics_body["state"] == "partial"
    by_metric = {series["metric"]: series for series in metrics_body["series"]}
    assert by_metric["mention_rate"]["points"] == []
    assert by_metric["mention_rate"]["formula_status"] == "missing_required_inputs"
    assert by_metric["sov"]["points"] == []
    assert by_metric["sov"]["formula_status"] == "missing_required_inputs"


@pytest.mark.asyncio
async def test_geo_score_daily_with_zero_denominator_is_partial_not_one_hundred_percent(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user)
    d = datetime.now().date()
    db_session.add(
        GeoScoreDaily(
            brand_id=12,
            date=datetime.combine(d, datetime.min.time()),
            target_llm="chatgpt",
            total_queries=0,
            mention_count=1,
            mention_rate=1.0,
            avg_sov=100.0,
            avg_position_rank=None,
            avg_sentiment_score=None,
            citation_rate=0.0,
            avg_visibility=80.0,
            avg_sentiment=None,
            avg_sov_score=100.0,
            avg_citation_score=0.0,
            avg_geo_score=80.0,
        )
    )
    await db_session.commit()

    overview = await client.get(
        f"/api/v1/projects/{p.id}/overview",
        headers=_bearer(user),
        params={"brand_id": 12},
    )

    assert overview.status_code == 200
    body = overview.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "missing_required_inputs"
    assert "geo_score_daily.total_queries" in body["missing_inputs"]
    assert body["evidence_counts"]["geo_score_daily_rows"] == 1
    assert body["evidence_counts"]["eligible_response_count"] == 0
    assert _card_by_key(body, "mention_rate")["value"] is None
    assert _card_by_key(body, "sov")["value"] is None
    for key in ("geo_score", "mention_rate", "sov", "avg_sentiment"):
        card = _card_by_key(body, key)
        assert card["value"] is None
        assert card["formula_status"] == "missing_required_inputs"


@pytest.mark.asyncio
async def test_partial_overview_propagates_missing_inputs_to_nested_kpis(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user)
    d = datetime.now().date()
    db_session.add(
        GeoScoreDaily(
            brand_id=12,
            date=datetime.combine(d, datetime.min.time()),
            target_llm="chatgpt",
            total_queries=0,
            mention_count=58,
            mention_rate=0.829,
            avg_sov=1.0,
            avg_position_rank=None,
            avg_sentiment_score=0.5,
            citation_rate=0.0,
            avg_visibility=0.0,
            avg_sentiment=0.5,
            avg_sov_score=1.0,
            avg_citation_score=0.0,
            avg_geo_score=0.0,
        )
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{p.id}/overview",
        headers=_bearer(user),
        params={"brand_id": 12},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "missing_required_inputs"
    assert body["evidence_counts"]["eligible_response_count"] == 0
    assert "eligible_response_denominator" in body["missing_inputs"]
    for key in ("geo_score", "mention_rate", "sov", "avg_sentiment"):
        card = _card_by_key(body, key)
        assert card["value"] is None
        assert card["formula_status"] == "missing_required_inputs"


@pytest.mark.asyncio
async def test_metrics_withhold_fallback_points_when_formula_inputs_are_missing(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user)
    d = datetime.now().date()
    db_session.add(
        GeoScoreDaily(
            brand_id=12,
            date=datetime.combine(d, datetime.min.time()),
            target_llm="chatgpt",
            total_queries=0,
            mention_count=58,
            mention_rate=0.829,
            avg_sov=1.0,
            avg_position_rank=None,
            avg_sentiment_score=0.5,
            citation_rate=0.0,
            avg_visibility=0.0,
            avg_sentiment=0.5,
            avg_sov_score=1.0,
            avg_citation_score=0.0,
            avg_geo_score=0.0,
        )
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{p.id}/metrics",
        headers=_bearer(user),
        params={"brand_id": 12, "series": "mention_rate,sov,sentiment,citation"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "missing_required_inputs"
    by_metric = {series["metric"]: series for series in body["series"]}
    for metric in ("mention_rate", "sov", "sentiment", "citation"):
        assert by_metric[metric]["points"] == []
        assert by_metric[metric]["state"] == "partial"
        assert by_metric[metric]["formula_status"] == "missing_required_inputs"
    assert "brand_mentions.competitive_set" in by_metric["sov"]["missing_inputs"]
    assert "citation_sources" in by_metric["citation"]["missing_inputs"]


@pytest.mark.asyncio
async def test_citation_metric_agrees_with_citations_when_sources_absent(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user)
    d = datetime.now().date()
    db_session.add(
        GeoScoreDaily(
            brand_id=12,
            date=datetime.combine(d, datetime.min.time()),
            target_llm="chatgpt",
            total_queries=10,
            mention_count=5,
            mention_rate=0.5,
            avg_sov=0.5,
            avg_position_rank=1.0,
            avg_sentiment_score=0.5,
            citation_rate=0.4,
            avg_visibility=0.5,
            avg_sentiment=0.5,
            avg_sov_score=0.5,
            avg_citation_score=0.4,
            avg_geo_score=0.5,
        )
    )
    await db_session.commit()

    metrics = await client.get(
        f"/api/v1/projects/{p.id}/metrics",
        headers=_bearer(user),
        params={"brand_id": 12, "series": "citation"},
    )
    citations = await client.get(
        f"/api/v1/projects/{p.id}/citations",
        headers=_bearer(user),
    )

    assert metrics.status_code == 200, metrics.text
    assert citations.status_code == 200, citations.text
    citation_series = metrics.json()["series"][0]
    citations_body = citations.json()
    assert citations_body["state"] in {"empty", "partial"}
    assert citations_body["formula_status"] != "ok"
    assert citations_body["evidence_counts"]["citation_source_count"] == 0
    assert citation_series["points"] == []
    assert citation_series["state"] == "partial"
    assert citation_series["formula_status"] == "missing_required_inputs"
    assert "citation_sources" in citation_series["missing_inputs"]


@pytest.mark.asyncio
async def test_sentiment_trend_by_engine_does_not_override_empty_sentiment_contract(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user)
    d = datetime.now().date()
    db_session.add(
        GeoScoreDaily(
            brand_id=12,
            date=datetime.combine(d, datetime.min.time()),
            target_llm="chatgpt",
            total_queries=10,
            mention_count=5,
            mention_rate=0.5,
            avg_sov=0.5,
            avg_position_rank=1.0,
            avg_sentiment_score=0.5,
            citation_rate=0.0,
            avg_visibility=0.5,
            avg_sentiment=0.5,
            avg_sov_score=0.5,
            avg_citation_score=0.0,
            avg_geo_score=0.5,
        )
    )
    db_session.add(
        BrandMention(
            response_id=9601,
            brand_id=12,
            brand_name="Estee Lauder",
            mention_count=1,
            position_rank=1,
            sentiment=None,
            sentiment_score=0.5,
            created_at=datetime.now(),
        )
    )
    await db_session.commit()

    sentiment = await client.get(
        f"/api/v1/projects/{p.id}/sentiment",
        headers=_bearer(user),
    )
    trend = await client.get(
        f"/api/v1/projects/{p.id}/sentiment/trend-by-engine",
        headers=_bearer(user),
    )

    assert sentiment.status_code == 200, sentiment.text
    assert trend.status_code == 200, trend.text
    sentiment_body = sentiment.json()
    trend_body = trend.json()
    assert sentiment_body["state"] in {"empty", "partial"}
    assert sentiment_body["formula_status"] != "ok"
    assert trend_body["items"] == []
    assert trend_body["state"] == "partial"
    assert trend_body["formula_status"] == "missing_required_inputs"
    assert "brand_mentions.sentiment_score" in trend_body["missing_inputs"]


@pytest.mark.asyncio
async def test_competitor_metrics_target_only_extraction_does_not_emit_sov_100(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    # Issue #1185 / #1192: brand 99 needs an industry for the pinned-
    # competitors fallback path (no name-only mention here).
    p = await _project(db_session, user, competitor_brand_ids=(99,))
    db_session.add(ProjectCompetitor(project_id=p.id, brand_id=99, pinned_by=user.id))
    db_session.add(
        BrandMention(
            response_id=9201,
            brand_id=12,
            brand_name="Estee Lauder",
            mention_count=2,
            position_rank=1,
            sentiment_score=0.6,
            created_at=datetime.now(),
        )
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{p.id}/competitors/metrics",
        headers=_bearer(user),
        params={"brand_id": 12},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "missing_required_inputs"
    assert "brand_mentions.competitive_set" in body["missing_inputs"]
    assert body["primary"]["avg_sov"] is None
    assert body["primary"]["avg_mention_rate"] is None


@pytest.mark.asyncio
async def test_app_analytics_endpoints_expose_shared_no_fallback_contract_metadata(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user)
    db_session.add(
        BrandMention(
            response_id=9301,
            brand_id=12,
            brand_name="Estee Lauder",
            mention_count=1,
            position_rank=None,
            sentiment_score=None,
            created_at=datetime.now() - timedelta(days=1),
        )
    )
    await db_session.commit()

    paths = [
        f"/api/v1/projects/{p.id}/topics",
        f"/api/v1/projects/{p.id}/sentiment",
        f"/api/v1/projects/{p.id}/citations",
        f"/api/v1/projects/{p.id}/products",
    ]

    for path in paths:
        resp = await client.get(path, headers=_bearer(user))
        assert resp.status_code == 200
        body = resp.json()
        assert body["formula_status"] in {
            "missing_required_inputs",
            "no_evidence",
            "formula_pending_upstream",
        }
        assert isinstance(body["missing_inputs"], list)
        assert isinstance(body["evidence_counts"], dict)
        assert body["selected_filters"]["project_id"] == p.id
        assert body["selected_filters"]["brand_id"] == 12
        assert body["source_provenance"]
