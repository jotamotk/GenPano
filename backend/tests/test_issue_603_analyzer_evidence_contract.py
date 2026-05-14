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
    ProjectCompetitor,
    ProjectTopicPin,
    ResponseAnalysis,
    User,
)
from sqlalchemy import text
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


async def _seed_admin_chain_tables(db_session: AsyncSession) -> None:
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


async def _seed_chain_response(
    db_session: AsyncSession,
    *,
    topic_id: int,
    prompt_id: int,
    query_id: int,
    response_id: int,
) -> None:
    await db_session.execute(
        text(
            """
            INSERT INTO topics (id, brand_id, text, category, status, created_at)
            VALUES (:topic_id, 12, :topic_text, 'product', 'active', :day)
            """
        ),
        {"topic_id": topic_id, "topic_text": f"Estee Lauder topic {topic_id}", "day": DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts
                (id, topic_id, text, intent, prompt_scope, language, status, created_at)
            VALUES (:prompt_id, :topic_id, :prompt_text, 'commercial', 'non_branded',
                    'en', 'active', :day)
            """
        ),
        {
            "prompt_id": prompt_id,
            "topic_id": topic_id,
            "prompt_text": f"Is Estee Lauder serum topic {topic_id} recommended?",
            "day": DAY,
        },
    )
    await db_session.execute(
        text(
            """
            INSERT INTO queries
                (id, target_llm, status, query_text, brand_id, profile_id, prompt_id,
                 created_at, executed_at, finished_at, latency_ms)
            VALUES (:query_id, 'chatgpt', 'done', :query_text, 12, 'PROF-603',
                    :prompt_id, :day, :day, :day, 100)
            """
        ),
        {
            "query_id": query_id,
            "prompt_id": prompt_id,
            "query_text": f"Is Estee Lauder serum topic {topic_id} recommended?",
            "day": DAY,
        },
    )
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, llm_version,
                 citations_json, created_at)
            VALUES (:response_id, :query_id, :prompt_id, :raw_text, 'chatgpt',
                    'commercial', 'gpt-test', '[]', :day)
            """
        ),
        {
            "response_id": response_id,
            "query_id": query_id,
            "prompt_id": prompt_id,
            "raw_text": f"Estee Lauder response for topic {topic_id}",
            "day": DAY,
        },
    )


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


