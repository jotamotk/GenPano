"""Issue #687: BestCoffer App analytics API state contract."""

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
    ProductScoreDaily,
    Project,
    ProjectTopicPin,
    ResponseAnalysis,
    TopicScoreDaily,
    User,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._analytics_contract import _as_v3_package
from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)

BESTCOFFER_BRAND_ID = 24
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
        email=f"issue687-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue 687 User",
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
    primary_brand_id: int | None,
) -> Project:
    p = Project(
        id=_new_id(),
        user_id=user.id,
        name=f"BestCoffer project {uuid.uuid4().hex[:6]}",
        primary_brand_id=primary_brand_id,
        industry_id=7,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p


async def _seed_admin_chain_tables(db_session: AsyncSession) -> None:
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


async def _seed_bestcoffer_response(db_session: AsyncSession) -> None:
    await db_session.execute(
        text(
            """
            INSERT INTO topics (id, brand_id, text, category, status, created_at)
            VALUES (68701, :brand_id, 'BestCoffer espresso workflow', 'product', 'active', :day)
            """
        ),
        {"brand_id": BESTCOFFER_BRAND_ID, "day": DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts
                (id, topic_id, text, intent, prompt_scope, language, status, created_at)
            VALUES (68702, 68701, 'BestCoffer commercial coffee machine options',
                    'commercial', 'non_branded', 'en', 'active', :day)
            """
        ),
        {"day": DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO queries
                (id, target_llm, status, query_text, brand_id, profile_id, prompt_id,
                 created_at, executed_at, finished_at, latency_ms)
            VALUES (68703, 'deepseek', 'done', 'BestCoffer cafe equipment comparison',
                    :brand_id, 'PROF-687', 68702, :day, :day, :day, 100)
            """
        ),
        {"brand_id": BESTCOFFER_BRAND_ID, "day": DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, llm_version,
                 citations_json, created_at)
            VALUES (68704, 68703, 68702, 'BestCoffer has collected response text.',
                    'deepseek', 'commercial', 'deepseek-v3', '[]', :day)
            """
        ),
        {"day": DAY},
    )
    await db_session.commit()


async def _seed_bestcoffer_response_two(db_session: AsyncSession) -> None:
    await db_session.execute(
        text(
            """
            INSERT INTO queries
                (id, target_llm, status, query_text, brand_id, profile_id, prompt_id,
                 created_at, executed_at, finished_at, latency_ms)
            VALUES (68705, 'deepseek', 'done', 'BestCoffer second comparison',
                    :brand_id, 'PROF-687', 68702, :day, :day, :day, 100)
            """
        ),
        {"brand_id": BESTCOFFER_BRAND_ID, "day": DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, llm_version,
                 citations_json, created_at)
            VALUES (68706, 68705, 68702, 'BestCoffer second collected response.',
                    'deepseek', 'commercial', 'deepseek-v3', '[]', :day)
            """
        ),
        {"day": DAY},
    )
    await db_session.commit()


