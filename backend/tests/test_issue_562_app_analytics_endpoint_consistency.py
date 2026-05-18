"""Issue #562: App analytics endpoints must share evidence semantics."""

from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from genpano_models import (
    BrandMention,
    CitationSource,
    Project,
    ProjectCompetitor,
    ResponseAnalysis,
    User,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)

WINDOW_FROM = "2026-04-24"
WINDOW_TO = "2026-05-07"
WINDOW_DAY = datetime(2026, 4, 24, 2, 44, 46)
REPAIR_DAY = datetime(2026, 5, 11, 9, 30, 0)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


def _v3_package(*, target_sentiment: str | None = None) -> dict:
    sentiment_status = "partial"
    sentiment_reasons = ["missing_sentiment_driver_quote"]
    if target_sentiment is None:
        sentiment_reasons.append("missing_sentiment_label")
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
            "configured_competitors": [
                {"brand_id": 2, "canonical_name": "La Roche-Posay", "mentioned": True}
            ],
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
            "label": target_sentiment,
            "score": 0.42,
            "drivers": [],
            "source_quotes": [],
            "formula_status": sentiment_status,
            "reason_codes": sentiment_reasons,
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
            "sentiment_component": sentiment_status,
            "sov_component": "ok",
            "citation_component": "ok",
            "formula_status": "partial",
            "reason_codes": ["sentiment_component_partial"],
        },
    }


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"issue562-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue 562 User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