@pytest.mark.asyncio
async def test_analyzer_rollup_ignores_same_brand_packages_outside_project_response_scope(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    own_packages = _base_packages(response_id=6401)
    other_packages = _base_packages(response_id=6402)
    other_packages["sov"].update(
        {
            "status": "missing_required_inputs",
            "formula_status": "missing_required_inputs",
            "reason_codes": ["target_only_sov"],
            "denominator_competitive_mentions": 1,
            "sov": None,
            "competitors": [],
        }
    )
    db_session.add(_geo_score())
    db_session.add_all(
        [
            BrandMention(
                response_id=6401,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=1,
                position_rank=1,
                sentiment="positive",
                sentiment_score=0.8,
                created_at=DAY,
            ),
            _analysis(6401, own_packages),
            _analysis(6402, other_packages),
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
    assert body["metric_formula_evidence"]["sov"]["formula_status"] == "ok"
    assert "target_only_sov" not in body["missing_reasons"]
    assert body["evidence_counts"]["analyzer_package_count"] == 1
    assert body["evidence_counts"]["analyzer_sov_denominator_competitive_mentions"] == 2


@pytest.mark.asyncio
async def test_analyzer_rollup_keeps_sov_visible_when_mixed_packages_have_competitor_denominator(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    await _seed_admin_chain_tables(db_session)
    db_session.add(ProjectTopicPin(project_id=project.id, topic_id=74401, state="tracked"))
    db_session.add(ProjectTopicPin(project_id=project.id, topic_id=74402, state="tracked"))
    await _seed_chain_response(
        db_session,
        topic_id=74401,
        prompt_id=74411,
        query_id=74421,
        response_id=74431,
    )
    await _seed_chain_response(
        db_session,
        topic_id=74402,
        prompt_id=74412,
        query_id=74422,
        response_id=74432,
    )
    target_only = _base_packages(response_id=74431)
    target_only["coverage"].update(
        {
            "status": "partial",
            "formula_status": "partial",
            "reason_codes": ["partial_analyzer_coverage", "missing_analyzer_rows"],
        }
    )
    target_only["sov"].update(
        {
            "status": "missing_required_inputs",
            "formula_status": "missing_required_inputs",
            "reason_codes": ["target_only_sov"],
            "numerator_target_mentions": 35,
            "denominator_competitive_mentions": 35,
            "sov": None,
            "competitors": [],
        }
    )
    with_competitor = _base_packages(response_id=74432)
    with_competitor["sov"].update(
        {
            "numerator_target_mentions": 0,
            "denominator_competitive_mentions": 211,
            "sov": 0.0,
            "competitors": [{"brand_id": 2, "brand_name": "Competitor", "mention_count": 211}],
            "sample_response_ids": [74432],
        }
    )
    db_session.add_all(
        [
            BrandMention(
                response_id=74431,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=35,
                sentiment="positive",
                sentiment_score=0.8,
                created_at=DAY,
            ),
            BrandMention(
                response_id=74432,
                brand_id=2,
                brand_name="Competitor",
                mention_count=211,
                sentiment="neutral",
                sentiment_score=0.0,
                created_at=DAY,
            ),
            _analysis(74431, target_only),
            _analysis(74432, with_competitor),
        ]
    )
    await db_session.commit()

    metrics = await client.get(
        f"/api/v1/projects/{project.id}/metrics",
        headers=_bearer(user),
        params={
            "brand_id": 12,
            "from": DAY.date().isoformat(),
            "to": DAY.date().isoformat(),
            "series": "sov",
        },
    )

    assert metrics.status_code == 200, metrics.text
    body = metrics.json()
    sov_series = body["series"][0]
    assert sov_series["points"][0]["value"] == pytest.approx(35 / 246, abs=0.0001)
    assert body["formula_status"] == "partial"
    assert sov_series["formula_status"] == "ok"
    assert "target_only_sov" not in sov_series["missing_inputs"]
    assert body["metric_formula_evidence"]["sov"]["numerator_count"] == 35
    assert body["metric_formula_evidence"]["sov"]["denominator_count"] == 246


@pytest.mark.asyncio
async def test_analyzer_rollup_ignores_same_brand_packages_from_another_project_chain(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    other_project = Project(
        user_id=user.id,
        name=f"Issue 603 other {uuid.uuid4().hex[:6]}",
        primary_brand_id=12,
        industry_id=7,
    )
    db_session.add(other_project)
    await db_session.flush()
    db_session.add_all(
        [
            ProjectTopicPin(project_id=project.id, topic_id=6801, state="tracked"),
            ProjectTopicPin(project_id=other_project.id, topic_id=6802, state="tracked"),
        ]
    )
    await _seed_admin_chain_tables(db_session)
    await _seed_chain_response(
        db_session,
        topic_id=6801,
        prompt_id=68011,
        query_id=68012,
        response_id=68013,
    )
    await _seed_chain_response(
        db_session,
        topic_id=6802,
        prompt_id=68021,
        query_id=68022,
        response_id=68023,
    )
    db_session.add(_geo_score())
    db_session.add_all(
        [
            BrandMention(
                response_id=68013,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=1,
                sentiment="positive",
                sentiment_score=0.8,
                created_at=DAY,
            ),
            BrandMention(
                response_id=68023,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=1,
                sentiment="positive",
                sentiment_score=0.8,
                created_at=DAY,
            ),
            _analysis(68023, _base_packages(response_id=68023)),
        ]
    )
    await db_session.commit()

    chart = await client.get(
        f"/api/v1/projects/{project.id}/metrics/by-engine",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert chart.status_code == 200, chart.text
    body = chart.json()
    assert body["state"] == "partial"
    assert body["evidence_counts"].get("analyzer_package_count", 0) == 0
    assert body["metric_formula_evidence"]["sov"]["formula_status"] == "partial"
    assert body["items"][0]["sov"] is None
    assert "missing_analyzer_fact_packages" in body["missing_reasons"]


@pytest.mark.asyncio
async def test_overview_trends_are_withheld_when_analyzer_package_blocks_metric(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    packages = _base_packages(response_id=6501)
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
                "sov": "missing_required_inputs",
                "sentiment": "partial",
                "citation": "ok",
            },
            "reason_codes": ["sov_missing_required_inputs", "sentiment_partial"],
        }
    )
    db_session.add(_geo_score())
    db_session.add_all(
        [
            BrandMention(
                response_id=6501,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=1,
                sentiment="positive",
                sentiment_score=0.8,
                created_at=DAY,
            ),
            _analysis(6501, packages),
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
    # SoV: analyzer reports `missing_required_inputs` + `target_only_sov`.
    # Critical block — value must be withheld per the no-fallback contract.
    assert _card(body, "sov")["value"] is None
    # Issue #948: sentiment analyzer reports `partial` (drivers missing
    # but the sentiment_score itself is computable). The KPI card value
    # is preserved with formula_status=partial so the frontend renders
    # the number; trends that depend on `pano_score` package are still
    # withheld per `_apply_score_component_contract` / `metric_missing_inputs`.
    sentiment_card = _card(body, "avg_sentiment")
    assert sentiment_card["value"] is not None
    assert sentiment_card["formula_status"] == "partial"
    assert body["sov_30d"] == []
    assert body["sentiment_30d"] == []
    assert body["geo_score_30d"] == []


@pytest.mark.asyncio
async def test_engine_metrics_chart_applies_analyzer_proof_to_legacy_series(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    packages = _base_packages(response_id=6601)
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
    db_session.add(_geo_score())
    db_session.add_all(
        [
            BrandMention(
                response_id=6601,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=1,
                sentiment="positive",
                sentiment_score=0.8,
                created_at=DAY,
            ),
            _analysis(6601, packages),
        ]
    )
    await db_session.commit()

    chart = await client.get(
        f"/api/v1/projects/{project.id}/metrics/by-engine",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert chart.status_code == 200, chart.text
    body = chart.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "partial"
    assert body["metric_formula_evidence"]["sov"]["formula_status"] == "missing_required_inputs"
    assert body["items"][0]["sov"] is None
    assert "target_only_sov" in body["missing_inputs"]


@pytest.mark.asyncio
async def test_engine_metrics_chart_nulls_legacy_values_when_analyzer_packages_missing(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    db_session.add(_geo_score())
    db_session.add(
        BrandMention(
            response_id=6651,
            brand_id=12,
            brand_name="Estee Lauder",
            mention_count=1,
            sentiment="positive",
            sentiment_score=0.8,
            created_at=DAY,
        )
    )
    await db_session.commit()

    chart = await client.get(
        f"/api/v1/projects/{project.id}/metrics/by-engine",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert chart.status_code == 200, chart.text
    body = chart.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "partial"
    assert "response_analyses.raw_analysis_json.analyzer_fact_packages" in body["missing_inputs"]
    assert body["metric_formula_evidence"]["coverage"]["formula_status"] == (
        "missing_required_inputs"
    )
    assert body["metric_formula_evidence"]["sov"]["formula_status"] == ("missing_required_inputs")
    assert body["metric_formula_evidence"]["sentiment"]["formula_status"] in {
        "partial",
        "missing_required_inputs",
    }
    assert body["metric_formula_evidence"]["citation"]["formula_status"] in {
        "partial",
        "missing_required_inputs",
    }
    assert body["items"][0]["mention_rate"] is None
    assert body["items"][0]["sov"] is None
    assert body["items"][0]["sentiment"] is None
    assert body["items"][0]["citation_rate"] is None


@pytest.mark.asyncio
async def test_sentiment_by_engine_clears_legacy_counts_when_analyzer_packages_missing(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    await _seed_admin_chain_tables(db_session)
    await _seed_chain_response(
        db_session,
        topic_id=6661,
        prompt_id=6662,
        query_id=6663,
        response_id=6664,
    )
    db_session.add(
        BrandMention(
            response_id=6664,
            brand_id=12,
            brand_name="Estee Lauder",
            mention_count=1,
            sentiment="positive",
            sentiment_score=0.8,
            created_at=DAY,
        )
    )
    await db_session.commit()

    chart = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/by-engine",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert chart.status_code == 200, chart.text
    body = chart.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "partial"
    assert body["items"] == []
    assert body["evidence_count"] == 1
    assert "response_analyses.raw_analysis_json.analyzer_fact_packages" in body["missing_inputs"]
    assert body["metric_formula_evidence"]["sentiment"]["formula_status"] in {
        "partial",
        "missing_required_inputs",
    }


@pytest.mark.asyncio
async def test_sentiment_by_engine_recovers_failed_legacy_query_before_contract_context(
    client,
    user: User,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await _project(db_session, user)
    await _seed_admin_chain_tables(db_session)
    await _seed_chain_response(
        db_session,
        topic_id=6681,
        prompt_id=6682,
        query_id=6683,
        response_id=6684,
    )
    packages = _base_packages(response_id=6684)
    packages["sentiment"].update(
        {
            "status": "partial",
            "formula_status": "partial",
            "reason_codes": ["missing_competitor_sentiment_evidence"],
            "driver_count": 1,
            "quote_count": 1,
        }
    )
    db_session.add_all(
        [
            ProjectCompetitor(project_id=project.id, brand_id=2),
            BrandMention(
                response_id=6684,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=1,
                sentiment="positive",
                sentiment_score=0.8,
                created_at=DAY,
            ),
            _analysis(6684, packages),
        ]
    )
    await db_session.commit()

    from app.api.v1.projects import _charts_service as charts_service

    async def no_response_window(
        *args: object,
        **kwargs: object,
    ) -> tuple[list[object], int, dict[str, int], list[str]]:
        return [], 0, {}, []

    async def admin_fact_rows(*args: object, **kwargs: object) -> list[dict[str, object]]:
        return [
            {
                "response_id": 6684,
                "target_llm": "chatgpt",
                "positive_mentions": 1,
                "neutral_mentions": 0,
                "negative_mentions": 0,
            }
        ]

    monkeypatch.setattr(
        charts_service,
        "_sentiment_by_engine_from_response_window",
        no_response_window,
    )
    monkeypatch.setattr(charts_service, "_admin_fact_rows", admin_fact_rows)

    original_execute = AsyncSession.execute
    original_rollback = AsyncSession.rollback
    poisoned_session_ids: set[int] = set()

    async def execute_with_poison(
        self: AsyncSession,
        statement: object,
        *args: object,
        **kwargs: object,
    ):
        statement_text = str(statement)
        if id(self) in poisoned_session_ids:
            raise RuntimeError("current transaction is aborted, commands ignored until end")
        if "COUNT(*)::int AS cnt" in statement_text and "JOIN llm_responses r" in statement_text:
            poisoned_session_ids.add(id(self))
            raise RuntimeError("simulated legacy sentiment by-engine query failure")
        return await original_execute(self, statement, *args, **kwargs)

    async def rollback_clears_poison(self: AsyncSession) -> None:
        poisoned_session_ids.discard(id(self))
        await original_rollback(self)

    monkeypatch.setattr(AsyncSession, "execute", execute_with_poison)
    monkeypatch.setattr(AsyncSession, "rollback", rollback_clears_poison)

    chart = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/by-engine",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert chart.status_code == 200, chart.text
    body = chart.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "partial"
    assert body["items"] == []
    assert body["evidence_count"] == 1
    assert body["selected_filters"]["competitor_brand_ids"] == [2]
    assert body["metric_formula_evidence"]["sentiment"]["formula_status"] == "partial"
    assert "missing_competitor_sentiment_evidence" in body["missing_inputs"]


@pytest.mark.asyncio
async def test_citation_composition_clears_legacy_segments_when_analyzer_packages_missing(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    await _seed_admin_chain_tables(db_session)
    await _seed_chain_response(
        db_session,
        topic_id=6671,
        prompt_id=6672,
        query_id=6673,
        response_id=6674,
    )
    mention = BrandMention(
        response_id=6674,
        brand_id=12,
        brand_name="Estee Lauder",
        mention_count=1,
        sentiment="positive",
        sentiment_score=0.8,
        created_at=DAY,
    )
    db_session.add(mention)
    await db_session.flush()
    db_session.add(
        CitationSource(
            response_id=6674,
            mention_id=mention.id,
            url="https://example.com/evidence",
            domain="example.com",
            title="Evidence",
            source_type="publisher",
            created_at=DAY,
        )
    )
    await db_session.commit()

    chart = await client.get(
        f"/api/v1/projects/{project.id}/citations/composition",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert chart.status_code == 200, chart.text
    body = chart.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "partial"
    assert body["segments"] == []
    assert body["total"] == 0
    assert body["evidence_count"] == 1
    assert "response_analyses.raw_analysis_json.analyzer_fact_packages" in body["missing_inputs"]
    assert body["metric_formula_evidence"]["citation"]["formula_status"] in {
        "partial",
        "missing_required_inputs",
    }


@pytest.mark.asyncio
async def test_sentiment_and_citation_charts_apply_analyzer_package_status(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    packages = _base_packages(response_id=6701)
    packages["sentiment"].update(
        {
            "status": "partial",
            "formula_status": "partial",
            "reason_codes": ["missing_sentiment_driver_quote"],
            "driver_count": 0,
            "quote_count": 0,
        }
    )
    packages["citations"].update(
        {
            "status": "partial",
            "formula_status": "partial",
            "citation_count": 2,
            "attributed_count": 1,
            "unresolved_count": 1,
            "reason_codes": ["unresolved_citation_attribution"],
        }
    )
    mention = BrandMention(
        response_id=6701,
        brand_id=12,
        brand_name="Estee Lauder",
        mention_count=1,
        sentiment="positive",
        sentiment_score=0.8,
        created_at=DAY,
    )
    db_session.add(mention)
    await db_session.flush()
    db_session.add_all(
        [
            GeoScoreDaily(
                brand_id=12,
                date=datetime.combine(DAY.date(), datetime.min.time()),
                target_llm="chatgpt",
                total_queries=10,
                mention_count=5,
                mention_rate=0.5,
                avg_sov=0.5,
                avg_position_rank=1.0,
                avg_sentiment_score=0.8,
                citation_rate=0.5,
                avg_visibility=0.7,
                avg_sentiment=0.8,
                avg_sov_score=0.5,
                avg_citation_score=0.5,
                avg_geo_score=0.8,
            ),
            CitationSource(
                response_id=6701,
                mention_id=mention.id,
                url="https://example.com/target",
                domain="example.com",
                title="Target evidence",
                source_type="publisher",
                created_at=DAY,
            ),
            CitationSource(
                response_id=6701,
                mention_id=None,
                url="https://unresolved.example/source",
                domain="unresolved.example",
                title="Unresolved evidence",
                source_type="social",
                created_at=DAY,
            ),
            _analysis(6701, packages),
        ]
    )
    await db_session.commit()

    sentiment = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/by-engine",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )
    authority = await client.get(
        f"/api/v1/projects/{project.id}/citations/authority-trend",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )
    composition = await client.get(
        f"/api/v1/projects/{project.id}/citations/composition",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert sentiment.status_code == 200, sentiment.text
    assert authority.status_code == 200, authority.text
    assert composition.status_code == 200, composition.text
    sentiment_body = sentiment.json()
    authority_body = authority.json()
    composition_body = composition.json()
    assert sentiment_body["state"] == "partial"
    assert sentiment_body["formula_status"] == "partial"
    assert "missing_sentiment_driver_quote" in sentiment_body["missing_inputs"]
    assert authority_body["state"] == "partial"
    assert authority_body["formula_status"] == "partial"
    assert "unresolved_citation_attribution" in authority_body["missing_inputs"]
    assert authority_body["points"] == []
    assert composition_body["state"] == "partial"
    assert composition_body["formula_status"] == "partial"
    assert composition_body["segments"] == []
    assert composition_body["total"] == 0
    assert composition_body["metric_formula_evidence"]["citation"]["unresolved_count"] == 1
