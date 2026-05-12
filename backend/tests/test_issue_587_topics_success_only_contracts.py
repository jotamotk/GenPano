"""Issue #587: successful-only Topics drilldown backend contracts."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    BrandMention,
    CitationSource,
    KgRelationCandidate,
    ProductFeatureMention,
    Project,
    ResponseAnalysis,
    SentimentDriver,
    User,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects import _topic_analysis_service as topic_service
from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


def test_latest_response_order_places_null_created_at_after_dated_rows() -> None:
    assert (
        topic_service._response_latest_order_sql({"id", "created_at"})
        == "r2.created_at IS NULL ASC, r2.created_at DESC, r2.id DESC"
    )
    assert topic_service._response_latest_order_sql({"id"}) == "r2.id DESC"


def test_response_preview_normalizes_truncates_and_handles_empty_text() -> None:
    assert topic_service._response_preview(None) is None
    assert topic_service._response_preview(" \n\t ") is None
    assert topic_service._response_preview(" alpha\n  beta\tgamma ", max_chars=12) == "alpha beta g"


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"issue587-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue 587 User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


async def _seed_success_only_workspace(
    db_session: AsyncSession,
    user: User,
) -> tuple[Project, dict[str, int | str]]:
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
        user_id=user.id,
        name="Issue 587 Topics",
        primary_brand_id=12,
        industry_id=7,
    )
    db_session.add(project)
    await db_session.flush()

    now = datetime.now()
    success_day = now - timedelta(days=20)
    latest_time = success_day.replace(hour=18, minute=30, second=0, microsecond=0)
    middle_time = success_day.replace(hour=12, minute=0, second=0, microsecond=0)
    older_time = success_day.replace(hour=9, minute=15, second=0, microsecond=0)
    recent_time = now - timedelta(days=1)

    await db_session.execute(
        text("INSERT INTO brands (id, name, industry) VALUES (12, 'Test Brand', 'Beauty')")
    )
    await db_session.execute(
        text(
            """
            INSERT INTO topics (id, brand_id, text, category, status, created_at)
            VALUES (58701, 12, 'Retinol proof', 'product', 'active', :created_at)
            """
        ),
        {"created_at": success_day},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts
                (id, topic_id, text, intent, prompt_scope, language, status, created_at)
            VALUES
                (58702, 58701, 'Which retinol serum has the best proof?',
                 'commercial', 'non_branded', 'en', 'active', :created_at)
            """
        ),
        {"created_at": success_day},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO queries
                (id, target_llm, status, query_text, brand_id, profile_id, prompt_id,
                 created_at, executed_at, finished_at, latency_ms)
            VALUES
                (587101, 'chatgpt', 'done', 'Which retinol serum has the best proof?',
                 12, 'MISSING-PROFILE', 58702, :older_time, :older_time, :older_time, 900),
                (587102, 'chatgpt', 'done', 'Which retinol serum has the best proof?',
                 12, 'MISSING-PROFILE', 58702, :latest_time, :latest_time, :latest_time, 700),
                (587106, 'doubao', 'done', 'Which retinol serum has the best proof?',
                 12, 'MISSING-PROFILE', 58702, :middle_time, :middle_time, :middle_time, 850),
                (587103, 'chatgpt', 'failed', 'Which retinol serum has the best proof?',
                 12, 'MISSING-PROFILE', 58702, :recent_time, :recent_time, :recent_time, 1200),
                (587104, 'chatgpt', 'pending', 'Which retinol serum has the best proof?',
                 12, 'MISSING-PROFILE', 58702, :recent_time, NULL, NULL, NULL),
                (587105, 'chatgpt', 'done', 'Which retinol serum has the best proof?',
                 12, 'MISSING-PROFILE', 58702, :recent_time, :recent_time, :recent_time, 650)
            """
        ),
        {
            "older_time": older_time,
            "middle_time": middle_time,
            "latest_time": latest_time,
            "recent_time": recent_time,
        },
    )
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, llm_version,
                 citations_json, created_at)
            VALUES
                (587201, 587101, 58702,
                 'Older complete answer mentioning Test Brand and Old Rival.',
                 'chatgpt', 'commercial', 'gpt-test', '[]', :older_time),
                (587202, 587102, 58702,
                 'Latest complete answer   mentioning Test Brand,
Rival Lab, and Retinol Pro.',
                 'chatgpt', 'commercial', 'gpt-test', '[]', :latest_time),
                (587203, 587106, 58702,
                 'Middle complete answer mentioning Test Brand from another engine.',
                 'doubao', 'commercial', 'doubao-test', '[]', :middle_time)
            """
        ),
        {
            "older_time": older_time,
            "latest_time": latest_time,
            "middle_time": middle_time,
        },
    )

    older_analysis = ResponseAnalysis(
        response_id=587201,
        target_brand_mentioned=True,
        target_brand_rank=2,
        target_brand_sentiment="neutral",
        sentiment_score=0.1,
        geo_score=0.55,
        raw_analysis_json={
            "relations": [
                {
                    "entity_kind": "brand",
                    "a_name": "Old Rival",
                    "b_name": "Archived Brand",
                    "type": "COMPETES_WITH",
                    "response_id": 587201,
                }
            ]
        },
        analyzed_at=older_time,
    )
    latest_analysis = ResponseAnalysis(
        response_id=587202,
        target_brand_mentioned=True,
        target_brand_rank=1,
        target_brand_sentiment="positive",
        visibility_score=0.9,
        sentiment_score=0.82,
        citation_score=1.0,
        geo_score=0.91,
        raw_analysis_json={
            "relations": [
                {
                    "entity_kind": "brand",
                    "a_name": "Test Brand",
                    "b_name": "Rival Lab",
                    "type": "COMPETES_WITH",
                    "confidence": 0.88,
                    "response_id": 587202,
                    "evidence": "same response relation",
                },
                {
                    "entity_kind": "brand",
                    "a_name": "Leaky Global Brand",
                    "b_name": "Unrelated Brand",
                    "type": "SAME_GROUP",
                    "response_id": 999999,
                    "evidence": "wrong response relation",
                },
            ]
        },
        analyzed_at=latest_time,
    )
    middle_analysis = ResponseAnalysis(
        response_id=587203,
        target_brand_mentioned=True,
        target_brand_rank=1,
        target_brand_sentiment="positive",
        sentiment_score=0.7,
        geo_score=0.8,
        raw_analysis_json={},
        analyzed_at=middle_time,
    )
    db_session.add_all([older_analysis, latest_analysis, middle_analysis])
    await db_session.flush()

    old_mention = BrandMention(
        response_id=587201,
        brand_id=12,
        brand_name="Test Brand",
        sentiment="neutral",
        sentiment_score=0.1,
        position_rank=2,
        context_snippet="older mention",
        created_at=older_time,
    )
    current_mention = BrandMention(
        response_id=587202,
        brand_id=12,
        brand_name="Test Brand",
        product_name="Retinol Pro",
        sentiment="positive",
        sentiment_score=0.82,
        position_rank=1,
        context_snippet="clinical proof",
        created_at=latest_time,
    )
    competitor_mention = BrandMention(
        response_id=587202,
        brand_id=77,
        brand_name="Rival Lab",
        product_name="Night Serum",
        sentiment="neutral",
        sentiment_score=0.0,
        position_rank=2,
        context_snippet="comparison",
        created_at=latest_time,
    )
    middle_mention = BrandMention(
        response_id=587203,
        brand_id=12,
        brand_name="Test Brand",
        sentiment="positive",
        sentiment_score=0.7,
        position_rank=1,
        context_snippet="another engine",
        created_at=middle_time,
    )
    db_session.add_all([old_mention, current_mention, competitor_mention, middle_mention])
    await db_session.flush()

    db_session.add_all(
        [
            CitationSource(
                response_id=587202,
                mention_id=current_mention.id,
                url="https://example.com/current-proof",
                domain="example.com",
                title="Current proof",
                citation_index=1,
                source_type="article",
                created_at=latest_time,
            ),
            CitationSource(
                response_id=587202,
                mention_id=competitor_mention.id,
                url="https://example.com/competitor-proof",
                domain="example.com",
                title="Competitor proof",
                citation_index=2,
                source_type="article",
                created_at=latest_time,
            ),
            ProductFeatureMention(
                analysis_id=latest_analysis.id,
                brand_name="Test Brand",
                product_name="Retinol Pro",
                feature_name="clinical proof",
                feature_sentiment="positive",
                context_snippet="clinical proof quote",
                scenario="anti-aging",
                price_positioning="premium",
                created_at=latest_time,
            ),
            SentimentDriver(
                mention_id=current_mention.id,
                response_id=587202,
                brand_name="Test Brand",
                driver_text="Clinical proof is cited",
                polarity="positive",
                category="proof",
                strength=0.9,
                source_quote="clinical proof",
                created_at=latest_time,
            ),
            SentimentDriver(
                mention_id=old_mention.id,
                response_id=587201,
                brand_name="Test Brand",
                driver_text="Old response driver",
                polarity="neutral",
                category="legacy",
                strength=0.4,
                source_quote="older mention",
                created_at=older_time,
            ),
            KgRelationCandidate(
                entity_kind="brand",
                a_id=12,
                b_id=77,
                type="COMPETES_WITH",
                confidence=0.77,
                evidence={"response_id": 587202, "quote": "Rival Lab comparison"},
                status="pending",
                llm_model="gpt-test",
                created_at=latest_time,
            ),
            KgRelationCandidate(
                entity_kind="brand",
                a_id=12,
                b_id=88,
                type="SAME_GROUP",
                confidence=0.66,
                evidence={"response_id": 999999, "quote": "wrong response"},
                status="pending",
                llm_model="gpt-test",
                created_at=latest_time,
            ),
        ]
    )
    await db_session.commit()

    return project, {
        "topic_id": 58701,
        "prompt_id": 58702,
        "older_query_id": 587101,
        "latest_query_id": 587102,
        "middle_query_id": 587106,
        "failed_query_id": 587103,
        "pending_query_id": 587104,
        "no_response_query_id": 587105,
        "latest_response_id": 587202,
        "latest_response_created_at": str(latest_time),
        "success_day": success_day.date().isoformat(),
    }


