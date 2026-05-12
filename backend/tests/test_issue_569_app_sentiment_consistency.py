"""Issue #569: sentiment score/label surfaces must share target evidence."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from genpano_models import GeoScoreDaily, User
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._overview_service import get_brand_overview
from app.user_auth.jwt import sign_user_access_token
from tests.test_issue_562_app_analytics_endpoint_consistency import (
    REPAIR_DAY,
    WINDOW_DAY,
    WINDOW_FROM,
    WINDOW_TO,
    _seed_live_shaped_admin_facts,
)

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
        email=f"issue569-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue 569 User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


async def _seed_live_shaped_sentiment_gap(db_session: AsyncSession, user: User):
    project = await _seed_live_shaped_admin_facts(
        db_session,
        user,
        target_sentiment="positive",
    )
    db_session.add(
        GeoScoreDaily(
            brand_id=12,
            date=datetime.combine(WINDOW_DAY.date(), datetime.min.time()),
            target_llm="chatgpt",
            total_queries=6,
            mention_count=6,
            mention_rate=1.0,
            avg_sov=0.973,
            avg_position_rank=1.0,
            avg_sentiment_score=0.42,
            citation_rate=0.5,
            avg_visibility=52.0,
            avg_sentiment=0.42,
            avg_sov_score=0.973,
            avg_citation_score=0.0,
            avg_geo_score=0.41,
        )
    )
    await db_session.execute(
        text(
            """
            UPDATE response_analyses
            SET raw_analysis_json = :payload
            WHERE response_id = 401
            """
        ),
        {
            "payload": json.dumps(
                {
                    "canonical_alias_repairs": [
                        {
                            "brand_id": 12,
                            "owner_brand_id": 12,
                            "missing_sources": ["llm_brand_sentiment"],
                            "state": "partial",
                        }
                    ]
                }
            )
        },
    )
    await db_session.commit()
    return project


@pytest.mark.asyncio
async def test_live_target_sentiment_scores_power_all_score_label_surfaces(
    client,
    db_session: AsyncSession,
    user: User,
) -> None:
    project = await _seed_live_shaped_sentiment_gap(db_session, user)
    headers = _bearer(user)
    params = {"from": WINDOW_FROM, "to": WINDOW_TO}

    overview = await get_brand_overview(
        db_session,
        project,
        from_date=WINDOW_DAY.date(),
        to_date=REPAIR_DAY.date(),
        brand_id_override=12,
    )
    sentiment = await client.get(
        f"/api/v1/projects/{project.id}/sentiment",
        headers=headers,
        params=params,
    )
    by_engine = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/by-engine",
        headers=headers,
        params=params,
    )
    trend = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/trend-by-engine",
        headers=headers,
        params=params,
    )
    metrics = await client.get(
        f"/api/v1/projects/{project.id}/metrics",
        headers=headers,
        params={**params, "brand_id": 12, "series": "sentiment"},
    )

    assert sentiment.status_code == 200, sentiment.text
    assert by_engine.status_code == 200, by_engine.text
    assert trend.status_code == 200, trend.text
    assert metrics.status_code == 200, metrics.text

    overview_body = overview.model_dump(mode="json")
    sentiment_card = next(
        card for card in overview_body["kpi_cards"] if card["metric_key"] == "sentiment"
    )
    assert "llm_brand_sentiment" in overview_body["missing_inputs"]
    assert sentiment_card["value"] == pytest.approx(0.42)
    assert sentiment_card["formula_status"] == "ok"

    sentiment_body = sentiment.json()
    assert sentiment_body["state"] == "partial"
    assert sentiment_body["formula_status"] == "missing_required_inputs"
    assert sentiment_body["distribution"]["positive_count"] == 1
    assert sentiment_body["trend_30d"][0]["avg_score"] == pytest.approx(0.42)
    assert sentiment_body["missing_inputs"] == ["sentiment_drivers.source_quote"]

    by_engine_body = by_engine.json()
    assert by_engine_body["state"] == "ok"
    assert by_engine_body["formula_status"] == "ok"
    assert by_engine_body["items"][0]["engine"] == "chatgpt"
    assert by_engine_body["items"][0]["positive"] == 1

    trend_body = trend.json()
    assert trend_body["state"] == "ok"
    assert trend_body["formula_status"] == "ok"
    assert trend_body["items"][0]["by_engine"]["chatgpt"] == pytest.approx(0.42)

    metric_series = metrics.json()["series"][0]
    assert metric_series["state"] == "ok"
    assert metric_series["formula_status"] == "ok"
    assert metric_series["points"][0]["value"] == pytest.approx(0.42)
