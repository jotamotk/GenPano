"""Phase E.1 — synchronous export download with CSV materialization."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    BrandMention,
    GeoScoreDaily,
    Project,
    ProjectCompetitor,
    SentimentDriver,
    User,
)
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
        email=f"e1-{uuid.uuid4().hex[:6]}@example.com",
        name="E1",
        role="paid",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, user: User) -> Project:
    p = Project(
        id=_new_id(),
        user_id=user.id,
        name="Exp Project",
        primary_brand_id=700,
    )
    db_session.add(p)
    await db_session.commit()
    return p


# ── mention_list ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_mention_list_csv(db_session, client, user, project):
    db_session.add_all(
        [
            BrandMention(
                response_id=8001,
                brand_id=700,
                brand_name="Acme",
                sentiment="positive",
                sentiment_score=0.6,
                created_at=datetime.now(UTC).replace(tzinfo=None),
            ),
            BrandMention(
                response_id=8002,
                brand_id=700,
                brand_name="Acme",
                sentiment="negative",
                sentiment_score=-0.5,
                created_at=datetime.now(UTC).replace(tzinfo=None),
            ),
        ]
    )
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=_bearer(user),
        json={"export_type": "mention_list"},
    )
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    dl = await client.get(
        f"/api/v1/projects/{project.id}/exports/{job_id}/download",
        headers=_bearer(user),
    )
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("text/csv")
    body = dl.text
    lines = body.strip().split("\n")
    assert lines[0].startswith("created_at,brand_id,brand_name,sentiment")
    # 2 data rows after header
    assert len(lines) == 3


@pytest.mark.asyncio
async def test_export_status_marked_done_after_download(db_session, client, user, project):
    db_session.add(
        BrandMention(
            response_id=8003,
            brand_id=700,
            brand_name="Acme",
            sentiment="positive",
        )
    )
    await db_session.commit()

    create = await client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=_bearer(user),
        json={"export_type": "mention_list"},
    )
    job_id = create.json()["id"]

    # status starts as 'queued'
    status_before = await client.get(
        f"/api/v1/projects/{project.id}/exports/{job_id}",
        headers=_bearer(user),
    )
    assert status_before.json()["status"] == "queued"

    # download synchronously materializes
    await client.get(
        f"/api/v1/projects/{project.id}/exports/{job_id}/download",
        headers=_bearer(user),
    )

    status_after = await client.get(
        f"/api/v1/projects/{project.id}/exports/{job_id}",
        headers=_bearer(user),
    )
    body = status_after.json()
    assert body["status"] == "done"
    assert body["row_count"] == 1
    assert body["finished_at"] is not None


# ── industry_ranking ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_industry_ranking_csv(db_session, client, user, project):
    today = datetime.now(UTC).replace(tzinfo=None).date()
    for bid in (700, 701, 702):
        for i in range(30):
            d = today - timedelta(days=29 - i)
            db_session.add(
                GeoScoreDaily(
                    brand_id=bid,
                    date=datetime.combine(d, datetime.min.time()),
                    target_llm="chatgpt",
                    avg_geo_score=80.0 - (bid - 700) * 5,
                    mention_rate=0.5,
                    total_queries=100,
                )
            )
    await db_session.commit()

    create = await client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=_bearer(user),
        json={"export_type": "industry_ranking"},
    )
    job_id = create.json()["id"]

    dl = await client.get(
        f"/api/v1/projects/{project.id}/exports/{job_id}/download",
        headers=_bearer(user),
    )
    body = dl.text
    lines = body.strip().split("\n")
    assert lines[0].startswith("brand_id,avg_geo_score_30d,rank")
    # 3 brands → 3 ranked rows
    assert len(lines) == 4
    # First data row should be the highest-scoring brand (700)
    assert lines[1].startswith("700,")


# ── competitor_matrix ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_competitor_matrix_csv(db_session, client, user, project):
    db_session.add(ProjectCompetitor(project_id=project.id, brand_id=801))
    today = datetime.now(UTC).replace(tzinfo=None).date()
    for bid in (700, 801):
        for i in range(30):
            d = today - timedelta(days=29 - i)
            db_session.add(
                GeoScoreDaily(
                    brand_id=bid,
                    date=datetime.combine(d, datetime.min.time()),
                    target_llm="chatgpt",
                    avg_geo_score=70.0 if bid == 700 else 80.0,
                    mention_rate=0.5,
                    total_queries=100,
                )
            )
    await db_session.commit()

    create = await client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=_bearer(user),
        json={"export_type": "competitor_matrix"},
    )
    job_id = create.json()["id"]
    dl = await client.get(
        f"/api/v1/projects/{project.id}/exports/{job_id}/download",
        headers=_bearer(user),
    )
    lines = dl.text.strip().split("\n")
    assert lines[0].startswith("my_brand_id,competitor_brand_id")
    assert len(lines) == 2  # header + 1 competitor row


# ── sentiment_list ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_export_sentiment_list_csv(db_session, client, user, project):
    # SentimentDriver joins via mention_id → brand_mentions.brand_id
    mention = BrandMention(
        response_id=9001,
        brand_id=700,
        brand_name="Acme",
    )
    db_session.add(mention)
    await db_session.commit()
    await db_session.refresh(mention)

    db_session.add(
        SentimentDriver(
            response_id=9001,
            mention_id=mention.id,
            brand_name="Acme",
            driver_text="great quality across the line",
            polarity="positive",
            category="quality",
            strength=0.8,
        )
    )
    await db_session.commit()

    create = await client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=_bearer(user),
        json={"export_type": "sentiment_list"},
    )
    dl = await client.get(
        f"/api/v1/projects/{project.id}/exports/{create.json()['id']}/download",
        headers=_bearer(user),
    )
    lines = dl.text.strip().split("\n")
    assert lines[0].startswith("created_at,brand_name,polarity,category,strength,driver_text")
    assert len(lines) == 2
    assert "quality" in lines[1]


# ── unimplemented type returns 422 ───────────────────────────────


@pytest.mark.asyncio
async def test_export_unimplemented_type_returns_422(db_session, client, user, project):
    create = await client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=_bearer(user),
        json={"export_type": "topic_coverage"},
    )
    dl = await client.get(
        f"/api/v1/projects/{project.id}/exports/{create.json()['id']}/download",
        headers=_bearer(user),
    )
    assert dl.status_code == 422


# ── multi-tenant: download from someone else's project → 404 ─────


@pytest.mark.asyncio
async def test_export_download_other_user_returns_404(db_session, client, user, project):
    other = User(
        id=_new_id(),
        email=f"o-{uuid.uuid4().hex[:6]}@example.com",
        name="Other",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(other)
    await db_session.commit()

    create = await client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=_bearer(user),
        json={"export_type": "mention_list"},
    )
    job_id = create.json()["id"]
    dl = await client.get(
        f"/api/v1/projects/{project.id}/exports/{job_id}/download",
        headers=_bearer(other),
    )
    assert dl.status_code == 404