@pytest.mark.asyncio
async def test_monitoring_contract_is_success_only_and_window_honest(
    client,
    db_session: AsyncSession,
    user: User,
) -> None:
    project, ids = await _seed_success_only_workspace(db_session, user)
    headers = _bearer(user)
    now = datetime.now().date()

    empty_7d = await client.get(
        f"/api/v1/projects/{project.id}/topics/monitoring",
        headers=headers,
        params={
            "from": (now - timedelta(days=6)).isoformat(),
            "to": now.isoformat(),
        },
    )
    assert empty_7d.status_code == 200, empty_7d.text
    assert empty_7d.json()["state"] == "empty"
    assert empty_7d.json()["summary"]["query_count"] == 0
    assert empty_7d.json()["summary"]["response_count"] == 0

    populated_30d = await client.get(
        f"/api/v1/projects/{project.id}/topics/monitoring",
        headers=headers,
        params={
            "from": (now - timedelta(days=29)).isoformat(),
            "to": now.isoformat(),
        },
    )
    assert populated_30d.status_code == 200, populated_30d.text
    body = populated_30d.json()
    assert body["state"] == "ok"
    assert body["summary"]["topic_count"] == 1
    assert body["summary"]["prompt_count"] == 1
    assert body["summary"]["query_count"] == 3
    assert body["summary"]["response_count"] == 3
    assert body["summary"]["citation_count"] == 2

    topic = body["topics"][0]
    assert topic["topic_id"] == ids["topic_id"]
    assert topic["query_count"] == 3
    assert topic["response_count"] == 3
    assert topic["citation_count"] == 2
    assert topic["citation_rate"] == pytest.approx(1 / 3, rel=0.01)
    assert topic["visibility_rate"] == pytest.approx(1.0)
    assert topic["sentiment_distribution"] == {
        "positive": 2,
        "neutral": 1,
        "negative": 0,
    }


