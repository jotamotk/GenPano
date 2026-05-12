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
    Profile,
    Project,
    ResponseAnalysis,
    Segment,
    User,
)
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._topic_analysis_service import _not_deleted_condition
from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def test_not_deleted_condition_is_postgres_boolean_safe():
    condition = _not_deleted_condition("s")

    assert "s.is_deleted = 0" not in condition
    assert "LOWER(CAST(s.is_deleted AS TEXT))" in condition
    assert "'false'" in condition


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
              (102, 42, 'Vitamin C', 'product', 'active', :now),
              (901, 900, 'Foreign brand topic', 'brand', 'active', :now)
            """
        ),
        {"now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts
                (id, topic_id, text, intent, prompt_scope, language, status, created_at)
            VALUES
              (201, 101, 'Best barrier repair cream?', 'commercial',
               'non_branded', 'en', 'active', :now),
              (202, 101, 'How does Test Brand repair sensitive skin?',
               'informational', 'branded', 'en', 'active', :now),
              (203, 102, 'Best vitamin c serum?', 'commercial',
               'non_branded', 'en', 'active', :now),
              (901, 901, 'Foreign brand prompt?', 'commercial',
               'non_branded', 'en', 'active', :now)
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
                 :d3, :d3, :d3, 900),
                (304, 'deepseek', 'done', 'Best barrier repair cream for redness?',
                 42, 'PROF-A', 201,
                 :d1, :d1, :d1, 700),
                (901, 'chatgpt', 'done', 'Foreign brand query?', 900, 'PROF-A', 901,
                 :d1, :d1, :d1, 700)
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
                 'chatgpt', 'informational', 'gpt-test', '[]', :d3),
                (403, 304, 201, 'Other Brand and Null Rival are often suggested first.',
                 'deepseek', 'commercial', 'gpt-test', '[]', :d1),
                (901, 901, 901, 'Foreign Brand should not leak into project metrics.',
                 'chatgpt', 'commercial', 'gpt-test', '[]', :d1)
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
            ResponseAnalysis(
                response_id=403,
                target_brand_mentioned=False,
                target_brand_rank=None,
                sentiment_score=0.1,
                geo_score=0.35,
            ),
            ResponseAnalysis(
                response_id=901,
                target_brand_mentioned=True,
                target_brand_rank=1,
                sentiment_score=0.9,
                geo_score=0.9,
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
    null_brand_competitor = BrandMention(
        response_id=403,
        brand_id=None,
        brand_name="Null Rival",
        sentiment="neutral",
        sentiment_score=0.1,
        position_rank=1,
        created_at=now - timedelta(days=1),
    )
    foreign_brand_mention = BrandMention(
        response_id=901,
        brand_id=900,
        brand_name="Foreign Brand",
        sentiment="positive",
        sentiment_score=0.9,
        position_rank=1,
        created_at=now - timedelta(days=1),
    )
    db_session.add_all(
        [
            mention_positive,
            mention_negative,
            competitor_mention,
            null_brand_competitor,
            foreign_brand_mention,
        ]
    )
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
async def test_overview_sov_includes_competitor_only_admin_fact_denominator(
    client,
    db_session,
    user,
):
    project = await _seed_admin_chain(db_session, user)

    resp = await client.get(
        f"/api/v1/projects/{project.id}/overview",
        headers=_bearer(user),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    sov_card = next(card for card in body["kpi_cards"] if card["metric_key"] == "sov")
    assert sov_card["value"] == pytest.approx(50.0)


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
    assert body["summary"]["topic_count"] == 1
    assert body["summary"]["prompt_count"] == 2
    assert body["summary"]["query_count"] == 3
    assert body["summary"]["response_count"] == 3
    barrier = next(row for row in body["topics"] if row["topic_id"] == 101)
    assert barrier["prompt_count"] == 2
    assert barrier["query_count"] == 3
    assert barrier["response_count"] == 3
    assert barrier["success_rate"] == pytest.approx(1.0, rel=0.01)
    assert barrier["engine_coverage"] == ["chatgpt", "deepseek"]
    assert barrier["mention_rate"] == pytest.approx(1 / 2, rel=0.01)
    assert barrier["visibility_rate"] == pytest.approx(1 / 2, rel=0.01)
    assert barrier["sov"] == pytest.approx(2 / 4, rel=0.01)
    assert barrier["sentiment_distribution"] == {"positive": 1, "neutral": 0, "negative": 1}
    assert barrier["citation_count"] == 1
    assert barrier["citation_rate"] == pytest.approx(1 / 3, rel=0.01)
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

    prompt_scope = await client.get(
        f"/api/v1/projects/{project.id}/topics/monitoring?prompt_scope=branded",
        headers=_bearer(user),
    )
    assert prompt_scope.status_code == 200, prompt_scope.text
    scoped_body = prompt_scope.json()
    assert scoped_body["summary"]["query_count"] == 1
    assert scoped_body["topics"][0]["mention_rate"] is None


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
    assert {row["status"] for row in query_body["items"]} == {"done"}
    done_query = next(row for row in query_body["items"] if row["query_id"] == 301)
    assert done_query["target_mentioned"] is True
    assert done_query["citation_count"] == 1
    assert done_query["daily_latest"][0]["query_id"] == 301

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
async def test_topic_monitoring_uses_project_primary_text_match_when_fact_brand_fk_is_wrong(
    client, db_session, user
):
    project = await _seed_admin_chain(db_session, user)
    now = datetime.now()
    await db_session.execute(
        text(
            """
            INSERT INTO brands (id, name, industry) VALUES
              (2, 'Wrong Owner', 'Beauty'),
              (12, 'Estee Lauder', 'Beauty')
            """
        )
    )
    project.primary_brand_id = 12
    await db_session.execute(
        text(
            """
            INSERT INTO topics (id, brand_id, text, category, status, created_at)
            VALUES (1401, 2, 'Misfiled beauty topic', 'brand', 'active', :now)
            """
        ),
        {"now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts
                (id, topic_id, text, intent, prompt_scope, language, status, created_at)
            VALUES
              (1402, 1401, 'Is Estee Lauder Advanced Night Repair good for anti-aging?',
               'commercial', 'non_branded', 'en', 'active', :now)
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
              (1403, 'chatgpt', 'done',
               'Is Estee Lauder Advanced Night Repair good for anti-aging?',
               2, 'PROF-A', 1402, :now, :now, :now, 800)
            """
        ),
        {"now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, llm_version,
                 citations_json, created_at)
            VALUES
              (1404, 1403, 1402,
               'Estee Lauder Advanced Night Repair is often recommended for anti-aging routines.',
               'chatgpt', 'commercial', 'gpt-test', '[]', :now)
            """
        ),
        {"now": now},
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project.id}/topics/monitoring",
        headers=_bearer(user),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "ok"
    assert body["summary"]["topic_count"] == 1
    assert body["summary"]["prompt_count"] == 1
    assert body["summary"]["query_count"] == 1
    assert body["summary"]["response_count"] == 1
    assert body["topics"][0]["topic_id"] == 1401
    assert body["topics"][0]["associated_brand"] == "Estee Lauder"

    prompts = await client.get(
        f"/api/v1/projects/{project.id}/topics/1401/prompts",
        headers=_bearer(user),
    )
    assert prompts.status_code == 200, prompts.text
    assert prompts.json()["total"] == 1

    queries = await client.get(
        f"/api/v1/projects/{project.id}/prompts/1402/queries",
        headers=_bearer(user),
    )
    assert queries.status_code == 200, queries.text
    assert queries.json()["total"] == 1

    response = await client.get(
        f"/api/v1/projects/{project.id}/queries/1403/response",
        headers=_bearer(user),
    )
    assert response.status_code == 200, response.text
    assert response.json()["response"]["raw_text"].startswith("Estee Lauder")


@pytest.mark.asyncio
async def test_topic_monitoring_brand_id_override_reads_selected_brand_chain(
    client, db_session, user
):
    project = await _seed_admin_chain(db_session, user)
    now = datetime.now()
    await db_session.execute(
        text("INSERT INTO brands (id, name, industry) VALUES (12, 'Estee Lauder', 'Beauty')")
    )
    await db_session.execute(
        text(
            """
            INSERT INTO topics (id, brand_id, text, category, status, created_at)
            VALUES (2401, 12, 'Estee Lauder anti-aging', 'brand', 'active', :now)
            """
        ),
        {"now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts
                (id, topic_id, text, intent, prompt_scope, language, status, created_at)
            VALUES
              (2402, 2401, 'Is Estee Lauder Advanced Night Repair worth it?',
               'commercial', 'non_branded', 'en', 'active', :now)
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
              (2403, 'chatgpt', 'done',
               'Is Estee Lauder Advanced Night Repair worth it?',
               12, 'PROF-A', 2402, :now, :now, :now, 700)
            """
        ),
        {"now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, llm_version,
                 citations_json, created_at)
            VALUES
              (2404, 2403, 2402,
               'Estee Lauder Advanced Night Repair is frequently recommended.',
               'chatgpt', 'commercial', 'gpt-test', '[]', :now)
            """
        ),
        {"now": now},
    )
    db_session.add(
        BrandMention(
            response_id=2404,
            brand_id=12,
            brand_name="Estee Lauder",
            sentiment="positive",
            sentiment_score=0.7,
            position_rank=1,
            created_at=now,
        )
    )
    db_session.add(
        ResponseAnalysis(
            response_id=2404,
            target_brand_mentioned=True,
            target_brand_rank=1,
            sentiment_score=0.7,
            geo_score=0.8,
        )
    )
    await db_session.commit()

    monitoring = await client.get(
        f"/api/v1/projects/{project.id}/topics/monitoring?brand_id=12",
        headers=_bearer(user),
    )

    assert monitoring.status_code == 200, monitoring.text
    body = monitoring.json()
    assert body["brand_id"] == 12
    assert body["summary"]["topic_count"] == 1
    assert body["summary"]["prompt_count"] == 1
    assert body["summary"]["query_count"] == 1
    assert body["summary"]["response_count"] == 1
    assert [row["topic_id"] for row in body["topics"]] == [2401]
    assert body["topics"][0]["associated_brand"] == "Estee Lauder"

    prompts = await client.get(
        f"/api/v1/projects/{project.id}/topics/2401/prompts?brand_id=12",
        headers=_bearer(user),
    )
    assert prompts.status_code == 200, prompts.text
    assert prompts.json()["total"] == 1

    queries = await client.get(
        f"/api/v1/projects/{project.id}/prompts/2402/queries?brand_id=12",
        headers=_bearer(user),
    )
    assert queries.status_code == 200, queries.text
    assert queries.json()["total"] == 1

    response = await client.get(
        f"/api/v1/projects/{project.id}/queries/2403/response?brand_id=12",
        headers=_bearer(user),
    )
    assert response.status_code == 200, response.text
    assert response.json()["response"]["raw_text"].startswith("Estee Lauder")

    activity = await client.get(
        f"/api/v1/projects/{project.id}/query-activity?brand_id=12",
        headers=_bearer(user),
    )
    assert activity.status_code == 200, activity.text
    assert activity.json()["brand_id"] == 12
    assert activity.json()["totals"]["queries"] == 1


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
    assert body["totals"]["responses"] == 3
    assert body["totals"]["analyzed"] == 3
    assert body["totals"]["mentions_target"] == 1
    assert body["totals"]["mention_denominator"] == 2
    assert body["by_status"]["done"] == 3
    assert "failed" not in body["by_status"]
    assert body["by_topic"][0]["topic_id"] == 101
    assert body["by_topic"][0]["mention_rate"] == pytest.approx(1 / 2, rel=0.01)


@pytest.mark.asyncio
async def test_project_metrics_use_filtered_admin_fact_set(client, db_session, user):
    project = await _seed_admin_chain(db_session, user)

    resp = await client.get(
        f"/api/v1/projects/{project.id}/metrics"
        "?series=mention_rate,sov"
        "&prompt_scope=non_branded"
        "&engine=chatgpt,deepseek",
        headers=_bearer(user),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "partial"
    assert body["formula_status"] in {"missing_required_inputs", "formula_pending_upstream"}
    by_metric = {series["metric"]: series["points"] for series in body["series"]}
    assert len(by_metric["mention_rate"]) == 1
    assert by_metric["mention_rate"][0]["value"] == pytest.approx(1 / 2, rel=0.01)
    assert len(by_metric["sov"]) == 1
    assert by_metric["sov"][0]["value"] == pytest.approx(1 / 3, rel=0.01)

    filtered = await client.get(
        f"/api/v1/projects/{project.id}/metrics"
        "?series=mention_rate,sov"
        "&prompt_scope=non_branded"
        "&engine=deepseek",
        headers=_bearer(user),
    )
    assert filtered.status_code == 200, filtered.text
    filtered_body = filtered.json()
    filtered_metric = {series["metric"]: series["points"] for series in filtered_body["series"]}
    assert filtered_metric["mention_rate"][0]["value"] == 0
    assert filtered_metric["sov"][0]["value"] == 0


@pytest.mark.asyncio
async def test_brand_override_uses_admin_fact_text_when_query_brand_fk_is_wrong(
    client, db_session, user
):
    project = await _seed_admin_chain(db_session, user)
    now = datetime.now()
    await db_session.execute(
        text(
            """
            INSERT INTO brands (id, name, industry) VALUES
              (2, '理肤泉', 'Beauty'),
              (12, '雅诗兰黛', 'Beauty')
            """
        )
    )
    await db_session.execute(
        text(
            """
            INSERT INTO topics (id, brand_id, text, category, status, created_at)
            VALUES (1201, 2, '理肤泉竞品分析', 'brand', 'active', :now)
            """
        ),
        {"now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts
                (id, topic_id, text, intent, prompt_scope, language, status, created_at)
            VALUES
              (1202, 1201, '雅诗兰黛小棕瓶适合哪些抗老需求?',
               'commercial', 'non_branded', 'zh', 'active', :now)
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
              (1203, 'chatgpt', 'done', '雅诗兰黛小棕瓶适合哪些抗老需求?',
               2, 'PROF-A', 1202, :now, :now, :now, 800)
            """
        ),
        {"now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, llm_version,
                 citations_json, created_at)
            VALUES
              (1204, 1203, 1202,
               '雅诗兰黛小棕瓶通常会被推荐给关注抗老、修护和稳定肤况的人群。',
               'chatgpt', 'commercial', 'gpt-test', '[]', :now)
            """
        ),
        {"now": now},
    )
    db_session.add(
        ResponseAnalysis(
            response_id=1204,
            target_brand_mentioned=True,
            target_brand_rank=1,
            sentiment_score=0.88,
            geo_score=0.82,
        )
    )
    await db_session.commit()

    metrics_resp = await client.get(
        f"/api/v1/projects/{project.id}/metrics",
        headers=_bearer(user),
        params={
            "brand_id": 12,
            "series": "mention_rate,sov,rank,sentiment",
            "prompt_scope": "non_branded",
        },
    )
    assert metrics_resp.status_code == 200, metrics_resp.text
    metrics_body = metrics_resp.json()
    assert metrics_body["brand_id"] == 12
    assert metrics_body["state"] == "partial"
    assert metrics_body["formula_status"] in {
        "missing_required_inputs",
        "formula_pending_upstream",
    }
    by_metric = {series["metric"]: series["points"] for series in metrics_body["series"]}
    assert by_metric["mention_rate"][0]["value"] == pytest.approx(0.0)
    assert by_metric["sov"] == []
    assert by_metric["rank"][0]["value"] == pytest.approx(1.0)
    assert by_metric["sentiment"][0]["value"] == pytest.approx(0.88)

    overview_resp = await client.get(
        f"/api/v1/projects/{project.id}/overview",
        headers=_bearer(user),
        params={"brand_id": 12},
    )
    assert overview_resp.status_code == 200, overview_resp.text
    overview_body = overview_resp.json()
    assert overview_body["brand_name"] == "雅诗兰黛"
    assert overview_body["state"] == "partial"
    assert overview_body["formula_status"] in {
        "missing_required_inputs",
        "formula_pending_upstream",
    }
    assert overview_body["geo_score_30d"]
    assert any(card["value"] > 0 for card in overview_body["kpi_cards"])

    competitors_resp = await client.get(
        f"/api/v1/projects/{project.id}/competitors/metrics",
        headers=_bearer(user),
        params={"brand_id": 12, "prompt_scope": "non_branded"},
    )
    assert competitors_resp.status_code == 200, competitors_resp.text
    competitors_body = competitors_resp.json()
    assert competitors_body["primary"]["brand_id"] == 12
    assert competitors_body["primary"]["brand_name"] == "雅诗兰黛"
    assert competitors_body["primary"]["avg_geo_score"] > 0
    assert competitors_body["competitors"] == []

    trends_resp = await client.get(
        f"/api/v1/projects/{project.id}/competitors/trends",
        headers=_bearer(user),
        params={"brand_id": 12, "metric": "geo_score"},
    )
    assert trends_resp.status_code == 200, trends_resp.text
    trends_body = trends_resp.json()
    primary_series = next(series for series in trends_body["series"] if series["is_primary"])
    assert primary_series["brand_id"] == 12
    assert primary_series["brand_name"] == "雅诗兰黛"
    assert primary_series["points"]


@pytest.mark.asyncio
async def test_brand_override_counts_text_matched_facts_without_analysis_or_mentions(
    client, db_session, user
):
    project = await _seed_admin_chain(db_session, user)
    now = datetime.now()
    await db_session.execute(
        text(
            """
            INSERT INTO brands (id, name, industry) VALUES
              (2, 'Wrong Owner', 'Beauty'),
              (12, 'Estee Lauder', 'Beauty')
            """
        )
    )
    await db_session.execute(
        text(
            """
            INSERT INTO topics (id, brand_id, text, category, status, created_at)
            VALUES (1301, 2, 'Misfiled beauty topic', 'brand', 'active', :now)
            """
        ),
        {"now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts
                (id, topic_id, text, intent, prompt_scope, language, status, created_at)
            VALUES
              (1302, 1301, 'Is Estee Lauder Advanced Night Repair good for anti-aging?',
               'commercial', 'non_branded', 'en', 'active', :now)
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
              (1303, 'chatgpt', 'done',
               'Is Estee Lauder Advanced Night Repair good for anti-aging?',
               2, 'PROF-A', 1302, :now, :now, :now, 800)
            """
        ),
        {"now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, llm_version,
                 citations_json, created_at)
            VALUES
              (1304, 1303, 1302,
               'Estee Lauder Advanced Night Repair is often recommended for anti-aging routines.',
               'chatgpt', 'commercial', 'gpt-test', '[]', :now)
            """
        ),
        {"now": now},
    )
    await db_session.commit()

    metrics_resp = await client.get(
        f"/api/v1/projects/{project.id}/metrics",
        headers=_bearer(user),
        params={
            "brand_id": 12,
            "series": "mention_rate,sov",
            "prompt_scope": "non_branded",
        },
    )
    assert metrics_resp.status_code == 200, metrics_resp.text
    metrics_body = metrics_resp.json()
    assert metrics_body["brand_id"] == 12
    assert metrics_body["state"] == "partial"
    assert metrics_body["formula_status"] in {
        "missing_required_inputs",
        "formula_pending_upstream",
    }
    by_metric = {series["metric"]: series["points"] for series in metrics_body["series"]}
    assert by_metric["mention_rate"][0]["value"] == pytest.approx(0.0)
    assert by_metric["sov"] == []

    overview_resp = await client.get(
        f"/api/v1/projects/{project.id}/overview",
        headers=_bearer(user),
        params={"brand_id": 12},
    )
    assert overview_resp.status_code == 200, overview_resp.text
    overview_body = overview_resp.json()
    assert overview_body["state"] == "partial"
    assert overview_body["formula_status"] in {
        "missing_required_inputs",
        "formula_pending_upstream",
    }
    assert overview_body["brand_name"] == "Estee Lauder"
    assert overview_body["geo_score_30d"] == []
    assert not any((card["value"] or 0) > 0 for card in overview_body["kpi_cards"])
    assert not any(row["mention_count"] > 0 for row in overview_body["top_prompts"])

    competitors_resp = await client.get(
        f"/api/v1/projects/{project.id}/competitors/metrics",
        headers=_bearer(user),
        params={"brand_id": 12, "prompt_scope": "non_branded"},
    )
    assert competitors_resp.status_code == 200, competitors_resp.text
    competitors_body = competitors_resp.json()
    assert competitors_body["primary"]["brand_id"] == 12
    assert competitors_body["primary"]["avg_mention_rate"] == pytest.approx(0.0)
    assert competitors_body["primary"]["avg_sov"] is None
    assert competitors_body["primary"]["avg_geo_score"] is None

    trends_resp = await client.get(
        f"/api/v1/projects/{project.id}/competitors/trends",
        headers=_bearer(user),
        params={"brand_id": 12, "metric": "geo_score"},
    )
    assert trends_resp.status_code == 200, trends_resp.text
    trends_body = trends_resp.json()
    primary_series = next(series for series in trends_body["series"] if series["is_primary"])
    assert primary_series["brand_id"] == 12
    assert primary_series["points"] == []


@pytest.mark.asyncio
async def test_topic_fact_set_scopes_by_response_brand_mentions_when_fk_and_text_do_not_match(
    client, db_session, user
):
    project = await _seed_admin_chain(db_session, user)
    now = datetime.now()
    project.primary_brand_id = 12
    await db_session.execute(
        text(
            """
            INSERT INTO brands (id, name, industry) VALUES
              (2, 'Wrong Owner', 'Beauty'),
              (12, 'Estee Lauder', 'Beauty')
            """
        )
    )
    await db_session.execute(
        text(
            """
            INSERT INTO topics (id, brand_id, text, category, status, created_at)
            VALUES (1501, 2, 'Night repair routine', 'product', 'active', :now)
            """
        ),
        {"now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts
                (id, topic_id, text, intent, prompt_scope, language, status, created_at)
            VALUES
              (1502, 1501, 'Which anti-aging serum is suitable for dry skin?',
               'commercial', 'non_branded', 'en', 'active', :now)
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
              (1503, 'chatgpt', 'done', 'anti-aging serum for dry skin',
               2, 'PROF-A', 1502, :now, :now, :now, 800)
            """
        ),
        {"now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, llm_version,
                 citations_json, created_at)
            VALUES
              (1504, 1503, 1502,
               'A repair serum is frequently recommended for dry skin routines.',
               'chatgpt', 'commercial', 'gpt-test', '[]', :now)
            """
        ),
        {"now": now},
    )
    db_session.add(
        ResponseAnalysis(
            response_id=1504,
            target_brand_mentioned=False,
            target_brand_rank=None,
            sentiment_score=0.4,
            geo_score=0.7,
        )
    )
    db_session.add_all(
        [
            BrandMention(
                response_id=1504,
                brand_id=12,
                brand_name="Estee Lauder",
                sentiment="positive",
                sentiment_score=0.4,
                position_rank=1,
                created_at=now,
            ),
            BrandMention(
                response_id=1504,
                brand_id=None,
                brand_name="Lancome",
                sentiment="neutral",
                sentiment_score=0,
                position_rank=2,
                created_at=now,
            ),
        ]
    )
    await db_session.commit()

    monitoring = await client.get(
        f"/api/v1/projects/{project.id}/topics/monitoring",
        headers=_bearer(user),
    )

    assert monitoring.status_code == 200, monitoring.text
    monitoring_body = monitoring.json()
    assert monitoring_body["state"] == "ok"
    assert monitoring_body["summary"]["topic_count"] == 1
    assert monitoring_body["summary"]["prompt_count"] == 1
    assert monitoring_body["summary"]["query_count"] == 1
    assert monitoring_body["summary"]["response_count"] == 1
    topic = monitoring_body["topics"][0]
    assert topic["topic_id"] == 1501
    assert topic["associated_brand"] == "Estee Lauder"
    assert topic["mention_rate"] == pytest.approx(1.0)
    assert topic["sov"] == pytest.approx(0.5)

    activity = await client.get(
        f"/api/v1/projects/{project.id}/query-activity",
        headers=_bearer(user),
    )
    assert activity.status_code == 200, activity.text
    assert activity.json()["totals"]["queries"] == 1
    assert activity.json()["totals"]["mentions_target"] == 1


@pytest.mark.asyncio
async def test_competitor_metrics_apply_admin_fact_filters(client, db_session, user):
    project = await _seed_admin_chain(db_session, user)

    resp = await client.get(
        f"/api/v1/projects/{project.id}/competitors/metrics"
        "?prompt_scope=non_branded"
        "&engine=deepseek",
        headers=_bearer(user),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "partial"
    assert body["formula_status"] in {"missing_required_inputs", "formula_pending_upstream"}
    assert body["primary"] is None
    assert [row["brand_name"] for row in body["competitors"]] == ["Null Rival"]
    assert body["competitors"][0]["avg_sov"] is None

    empty = await client.get(
        f"/api/v1/projects/{project.id}/competitors/metrics"
        "?prompt_scope=non_branded"
        "&engine=missing",
        headers=_bearer(user),
    )
    assert empty.status_code == 200, empty.text
    empty_body = empty.json()
    assert empty_body["state"] == "partial"
    assert empty_body["competitors"] == []


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
    assert barrier["negative_ratio"] == pytest.approx(1 / 3, rel=0.01)
    assert barrier["sample_snippet"] == "cautiously"

    gap = await client.get(
        f"/api/v1/projects/{project.id}/citations/content-gap",
        headers=headers,
    )
    assert gap.status_code == 200, gap.text
    gap_body = gap.json()
    barrier_gap = next(row for row in gap_body["topics"] if row["topic_id"] == 101)
    assert barrier_gap["mention_rate"] == pytest.approx(1 / 2, rel=0.01)
    assert barrier_gap["citation_rate"] == pytest.approx(1 / 3, rel=0.01)
    assert barrier_gap["gap_score"] == pytest.approx(1 / 6, rel=0.01)
    assert gap_body["page_type_distribution"][0]["page_type"] == "article"


@pytest.mark.asyncio
async def test_phase5_charts_use_text_matched_admin_facts_and_explain_missing_dimensions(
    client, db_session, user
):
    project = await _seed_admin_chain(db_session, user)
    project.primary_brand_id = 12
    now = datetime.now()
    await db_session.execute(
        text(
            """
            INSERT INTO brands (id, name, industry) VALUES
              (2, 'Source Owner', 'Beauty'),
              (12, 'Estee Lauder', 'Beauty')
            """
        )
    )
    await db_session.execute(
        text(
            """
            INSERT INTO topics (id, brand_id, text, category, status, created_at)
            VALUES (2501, 2, 'Misfiled anti-aging serum', 'product', 'active', :now)
            """
        ),
        {"now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts
                (id, topic_id, text, intent, prompt_scope, language, status, created_at)
            VALUES
              (2502, 2501, 'Is Estee Lauder Advanced Night Repair good for anti-aging?',
               'commercial', 'non_branded', 'en', 'active', :now)
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
              (2503, 'chatgpt', 'done',
               'Is Estee Lauder Advanced Night Repair good for anti-aging?',
               2, 'PROF-A', 2502, :now, :now, :now, 800)
            """
        ),
        {"now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, llm_version,
                 citations_json, created_at)
            VALUES
              (2504, 2503, 2502,
               'Estee Lauder Advanced Night Repair is frequently recommended for anti-aging.',
               'chatgpt', 'commercial', 'gpt-test', '[]', :now)
            """
        ),
        {"now": now},
    )
    db_session.add(
        ResponseAnalysis(
            response_id=2504,
            target_brand_mentioned=False,
            target_brand_rank=None,
            sentiment_score=0.82,
            geo_score=0.79,
        )
    )
    db_session.add(
        BrandMention(
            response_id=2504,
            brand_id=12,
            brand_name="Estee Lauder",
            sentiment="positive",
            sentiment_score=0.82,
            mention_count=4,
            position_rank=1,
            context_snippet="Estee Lauder Advanced Night Repair",
            created_at=now,
        )
    )
    await db_session.commit()

    headers = _bearer(user)

    engine_metrics = await client.get(
        f"/api/v1/projects/{project.id}/metrics/by-engine",
        headers=headers,
    )
    assert engine_metrics.status_code == 200, engine_metrics.text
    engine_body = engine_metrics.json()
    assert engine_body["state"] == "ok"
    assert engine_body["state_reason"] == "data_available"
    assert engine_body["evidence_count"] >= 1
    chatgpt = next(row for row in engine_body["items"] if row["engine"] == "chatgpt")
    assert chatgpt["mention_rate"] == pytest.approx(1.0)
    assert chatgpt["mention_rate"] <= 1.0
    assert chatgpt["sov"] == pytest.approx(1.0)

    position = await client.get(
        f"/api/v1/projects/{project.id}/position-distribution",
        headers=headers,
    )
    assert position.status_code == 200, position.text
    position_body = position.json()
    assert position_body["state"] == "ok"
    assert position_body["evidence_count"] >= 1
    assert position_body["total_mentions"] >= 1

    heatmap = await client.get(
        f"/api/v1/projects/{project.id}/topic-heatmap",
        headers=headers,
    )
    assert heatmap.status_code == 200, heatmap.text
    heatmap_body = heatmap.json()
    assert heatmap_body["state"] == "ok"
    primary_row = next(row for row in heatmap_body["rows"] if row["brand_id"] == 12)
    topic_cell = next(cell for cell in primary_row["values"] if cell["topic_id"] == 2501)
    assert topic_cell["value"] == pytest.approx(1.0)
    assert topic_cell["sample"] == 1

    sentiment = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/by-engine",
        headers=headers,
    )
    assert sentiment.status_code == 200, sentiment.text
    sentiment_body = sentiment.json()
    assert sentiment_body["state"] == "ok"
    assert sentiment_body["evidence_count"] >= 1
    chatgpt_sentiment = next(row for row in sentiment_body["items"] if row["engine"] == "chatgpt")
    assert chatgpt_sentiment["positive"] >= 1

    samples = await client.get(
        f"/api/v1/projects/{project.id}/mention-samples",
        headers=headers,
    )
    assert samples.status_code == 200, samples.text
    samples_body = samples.json()
    assert samples_body["state"] == "ok"
    assert samples_body["state_reason"] == "data_available"
    assert samples_body["evidence_count"] >= 1
    assert any(
        "Estee Lauder Advanced Night Repair" in row["snippet"] for row in samples_body["items"]
    )

    citations = await client.get(
        f"/api/v1/projects/{project.id}/citations/composition",
        headers=headers,
    )
    assert citations.status_code == 200, citations.text
    citations_body = citations.json()
    assert citations_body["state"] == "empty"
    assert citations_body["state_reason"] == "no_citation_data"
    assert citations_body["evidence_count"] >= 1
    assert citations_body["total"] == 0

    products = await client.get(
        f"/api/v1/projects/{project.id}/products",
        headers=headers,
    )
    assert products.status_code == 200, products.text
    products_body = products.json()
    assert products_body["state"] == "partial"
    assert products_body["state_reason"] == "missing_formula_inputs"
    assert "product_score_daily" in products_body["missing_inputs"]
    assert products_body["evidence_count"] >= 1
