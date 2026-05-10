"""Phase 2.1 — GET /v1/projects/:id/overview."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import BrandMention, GeoScoreDaily, Project, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"o-{uuid.uuid4().hex[:6]}@example.com",
        name="Overview User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def empty_project(db_session: AsyncSession, user: User) -> Project:
    p = Project(
        user_id=user.id,
        name="Empty Project",
        primary_brand_id=None,  # no brand → state='empty'
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p


@pytest_asyncio.fixture
async def project_with_data(db_session: AsyncSession, user: User) -> Project:
    p = Project(
        user_id=user.id,
        name="With Data",
        primary_brand_id=42,
        industry_id=1,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    # Insert 30d of geo_score_daily for brand 42
    today = datetime.now().date()
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=70.0 + i * 0.5,
                mention_rate=0.5 + i * 0.005,
                avg_sov=0.3 + i * 0.005,
                avg_sentiment=0.6 + i * 0.005,
                total_queries=100,
            )
        )
    # Insert some brand_mentions for top_prompts test
    for i in range(5):
        db_session.add(
            BrandMention(
                response_id=1000 + i,
                brand_id=42,
                brand_name="Test Brand",
                position_rank=i + 1,
                sentiment_score=0.7,
                created_at=datetime.now() - timedelta(days=i),
            )
        )
    await db_session.commit()
    return p


@pytest.mark.asyncio
async def test_overview_empty_state(client, user, empty_project):
    """Project without primary_brand_id → state='empty', zero KPIs."""
    resp = await client.get(f"/api/v1/projects/{empty_project.id}/overview", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "empty"
    assert body["brand_id"] is None
    assert body["geo_score_30d"] == []
    assert body["sov_30d"] == []
    assert body["sentiment_30d"] == []
    assert len(body["kpi_cards"]) == 4
    for c in body["kpi_cards"]:
        assert c["value"] == 0
        assert c["delta_30d_pct"] is None


@pytest.mark.asyncio
async def test_overview_with_data(client, user, project_with_data):
    """Project with geo_score_daily rows returns populated trends + KPIs."""
    resp = await client.get(
        f"/api/v1/projects/{project_with_data.id}/overview",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "ok"
    assert body["brand_id"] == 42
    assert body["industry_id"] == 1
    # 30d window has 30 data points
    assert len(body["geo_score_30d"]) == 30
    assert len(body["sov_30d"]) == 30
    # KPI cards have non-zero values
    geo_card = next(c for c in body["kpi_cards"] if c["label_en"] == "GeoScore")
    assert geo_card["value"] > 0
    # Top prompts populated
    assert len(body["top_prompts"]) >= 1
    assert body["top_prompts"][0]["mention_count"] >= 1


@pytest.mark.asyncio
async def test_overview_cross_tenant_returns_404(client, user, project_with_data, db_session):
    """Different user → 404."""
    other = User(
        id=_new_id(),
        email=f"x-{uuid.uuid4().hex[:6]}@example.com",
        name="Other",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(other)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project_with_data.id}/overview",
        headers=_bearer(other),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_overview_no_auth_returns_401(client, project_with_data):
    resp = await client.get(f"/api/v1/projects/{project_with_data.id}/overview")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_overview_brand_id_override_swaps_brand(client, user, project_with_data):
    """`?brand_id=X` overrides the project's primary brand. Drives the
    DashboardPage brand picker (cross-industry brand viewing). The
    project still scopes industry and ownership; only brand_id changes
    in the response and downstream queries."""
    resp = await client.get(
        f"/api/v1/projects/{project_with_data.id}/overview?brand_id=99",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    # Override took effect even though no geo_score_daily rows exist for
    # brand_id=99 in the fixture — state collapses to 'empty', brand_id
    # echoes the override.
    assert body["brand_id"] == 99
    assert body["state"] == "empty"
    assert all(c["value"] == 0 for c in body["kpi_cards"])


@pytest.mark.asyncio
async def test_overview_brand_id_override_falsy_keeps_default(client, user, project_with_data):
    """Omitting `brand_id` keeps the project's primary_brand_id."""
    resp = await client.get(
        f"/api/v1/projects/{project_with_data.id}/overview",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    assert resp.json()["brand_id"] == 42