@pytest.mark.asyncio
async def test_prompt_and_query_contracts_use_daily_latest_and_attempts(
    client,
    db_session: AsyncSession,
    user: User,
) -> None:
    project, ids = await _seed_success_only_workspace(db_session, user)
    headers = _bearer(user)
    now = datetime.now().date()
    params = {
        "from": (now - timedelta(days=29)).isoformat(),
        "to": now.isoformat(),
    }

    prompts = await client.get(
        f"/api/v1/projects/{project.id}/topics/{ids['topic_id']}/prompts",
        headers=headers,
        params=params,
    )
    assert prompts.status_code == 200, prompts.text
    prompt = prompts.json()["items"][0]
    assert prompt["query_count"] == 3
    assert prompt["response_count"] == 3
    assert prompt["citation_count"] == 2
    assert prompt["citation_rate"] == pytest.approx(1 / 3, rel=0.01)
    assert prompt["visibility_rate"] == pytest.approx(1.0)
    assert prompt["sentiment_distribution"] == {
        "positive": 2,
        "neutral": 1,
        "negative": 0,
    }

    queries = await client.get(
        f"/api/v1/projects/{project.id}/prompts/{ids['prompt_id']}/queries",
        headers=headers,
        params=params,
    )
    assert queries.status_code == 200, queries.text
    query_body = queries.json()
    assert query_body["total"] == 1
    group = query_body["items"][0]
    assert group["query_id"] == ids["latest_query_id"]
    assert group["response_id"] == ids["latest_response_id"]
    assert group["status"] == "done"
    assert group["profile_name"] == "Unknown profile"
    assert group["citation_count"] == 2
    assert [row["query_id"] for row in group["daily_latest"]] == [ids["latest_query_id"]]
    assert group["daily_latest"][0]["date"] == ids["success_day"]
    assert (
        group["daily_latest"][0]["response_preview"]
        == "Latest complete answer mentioning Test Brand, Rival Lab, and Retinol Pro."
    )
    assert group["daily_latest"][0]["response_created_at"] == ids["latest_response_created_at"]
    assert group["daily_latest"][0]["citation_count"] == 2

    excluded_ids = {
        ids["failed_query_id"],
        ids["pending_query_id"],
        ids["no_response_query_id"],
    }
    assert excluded_ids.isdisjoint({row["query_id"] for row in group["daily_latest"]})

    detail = await client.get(
        f"/api/v1/projects/{project.id}/queries/{ids['latest_query_id']}/response",
        headers=headers,
    )
    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert detail_body["query"]["profile_name"] == "Unknown profile"
    assert detail_body["response"]["raw_text"].startswith("Latest complete answer")
    assert len(detail_body["citations"]) == group["daily_latest"][0]["citation_count"]
    assert [a["query_id"] for a in detail_body["attempts"]] == [
        ids["latest_query_id"],
        ids["middle_query_id"],
        ids["older_query_id"],
    ]
    assert all(a["response"]["raw_text"] for a in detail_body["attempts"])
    assert detail_body["attempts"][0]["profile_name"] == "Unknown profile"
    assert len(detail_body["attempts"][0]["citations"]) == 2


