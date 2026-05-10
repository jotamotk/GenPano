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
              (201, 101, 'Best barrier repair cream?', 'commercial', 'non_branded', 'en', 'active', :now),
              (202, 101, 'How does Test Brand repair sensitive skin?', 'informational', 'branded', 'en', 'active', :now),
              (203, 102, 'Best vitamin c serum?', 'commercial', 'non_branded', 'en', 'active', :now),
              (901, 901, 'Foreign brand prompt?', 'commercial', 'non_branded', 'en', 'active', :now)
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
                (304, 'deepseek', 'done', 'Best barrier repair cream for redness?', 42, 'PROF-A', 201,
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
    assert body["summary"]["query_count"] == 4
    assert body["summary"]["response_count"] == 3
    barrier = next(row for row in body["topics"] if row["topic_id"] == 101)
    assert barrier["prompt_count"] == 2
    assert barrier["query_count"] == 4
    assert barrier["response_count"] == 3
    assert barrier["success_rate"] == pytest.approx(3 / 4, rel=0.01)
    assert barrier["engine_coverage"] == ["chatgpt", "deepseek", "doubao"]
    assert barrier["mention_rate"] == pytest.approx(1 / 2, rel=0.01)
    assert barrier["sov"] == pytest.approx(2 / 4, rel=0.01)
    assert barrier["sentiment_distribution"] == {"positive": 1, "neutral": 0, "negative": 1}
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
    assert scoped.json()["summary"]["query_count"] == 4

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
    assert query_body["total"] == 3
    assert {row["status"] for row in query_body["items"]} == {"done", "failed"}
    done_query = next(row for row in query_body["items"] if row["query_id"] == 301)
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
    assert body["totals"]["queries"] == 4
    assert body["totals"]["responses"] == 3
    assert body["totals"]["analyzed"] == 3
    assert body["totals"]["mentions_target"] == 1
    assert body["totals"]["mention_denominator"] == 2
    assert body["by_status"]["done"] == 3
    assert body["by_status"]["failed"] == 1
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
    assert body["state"] == "ok"
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
    filtered_metric = {
        series["metric"]: series["points"] for series in filtered_body["series"]
    }
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
              (1202, 1201, '雅诗兰黛小棕瓶适合哪些抗老需求？',
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
              (1203, 'chatgpt', 'done', '雅诗兰黛小棕瓶适合哪些抗老需求？',
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
    assert metrics_body["state"] == "ok"
    by_metric = {series["metric"]: series["points"] for series in metrics_body["series"]}
    assert by_metric["mention_rate"][0]["value"] == pytest.approx(1.0)
    assert by_metric["sov"][0]["value"] == pytest.approx(1.0)
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
    assert overview_body["state"] == "ok"
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
    assert metrics_body["state"] == "ok"
    by_metric = {series["metric"]: series["points"] for series in metrics_body["series"]}
    assert by_metric["mention_rate"][0]["value"] == pytest.approx(1.0)
    assert by_metric["sov"][0]["value"] == pytest.approx(1.0)

    overview_resp = await client.get(
        f"/api/v1/projects/{project.id}/overview",
        headers=_bearer(user),
        params={"brand_id": 12},
    )
    assert overview_resp.status_code == 200, overview_resp.text
    overview_body = overview_resp.json()
    assert overview_body["state"] == "ok"
    assert overview_body["brand_name"] == "Estee Lauder"
    assert overview_body["geo_score_30d"]
    assert any(
        card["label_en"] == "Mention Rate" and card["value"] > 0
        for card in overview_body["kpi_cards"]
    )
    assert any(row["mention_count"] > 0 for row in overview_body["top_prompts"])

    competitors_resp = await client.get(
        f"/api/v1/projects/{project.id}/competitors/metrics",
        headers=_bearer(user),
        params={"brand_id": 12, "prompt_scope": "non_branded"},
    )
    assert competitors_resp.status_code == 200, competitors_resp.text
    competitors_body = competitors_resp.json()
    assert competitors_body["primary"]["brand_id"] == 12
    assert competitors_body["primary"]["avg_mention_rate"] == pytest.approx(1.0)
    assert competitors_body["primary"]["avg_sov"] == pytest.approx(1.0)
    assert competitors_body["primary"]["avg_geo_score"] > 0

    trends_resp = await client.get(
        f"/api/v1/projects/{project.id}/competitors/trends",
        headers=_bearer(user),
        params={"brand_id": 12, "metric": "geo_score"},
    )
    assert trends_resp.status_code == 200, trends_resp.text
    trends_body = trends_resp.json()
    primary_series = next(series for series in trends_body["series"] if series["is_primary"])
    assert primary_series["brand_id"] == 12
    assert primary_series["points"]
    assert primary_series["points"][0]["value"] > 0


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
    assert body["state"] == "ok"
    assert body["primary"] is None
    assert [row["brand_name"] for row in body["competitors"]] == ["Null Rival"]
    assert body["competitors"][0]["avg_sov"] == 1

    empty = await client.get(
        f"/api/v1/projects/{project.id}/competitors/metrics"
        "?prompt_scope=non_branded"
        "&engine=missing",
        headers=_bearer(user),
    )
    assert empty.status_code == 200, empty.text
    assert empty.json()["state"] == "empty"
    assert empty.json()["competitors"] == []


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
