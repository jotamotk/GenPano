"""App topic analytics over Admin Topic -> Prompt -> Query -> Response data."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    BrandMention,
    CitationSource,
    Project,
    ResponseAnalysis,
    Segment,
    Profile,
    User,
)
from sqlalchemy import text
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
        email=f"topic-{uuid.uuid4().hex[:6]}@example.com",
        name="Topic User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


async def _seed_admin_chain(db_session: AsyncSession, user: User) -> Project:
    """Create a small Admin-shaped chain in sqlite.

    The test DB only has upstream stubs for brands/prompts/llm_responses, so
    this fixture adds the legacy columns used by the production Admin tables.
    """

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

    now = datetime.now()
    db_session.add(
        Segment(
            id="SEG-A",
            brand_id="42",
            brand_name="Test Brand",
            name="Sensitive Skin",
            industry="Beauty",
            status="active",
            weight=1,
        )
    )
    db_session.add(
        Profile(
            id="PROF-A",
            segment_id="SEG-A",
            brand_id="42",
            brand_name="Test Brand",
            name="Shanghai buyer",
            demographic="25-34",
            need="repair",
            status="active",
            weight=1,
        )
    )
    project = Project(user_id=user.id, name="Admin Topic Chain", primary_brand_id=42, industry_id=1)
    db_session.add(project)
    await db_session.flush()

    await db_session.execute(
        text("INSERT INTO brands (id, name, industry) VALUES (42, 'Test Brand', 'Beauty')")
    )
    await db_session.execute(
        text(
            """
            INSERT INTO topics (id, brand_id, text, category, status, created_at)
            VALUES
              (101, 42, 'Barrier repair', 'product', 'active', :now),
              (102, 42, 'Vitamin C', 'product', 'active', :now)
            """
        ),
        {"now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts (id, topic_id, text, intent, language, status, created_at)
            VALUES
              (201, 101, 'Best barrier repair cream?', 'commercial', 'en', 'active', :now),
              (202, 101, 'How to repair sensitive skin?', 'informational', 'en', 'active', :now),
              (203, 102, 'Best vitamin c serum?', 'commercial', 'en', 'active', :now)
            """
        ),
        {"now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO queries
                (id, target_llm, status, query_text, brand_id, profile_id, prompt_id,
                 created_at, executed_at, finished_at, latency_ms)
            VALUES
                (301, 'chatgpt', 'done', 'Best barrier repair cream?', 42, 'PROF-A', 201,
                 :d1, :d1, :d1, 1200),
                (302, 'doubao', 'failed', 'Best barrier repair cream?', 42, 'PROF-A', 201,
                 :d2, :d2, :d2, 3000),
                (303, 'chatgpt', 'done', 'How to repair sensitive skin?', 42, 'PROF-A', 202,
                 :d3, :d3, :d3, 900)
            """
        ),
        {"d1": now - timedelta(days=1), "d2": now - timedelta(days=2), "d3": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, llm_version,
                 citations_json, created_at)
            VALUES
                (401, 301, 201, 'Test Brand is a strong barrier option.', 'chatgpt',
                 'commercial', 'gpt-test', '[]', :d1),
                (402, 303, 202, 'A gentle routine can mention Test Brand cautiously.',
                 'chatgpt', 'informational', 'gpt-test', '[]', :d3)
            """
        ),
        {"d1": now - timedelta(days=1), "d3": now},
    )
    db_session.add_all(
        [
            ResponseAnalysis(
                response_id=401,
                target_brand_mentioned=True,
                target_brand_rank=1,
                sentiment_score=0.8,
                geo_score=0.76,
            ),
            ResponseAnalysis(
                response_id=402,
                target_brand_mentioned=True,
                target_brand_rank=3,
                sentiment_score=-0.2,
                geo_score=0.55,
            ),
        ]
    )
    await db_session.flush()
    mention_positive = BrandMention(
        response_id=401,
        brand_id=42,
        brand_name="Test Brand",
        sentiment="positive",
        sentiment_score=0.8,
        position_rank=1,
        context_snippet="strong barrier option",
        created_at=now - timedelta(days=1),
    )
    mention_negative = BrandMention(
        response_id=402,
        brand_id=42,
        brand_name="Test Brand",
        sentiment="negative",
        sentiment_score=-0.2,
        position_rank=3,
        context_snippet="cautiously",
        created_at=now,
    )
    competitor_mention = BrandMention(
        response_id=401,
        brand_id=77,
        brand_name="Other Brand",
        sentiment="neutral",
        sentiment_score=0.0,
        position_rank=2,
        created_at=now - timedelta(days=1),
    )
    db_session.add_all([mention_positive, mention_negative, competitor_mention])
    await db_session.flush()
    db_session.add(
        CitationSource(
            response_id=401,
            mention_id=mention_positive.id,
            url="https://example.com/barrier",
            domain="example.com",
            source_type="article",
            created_at=now - timedelta(days=1),
        )
    )
    await db_session.commit()
    return project