async def _seed_unrelated_bestcoffer_facts(db_session: AsyncSession) -> None:
    await db_session.execute(
        text(
            """
            INSERT INTO topics (id, brand_id, text, category, status, created_at)
            VALUES (68711, :brand_id, 'BestCoffer unrelated project topic',
                    'product', 'active', :day)
            """
        ),
        {"brand_id": BESTCOFFER_BRAND_ID, "day": DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts
                (id, topic_id, text, intent, prompt_scope, language, status, created_at)
            VALUES (68712, 68711, 'BestCoffer unrelated project prompt',
                    'commercial', 'non_branded', 'en', 'active', :day)
            """
        ),
        {"day": DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO queries
                (id, target_llm, status, query_text, brand_id, profile_id, prompt_id,
                 created_at, executed_at, finished_at, latency_ms)
            VALUES (68713, 'deepseek', 'done', 'BestCoffer other project comparison',
                    :brand_id, 'PROF-OTHER-687', 68712, :day, :day, :day, 100)
            """
        ),
        {"brand_id": BESTCOFFER_BRAND_ID, "day": DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, llm_version,
                 citations_json, created_at)
            VALUES (68714, 68713, 68712, 'BestCoffer unrelated App facts exist.',
                    'deepseek', 'commercial', 'deepseek-v3', '[]', :day)
            """
        ),
        {"day": DAY},
    )
    mention = BrandMention(
        response_id=68714,
        brand_id=BESTCOFFER_BRAND_ID,
        brand_name="BestCoffer",
        mention_count=3,
        sentiment="positive",
        sentiment_score=0.8,
        created_at=DAY,
    )
    db_session.add(mention)
    await db_session.flush()
    db_session.add(
        CitationSource(
            response_id=68714,
            mention_id=mention.id,
            url="https://example.com/bestcoffer-other-project",
            domain="example.com",
            title="BestCoffer other project evidence",
            source_type="article",
            created_at=DAY,
        )
    )
    await db_session.commit()


def _bestcoffer_package(*, response_id: int, status: str = "ok") -> dict[str, Any]:
    analyzed_ids = [response_id] if status == "ok" else []
    return {
        "version": "issue_602_v1",
        "entities": {"target_brand_id": BESTCOFFER_BRAND_ID},
        "coverage": {
            "status": status,
            "formula_status": status,
            "eligible_response_ids": [response_id],
            "analyzed_response_ids": analyzed_ids,
            "failed_response_ids": [],
            "missing_analyzer_response_ids": [],
            "eligible_count": 1,
            "analyzed_count": len(analyzed_ids),
            "failed_count": 0,
            "missing_analyzer_count": 0,
            "reason_codes": [] if status == "ok" else ["partial_analyzer_coverage"],
            "chains": [{"response_id": response_id, "collected_at": DAY.isoformat()}],
        },
        "sov": {
            "status": "ok",
            "formula_status": "ok",
            "numerator_target_mentions": 3,
            "denominator_competitive_mentions": 5,
            "competitors": [{"brand_id": 12, "brand_name": "Estee Lauder"}],
            "reason_codes": [],
            "sample_response_ids": [response_id],
        },
        "sentiment": {
            "status": "partial",
            "formula_status": "partial",
            "score_count": 1,
            "label_count": 1,
            "driver_count": 0,
            "quote_count": 0,
            "reason_codes": ["missing_sentiment_driver_quote"],
            "sample_response_ids": [response_id],
        },
        "citations": {
            "status": "partial",
            "formula_status": "partial",
            "citation_count": 1,
            "attributed_count": 0,
            "unresolved_count": 1,
            "reason_codes": ["unresolved_citation_attribution"],
            "sample_response_ids": [response_id],
        },
        "pano_geo": {
            "status": "partial",
            "formula_status": "partial",
            "component_readiness": {
                "coverage": status,
                "sov": "ok",
                "sentiment": "partial",
                "citation": "partial",
            },
            "reason_codes": ["sentiment_partial", "citation_partial"],
        },
    }


def _bestcoffer_package_v3(*, response_id: int, status: str = "ok") -> dict[str, Any]:
    analyzed = status == "ok"
    return {
        "analyzer_version": "v3",
        "response_id": response_id,
        "query_id": 68703 if response_id == 68704 else response_id - 1,
        "prompt_id": 68702,
        "topic_id": 68701,
        "project_ids": [],
        "source_brand_id": BESTCOFFER_BRAND_ID,
        "target_brand_id": BESTCOFFER_BRAND_ID,
        "engine": "deepseek",
        "collected_at": DAY.isoformat(),
        "analysis_started_at": DAY.isoformat(),
        "analysis_completed_at": DAY.isoformat(),
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "prompt_version": "issue-711-test",
        "raw_output_sha256": "abc123",
        "idempotency_key": f"{response_id}:v3:abc123",
        "eligibility": {
            "eligible": True,
            "success_response": analyzed,
            "invalid_reason": None,
            "missing_reason_codes": [] if analyzed else ["missing_analyzer_rows"],
        },
        "coverage": {
            "eligible_response_count_basis": 1,
            "analyzed": analyzed,
            "parse_status": "ok",
            "validation_errors": [] if analyzed else ["missing_analyzer_rows"],
        },
        "entities": {
            "target": {
                "brand_id": BESTCOFFER_BRAND_ID,
                "canonical_name": "BestCoffer",
                "mentioned": True,
                "mention_count": 3,
                "position_rank": 1,
            },
            "configured_competitors": [
                {
                    "brand_id": 12,
                    "canonical_name": "Estee Lauder",
                    "mentioned": True,
                    "mention_count": 1,
                }
            ],
            "response_named_brands": [],
        },
        "visibility": {
            "is_visible": True,
            "rank": 1,
            "position_type": "ranked_list",
            "visibility_score": 1.0,
            "formula_status": "ok" if analyzed else "missing",
            "reason_codes": [] if analyzed else ["missing_analyzer_rows"],
        },
        "sov": {
            "numerator_target_mentions": 3,
            "denominator_competitive_mentions": 4,
            "denominator_brand_ids": [12],
            "denominator_raw_names": ["Estee Lauder"],
            "formula_status": status,
            "reason_codes": [] if analyzed else ["missing_analyzer_rows"],
            "sample_response_ids": [response_id],
        },
        "sentiment": {
            "label": "positive",
            "score": 0.8,
            "drivers": [
                {
                    "driver_text": "quiet grinder",
                    "polarity": "positive",
                    "source_quote": "BestCoffer is quiet",
                }
            ],
            "source_quotes": ["BestCoffer is quiet"],
            "formula_status": status,
            "reason_codes": [] if analyzed else ["missing_analyzer_rows"],
        },
        "citations": {
            "total_citations": 1,
            "attributed_citations": [
                {
                    "citation_id": 1,
                    "domain": "example.com",
                    "source_type": "publisher",
                    "tier": 2,
                }
            ],
            "unresolved_citations": [],
            "domains": ["example.com"],
            "source_types": ["publisher"],
            "formula_status": status,
            "reason_codes": [] if analyzed else ["missing_analyzer_rows"],
        },
        "rank": {
            "best_rank": 1,
            "rank_bucket": "top_3",
            "rank_basis": "position_rank",
            "formula_status": status,
            "reason_codes": [] if analyzed else ["missing_analyzer_rows"],
        },
        "topic": {
            "topic_id": 68701,
            "topic_name": "BestCoffer espresso workflow",
            "dimension": "product",
            "associated_brand_id": BESTCOFFER_BRAND_ID,
            "prompt_id": 68702,
            "query_id": 68703,
        },
        "products": [],
        "topic_metrics": {
            "visible": True,
            "visibility_rate_basis": 1,
            "sentiment_basis": 1,
            "citation_basis": 1,
            "rank_basis": 1,
            "formula_status": status,
            "reason_codes": [] if analyzed else ["missing_analyzer_rows"],
        },
        "geo_pano": {
            "visibility_component": status,
            "sentiment_component": status,
            "sov_component": status,
            "citation_component": status,
            "geo_score": None,
            "pano_score": None,
            "formula_status": status,
            "reason_codes": [] if analyzed else ["missing_analyzer_rows"],
        },
    }


def _analysis(response_id: int, package: dict[str, Any]) -> ResponseAnalysis:
    return ResponseAnalysis(
        response_id=response_id,
        target_brand_mentioned=True,
        target_brand_rank=1,
        target_brand_sentiment="positive",
        sentiment_score=0.8,
        geo_score=0.8,
        raw_analysis_json={"analyzer_fact_packages": package},
        created_at=DAY,
    )


def _analysis_v3(response_id: int, package: dict[str, Any]) -> ResponseAnalysis:
    return ResponseAnalysis(
        response_id=response_id,
        target_brand_mentioned=True,
        target_brand_rank=1,
        target_brand_sentiment="positive",
        sentiment_score=0.8,
        geo_score=0.8,
        raw_analysis_json={"analyzer_fact_package_v3": package},
        created_at=DAY,
    )


def _card_values(body: dict[str, Any]) -> list[float | None]:
    return [card["value"] for card in body["kpi_cards"]]


def _assert_selected_project_missing_contract(body: dict[str, Any]) -> None:
    assert body["brand_id"] == BESTCOFFER_BRAND_ID
    assert body["state"] == "partial"
    assert body["state_reason"] == "analysis_missing"
    assert body["formula_status"] == "missing_required_inputs"
    assert "analysis_missing" in body["missing_reasons"]
    assert "no_aggregate_rows" in body["missing_reasons"]
    assert body["evidence_counts"]["admin_fact_response_count"] == 1
    assert body["evidence_counts"]["response_analysis_count"] == 0
    assert body["evidence_counts"]["brand_mention_count"] == 1
    assert body["evidence_counts"]["citation_source_count"] == 1
    assert body["metric_formula_evidence"]["coverage"]["sample_response_ids"] == [68704]


def test_v3_package_preserves_zero_eligible_response_count_basis() -> None:
    package = _bestcoffer_package_v3(response_id=68704)
    package["coverage"]["eligible_response_count_basis"] = 0

    normalized = _as_v3_package({"analyzer_fact_package_v3": package})

    assert normalized is not None
    assert normalized["coverage"]["eligible_count"] == 0


@pytest.mark.asyncio
async def test_brand_override_on_unbound_project_returns_project_binding_state(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user, primary_brand_id=None)
    db_session.add(
        GeoScoreDaily(
            brand_id=BESTCOFFER_BRAND_ID,
            date=DAY,
            target_llm="deepseek",
            total_queries=10,
            mention_count=5,
            mention_rate=0.5,
            avg_sov=0.4,
            avg_position_rank=1.5,
            avg_sentiment=0.2,
            citation_rate=0.1,
            avg_geo_score=0.7,
        )
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project.id}/overview",
        headers=_bearer(user),
        params={"brand_id": BESTCOFFER_BRAND_ID},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["brand_id"] == BESTCOFFER_BRAND_ID
    assert body["state"] == "empty"
    assert body["state_reason"] == "missing_project_brand_binding"
    assert body["formula_status"] == "missing_required_inputs"
    assert body["project_scope"]["primary_brand_id"] is None
    assert body["project_scope"]["requested_brand_id"] == BESTCOFFER_BRAND_ID
    assert body["project_scope"]["missing_reason"] == "missing_project_brand_binding"
    assert "project_unbound" in body["missing_reasons"]
    assert "project.primary_brand_id" in body["missing_inputs"]
    assert "project_competitors.brand_id" in body["missing_inputs"]
    assert body["evidence_counts"]["geo_score_daily_rows"] == 1
    assert body["evidence_counts"]["competitor_brand_count"] == 0
    assert _card_values(body) == [None, None, None, None]
    assert body["geo_score_30d"] == []
    assert body["sov_30d"] == []
    assert body["sentiment_30d"] == []


@pytest.mark.asyncio
async def test_raw_responses_without_analyzer_or_aggregate_rows_report_missing_contract(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user, primary_brand_id=BESTCOFFER_BRAND_ID)
    await _seed_admin_chain_tables(db_session)
    await _seed_bestcoffer_response(db_session)

    resp = await client.get(
        f"/api/v1/projects/{project.id}/metrics",
        headers=_bearer(user),
        params={
            "brand_id": BESTCOFFER_BRAND_ID,
            "from": DAY.date().isoformat(),
            "to": DAY.date().isoformat(),
            "series": "mention_rate,sov,sentiment,citation",
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["brand_id"] == BESTCOFFER_BRAND_ID
    assert body["state"] == "partial"
    assert body["state_reason"] == "analysis_missing"
    assert body["formula_status"] == "missing_required_inputs"
    assert "analysis_missing" in body["missing_reasons"]
    assert "no_aggregate_rows" in body["missing_reasons"]
    assert "response_analyses" in body["missing_inputs"]
    assert "geo_score_daily" in body["missing_inputs"]
    assert body["evidence_counts"]["admin_fact_response_count"] == 1
    assert body["evidence_counts"]["response_analysis_count"] == 0
    assert body["evidence_counts"]["geo_score_daily_rows"] == 0
    assert body["metric_formula_evidence"]["coverage"]["formula_status"] == (
        "missing_required_inputs"
    )
    assert "analysis_missing" in body["metric_formula_evidence"]["coverage"]["reason_codes"]
    assert all(series["points"] == [] for series in body["series"])


@pytest.mark.asyncio
async def test_unrelated_brand_facts_do_not_hide_selected_project_missing_state(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user, primary_brand_id=BESTCOFFER_BRAND_ID)
    other_project = await _project(db_session, user, primary_brand_id=BESTCOFFER_BRAND_ID)
    await _seed_admin_chain_tables(db_session)
    await _seed_bestcoffer_response(db_session)
    await _seed_unrelated_bestcoffer_facts(db_session)
    db_session.add_all(
        [
            ProjectTopicPin(project_id=project.id, topic_id=68701, state="tracked"),
            ProjectTopicPin(project_id=other_project.id, topic_id=68711, state="tracked"),
        ]
    )
    await db_session.commit()

    params = {
        "brand_id": BESTCOFFER_BRAND_ID,
        "from": DAY.date().isoformat(),
        "to": DAY.date().isoformat(),
    }

    metrics = await client.get(
        f"/api/v1/projects/{project.id}/metrics",
        headers=_bearer(user),
        params={**params, "series": "mention_rate,sov,sentiment,citation"},
    )
    overview = await client.get(
        f"/api/v1/projects/{project.id}/overview",
        headers=_bearer(user),
        params=params,
    )

    assert metrics.status_code == 200, metrics.text
    assert overview.status_code == 200, overview.text
    _assert_selected_project_missing_contract(metrics.json())
    _assert_selected_project_missing_contract(overview.json())


@pytest.mark.asyncio
async def test_sentiment_and_citations_honor_requested_brand_override(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user, primary_brand_id=12)
    await _seed_admin_chain_tables(db_session)
    await _seed_bestcoffer_response(db_session)
    db_session.add(ProjectTopicPin(project_id=project.id, topic_id=68701, state="tracked"))
    mention = BrandMention(
        response_id=68704,
        brand_id=BESTCOFFER_BRAND_ID,
        brand_name="BestCoffer",
        mention_count=3,
        sentiment="positive",
        sentiment_score=0.8,
        created_at=DAY,
    )
    db_session.add(mention)
    await db_session.flush()
    db_session.add_all(
        [
            CitationSource(
                response_id=68704,
                mention_id=mention.id,
                url="https://example.com/bestcoffer-selected",
                domain="example.com",
                title="BestCoffer selected project evidence",
                source_type="article",
                created_at=DAY,
            ),
            _analysis_v3(68704, _bestcoffer_package_v3(response_id=68704)),
        ]
    )
    await db_session.commit()

    params = {
        "brand_id": BESTCOFFER_BRAND_ID,
        "from": DAY.date().isoformat(),
        "to": DAY.date().isoformat(),
    }
    sentiment = await client.get(
        f"/api/v1/projects/{project.id}/sentiment",
        headers=_bearer(user),
        params=params,
    )
    citations = await client.get(
        f"/api/v1/projects/{project.id}/citations",
        headers=_bearer(user),
        params=params,
    )
    composition = await client.get(
        f"/api/v1/projects/{project.id}/citations/composition",
        headers=_bearer(user),
        params=params,
    )
    detail = await client.get(
        f"/api/v1/projects/{project.id}/queries/68703/response",
        headers=_bearer(user),
        params={"brand_id": BESTCOFFER_BRAND_ID},
    )

    assert sentiment.status_code == 200, sentiment.text
    assert citations.status_code == 200, citations.text
    assert composition.status_code == 200, composition.text
    assert detail.status_code == 200, detail.text
    sentiment_body = sentiment.json()
    citations_body = citations.json()
    composition_body = composition.json()
    detail_body = detail.json()
    assert sentiment_body["brand_id"] == BESTCOFFER_BRAND_ID
    assert sentiment_body["selected_filters"]["brand_id"] == BESTCOFFER_BRAND_ID
    assert citations_body["brand_id"] == BESTCOFFER_BRAND_ID
    assert citations_body["selected_filters"]["brand_id"] == BESTCOFFER_BRAND_ID
    assert citations_body["total"] == 1
    assert citations_body["items"][0]["response_id"] == 68704
    assert composition_body["selected_filters"]["brand_id"] == BESTCOFFER_BRAND_ID
    assert composition_body["total"] == 1
    assert detail_body["selected_filters"]["brand_id"] == BESTCOFFER_BRAND_ID
    assert detail_body["selected_filters"]["query_id"] == 68703
    assert detail_body["formula_status"] in {"ok", "missing_required_inputs"}
    assert detail_body["metric_formula_evidence"]["pano_geo"]["formula_status"] == "ok"
    assert detail_body["analyzer_coverage"]["analyzer_package_count"] == 1


@pytest.mark.asyncio
async def test_pinned_topic_eligibility_honors_requested_brand_override(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user, primary_brand_id=12)
    await _seed_admin_chain_tables(db_session)
    db_session.add(ProjectTopicPin(project_id=project.id, topic_id=71201, state="tracked"))
    await db_session.execute(
        text(
            """
            INSERT INTO topics (id, brand_id, text, category, status, created_at)
            VALUES (71201, 12, 'Estee Lauder serum routine', 'brand', 'active', :day)
            """
        ),
        {"day": DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts
                (id, topic_id, text, intent, prompt_scope, language, status, created_at)
            VALUES (71202, 71201, 'Estee Lauder serum recommendations',
                    'commercial', 'non_branded', 'en', 'active', :day)
            """
        ),
        {"day": DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO queries
                (id, target_llm, status, query_text, brand_id, profile_id, prompt_id,
                 created_at, executed_at, finished_at, latency_ms)
            VALUES (71203, 'deepseek', 'done', 'Estee Lauder serum recommendations',
                    12, 'PROF-712', 71202, :day, :day, :day, 100)
            """
        ),
        {"day": DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, llm_version,
                 citations_json, created_at)
            VALUES (71204, 71203, 71202, 'Estee Lauder has collected response text.',
                    'deepseek', 'commercial', 'deepseek-v3', '[]', :day)
            """
        ),
        {"day": DAY},
    )
    package = _bestcoffer_package_v3(response_id=71204)
    package["source_brand_id"] = 12
    package["target_brand_id"] = 12
    package["entities"]["target"]["brand_id"] = 12
    package["entities"]["target"]["canonical_name"] = "Estee Lauder"
    db_session.add(_analysis_v3(71204, package))
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project.id}/metrics",
        headers=_bearer(user),
        params={
            "brand_id": BESTCOFFER_BRAND_ID,
            "from": DAY.date().isoformat(),
            "to": DAY.date().isoformat(),
            "series": "mention_rate,sov,sentiment,citation",
        },
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["selected_filters"]["brand_id"] == BESTCOFFER_BRAND_ID
    assert body["evidence_counts"]["admin_fact_response_count"] == 0
    assert body["evidence_counts"]["response_analysis_count"] == 0


