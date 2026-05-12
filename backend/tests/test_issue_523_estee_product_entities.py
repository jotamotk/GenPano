from __future__ import annotations

from datetime import datetime

import pytest
from genpano_models import BrandMention, ProductScoreDaily, Project, ResponseAnalysis, User
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.pipeline.app_product_entities import (
    ProductEntityBackfillConfig,
    backfill_product_entities,
    extract_product_names,
)


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 5, 11, 10, 30, 0)


async def _seed_admin_tables(db_session: AsyncSession) -> None:
    await db_session.execute(text("ALTER TABLE brands ADD COLUMN name TEXT"))
    await db_session.execute(text("ALTER TABLE brands ADD COLUMN name_zh TEXT"))
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
                prompt_id INTEGER,
                created_at DATETIME,
                finished_at DATETIME
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
        "ALTER TABLE llm_responses ADD COLUMN created_at DATETIME",
    ]:
        await db_session.execute(text(ddl))


async def _seed_project(db_session: AsyncSession) -> Project:
    user = User(
        id="issue-523-user",
        email="issue-523@example.com",
        name="Issue 523",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
    )
    project = Project(
        id="95d43022-a5c8-5944-b6d6-34b29faa18b5",
        user_id=user.id,
        name="Estee product slice",
        primary_brand_id=12,
        industry_id=1,
    )
    db_session.add_all([user, project])
    await db_session.commit()
    return project


async def _seed_response(
    db_session: AsyncSession,
    *,
    response_id: int,
    raw_text: str,
    query_text: str,
    now: datetime,
    canonical_mention: bool = True,
) -> None:
    await db_session.execute(
        text(
            "INSERT INTO topics (id, brand_id, text, category, status, created_at) "
            "VALUES (:topic_id, 2, 'Misfiled Estee product', 'product', 'active', :now)"
        ),
        {"topic_id": response_id + 100, "now": now},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO prompts
                (id, topic_id, text, intent, prompt_scope, language, status, created_at)
            VALUES
                (:prompt_id, :topic_id, :prompt_text, 'commercial', 'non_branded',
                 'en', 'active', :now)
            """
        ),
        {
            "prompt_id": response_id + 200,
            "topic_id": response_id + 100,
            "prompt_text": query_text,
            "now": now,
        },
    )
    await db_session.execute(
        text(
            """
            INSERT INTO queries
                (id, target_llm, status, query_text, brand_id, prompt_id, created_at, finished_at)
            VALUES
                (:query_id, 'chatgpt', 'done', :query_text, 2, :prompt_id, :now, :now)
            """
        ),
        {
            "query_id": response_id + 300,
            "query_text": query_text,
            "prompt_id": response_id + 200,
            "now": now,
        },
    )
    await db_session.execute(
        text(
            """
            INSERT INTO llm_responses
                (id, query_id, prompt_id, raw_text, target_llm, intent, created_at)
            VALUES
                (:response_id, :query_id, :prompt_id, :raw_text, 'chatgpt', 'commercial', :now)
            """
        ),
        {
            "response_id": response_id,
            "query_id": response_id + 300,
            "prompt_id": response_id + 200,
            "raw_text": raw_text,
            "now": now,
        },
    )
    db_session.add(
        ResponseAnalysis(
            response_id=response_id,
            target_brand_mentioned=canonical_mention,
            sentiment_score=0.82,
            geo_score=0.79,
        )
    )
    if canonical_mention:
        db_session.add(
            BrandMention(
                response_id=response_id,
                brand_id=12,
                brand_name="Estee Lauder",
                product_name=None,
                sentiment="positive",
                sentiment_score=0.82,
                mention_count=1,
                position_rank=1,
                context_snippet=raw_text,
                created_at=now,
            )
        )
    await db_session.commit()


def test_extract_product_names_requires_explicit_product_alias() -> None:
    assert extract_product_names("Estee Lauder is mentioned as a strong beauty brand.") == []
    assert extract_product_names(
        "Estee Lauder Advanced Night Repair is often recommended for anti-aging."
    ) == ["Advanced Night Repair"]
    assert extract_product_names("雅诗兰黛小棕瓶适合夜间修护。") == ["Advanced Night Repair"]


@pytest.mark.asyncio
async def test_cross_owner_estee_product_backfill_is_idempotent(
    db_session: AsyncSession, now: datetime
) -> None:
    await _seed_admin_tables(db_session)
    await db_session.execute(
        text(
            "INSERT INTO brands (id, name, name_zh) VALUES "
            "(2, 'Source Owner', '来源品牌'), (12, 'Estee Lauder', '雅诗兰黛')"
        )
    )
    await _seed_project(db_session)
    await _seed_response(
        db_session,
        response_id=52301,
        raw_text="Estee Lauder Advanced Night Repair is often recommended for anti-aging.",
        query_text="Is Estee Lauder Advanced Night Repair good for anti-aging?",
        now=now,
    )

    config = ProductEntityBackfillConfig(canonical_brand_id=12, source_brand_ids=(2,))
    first = await backfill_product_entities(db_session, config=config, dry_run=False)
    second = await backfill_product_entities(db_session, config=config, dry_run=False)

    assert first.scanned_responses == 1
    assert first.evidence_responses == 1
    assert first.product_names == ["Advanced Night Repair"]
    assert first.brand_mentions_updated == 1
    assert first.product_score_rows_upserted == 1
    assert second.product_score_rows_upserted == 1

    mention = (
        await db_session.execute(select(BrandMention).where(BrandMention.response_id == 52301))
    ).scalar_one()
    assert mention.product_name == "Advanced Night Repair"

    rows = (await db_session.execute(select(ProductScoreDaily))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.brand_id == 12
    assert row.product_name == "Advanced Night Repair"
    assert row.total_queries == 1
    assert row.mention_count == 1
    assert row.mention_rate == pytest.approx(1.0)
    assert row.avg_geo_score == pytest.approx(79.0)
    assert row.avg_sentiment_score == pytest.approx(0.82)


@pytest.mark.asyncio
async def test_estee_product_backfill_does_not_create_brand_only_products(
    db_session: AsyncSession, now: datetime
) -> None:
    await _seed_admin_tables(db_session)
    await db_session.execute(
        text("INSERT INTO brands (id, name) VALUES (2, 'Source Owner'), (12, 'Estee Lauder')")
    )
    await _seed_project(db_session)
    await _seed_response(
        db_session,
        response_id=52302,
        raw_text="Estee Lauder is mentioned as a strong beauty brand.",
        query_text="Which beauty brand is visible?",
        now=now,
    )

    result = await backfill_product_entities(
        db_session,
        config=ProductEntityBackfillConfig(canonical_brand_id=12, source_brand_ids=(2,)),
        dry_run=False,
    )

    assert result.scanned_responses == 1
    assert result.evidence_responses == 0
    assert result.product_names == []
    assert result.brand_mentions_updated == 0
    assert (
        await db_session.execute(select(func.count()).select_from(ProductScoreDaily))
    ).scalar_one() == 0
