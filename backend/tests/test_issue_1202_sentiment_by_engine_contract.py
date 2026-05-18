"""Issue #1202: sentiment by-engine empty states explain engine attribution gaps."""

from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from genpano_models import BrandMention, Project, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)

WINDOW_FROM = "2026-05-11"
WINDOW_TO = "2026-05-18"
WINDOW_DAY = datetime(2026, 5, 12, 10, 15, 0)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"issue1202-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue 1202 User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest.mark.asyncio
async def test_sentiment_by_engine_explains_missing_engine_when_sentiment_evidence_exists(
    client,
    db_session: AsyncSession,
    user: User,
) -> None:
    project = Project(
        id="95d43022-a5c8-5944-b6d6-34b29faa18b5",
        user_id=user.id,
        name="Issue 1202 Sentiment Engine Project",
        primary_brand_id=12,
        industry_id=7,
    )
    db_session.add(project)
    db_session.add_all(
        [
            BrandMention(
                response_id=120200 + idx,
                brand_id=12,
                brand_name="Estee Lauder",
                mention_count=1,
                sentiment=sentiment,
                sentiment_score=score,
                created_at=WINDOW_DAY,
            )
            for idx, (sentiment, score) in enumerate(
                [
                    ("positive", 0.8),
                    ("neutral", 0.0),
                    ("negative", -0.4),
                ],
                start=1,
            )
        ]
    )
    await db_session.commit()

    headers = _bearer(user)
    params = {"brand_id": 12, "from": WINDOW_FROM, "to": WINDOW_TO}
    sentiment = await client.get(
        f"/api/v1/projects/{project.id}/sentiment",
        headers=headers,
        params=params,
    )
    by_engine = await client.get(
        f"/api/v1/projects/{project.id}/sentiment/by-engine",
        headers=headers,
        params=params,
    )

    assert sentiment.status_code == 200, sentiment.text
    sentiment_body = sentiment.json()
    assert sentiment_body["state"] in {"ok", "partial"}
    assert sentiment_body["evidence_count"] == 3
    assert (
        sum(
            sentiment_body["distribution"][key]
            for key in ("positive_count", "neutral_count", "negative_count")
        )
        == 3
    )

    assert by_engine.status_code == 200, by_engine.text
    body = by_engine.json()
    assert body["items"] == []
    assert body["state"] == "partial"
    assert body["formula_status"] != "no_evidence"
    assert body["evidence_count"] == 3
    assert "llm_responses.target_llm" in body["missing_inputs"]
    assert "queries.target_llm" in body["missing_inputs"]
    assert "llm_responses.target_llm" in body["missing_sources"]
    assert "queries.target_llm" in body["missing_sources"]