@pytest.mark.asyncio
async def test_topic_and_position_endpoints_apply_requested_brand_scope_and_analyzer_gate(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user, primary_brand_id=12)
    await _seed_admin_chain_tables(db_session)
    await _seed_bestcoffer_response(db_session)
    await _seed_bestcoffer_response_two(db_session)
    db_session.add(ProjectTopicPin(project_id=project.id, topic_id=68701, state="tracked"))
    partial_package = _bestcoffer_package(response_id=68704)
    partial_package["coverage"].update(
        {
            "status": "partial",
            "formula_status": "partial",
            "eligible_response_ids": [68704, 68706],
            "analyzed_response_ids": [68704],
            "missing_analyzer_response_ids": [68706],
            "eligible_count": 2,
            "analyzed_count": 1,
            "missing_analyzer_count": 1,
            "reason_codes": ["missing_analyzer_rows"],
        }
    )
    db_session.add_all(
        [
            BrandMention(
                response_id=68704,
                brand_id=BESTCOFFER_BRAND_ID,
                brand_name="BestCoffer",
                mention_count=3,
                sentiment="negative",
                sentiment_score=0.2,
                position_rank=1,
                created_at=DAY,
            ),
            BrandMention(
                response_id=68706,
                brand_id=BESTCOFFER_BRAND_ID,
                brand_name="BestCoffer",
                mention_count=1,
                sentiment="positive",
                sentiment_score=0.7,
                position_rank=2,
                created_at=DAY,
            ),
            BrandMention(
                response_id=68704,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=99,
                sentiment="positive",
                sentiment_score=0.9,
                position_rank=8,
                created_at=DAY,
            ),
            TopicScoreDaily(
                brand_id=BESTCOFFER_BRAND_ID,
                topic_id=68701,
                date=DAY,
                mention_count=4,
                total_responses=2,
                mention_rate=1.0,
                avg_sentiment_score=0.45,
            ),
            TopicScoreDaily(
                brand_id=12,
                topic_id=68701,
                date=DAY,
                mention_count=99,
                total_responses=1,
                mention_rate=1.0,
                avg_sentiment_score=0.9,
            ),
            ProductScoreDaily(
                brand_id=BESTCOFFER_BRAND_ID,
                product_name="BestCoffer Pro",
                category="espresso",
                date=DAY,
                target_llm="deepseek",
                total_queries=2,
                mention_count=4,
                mention_rate=1.0,
                avg_position_rank=1.5,
                avg_geo_score=0.7,
                avg_sentiment_score=0.45,
                category_sov_pct=42.0,
                category_rank=1,
                win_rate=0.6,
            ),
            ProductScoreDaily(
                brand_id=12,
                product_name="Estee Serum",
                category="skincare",
                date=DAY,
                target_llm="deepseek",
                total_queries=1,
                mention_count=99,
                mention_rate=1.0,
                avg_position_rank=1.0,
                avg_geo_score=0.9,
                avg_sentiment_score=0.9,
                category_sov_pct=90.0,
                category_rank=1,
                win_rate=1.0,
            ),
            _analysis(68704, partial_package),
        ]
    )
    await db_session.commit()

    params = {
        "brand_id": BESTCOFFER_BRAND_ID,
        "from": DAY.date().isoformat(),
        "to": DAY.date().isoformat(),
    }
    monitoring = await client.get(
        f"/api/v1/projects/{project.id}/topics/monitoring",
        headers=_bearer(user),
        params=params,
    )
    position = await client.get(
        f"/api/v1/projects/{project.id}/position-distribution",
        headers=_bearer(user),
        params=params,
    )
    heatmap = await client.get(
        f"/api/v1/projects/{project.id}/topic-heatmap",
        headers=_bearer(user),
        params={**params, "metric": "sentiment"},
    )
    attribution = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/topic-attribution",
        headers=_bearer(user),
        params=params,
    )
    products = await client.get(
        f"/api/v1/projects/{project.id}/products",
        headers=_bearer(user),
        params=params,
    )
    engine_metrics = await client.get(
        f"/api/v1/projects/{project.id}/metrics/by-engine",
        headers=_bearer(user),
        params=params,
    )
    sentiment_by_engine = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/by-engine",
        headers=_bearer(user),
        params=params,
    )
    sentiment_trend = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/trend-by-engine",
        headers=_bearer(user),
        params=params,
    )

    for resp in (
        monitoring,
        position,
        heatmap,
        attribution,
        products,
        engine_metrics,
        sentiment_by_engine,
        sentiment_trend,
    ):
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["state"] == "partial"
        assert body["formula_status"] == "partial"
        assert body["selected_filters"]["brand_id"] == BESTCOFFER_BRAND_ID
        assert "missing_analyzer_rows" in body["missing_reasons"]

    heatmap_body = heatmap.json()
    assert heatmap_body["rows"][0]["brand_id"] == BESTCOFFER_BRAND_ID
    assert all(row["brand_id"] != 12 for row in heatmap_body["rows"])
    assert heatmap_body["metric_formula_evidence"]["sentiment"]["formula_status"] == "partial"
    products_body = products.json()
    assert [item["brand_id"] for item in products_body["items"]] == [BESTCOFFER_BRAND_ID]
    assert products_body["items"][0]["product_name"] == "BestCoffer Pro"
    assert all(item["brand_id"] != 12 for item in products_body["items"])
    assert all(item["mention_rate"] is None for item in engine_metrics.json()["items"])
    assert all(item["sentiment"] is None for item in engine_metrics.json()["items"])
    assert sentiment_by_engine.json()["items"] == []
    assert sentiment_trend.json()["items"] == []
    assert position.json()["total_mentions"] == 2
    assert attribution.json()["metric_formula_evidence"]["sentiment"]["formula_status"] == "partial"


