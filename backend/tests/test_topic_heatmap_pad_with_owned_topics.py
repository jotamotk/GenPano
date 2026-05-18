"""Regression: /topic-heatmap pads top-N with brand-owned topics when
`topic_score_daily` is sparse.

Captured evidence — bestCoffer (brand_id=24) in production:
  https://github.com/jotamotk/trash_test/actions/runs/26045540877
  - topics_owned (in `topics` table)         = 13
  - topics_with_daily_rows (topic_score_daily)= 4
  - distinct_topics returned by Path A SQL    = 4
  - body_sha256(top_n=8) == body_sha256(top_n=30)  (raising the cap did NOTHING)

Real captured topic_ids with rollup rows (and SUM(mention_count) values, all
brand_id=24):
  153 「企业级AI数据脱敏工具选购指南」              total_mentions=33
  154 「非结构化数据AI脱敏准确率测评参考」          total_mentions=7
  158 「跨境资本交易尽职调查文件协作工具选购指南」  total_mentions=5
  159 「内置多行业合规模版的AI脱敏工具选购指南」    total_mentions=2

These four are the ones the user saw in the screenshot. The remaining 9
topics in the `topics` table for bestCoffer have NO `topic_score_daily`
rows in the window, so they were dropped. This test seeds those four with
their REAL ids and mention counts plus the other nine as owned-but-unscored,
and verifies the heatmap response surfaces all 10 requested columns
(value=None / sample=0 for the padded ones).
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime

import pytest
import pytest_asyncio
from genpano_models import Project, TopicScoreDaily, User
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)

BESTCOFFER_BRAND_ID = 24
WINDOW_DAY = date(2026, 5, 12)
SCORED_TOPICS: list[tuple[int, str, int]] = [
    (153, "企业级AI数据脱敏工具选购指南", 33),
    (154, "非结构化数据AI脱敏准确率测评参考", 7),
    (158, "跨境资本交易尽职调查文件协作工具选购指南", 5),
    (159, "内置多行业合规模版的AI脱敏工具选购指南", 2),
]
UNSCORED_TOPICS: list[tuple[int, str]] = [
    (162, "投融资尽职调查虚拟数据室服务选购指南"),
    (170, "AI数据脱敏工具厂商对比"),
    (171, "并购交易尽调数据室对比"),
    (172, "金融行业AI脱敏合规检查清单"),
    (173, "医疗行业脱敏工具评估"),
    (174, "数据安全合规模版定制"),
    (175, "脱敏工具准确率行业评测"),
    (176, "数据室协作场景方案"),
    (177, "合规文档自动化脱敏"),
]


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=f"heatmap-pad-{uuid.uuid4().hex[:6]}@example.com",
        name="Heatmap Pad User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def bestcoffer_project(db_session: AsyncSession, user: User) -> Project:
    p = Project(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name="BestCoffer heatmap pad project",
        primary_brand_id=BESTCOFFER_BRAND_ID,
        industry_id=7,
    )
    db_session.add(p)
    await db_session.commit()
    return p


async def _create_topics_table(db_session: AsyncSession) -> None:
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
    await db_session.commit()


async def _seed_owned_topics(db_session: AsyncSession) -> None:
    now = datetime(2026, 5, 12, 8, 0, 0)
    rows: list[tuple[int, str]] = [
        *((tid, name) for tid, name, _ in SCORED_TOPICS),
        *UNSCORED_TOPICS,
    ]
    for tid, name in rows:
        await db_session.execute(
            text(
                "INSERT INTO topics (id, brand_id, text, category, status, created_at) "
                "VALUES (:id, :bid, :txt, 'product', 'active', :day)"
            ),
            {"id": tid, "bid": BESTCOFFER_BRAND_ID, "txt": name, "day": now},
        )
    await db_session.commit()


async def _seed_topic_score_daily(db_session: AsyncSession) -> None:
    for tid, _, mentions in SCORED_TOPICS:
        db_session.add(
            TopicScoreDaily(
                brand_id=BESTCOFFER_BRAND_ID,
                topic_id=tid,
                date=WINDOW_DAY,
                total_responses=mentions * 2,
                mention_count=mentions,
                mention_rate=0.5,
                avg_sentiment_score=0.6,
            )
        )
    await db_session.commit()


@pytest.mark.asyncio
async def test_topic_heatmap_pads_with_brand_owned_topics(
    client: AsyncClient,
    user: User,
    bestcoffer_project: Project,
    db_session: AsyncSession,
) -> None:
    """When topic_score_daily has fewer than top_n topics for the brand,
    the heatmap response is padded with topics from the `topics` table
    so the user sees all requested columns (data-bearing + empty)."""
    await _create_topics_table(db_session)
    await _seed_owned_topics(db_session)
    await _seed_topic_score_daily(db_session)

    response = await client.get(
        f"/api/v1/projects/{bestcoffer_project.id}/topic-heatmap",
        headers=_bearer(user),
        params={
            "brand_id": BESTCOFFER_BRAND_ID,
            "metric": "sentiment",
            "top_n": 10,
            "from": WINDOW_DAY.isoformat(),
            "to": WINDOW_DAY.isoformat(),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()

    primary_row = next(
        (row for row in body["rows"] if row["brand_id"] == BESTCOFFER_BRAND_ID),
        None,
    )
    assert primary_row is not None, f"no primary brand row in {body}"

    column_count = len(primary_row["values"])
    assert column_count == 10, (
        f"expected 10 columns after padding from topics table, got {column_count}. "
        f"Real captured evidence: bestCoffer has topics_owned=13, "
        f"topics_with_daily_rows=4. Without padding only 4 columns would render."
    )

    returned_ids = {cell["topic_id"] for cell in primary_row["values"]}
    real_scored_ids = {tid for tid, _, _ in SCORED_TOPICS}
    assert real_scored_ids.issubset(returned_ids), (
        f"expected the 4 real scored topic_ids {real_scored_ids} to be in "
        f"returned columns {returned_ids}"
    )

    padded_cells = [
        cell for cell in primary_row["values"] if cell["topic_id"] not in real_scored_ids
    ]
    assert padded_cells, "expected at least one padded (no-data) column"
    for cell in padded_cells:
        assert cell["value"] is None, (
            f"padded column for topic_id={cell['topic_id']} should have value=None, "
            f"got {cell['value']}"
        )
        assert cell["sample"] == 0, (
            f"padded column for topic_id={cell['topic_id']} should have sample=0, "
            f"got {cell['sample']}"
        )