async def _seed_live_shaped_admin_facts(
    db_session: AsyncSession,
    user: User,
    *,
    target_sentiment: str | None = None,
) -> Project:
    await db_session.execute(text("ALTER TABLE brands ADD COLUMN name TEXT"))
    await db_session.execute(text("ALTER TABLE brands ADD COLUMN industry TEXT"))
    await db_session.execute(
        text(
            """
            CREATE TABLE topics (
                id INTEGER PRIMARY KEY,
                brand_id INTEGER,
                text TEXT,
                category TEXT,
                status TEXT,
                created_at DATETIME
            )
            """
        )
    )
    for ddl in [
        "ALTER TABLE prompts ADD COLUMN topic_id INTEGER",
        "ALTER TABLE prompts ADD COLUMN text TEXT",
        "ALTER TABLE prompts ADD COLUMN intent TEXT",
        "ALTER TABLE prompts ADD COLUMN prompt_scope TEXT",
        "ALTER TABLE prompts ADD COLUMN language TEXT",
        "ALTER TABLE prompts ADD COLUMN status TEXT",
        "ALTER TABLE prompts ADD COLUMN created_at DATETIME",
    ]:
        await db_session.execute(text(ddl))
    await db_session.execute(
        text(
            """
            CREATE TABLE queries (
                id INTEGER PRIMARY KEY,
                target_llm TEXT,
                status TEXT,
                query_text TEXT,
                brand_id INTEGER,
                profile_id TEXT,
                prompt_id INTEGER,
                created_at DATETIME,
                executed_at DATETIME,
                finished_at DATETIME,
                latency_ms INTEGER
            )
            """
        )
    )
    for ddl in [
        "ALTER TABLE llm_responses ADD COLUMN query_id INTEGER",
        "ALTER TABLE llm_responses ADD COLUMN prompt_id INTEGER",
        "ALTER TABLE llm_responses ADD COLUMN raw_text TEXT",
        "ALTER TABLE llm_responses ADD COLUMN target_llm TEXT",
        "ALTER TABLE llm_responses ADD COLUMN intent TEXT",
        "ALTER TABLE llm_responses ADD COLUMN llm_version TEXT",
        "ALTER TABLE llm_responses ADD COLUMN citations_json TEXT",
        "ALTER TABLE llm_responses ADD COLUMN created_at DATETIME",
    ]:
        await db_session.execute(text(ddl))

    project = Project(
        id="95d43022-a5c8-5944-b6d6-34b29faa18b5",
        user_id=user.id,
        name="Estee Lauder / App Analytics",
        primary_brand_id=12,
        industry_id=7,
    )
    db_session.add(project)
    db_session.add(ProjectCompetitor(project_id=project.id, brand_id=2, pinned_by=user.id))
    await db_session.flush()

    await db_session.execute(
        text(
            """
            INSERT INTO brands (id, name, industry) VALUES
              (12, 'Estee Lauder', 'Beauty'),
              (2, 'La Roche-Posay', 'Beauty')
            """
        )
    )
    await db_session.execute(
        text(
            """
            INSERT INTO topics (id, brand_id, text, category, status, created_at)
            VALUES (101, 2, 'Estee Lauder competitor evidence', 'brand', 'active', :day)
            """
        ),
        {"day": WINDOW_DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts
                (id, topic_id, text, intent, prompt_scope, language, status, created_at)
            VALUES
              (201, 101, 'Which anti-aging serum should I choose?',
               'commercial', 'non_branded', 'en', 'active', :day)
            """
        ),
        {"day": WINDOW_DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO queries
                (id, target_llm, status, query_text, brand_id, profile_id, prompt_id,
                 created_at, executed_at, finished_at, latency_ms)
            VALUES
              -- Issue #1225: queries.brand_id is the brand the query was
              -- issued FOR. The original seed used brand_id=2 (competitor)
              -- because the topic was framed as "competitor evidence", but
              -- in a real project queries are issued for the project's
              -- primary brand (12 = Estee Lauder). The PRD-APP-ANALYTICS-003
              -- revised citation_share denominator (window-total citations
              -- scoped to the target brand's queries) requires this
              -- realistic shape.
              (301, 'chatgpt', 'done', 'anti-aging serum options', 12, NULL, 201,
               :day, :day, :day, 700),
              (302, 'deepseek', 'done', 'anti-aging serum comparison', 12, NULL, 201,
               :day, :day, :day, 800)
            """
        ),
        {"day": WINDOW_DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, llm_version,
                 citations_json, created_at)
            VALUES
              (401, 301, 201,
               'Estee Lauder is cited often; La Roche-Posay is also mentioned.',
               'chatgpt', 'commercial', 'gpt-test', '[]', :day),
              (402, 302, 201,
               'The category has options, but this response has no target mention.',
               'deepseek', 'commercial', 'gpt-test', '[]', :day)
            """
        ),
        {"day": WINDOW_DAY},
    )
    db_session.add_all(
        [
            ResponseAnalysis(
                response_id=401,
                target_brand_mentioned=True,
                target_brand_rank=1,
                sentiment_score=0.42,
                geo_score=0.76,
                raw_analysis_json={
                    "analyzer_fact_package_v3": _v3_package(target_sentiment=target_sentiment)
                },
            ),
        ]
    )
    await db_session.flush()

    target = BrandMention(
        response_id=401,
        brand_id=12,
        brand_name="Estee Lauder",
        mention_count=36,
        position_rank=1,
        sentiment=target_sentiment,
        sentiment_score=0.42,
        created_at=REPAIR_DAY,
    )
    competitor = BrandMention(
        response_id=401,
        brand_id=2,
        brand_name="La Roche-Posay",
        mention_count=1,
        position_rank=2,
        sentiment=None,
        sentiment_score=None,
        created_at=REPAIR_DAY,
    )
    db_session.add_all([target, competitor])
    await db_session.flush()
    db_session.add(
        # Issue #1225 (PRD-APP-ANALYTICS-003 revised): the citation_share
        # metric now requires the citation row's created_at to fall inside
        # the requested window (consistent with the existing
        # `citation_source_count` aggregate at builder.py:946-961). The
        # original fixture used REPAIR_DAY (May 11, outside the April
        # 24-May 7 window) to test the brand-mention "repaired after
        # window" path, which was only valid for the old bucket-based
        # denominator. Keep the citation inside the window so the citation
        # series renders with the new window-total denominator.
        CitationSource(
            response_id=401,
            mention_id=target.id,
            url="https://example.com/estee-evidence",
            domain="example.com",
            title="Estee evidence",
            source_type="article",
            created_at=WINDOW_DAY,
        )
    )
    await db_session.commit()
    return project


@pytest.mark.asyncio
async def test_metrics_sov_and_citation_use_same_admin_fact_window_as_overview(
    client,
    db_session: AsyncSession,
    user: User,
) -> None:
    project = await _seed_live_shaped_admin_facts(db_session, user)
    headers = _bearer(user)
    params = {"from": WINDOW_FROM, "to": WINDOW_TO, "brand_id": 12}

    overview = await client.get(
        f"/api/v1/projects/{project.id}/overview",
        headers=headers,
        params=params,
    )
    metrics = await client.get(
        f"/api/v1/projects/{project.id}/metrics",
        headers=headers,
        params={**params, "series": "mention_rate,sov,citation"},
    )
    citations = await client.get(
        f"/api/v1/projects/{project.id}/citations",
        headers=headers,
        params={"from": WINDOW_FROM, "to": WINDOW_TO},
    )
    composition = await client.get(
        f"/api/v1/projects/{project.id}/citations/composition",
        headers=headers,
        params={"from": WINDOW_FROM, "to": WINDOW_TO},
    )
    authority = await client.get(
        f"/api/v1/projects/{project.id}/citations/authority-trend",
        headers=headers,
        params={"from": WINDOW_FROM, "to": WINDOW_TO},
    )

    assert overview.status_code == 200, overview.text
    assert metrics.status_code == 200, metrics.text
    assert citations.status_code == 200, citations.text
    assert composition.status_code == 200, composition.text
    assert authority.status_code == 200, authority.text

    overview_body = overview.json()
    assert overview_body["formula_status"] == "partial"
    assert "missing_sentiment_driver_quote" in overview_body["missing_reasons"]
    sov_card = next(card for card in overview_body["kpi_cards"] if card["metric_key"] == "sov")
    assert sov_card["value"] == pytest.approx(97.3)
    assert sov_card["formula_status"] == "ok"

    series = {row["metric"]: row for row in metrics.json()["series"]}
    assert series["sov"]["points"][0]["value"] == pytest.approx(0.973)
    assert series["sov"]["formula_status"] == "ok"
    # Issue #1225 (PRD-APP-ANALYTICS-003 revised 2026-05-18): with the
    # window-total citation denominator, this minimal fixture (one target
    # citation, no other citations in the brand's queries) cannot produce
    # a meaningful ratio — the contract correctly degrades the series to
    # `state="partial"` with `missing_inputs` flagging the absent inputs.
    # The previous assertion (`value == 1.0` from target/target) was the
    # pre-PRD-revision 100% degeneracy this issue explicitly removed.
    assert series["citation"]["state"] == "partial"
    assert series["citation"]["points"] == []

    citation_body = citations.json()
    assert citation_body["total"] == 1
    assert citation_body["items"][0]["domain"] == "example.com"
    assert citation_body["formula_status"] == "partial"
    assert "missing_sentiment_driver_quote" in citation_body["missing_reasons"]
    composition_body = composition.json()
    assert composition_body["total"] == 1
    assert composition_body["segments"]
    assert composition_body["formula_status"] == "partial"
    assert "missing_sentiment_driver_quote" in composition_body["missing_inputs"]
    authority_body = authority.json()
    assert authority_body["points"]
    assert authority_body["formula_status"] == "partial"


@pytest.mark.asyncio
async def test_sentiment_routes_share_partial_state_when_scores_exist_without_labels(
    client,
    db_session: AsyncSession,
    user: User,
) -> None:
    project = await _seed_live_shaped_admin_facts(db_session, user)
    headers = _bearer(user)
    params = {"from": WINDOW_FROM, "to": WINDOW_TO}

    sentiment = await client.get(
        f"/api/v1/projects/{project.id}/sentiment",
        headers=headers,
        params=params,
    )
    trend = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/trend-by-engine",
        headers=headers,
        params=params,
    )
    metric = await client.get(
        f"/api/v1/projects/{project.id}/metrics",
        headers=headers,
        params={**params, "brand_id": 12, "series": "sentiment"},
    )
    by_engine = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/by-engine",
        headers=headers,
        params=params,
    )

    assert sentiment.status_code == 200, sentiment.text
    assert trend.status_code == 200, trend.text
    assert metric.status_code == 200, metric.text
    assert by_engine.status_code == 200, by_engine.text
    sentiment_body = sentiment.json()
    trend_body = trend.json()
    metric_body = metric.json()
    by_engine_body = by_engine.json()
    assert sentiment_body["state"] == "partial"
    assert sentiment_body["formula_status"] == "partial"
    assert sentiment_body["evidence_count"] == 1
    assert "brand_mentions.sentiment" in sentiment_body["missing_inputs"]
    assert "missing_sentiment_label" in sentiment_body["missing_reasons"]
    assert trend_body["state"] == "partial"
    assert trend_body["formula_status"] == "missing_required_inputs"
    assert trend_body["evidence_count"] == 1
    assert "brand_mentions.sentiment" in trend_body["missing_inputs"]
    assert by_engine_body["state"] == "partial"
    assert by_engine_body["formula_status"] == "missing_required_inputs"
    assert by_engine_body["evidence_count"] == 1
    assert "brand_mentions.sentiment" in by_engine_body["missing_inputs"]
    metric_series = metric_body["series"][0]
    assert metric_series["points"] == []
    assert metric_series["state"] == "partial"
    assert metric_series["formula_status"] in {"partial", "missing_required_inputs"}


@pytest.mark.asyncio
async def test_sentiment_scores_and_labels_are_visible_when_only_drivers_are_missing(
    client,
    db_session: AsyncSession,
    user: User,
) -> None:
    project = await _seed_live_shaped_admin_facts(
        db_session,
        user,
        target_sentiment="positive",
    )
    headers = _bearer(user)
    params = {"from": WINDOW_FROM, "to": WINDOW_TO}

    sentiment = await client.get(
        f"/api/v1/projects/{project.id}/sentiment",
        headers=headers,
        params=params,
    )
    trend = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/trend-by-engine",
        headers=headers,
        params=params,
    )
    metric = await client.get(
        f"/api/v1/projects/{project.id}/metrics",
        headers=headers,
        params={**params, "brand_id": 12, "series": "sentiment"},
    )
    by_engine = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/by-engine",
        headers=headers,
        params=params,
    )

    assert sentiment.status_code == 200, sentiment.text
    assert trend.status_code == 200, trend.text
    assert metric.status_code == 200, metric.text
    assert by_engine.status_code == 200, by_engine.text
    sentiment_body = sentiment.json()
    trend_body = trend.json()
    metric_series = metric.json()["series"][0]
    by_engine_body = by_engine.json()

    assert sentiment_body["distribution"]["positive_count"] == 1
    assert sentiment_body["trend_30d"][0]["avg_score"] == pytest.approx(0.42)
    assert sentiment_body["state"] == "partial"
    assert sentiment_body["formula_status"] == "partial"
    assert "sentiment_drivers.source_quote" in sentiment_body["missing_inputs"]
    assert "missing_sentiment_driver_quote" in sentiment_body["missing_reasons"]
    assert sentiment_body["top_drivers"] == []
    assert trend_body["state"] == "partial"
    assert trend_body["formula_status"] == "partial"
    assert trend_body["items"] == []
    assert "missing_sentiment_driver_quote" in trend_body["missing_reasons"]
    assert by_engine_body["state"] == "partial"
    assert by_engine_body["formula_status"] == "partial"
    assert by_engine_body["items"] == []
    # Issue #948: sentiment metric points survive when only peripheral
    # analyzer drivers are missing — the underlying sentiment_score is
    # real and computable. The test name confirms this contract.
    assert metric_series["formula_status"] == "partial"
    assert len(metric_series["points"]) == 1
    assert metric_series["points"][0]["value"] == pytest.approx(0.42)