@pytest.mark.asyncio
async def test_topic_heatmap_fact_fallback_uses_requested_brand_scope(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user, primary_brand_id=12)
    await _seed_admin_chain_tables(db_session)
    await _seed_bestcoffer_response(db_session)
    db_session.add(ProjectTopicPin(project_id=project.id, topic_id=68701, state="tracked"))
    db_session.add_all(
        [
            BrandMention(
                response_id=68704,
                brand_id=BESTCOFFER_BRAND_ID,
                brand_name="BestCoffer",
                mention_count=2,
                sentiment="positive",
                sentiment_score=0.8,
                position_rank=1,
                created_at=DAY,
            ),
            BrandMention(
                response_id=68704,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=99,
                sentiment="positive",
                sentiment_score=0.9,
                position_rank=1,
                created_at=DAY,
            ),
            _analysis_v3(68704, _bestcoffer_package_v3(response_id=68704)),
        ]
    )
    await db_session.commit()

    heatmap = await client.get(
        f"/api/v1/projects/{project.id}/topic-heatmap",
        headers=_bearer(user),
        params={
            "brand_id": BESTCOFFER_BRAND_ID,
            "from": DAY.date().isoformat(),
            "to": DAY.date().isoformat(),
        },
    )

    assert heatmap.status_code == 200, heatmap.text
    body = heatmap.json()
    assert body["selected_filters"]["brand_id"] == BESTCOFFER_BRAND_ID
    assert body["rows"][0]["brand_id"] == BESTCOFFER_BRAND_ID
    assert all(row["brand_id"] != 12 for row in body["rows"])
    assert body["metric_formula_evidence"]["pano_geo"]["formula_status"] == "ok"
