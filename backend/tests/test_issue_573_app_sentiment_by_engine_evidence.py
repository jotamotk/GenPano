"""Issue #573: sentiment by-engine must use response-window target evidence."""

from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from genpano_models import BrandMention, Project, User
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)

WINDOW_FROM = "2026-04-24"
WINDOW_TO = "2026-05-07"
WINDOW_DAY = datetime(2026, 4, 24, 2, 44, 46)
REPAIR_DAY = datetime(2026, 5, 11, 9, 30, 0)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"issue573-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue 573 User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


async def _seed_response_window_sentiment(
    db_session: AsyncSession,
    user: User,
    *,
    include_engine: bool,
) -> Project:
    await db_session.execute(text("ALTER TABLE brands ADD COLUMN name TEXT"))
    await db_session.execute(text("ALTER TABLE llm_responses ADD COLUMN created_at DATETIME"))
    if include_engine:
        await db_session.execute(text("ALTER TABLE llm_responses ADD COLUMN target_llm TEXT"))

    project = Project(
        id=str(uuid.uuid4()),
        user_id=user.id,
        name="Issue 573 Sentiment Project",
        primary_brand_id=12,
        industry_id=7,
    )
    db_session.add(project)
    await db_session.flush()

    await db_session.execute(text("INSERT INTO brands (id, name) VALUES (12, 'Estee Lauder')"))
    if include_engine:
        await db_session.execute(
            text(
                """
                INSERT INTO llm_responses (id, target_llm, created_at)
                VALUES (901, 'chatgpt', :day)
                """
            ),
            {"day": WINDOW_DAY},
        )
    else:
        await db_session.execute(
            text("INSERT INTO llm_responses (id, created_at) VALUES (901, :day)"),
            {"day": WINDOW_DAY},
        )

    db_session.add(
        BrandMention(
            response_id=901,
            brand_id=12,
            brand_name="Estee Lauder",
            mention_count=1,
            sentiment="positive",
            sentiment_score=0.42,
            created_at=REPAIR_DAY,
        )
    )
    await db_session.commit()
    return project


@pytest.mark.asyncio
async def test_sentiment_by_engine_uses_response_window_when_mentions_were_repaired_later(
    client,
    db_session: AsyncSession,
    user: User,
) -> None:
    project = await _seed_response_window_sentiment(
        db_session,
        user,
        include_engine=True,
    )

    response = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/by-engine",
        headers=_bearer(user),
        params={"from": WINDOW_FROM, "to": WINDOW_TO},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "partial"
    assert body["evidence_count"] == 1
    assert body["evidence_counts"]["sentiment_label_count"] == 1
    assert "response_analyses.raw_analysis_json.analyzer_fact_packages" in body["missing_inputs"]
    assert body["items"] == [
        {
            "engine": "chatgpt",
            "positive": 1,
            "neutral": 0,
            "negative": 0,
        }
    ]


@pytest.mark.asyncio
async def test_sentiment_by_engine_reports_missing_engine_when_target_sentiment_exists(
    client,
    db_session: AsyncSession,
    user: User,
) -> None:
    project = await _seed_response_window_sentiment(
        db_session,
        user,
        include_engine=False,
    )

    response = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/by-engine",
        headers=_bearer(user),
        params={"from": WINDOW_FROM, "to": WINDOW_TO},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "missing_required_inputs"
    assert body["evidence_count"] == 1
    assert body["items"] == []
    assert "llm_responses.target_llm" in body["missing_inputs"]
    assert "response_analyses.raw_analysis_json.analyzer_fact_packages" in body["missing_inputs"]
    assert "llm_responses.target_llm" in body["missing_sources"]