@pytest.mark.asyncio
async def test_query_activity_keeps_failed_pending_and_no_response_queries(
    client,
    db_session: AsyncSession,
    user: User,
) -> None:
    project, _ids = await _seed_success_only_workspace(db_session, user)

    activity = await client.get(
        f"/api/v1/projects/{project.id}/query-activity",
        headers=_bearer(user),
    )

    assert activity.status_code == 200, activity.text
    body = activity.json()
    assert body["totals"]["queries"] == 6
    assert body["totals"]["responses"] == 3
    assert body["by_status"]["done"] == 4
    assert body["by_status"]["failed"] == 1
    assert body["by_status"]["pending"] == 1


@pytest.mark.asyncio
async def test_response_detail_uses_daily_latest_response_id_with_backfilled_duplicates(
    client,
    db_session: AsyncSession,
    user: User,
) -> None:
    project, ids = await _seed_success_only_workspace(db_session, user)
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, llm_version,
                 citations_json, created_at)
            VALUES
                (587299, 587102, 58702,
                 'Backfilled stale duplicate answer with null timestamp.',
                 'chatgpt', 'commercial', 'gpt-test', '[]', NULL)
            """
        )
    )
    await db_session.commit()
    headers = _bearer(user)

    prompts = await client.get(
        f"/api/v1/projects/{project.id}/topics/{ids['topic_id']}/prompts",
        headers=headers,
    )
    assert prompts.status_code == 200, prompts.text
    prompt = prompts.json()["items"][0]
    assert prompt["query_count"] == 3
    assert prompt["success_rate"] == pytest.approx(1.0)

    queries = await client.get(
        f"/api/v1/projects/{project.id}/prompts/{ids['prompt_id']}/queries",
        headers=headers,
    )
    assert queries.status_code == 200, queries.text
    group = queries.json()["items"][0]
    assert sum(item["attempt_count"] for item in queries.json()["items"]) == prompt["query_count"]
    daily_latest = group["daily_latest"][0]
    assert daily_latest["response_id"] == ids["latest_response_id"]

    detail = await client.get(
        f"/api/v1/projects/{project.id}/queries/{ids['latest_query_id']}/response",
        headers=headers,
    )

    assert detail.status_code == 200, detail.text
    detail_body = detail.json()
    assert detail_body["response"]["response_id"] == daily_latest["response_id"]
    assert detail_body["response"]["raw_text"].startswith("Latest complete answer")
    assert len(detail_body["citations"]) == daily_latest["citation_count"] == 2


@pytest.mark.asyncio
async def test_response_detail_analyzer_facts_are_response_scoped(
    client,
    db_session: AsyncSession,
    user: User,
) -> None:
    project, ids = await _seed_success_only_workspace(db_session, user)

    detail = await client.get(
        f"/api/v1/projects/{project.id}/queries/{ids['latest_query_id']}/response",
        headers=_bearer(user),
    )

    assert detail.status_code == 200, detail.text
    facts = detail.json()["analyzer_facts"]
    assert [brand["brand_name"] for brand in facts["brands_mentioned"]] == [
        "Test Brand",
        "Rival Lab",
    ]
    assert [item["feature_name"] for item in facts["products_features_attributes"]] == [
        "clinical proof"
    ]
    assert [driver["driver_text"] for driver in facts["sentiment_drivers"]] == [
        "Clinical proof is cited"
    ]

    relation_labels = {
        (relation["source"], relation.get("a_name"), relation.get("b_name"), relation["type"])
        for relation in facts["relations"]
    }
    assert (
        "response_analyses.raw_analysis_json",
        "Test Brand",
        "Rival Lab",
        "COMPETES_WITH",
    ) in relation_labels
    assert ("kg_relation_candidates", None, None, "COMPETES_WITH") in relation_labels
    assert all("Leaky Global Brand" != relation.get("a_name") for relation in facts["relations"])
    assert all(relation.get("b_id") != 88 for relation in facts["relations"])
