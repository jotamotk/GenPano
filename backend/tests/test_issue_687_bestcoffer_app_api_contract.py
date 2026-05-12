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
    Project,
    ProjectTopicPin,
    User,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
