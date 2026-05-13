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
) -> None:
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
            "quality_flag_count": 0 if linked_citation else 1,
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
    if linked_citation:
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
    else:
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
