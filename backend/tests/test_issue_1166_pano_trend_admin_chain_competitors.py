"""Issue #1166 / #1153: PANO trend chart must keep competitor series even when
the admin-chain code path supplies a higher-quality primary series.

Captured 2026-05-18 from the live bestCoffer project via
`app-analytics-readonly-evidence.yml` run
https://github.com/jotamotk/trash_test/actions/runs/26040916185 — the live
`/competitors/trends` response contained ONLY the primary series
(`series_count=1`) even though the project had `competitor_brand_ids: [2]`
configured. This regression test pins the new behavior: when admin chain is
active, the response must still include one series per configured competitor.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
import pytest_asyncio
from genpano_models import (
    GeoScoreDaily,
    Project,
    ProjectCompetitor,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._brand_dto import CompetitorTrendPoint, CompetitorTrendSeries
from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    user = User(
        id=_new_id(),
        email=f"issue1166-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue 1166 User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def project_with_pinned_competitor(
    db_session: AsyncSession, user: User
) -> Project:
    """Mirror of the live captured shape: 1 primary + 1 pinned competitor +
    GeoScoreDaily rows for the competitor.

    Live evidence the fixture mirrors (from the workflow run above):
    - project_scope.primary_brand_id = 12 ("雅诗兰黛")
    - project_scope.competitor_brand_ids = [2] (理肤泉)
    - period 2026-04-18 .. 2026-05-18
    """
    project = Project(
        user_id=user.id,
        name="Issue 1166 Admin-chain Project",
        primary_brand_id=12,
        industry_id=7,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    # Seed GeoScoreDaily rows for the competitor inside the window (3 days).
    base_day = date(2026, 4, 24)
    for offset, value in enumerate((30.0, 42.0, 35.0)):
        db_session.add(
            GeoScoreDaily(
                brand_id=2,
                date=datetime.combine(base_day + timedelta(days=offset), datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=value,
                mention_rate=0.1,
                avg_sov=0.05,
                avg_sentiment=0.5,
                total_queries=10,
            )
        )
    db_session.add(
        ProjectCompetitor(project_id=project.id, brand_id=2, pinned_by=user.id)
    )
    await db_session.commit()
    return project


@pytest.mark.asyncio
async def test_competitor_trends_keeps_competitor_series_when_admin_chain_serves_primary(
    client,
    user: User,
    project_with_pinned_competitor: Project,
) -> None:
    """Regression for #1166: admin chain must not strip competitor series.

    Before this fix, `get_competitor_trends` early-returned
    `series=[fact_primary_series]` when admin chain was available, silently
    dropping every pinned competitor from the response. The frontend
    `PanoTrendChart` legend (fed from `/competitors/metrics`) then showed the
    competitor names, but the chart had no points to plot → user-reported
    "这里没有竞品的数据" symptom.
    """
    fake_primary_fact = CompetitorTrendSeries(
        brand_id=12,
        brand_name="雅诗兰黛",
        is_primary=True,
        points=[CompetitorTrendPoint(date="2026-04-24", value=0.0)],
    )
    with (
        patch(
            "app.api.v1.projects._brand_service._has_admin_chain",
            return_value=True,
        ),
        patch(
            "app.api.v1.projects._brand_service._fact_primary_trend_series",
            return_value=fake_primary_fact,
        ),
    ):
        resp = await client.get(
            f"/api/v1/projects/{project_with_pinned_competitor.id}/competitors/trends",
            headers=_bearer(user),
            params={
                "brand_id": 12,
                "metric": "geo_score",
                "from": "2026-04-18",
                "to": "2026-05-18",
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()

    brand_ids_in_response = {s["brand_id"] for s in body["series"]}
    assert brand_ids_in_response == {12, 2}, (
        f"Expected both primary (12) and competitor (2) in series, got {brand_ids_in_response}. "
        "Admin-chain code path is dropping competitor series — see #1166."
    )

    primary_series = next(s for s in body["series"] if s["is_primary"])
    competitor_series = next(s for s in body["series"] if not s["is_primary"])

    assert primary_series["brand_id"] == 12
    assert primary_series["points"] == [{"date": "2026-04-24", "value": 0.0}]

    assert competitor_series["brand_id"] == 2
    assert len(competitor_series["points"]) == 3
    assert all(p["value"] is not None for p in competitor_series["points"])


@pytest.mark.asyncio
async def test_competitor_trends_admin_chain_primary_only_when_no_competitors(
    client,
    user: User,
    db_session: AsyncSession,
) -> None:
    """Counterpart: when no competitors are configured, admin chain still yields
    just the primary — pre-fix behavior preserved for that case."""
    project = Project(
        user_id=user.id,
        name="Issue 1166 Solo Project",
        primary_brand_id=12,
        industry_id=7,
    )
    db_session.add(project)
    await db_session.commit()

    fake_primary_fact = CompetitorTrendSeries(
        brand_id=12,
        brand_name="雅诗兰黛",
        is_primary=True,
        points=[CompetitorTrendPoint(date="2026-04-24", value=0.0)],
    )
    with (
        patch(
            "app.api.v1.projects._brand_service._has_admin_chain",
            return_value=True,
        ),
        patch(
            "app.api.v1.projects._brand_service._fact_primary_trend_series",
            return_value=fake_primary_fact,
        ),
        patch(
            "app.api.v1.projects._brand_service.discover_related_brand_ids",
            return_value=[],
        ),
    ):
        resp = await client.get(
            f"/api/v1/projects/{project.id}/competitors/trends",
            headers=_bearer(user),
            params={
                "brand_id": 12,
                "metric": "geo_score",
                "from": "2026-04-18",
                "to": "2026-05-18",
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {s["brand_id"] for s in body["series"]} == {12}
    assert body["series"][0]["is_primary"] is True