@pytest.mark.asyncio
async def test_topic_monitoring_aggregates_admin_chain(client, db_session, user):
    project = await _seed_admin_chain(db_session, user)

    resp = await client.get(
        f"/api/v1/projects/{project.id}/topics/monitoring",
        headers=_bearer(user),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "ok"
    assert body["summary"]["topic_count"] == 2
    assert body["summary"]["prompt_count"] == 3
    assert body["summary"]["query_count"] == 3
    assert body["summary"]["response_count"] == 2
    barrier = next(row for row in body["topics"] if row["topic_id"] == 101)
    assert barrier["prompt_count"] == 2
    assert barrier["query_count"] == 3
    assert barrier["response_count"] == 2
    assert barrier["success_rate"] == pytest.approx(2 / 3, rel=0.01)
    assert barrier["engine_coverage"] == ["chatgpt", "doubao"]
    assert barrier["mention_rate"] == 1.0
    assert barrier["sov"] == pytest.approx(2 / 3, rel=0.01)
    assert barrier["sentiment_distribution"] == {"positive": 1, "neutral": 0, "negative": 1}
    assert barrier["citation_rate"] == pytest.approx(0.5, rel=0.01)
    assert {row["intent"] for row in body["intent_matrix"]} == {
        "commercial",
        "informational",
    }

    scoped = await client.get(
        f"/api/v1/projects/{project.id}/topics/monitoring?segment_id=SEG-A&profile_id=PROF-A",
        headers=_bearer(user),
    )
    assert scoped.status_code == 200, scoped.text
    assert scoped.json()["summary"]["query_count"] == 3

    empty = await client.get(
        f"/api/v1/projects/{project.id}/topics/monitoring?segment_id=SEG-MISSING",
        headers=_bearer(user),
    )
    assert empty.status_code == 200, empty.text
    assert empty.json()["state"] == "empty"
    assert empty.json()["summary"]["query_count"] == 0


@pytest.mark.asyncio
async def test_topic_prompt_query_response_drilldown(client, db_session, user):
    project = await _seed_admin_chain(db_session, user)
    headers = _bearer(user)

    prompts = await client.get(
        f"/api/v1/projects/{project.id}/topics/101/prompts",
        headers=headers,
    )
    assert prompts.status_code == 200, prompts.text
    prompt_body = prompts.json()
    assert prompt_body["total"] == 2
    assert prompt_body["items"][0]["query_count"] >= 1

    queries = await client.get(
        f"/api/v1/projects/{project.id}/prompts/201/queries",
        headers=headers,
    )
    assert queries.status_code == 200, queries.text
    query_body = queries.json()
    assert query_body["total"] == 2
    assert {row["status"] for row in query_body["items"]} == {"done", "failed"}
    done_query = next(row for row in query_body["items"] if row["status"] == "done")
    assert done_query["target_mentioned"] is True
    assert done_query["citation_count"] == 1

    response = await client.get(
        f"/api/v1/projects/{project.id}/queries/301/response",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["query"]["query_id"] == 301
    assert detail["response"]["raw_text"].startswith("Test Brand")
    assert detail["analysis"]["geo_score"] == pytest.approx(0.76)
    assert detail["brand_mentions"][0]["brand_name"] == "Test Brand"
    assert detail["citations"][0]["domain"] == "example.com"


@pytest.mark.asyncio
async def test_project_query_activity_is_project_scoped(client, db_session, user):
    project = await _seed_admin_chain(db_session, user)

    resp = await client.get(
        f"/api/v1/projects/{project.id}/query-activity",
        headers=_bearer(user),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["totals"]["queries"] == 3
    assert body["totals"]["responses"] == 2
    assert body["totals"]["analyzed"] == 2
    assert body["totals"]["mentions_target"] == 2
    assert body["by_status"]["done"] == 2
    assert body["by_status"]["failed"] == 1
    assert body["by_topic"][0]["topic_id"] == 101


@pytest.mark.asyncio
async def test_project_segments_exposes_admin_segments(client, db_session, user):
    project = await _seed_admin_chain(db_session, user)

    resp = await client.get(
        f"/api/v1/projects/{project.id}/segments",
        headers=_bearer(user),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "ok"
    assert body["items"][0]["segment_id"] == "SEG-A"
    assert body["items"][0]["active_profile_count"] == 1


@pytest.mark.asyncio
async def test_chart_metric_corrections_use_admin_topic_response_chain(client, db_session, user):
    project = await _seed_admin_chain(db_session, user)
    headers = _bearer(user)

    attribution = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/topic-attribution",
        headers=headers,
    )
    assert attribution.status_code == 200, attribution.text
    attr_body = attribution.json()
    barrier = next(row for row in attr_body["items"] if row["topic_id"] == 101)
    assert barrier["topic_name"] == "Barrier repair"
    assert barrier["negative_count"] == 1
    assert barrier["negative_ratio"] == pytest.approx(0.5)
    assert barrier["sample_snippet"] == "cautiously"

    gap = await client.get(
        f"/api/v1/projects/{project.id}/citations/content-gap",
        headers=headers,
    )
    assert gap.status_code == 200, gap.text
    gap_body = gap.json()
    barrier_gap = next(row for row in gap_body["topics"] if row["topic_id"] == 101)
    assert barrier_gap["mention_rate"] == 1.0
    assert barrier_gap["citation_rate"] == pytest.approx(0.5)
    assert barrier_gap["gap_score"] == pytest.approx(0.5)
    assert gap_body["page_type_distribution"][0]["page_type"] == "article"
