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
) -> Project:
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


@pytest.mark.asyncio
async def test_competitor_metrics_target_only_extraction_does_not_emit_sov_100(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    p = await _project(db_session, user)
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
