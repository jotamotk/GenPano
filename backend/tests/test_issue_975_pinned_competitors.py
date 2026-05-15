"""Regression test for issue #975 — pinned cross-industry competitors.

PRs #978 and #982 scoped the auto-discovery path and resolved
`industry_id` → `industry_name` everywhere. But the user reported the
competitor panel still showed cross-industry brands in live data —
because the `ProjectCompetitor` (pinned) path was never scoped. This
test pins a cross-industry brand and asserts the API drops it.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    BrandMention,
    GeoScoreDaily,
    Project,
    ProjectCompetitor,
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
        email=f"i975pin-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue975 Pin",
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
async def project_with_crossindustry_pin(db_session: AsyncSession, user: User) -> Project:
    """Pin a Cookware brand on a Sportswear primary's project.

    Primary 420 = Sportswear. Pins 421 (Sportswear, expected to remain)
    and 422 (Cookware, expected to be dropped). No BrandMention rows
    forcing the response-entity SoV path means the test exercises the
    `ProjectCompetitor` pinned-competitors branch directly.
    """
    try:
        await db_session.execute(text("ALTER TABLE brands ADD COLUMN industry TEXT"))
    except Exception:
        pass

    await db_session.execute(
        text(
            "INSERT INTO brands (id, industry) VALUES "
            "(420, 'Sportswear'), (421, 'Sportswear'), (422, 'Cookware')"
        )
    )

    project = Project(
        user_id=user.id,
        name="Pinned cross-industry",
        primary_brand_id=420,
        industry_id=1,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])
    db_session.add(ProjectCompetitor(project_id=project.id, brand_id=421, pinned_by=user.id))
    db_session.add(ProjectCompetitor(project_id=project.id, brand_id=422, pinned_by=user.id))

    today = datetime.now().date()
    for bid, score in ((420, 80.0), (421, 70.0), (422, 60.0)):
        for i in range(10):
            d = today - timedelta(days=9 - i)
            db_session.add(
                GeoScoreDaily(
                    brand_id=bid,
                    date=datetime.combine(d, datetime.min.time()),
                    target_llm="chatgpt",
                    avg_geo_score=score + i * 0.1,
                    mention_rate=0.5,
                    avg_sov=0.3,
                    avg_sentiment=0.5,
                    total_queries=80,
                )
            )

    # No BrandMention rows in the analysis window → the response-entity
    # SoV short-circuit returns None and the ProjectCompetitor branch
    # runs.
    await db_session.commit()
    return project


@pytest.mark.asyncio
async def test_pinned_crossindustry_competitor_dropped_from_metrics(
    client, user, project_with_crossindustry_pin
):
    """`/projects/:id/competitors/metrics` must drop the pinned
    Cookware brand (422) since primary is Sportswear."""
    resp = await client.get(
        f"/api/v1/projects/{project_with_crossindustry_pin.id}/competitors/metrics",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    competitor_ids = {c["brand_id"] for c in body["competitors"]}
    assert 422 not in competitor_ids, (
        f"Cookware pin leaked into Sportswear competitor panel: {body['competitors']}"
    )
    assert 421 in competitor_ids


@pytest.mark.asyncio
async def test_pinned_crossindustry_competitor_dropped_from_trends(
    client, user, project_with_crossindustry_pin
):
    """`/projects/:id/competitors/trends` must drop pinned cross-
    industry brands as well."""
    resp = await client.get(
        f"/api/v1/projects/{project_with_crossindustry_pin.id}/competitors/trends",
        headers=_bearer(user),
        params={"metric": "geo_score"},
    )
    assert resp.status_code == 200
    body = resp.json()
    series_ids = {s["brand_id"] for s in body["series"]}
    assert 422 not in series_ids, f"Cookware pin leaked into trends series: {body['series']}"
    assert 421 in series_ids
