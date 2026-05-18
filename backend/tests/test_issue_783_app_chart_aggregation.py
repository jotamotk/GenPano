"""Issue #783: App chart aggregation uses analyzer v4 metric-ready facts."""

from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from genpano_models import (
    AnalysisFactLink,
    AnalyzerQualityFlag,
    AnalyzerRun,
    BrandMention,
    CitationSource,
    GeoScoreDaily,
    Project,
    ProjectCompetitor,
    ResponseAnalysis,
    ResponseEntity,
    ResponseRelationFact,
    SentimentDriver,
    User,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects import _analytics_contract as analytics_contract
from app.api.v1.projects import _metrics_service as metrics_service
from app.api.v1.projects import _overview_service as overview_service
from app.api.v1.projects._metrics_dto import MetricSeries, MetricSeriesPoint
from app.api.v1.projects._overview_dto import KpiCard
from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)

DAY = datetime(2026, 5, 13, 9, 30, 0)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    item = User(
        id=_new_id(),
        email=f"issue783-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue 783 User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(item)
    await db_session.commit()
    return item


async def _project(db_session: AsyncSession, user: User) -> Project:
    project = Project(
        user_id=user.id,
        name=f"Issue 783 {uuid.uuid4().hex[:6]}",
        primary_brand_id=12,
        industry_id=7,
    )
    db_session.add(project)
    await db_session.flush()
    db_session.add(ProjectCompetitor(project_id=project.id, brand_id=99, pinned_by=user.id))
    await db_session.commit()
    return project


async def _seed_admin_chain_tables(db_session: AsyncSession) -> None:
    await db_session.execute(text("ALTER TABLE brands ADD COLUMN name TEXT"))
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
            VALUES (:topic_id, 12, 'Estee Lauder topic', 'product', 'active', :day)
            """
        ),
        {"topic_id": topic_id, "day": DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts
                (id, topic_id, text, intent, prompt_scope, language, status, created_at)
            VALUES (:prompt_id, :topic_id, 'Which serum is best?', 'commercial',
                    'non_branded', 'en', 'active', :day)
            """
        ),
        {"prompt_id": prompt_id, "topic_id": topic_id, "day": DAY},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO queries
                (id, target_llm, status, query_text, brand_id, profile_id, prompt_id,
                 created_at, executed_at, finished_at, latency_ms)
            VALUES (:query_id, 'chatgpt', 'done', 'Which serum is best?', 12,
                    'PROF-783', :prompt_id, :day, :day, :day, 100)
            """
        ),
        {"query_id": query_id, "prompt_id": prompt_id, "day": DAY},
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
            "raw_text": "Estee Lauder Advanced Night Repair beats Clinique for repair.",
            "day": DAY,
        },
    )


async def _seed_first_class_v4_facts(
    db_session: AsyncSession,
    *,
    response_id: int,
    linked_citation: bool,
    create_citation_source: bool = True,
    create_analysis_fact_links: bool | None = None,
    create_quality_flag: bool | None = None,
) -> None:
    has_fact_links = (
        linked_citation if create_analysis_fact_links is None else create_analysis_fact_links
    )
    has_quality_flag = not linked_citation if create_quality_flag is None else create_quality_flag
    db_session.add(
        ResponseAnalysis(
            response_id=response_id,
            target_brand_mentioned=True,
            target_brand_rank=1,
            target_brand_sentiment="positive",
            sentiment_score=0.7,
            geo_score=0.8,
            raw_analysis_json=None,
            created_at=DAY,
            analyzed_at=DAY,
        )
    )
    target = BrandMention(
        response_id=response_id,
        brand_id=12,
        brand_name="Estee Lauder",
        mention_count=1,
        position_rank=1,
        sentiment="positive",
        sentiment_score=0.7,
        context_snippet="Estee Lauder Advanced Night Repair beats Clinique.",
        created_at=DAY,
    )
    competitor = BrandMention(
        response_id=response_id,
        brand_id=99,
        brand_name="Clinique",
        mention_count=1,
        position_rank=2,
        sentiment="neutral",
        sentiment_score=0.1,
        context_snippet="Clinique is compared as the alternate serum.",
        created_at=DAY,
    )
    db_session.add_all([target, competitor])
    await db_session.flush()

    db_session.add(
        SentimentDriver(
            mention_id=target.id,
            response_id=response_id,
            brand_name="Estee Lauder",
            driver_text="repair benefit",
            polarity="positive",
            category="benefit",
            strength=0.8,
            source_quote="beats Clinique for repair",
            created_at=DAY,
        )
    )
    if create_citation_source:
        db_session.add(
            CitationSource(
                response_id=response_id,
                mention_id=target.id if linked_citation else None,
                url="https://example.com/serum",
                domain="example.com",
                title="Serum evidence",
                citation_index=1,
                source_type="official",
                created_at=DAY,
            )
        )

    run = AnalyzerRun(
        response_id=response_id,
        schema_version="analyzer_v4",
        status="done",
        trigger_source="test",
        validator_summary_json={
            "schema_version": "analyzer_v4",
            "validator_status": "passed",
            "errors": [],
            "quality_flag_count": 1 if has_quality_flag else 0,
        },
        started_at=DAY,
        completed_at=DAY,
    )
    db_session.add(run)
    await db_session.flush()
    db_session.add_all(
        [
            ResponseEntity(
                run_id=run.id,
                response_id=response_id,
                entity_key="ent_estee",
                entity_type="brand",
                raw_name="Estee Lauder",
                canonical_id="12",
                canonical_name="Estee Lauder",
                canonicalization_status="matched",
                evidence_quote="Estee Lauder Advanced Night Repair",
                confidence=0.98,
            ),
            ResponseEntity(
                run_id=run.id,
                response_id=response_id,
                entity_key="ent_clinique",
                entity_type="brand",
                raw_name="Clinique",
                canonical_id="99",
                canonical_name="Clinique",
                canonicalization_status="matched",
                evidence_quote="beats Clinique for repair",
                confidence=0.92,
            ),
            ResponseRelationFact(
                run_id=run.id,
                response_id=response_id,
                relation_key="relation_compare",
                subject_entity_key="ent_estee",
                relation_type="compared_with",
                object_entity_key="ent_clinique",
                direction="undirected",
                evidence_quote="beats Clinique for repair",
                confidence=0.88,
                status="current",
            ),
        ]
    )
    if has_fact_links:
        db_session.add_all(
            [
                AnalysisFactLink(
                    run_id=run.id,
                    response_id=response_id,
                    fact_type="citation",
                    fact_key="citation_official",
                    linked_fact_type="mention",
                    linked_fact_key="mention_estee",
                    link_type="supports",
                    evidence_quote="example.com supports the Estee Lauder claim",
                    source_path="citations.citation_official.linked_fact_keys",
                    status="current",
                ),
                AnalysisFactLink(
                    run_id=run.id,
                    response_id=response_id,
                    fact_type="citation",
                    fact_key="citation_official",
                    linked_fact_type="relation",
                    linked_fact_key="relation_compare",
                    link_type="supports",
                    evidence_quote="example.com supports the comparison",
                    source_path="citations.citation_official.linked_fact_keys",
                    status="current",
                ),
            ]
        )
    if has_quality_flag:
        db_session.add(
            AnalyzerQualityFlag(
                run_id=run.id,
                response_id=response_id,
                flag_key="flag_unresolved_citation",
                severity="warning",
                code="unresolved_citation_attribution",
                message="Citation was not linked to a target mention or relation fact.",
                target_type="citation",
                target_key="citation_official",
                blocks_metric_readiness=True,
                evidence_json={"url": "https://example.com/serum"},
            )
        )
    await db_session.commit()


async def _seed_issue_1152_engine_facts(
    db_session: AsyncSession,
    *,
    topic_id: int,
    prompt_id: int,
    query_id: int,
    response_id: int,
    engine: str = "chatgpt",
    target_mentions: int = 0,
    competitor_mentions: int = 0,
    target_citation: bool = False,
) -> None:
    await _seed_chain_response(
        db_session,
        topic_id=topic_id,
        prompt_id=prompt_id,
        query_id=query_id,
        response_id=response_id,
    )
    await db_session.execute(
        text(
            """
            UPDATE queries SET target_llm = :engine WHERE id = :query_id
            """
        ),
        {"engine": engine, "query_id": query_id},
    )
    await db_session.execute(
        text(
            """
            UPDATE llm_responses SET target_llm = :engine WHERE id = :response_id
            """
        ),
        {"engine": engine, "response_id": response_id},
    )
    db_session.add(
        ResponseAnalysis(
            response_id=response_id,
            target_brand_mentioned=target_mentions > 0,
            target_brand_rank=1 if target_mentions > 0 else None,
            target_brand_sentiment="positive" if target_mentions > 0 else None,
            sentiment_score=0.7 if target_mentions > 0 else None,
            geo_score=0.8,
            raw_analysis_json=None,
            created_at=DAY,
            analyzed_at=DAY,
        )
    )
    target: BrandMention | None = None
    mentions: list[BrandMention] = []
    if target_mentions > 0:
        target = BrandMention(
            response_id=response_id,
            brand_id=12,
            brand_name="Estee Lauder",
            mention_count=target_mentions,
            position_rank=1,
            sentiment="positive",
            sentiment_score=0.7,
            context_snippet="Estee Lauder was recommended.",
            created_at=DAY,
        )
        mentions.append(target)
    if competitor_mentions > 0:
        mentions.append(
            BrandMention(
                response_id=response_id,
                brand_id=99,
                brand_name="Clinique",
                mention_count=competitor_mentions,
                position_rank=2,
                sentiment="neutral",
                sentiment_score=0.1,
                context_snippet="Clinique was also discussed.",
                created_at=DAY,
            )
        )
    db_session.add_all(mentions)
    await db_session.flush()
    if target is not None:
        db_session.add(
            SentimentDriver(
                mention_id=target.id,
                response_id=response_id,
                brand_name="Estee Lauder",
                driver_text="recommended",
                polarity="positive",
                category="recommendation",
                strength=0.8,
                source_quote="Estee Lauder was recommended.",
                created_at=DAY,
            )
        )
    if target_citation and target is not None:
        db_session.add(
            CitationSource(
                response_id=response_id,
                mention_id=target.id,
                url=f"https://example.com/issue-1152/{response_id}",
                domain="example.com",
                title="Issue 1152 evidence",
                citation_index=1,
                source_type="official",
                created_at=DAY,
            )
        )

    run = AnalyzerRun(
        response_id=response_id,
        schema_version="analyzer_v4",
        status="done",
        trigger_source="test",
        validator_summary_json={
            "schema_version": "analyzer_v4",
            "validator_status": "passed",
            "errors": [],
            "quality_flag_count": 0,
        },
        started_at=DAY,
        completed_at=DAY,
    )
    db_session.add(run)
    await db_session.flush()
    entities: list[ResponseEntity] = []
    if target_mentions > 0:
        entities.append(
            ResponseEntity(
                run_id=run.id,
                response_id=response_id,
                entity_key="ent_estee",
                entity_type="brand",
                raw_name="Estee Lauder",
                canonical_id="12",
                canonical_name="Estee Lauder",
                canonicalization_status="matched",
                evidence_quote="Estee Lauder was recommended.",
                confidence=0.98,
            )
        )
    if competitor_mentions > 0:
        entities.append(
            ResponseEntity(
                run_id=run.id,
                response_id=response_id,
                entity_key="ent_clinique",
                entity_type="brand",
                raw_name="Clinique",
                canonical_id="99",
                canonical_name="Clinique",
                canonicalization_status="matched",
                evidence_quote="Clinique was also discussed.",
                confidence=0.92,
            )
        )
    db_session.add_all(entities)
    if target_mentions > 0 and competitor_mentions > 0:
        db_session.add(
            ResponseRelationFact(
                run_id=run.id,
                response_id=response_id,
                relation_key="relation_compare",
                subject_entity_key="ent_estee",
                relation_type="compared_with",
                object_entity_key="ent_clinique",
                direction="undirected",
                evidence_quote="Estee Lauder and Clinique were compared.",
                confidence=0.88,
                status="current",
            )
        )
    if target_citation and target is not None:
        db_session.add(
            AnalysisFactLink(
                run_id=run.id,
                response_id=response_id,
                fact_type="citation",
                fact_key="citation_issue_1152",
                linked_fact_type="mention",
                linked_fact_key="mention_estee",
                link_type="supports",
                evidence_quote="Citation supports the Estee Lauder mention.",
                source_path="citations.citation_issue_1152.linked_fact_keys",
                status="current",
            )
        )
    await db_session.commit()


def _seed_issue_1152_geo_daily(
    db_session: AsyncSession,
    *,
    mention_rate: float,
    sov: float,
    citation_rate: float,
) -> None:
    db_session.add(
        GeoScoreDaily(
            brand_id=12,
            date=DAY,
            target_llm="chatgpt",
            total_queries=99,
            mention_count=99,
            mention_rate=mention_rate,
            avg_sov=sov,
            avg_position_rank=1.0,
            avg_sentiment_score=0.2,
            citation_rate=citation_rate,
            avg_visibility=mention_rate,
            avg_sentiment=0.2,
            avg_sov_score=sov,
            avg_citation_score=citation_rate,
            avg_geo_score=0.9,
        )
    )


@pytest.mark.asyncio
async def test_engine_metrics_prefers_fact_backed_visibility_over_stale_daily_rollup(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    await _seed_admin_chain_tables(db_session)
    await _seed_issue_1152_engine_facts(
        db_session,
        topic_id=115201,
        prompt_id=115202,
        query_id=115203,
        response_id=115204,
        target_mentions=1,
        competitor_mentions=2,
        target_citation=True,
    )
    await _seed_issue_1152_engine_facts(
        db_session,
        topic_id=115211,
        prompt_id=115212,
        query_id=115213,
        response_id=115214,
        target_mentions=0,
        competitor_mentions=1,
    )
    _seed_issue_1152_geo_daily(
        db_session,
        mention_rate=0.99,
        sov=0.99,
        citation_rate=0.99,
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/projects/{project.id}/metrics/by-engine",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "ok"
    assert body["formula_status"] == "ok"
    assert body["source_provenance"]
    assert "admin_facts" in body["source_provenance"]
    assert body["evidence_counts"]["admin_fact_response_count"] == 2
    assert body["metric_formula_evidence"]["coverage"]["formula_status"] == "ok"
    assert body["metric_formula_evidence"]["sov"]["formula_status"] == "ok"
    assert body["metric_formula_evidence"]["sov"]["denominator_count"] == 4
    assert len(body["items"]) == 1
    row = body["items"][0]
    assert row["engine"] == "chatgpt"
    assert row["mention_rate"] == 0.5
    assert row["sov"] == 0.25
    assert row["citation_rate"] == 1.0


@pytest.mark.asyncio
async def test_engine_metrics_marks_target_only_sov_partial_and_keeps_mention_rate_fact_backed(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    await _seed_admin_chain_tables(db_session)
    await _seed_issue_1152_engine_facts(
        db_session,
        topic_id=115221,
        prompt_id=115222,
        query_id=115223,
        response_id=115224,
        target_mentions=2,
        competitor_mentions=0,
        target_citation=True,
    )
    _seed_issue_1152_geo_daily(
        db_session,
        mention_rate=0.11,
        sov=1.0,
        citation_rate=0.77,
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/projects/{project.id}/metrics/by-engine",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "partial"
    assert body["state_reason"] == "partial_analyzer_data"
    assert body["formula_status"] == "partial"
    assert "target_only_sov" in body["missing_inputs"]
    assert "brand_mentions.competitive_set" in body["missing_inputs"]
    assert body["metric_formula_evidence"]["coverage"]["formula_status"] == "ok"
    sov_evidence = body["metric_formula_evidence"]["sov"]
    assert sov_evidence["formula_status"] == "missing_required_inputs"
    assert sov_evidence["numerator_count"] == 2
    assert sov_evidence["denominator_count"] == 2
    assert "target_only_sov" in sov_evidence["reason_codes"]
    assert "brand_mentions.competitive_set" in sov_evidence["reason_codes"]
    assert body["items"] == [
        {
            "engine": "chatgpt",
            "mention_rate": 1.0,
            "sov": None,
            "citation_rate": 1.0,
            "sentiment": 0.7,
        }
    ]


@pytest.mark.asyncio
async def test_engine_metrics_marks_mixed_engine_target_only_sov_row_partial(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    await _seed_admin_chain_tables(db_session)
    await _seed_issue_1152_engine_facts(
        db_session,
        topic_id=115231,
        prompt_id=115232,
        query_id=115233,
        response_id=115234,
        engine="chatgpt",
        target_mentions=2,
        competitor_mentions=0,
        target_citation=True,
    )
    await _seed_issue_1152_engine_facts(
        db_session,
        topic_id=115241,
        prompt_id=115242,
        query_id=115243,
        response_id=115244,
        engine="doubao",
        target_mentions=0,
        competitor_mentions=3,
    )
    _seed_issue_1152_geo_daily(
        db_session,
        mention_rate=0.33,
        sov=1.0,
        citation_rate=0.88,
    )
    await db_session.commit()

    response = await client.get(
        f"/api/v1/projects/{project.id}/metrics/by-engine",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "partial"
    assert body["state_reason"] == "partial_analyzer_data"
    assert body["formula_status"] == "partial"
    assert "target_only_sov" in body["missing_inputs"]
    assert "brand_mentions.competitive_set" in body["missing_inputs"]
    assert body["evidence_counts"]["admin_fact_response_count"] == 2
    assert body["evidence_counts"]["engine_target_only_sov_count"] == 1
    sov_evidence = body["metric_formula_evidence"]["sov"]
    assert sov_evidence["formula_status"] == "partial"
    assert "target_only_sov" in sov_evidence["reason_codes"]
    assert "brand_mentions.competitive_set" in sov_evidence["reason_codes"]

    rows = {row["engine"]: row for row in body["items"]}
    assert rows["chatgpt"]["mention_rate"] == 1.0
    assert rows["chatgpt"]["sov"] is None
    assert rows["doubao"]["mention_rate"] == 0.0
    assert rows["doubao"]["sov"] == 0.0


@pytest.mark.asyncio
async def test_engine_metrics_empty_response_keeps_explicit_contract_metadata(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)

    response = await client.get(
        f"/api/v1/projects/{project.id}/metrics/by-engine",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "empty"
    assert body["state_reason"] == "no_metric_data"
    assert body["formula_status"] == "no_evidence"
    assert body["items"] == []
    assert isinstance(body["evidence_counts"], dict)
    assert body["selected_filters"]["date_range"] == {
        "from": DAY.date().isoformat(),
        "to": DAY.date().isoformat(),
    }
    assert body["source_provenance"]


@pytest.mark.asyncio
async def test_topics_monitoring_keeps_formula_status_from_first_class_v4_evidence(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    await _seed_admin_chain_tables(db_session)
    await _seed_chain_response(
        db_session,
        topic_id=78361,
        prompt_id=78362,
        query_id=78363,
        response_id=78364,
    )
    await _seed_first_class_v4_facts(db_session, response_id=78364, linked_citation=True)

    response = await client.get(
        f"/api/v1/projects/{project.id}/topics/monitoring",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "ok"
    assert body["summary"]["response_count"] == 1
    assert body["formula_status"] == "ok"
    assert body["evidence_count"] == 1
    assert body["evidence_counts"]["admin_fact_response_count"] == 1
    assert body["evidence_counts"]["analyzer_run_count"] == 1
    assert body["evidence_counts"]["analyzer_entity_count"] == 2
    assert "analyzer_runs" in body["source_provenance"]


@pytest.mark.asyncio
async def test_topics_monitoring_normalizes_ok_state_partial_formula_without_missing_inputs(
    client,
    user: User,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = await _project(db_session, user)
    await _seed_admin_chain_tables(db_session)
    await _seed_chain_response(
        db_session,
        topic_id=78371,
        prompt_id=78372,
        query_id=78373,
        response_id=78374,
    )
    await _seed_first_class_v4_facts(db_session, response_id=78374, linked_citation=True)

    async def _partial_contract_without_missing_inputs(*args, **kwargs):
        return analytics_contract.AnalyticsContractContext(
            project_scope=analytics_contract.ProjectScope(
                project_id=project.id,
                primary_brand_id=project.primary_brand_id,
                requested_brand_id=project.primary_brand_id,
                competitor_brand_ids=[99],
            ),
            state="ok",
            state_reason="data_available",
            missing_inputs=[],
            missing_sources=[],
            missing_reasons=[],
            evidence_counts={
                "admin_fact_response_count": 1,
                "analyzer_run_count": 1,
                "analyzer_entity_count": 2,
            },
            formula_status="partial",
            formula_diagnostics=analytics_contract.formula_diagnostics_for("partial"),
            metric_formula_evidence={
                "coverage": {
                    "formula_status": "partial",
                    "reason_codes": [],
                    "source_tables": ["analyzer_runs"],
                }
            },
            selected_filters=kwargs.get("selected_filters") or {},
            source_provenance=["admin_facts", "analyzer_runs"],
        )

    monkeypatch.setattr(
        analytics_contract,
        "build_contract_context",
        _partial_contract_without_missing_inputs,
    )

    response = await client.get(
        f"/api/v1/projects/{project.id}/topics/monitoring",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "ok"
    assert body["state_reason"] == "data_available"
    assert body["evidence_count"] == 1
    assert body["missing_inputs"] == []
    assert body["missing_sources"] == []
    assert body["formula_status"] == "ok"
    assert body["formula_diagnostics"]["status"] == "ok"


@pytest.mark.asyncio
async def test_engine_metrics_use_first_class_v4_facts_without_raw_json_package(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    await _seed_admin_chain_tables(db_session)
    await _seed_chain_response(
        db_session,
        topic_id=78301,
        prompt_id=78302,
        query_id=78303,
        response_id=78304,
    )
    await _seed_first_class_v4_facts(db_session, response_id=78304, linked_citation=True)

    response = await client.get(
        f"/api/v1/projects/{project.id}/metrics/by-engine",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["formula_status"] == "ok"
    assert body["missing_inputs"] == []
    assert "analyzer_runs" in body["source_provenance"]
    assert "analysis_fact_links" in body["source_provenance"]
    assert (
        "response_analyses.raw_analysis_json.analyzer_fact_packages"
        not in (body["source_provenance"])
    )
    assert body["metric_formula_evidence"]["coverage"]["source_tables"] == ["analyzer_runs"]
    assert body["metric_formula_evidence"]["citation"]["source_tables"] == [
        "citation_sources",
        "analysis_fact_links",
    ]
    assert body["evidence_counts"]["analyzer_run_count"] == 1
    assert body["evidence_counts"]["analyzer_relation_fact_count"] == 1
    assert body["evidence_counts"]["analyzer_attributed_citation_count"] == 1
    assert body["items"] == [
        {
            "engine": "chatgpt",
            "mention_rate": 1.0,
            "sov": 0.5,
            "citation_rate": 1.0,
            "sentiment": 0.7,
        }
    ]


def test_sov_series_with_points_and_no_missing_inputs_keeps_ok_status() -> None:
    context = analytics_contract.AnalyticsContractContext(
        project_scope=analytics_contract.ProjectScope(
            project_id="project-898",
            primary_brand_id=12,
            requested_brand_id=12,
            competitor_brand_ids=[99],
        ),
        state="ok",
        state_reason="data_available",
        missing_inputs=[],
        missing_sources=[],
        missing_reasons=[],
        evidence_counts={
            "competitive_mention_count": 4,
            "admin_fact_response_count": 4,
        },
        formula_status="missing_required_inputs",
        formula_diagnostics=analytics_contract.formula_diagnostics_for("missing_required_inputs"),
        metric_formula_evidence={
            "sov": {
                "formula_status": "missing_required_inputs",
                "reason_codes": [],
                "numerator_count": 2,
                "denominator_count": 4,
                "source_tables": ["brand_mentions"],
            }
        },
        source_provenance=["admin_facts"],
    )
    series = [
        MetricSeries(
            metric="sov",
            points=[MetricSeriesPoint(date=DAY.date(), value=0.5)],
            formula_status="ok",
            missing_inputs=[],
            state="ok",
            evidence_count=1,
        )
    ]

    [sov_series] = metrics_service._apply_metric_series_contract(
        series,
        context,
        evidence_source="admin_facts",
    )

    assert sov_series.state == "ok"
    assert sov_series.points
    assert sov_series.missing_inputs == []
    assert sov_series.formula_status == "ok"


def test_sov_kpi_with_value_and_no_missing_inputs_keeps_ok_status() -> None:
    context = analytics_contract.AnalyticsContractContext(
        project_scope=analytics_contract.ProjectScope(
            project_id="project-898",
            primary_brand_id=12,
            requested_brand_id=12,
            competitor_brand_ids=[99],
        ),
        state="ok",
        state_reason="data_available",
        missing_inputs=[],
        missing_sources=[],
        missing_reasons=[],
        evidence_counts={
            "competitive_mention_count": 4,
            "admin_fact_response_count": 4,
            "analyzer_sov_numerator_target_mentions": 2,
            "analyzer_sov_denominator_competitive_mentions": 4,
            "analyzer_sov_competitor_count": 1,
        },
        formula_status="missing_required_inputs",
        formula_diagnostics=analytics_contract.formula_diagnostics_for("missing_required_inputs"),
        metric_formula_evidence={
            "sov": {
                "formula_status": "missing_required_inputs",
                "reason_codes": [],
                "numerator_count": 2,
                "denominator_count": 4,
                "competitor_count": 1,
                "source_tables": ["brand_mentions"],
            }
        },
        source_provenance=["admin_facts"],
    )
    cards = [
        KpiCard(
            label="Share of Voice",
            label_en="Share of Voice",
            label_zh="声量份额",
            metric_key="sov",
            value=43.3,
            formula_status="ok",
        )
    ]

    [sov_card] = overview_service._apply_kpi_contract(
        cards,
        context,
        evidence_source="admin_facts",
    )

    assert sov_card.value == pytest.approx(43.3)
    assert sov_card.formula_status == "ok"


@pytest.mark.asyncio
async def test_engine_metrics_keep_missing_v4_citation_sources_partial_and_null(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    await _seed_admin_chain_tables(db_session)
    await _seed_chain_response(
        db_session,
        topic_id=78321,
        prompt_id=78322,
        query_id=78323,
        response_id=78324,
    )
    await _seed_first_class_v4_facts(
        db_session,
        response_id=78324,
        linked_citation=False,
        create_citation_source=False,
    )

    response = await client.get(
        f"/api/v1/projects/{project.id}/metrics/by-engine",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "partial"
    assert "citation_sources" in body["missing_inputs"]
    assert body["metric_formula_evidence"]["citation"]["formula_status"] == (
        "missing_required_inputs"
    )
    assert body["metric_formula_evidence"]["citation"]["source_tables"] == [
        "citation_sources",
        "analysis_fact_links",
    ]
    assert body["evidence_counts"]["analyzer_citation_count"] == 0
    assert body["evidence_counts"]["analyzer_attributed_citation_count"] == 0
    assert body["items"] == [
        {
            "engine": "chatgpt",
            "mention_rate": 1.0,
            "sov": 0.5,
            "citation_rate": None,
            "sentiment": 0.7,
        }
    ]


@pytest.mark.asyncio
async def test_engine_metrics_keep_unlinked_v4_citations_partial_and_null(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    await _seed_admin_chain_tables(db_session)
    await _seed_chain_response(
        db_session,
        topic_id=78311,
        prompt_id=78312,
        query_id=78313,
        response_id=78314,
    )
    await _seed_first_class_v4_facts(db_session, response_id=78314, linked_citation=False)

    response = await client.get(
        f"/api/v1/projects/{project.id}/metrics/by-engine",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "partial"
    assert "unresolved_citation_attribution" in body["missing_inputs"]
    assert body["metric_formula_evidence"]["coverage"]["formula_status"] == "ok"
    assert body["metric_formula_evidence"]["sov"]["formula_status"] == "ok"
    assert body["metric_formula_evidence"]["sentiment"]["formula_status"] == "ok"
    assert body["metric_formula_evidence"]["citation"]["formula_status"] == (
        "missing_required_inputs"
    )
    assert body["evidence_counts"]["analyzer_unresolved_citation_count"] == 1
    assert body["items"] == [
        {
            "engine": "chatgpt",
            "mention_rate": 1.0,
            "sov": 0.5,
            "citation_rate": None,
            "sentiment": 0.7,
        }
    ]


@pytest.mark.asyncio
async def test_engine_metrics_keep_fact_linked_null_mention_citations_partial_and_null(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    project = await _project(db_session, user)
    await _seed_admin_chain_tables(db_session)
    await _seed_chain_response(
        db_session,
        topic_id=78331,
        prompt_id=78332,
        query_id=78333,
        response_id=78334,
    )
    await _seed_first_class_v4_facts(
        db_session,
        response_id=78334,
        linked_citation=False,
        create_analysis_fact_links=True,
        create_quality_flag=False,
    )

    response = await client.get(
        f"/api/v1/projects/{project.id}/metrics/by-engine",
        headers=_bearer(user),
        params={"from": DAY.date().isoformat(), "to": DAY.date().isoformat()},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "partial"
    assert "citation_sources.mention_id" in body["missing_inputs"]
    assert "unresolved_citation_attribution" in body["missing_inputs"]
    assert "analysis_fact_links" in body["source_provenance"]
    assert body["metric_formula_evidence"]["coverage"]["formula_status"] == "ok"
    assert body["metric_formula_evidence"]["sov"]["formula_status"] == "ok"
    assert body["metric_formula_evidence"]["sentiment"]["formula_status"] == "ok"
    citation_evidence = body["metric_formula_evidence"]["citation"]
    assert citation_evidence["formula_status"] == "missing_required_inputs"
    assert citation_evidence["citation_count"] == 1
    assert citation_evidence["attributed_count"] == 0
    assert citation_evidence["fact_link_count"] == 2
    assert "citation_sources.mention_id" in citation_evidence["reason_codes"]
    assert body["evidence_counts"]["analyzer_citation_count"] == 1
    assert body["evidence_counts"]["analyzer_attributed_citation_count"] == 0
    assert body["evidence_counts"]["analyzer_fact_link_count"] == 2
    assert body["items"] == [
        {
            "engine": "chatgpt",
            "mention_rate": 1.0,
            "sov": 0.5,
            "citation_rate": None,
            "sentiment": 0.7,
        }
    ]
