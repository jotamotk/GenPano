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


def _v3_package() -> dict:
    return {
        "analyzer_version": "v3",
        "response_id": 401,
        "query_id": 301,
        "prompt_id": 201,
        "topic_id": 101,
        "project_ids": [],
        "source_brand_id": 12,
        "target_brand_id": 12,
        "engine": "chatgpt",
        "collected_at": WINDOW_DAY.isoformat(),
        "analysis_started_at": WINDOW_DAY.isoformat(),
        "analysis_completed_at": WINDOW_DAY.isoformat(),
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "prompt_version": "test",
        "raw_output_sha256": "sha-401",
        "idempotency_key": "401:v3:sha",
        "eligibility": {"eligible": True, "success_response": True, "invalid_reason": None},
        "coverage": {
            "eligible_response_count_basis": 1,
            "analyzed": True,
            "parse_status": "ok",
            "validation_errors": [],
        },
        "entities": {
            "target": {
                "brand_id": 12,
                "canonical_name": "Estee Lauder",
                "mentioned": True,
                "mention_count": 36,
                "position_rank": 1,
            },
            "configured_competitors": [],
            "response_named_brands": [],
        },
        "visibility": {
            "is_visible": True,
            "rank": 1,
            "visibility_score": 1.0,
            "formula_status": "ok",
            "reason_codes": [],
        },
        "sov": {
            "numerator_target_mentions": 36,
            "denominator_competitive_mentions": 37,
            "denominator_brand_ids": [2],
            "denominator_raw_names": ["La Roche-Posay"],
            "formula_status": "ok",
            "reason_codes": [],
            "sample_response_ids": [401],
        },
        "sentiment": {
            "label": "positive",
            "score": 0.42,
            "drivers": [{"driver_text": "sentiment", "source_quote": "quoted sentiment"}],
            "source_quotes": ["quoted sentiment"],
            "formula_status": "ok",
            "reason_codes": [],
        },
        "citations": {
            "total_citations": 1,
            "attributed_citations": [{"domain": "example.com"}],
            "unresolved_citations": [],
            "formula_status": "ok",
            "reason_codes": [],
        },
        "rank": {"best_rank": 1, "formula_status": "ok", "reason_codes": []},
        "topic": {"topic_id": 101, "prompt_id": 201, "query_id": 301},
        "products": [],
        "topic_metrics": {"formula_status": "ok", "reason_codes": []},
        "geo_pano": {
            "visibility_component": "ok",
            "sentiment_component": "ok",
            "sov_component": "ok",
            "citation_component": "ok",
            "formula_status": "ok",
            "reason_codes": [],
        },
    }


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
                    "analyzer_fact_package_v3": _v3_package(),
                    "canonical_alias_repairs": [
                        {
                            "brand_id": 12,
                            "owner_brand_id": 12,
                            "missing_sources": ["llm_brand_sentiment"],
                            "state": "partial",
                        }
                    ],
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
    assert sentiment_body["formula_status"] in {"partial", "missing_required_inputs"}
    assert sentiment_body["distribution"]["positive_count"] == 1
    assert sentiment_body["trend_30d"][0]["avg_score"] == pytest.approx(0.42)
    assert "sentiment_drivers.source_quote" in sentiment_body["missing_inputs"]

    by_engine_body = by_engine.json()
    assert by_engine_body["state"] == "partial"
    assert by_engine_body["formula_status"] == "partial"
    if by_engine_body["items"]:
        assert by_engine_body["items"][0]["positive"] == 1

    trend_body = trend.json()
    assert trend_body["state"] in {"ok", "partial"}
    assert trend_body["formula_status"] in {"ok", "partial"}
    assert trend_body["items"][0]["by_engine"]["chatgpt"] == pytest.approx(0.42)

    metric_series = metrics.json()["series"][0]
    assert metric_series["state"] == "ok"
    assert metric_series["formula_status"] == "ok"
    assert metric_series["points"][0]["value"] == pytest.approx(0.42)
