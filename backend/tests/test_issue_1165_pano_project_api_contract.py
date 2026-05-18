"""Issue #1165: Pano Project/Brand API contract regressions."""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import GeoScoreDaily, Project, ProjectCompetitor, User
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
    user = User(
        id=_new_id(),
        email=f"issue1165-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue 1165 User",
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
async def bestcoffer_project(db_session: AsyncSession, user: User) -> Project:
    project = Project(
        user_id=user.id,
        name="BestCoffer Project",
        primary_brand_id=24,
        industry_id=7,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    today = date(2026, 5, 13)
    for brand_id, score in ((24, 74.0), (99, 68.0), (12, 91.0)):
        for offset in range(3):
            day = today - timedelta(days=2 - offset)
            db_session.add(
                GeoScoreDaily(
                    brand_id=brand_id,
                    date=datetime.combine(day, datetime.min.time()),
                    target_llm="chatgpt",
                    avg_geo_score=score + offset,
                    mention_rate=0.4,
                    avg_sov=0.3,
                    avg_sentiment=0.6,
                    total_queries=50,
                )
            )
    db_session.add(ProjectCompetitor(project_id=project.id, brand_id=99, pinned_by=user.id))
    await db_session.commit()
    return project


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "overview",
        "competitors/metrics",
        "competitors/trends",
    ],
)
async def test_project_endpoints_reject_unrelated_brand_override(
    client,
    user: User,
    bestcoffer_project: Project,
    path: str,
) -> None:
    """A stale brandId from another project must not replace the Project brand."""
    resp = await client.get(
        f"/api/v1/projects/{bestcoffer_project.id}/{path}",
        headers=_bearer(user),
        params={"brand_id": 12},
    )

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "validation_error"
    assert detail["field"] == "brand_id"
    assert detail["reason"] == "must match project primary brand or pinned competitor"


@pytest.mark.asyncio
async def test_competitor_trends_allow_project_competitor_with_concrete_dates(
    client,
    user: User,
    bestcoffer_project: Project,
) -> None:
    resp = await client.get(
        f"/api/v1/projects/{bestcoffer_project.id}/competitors/trends",
        headers=_bearer(user),
        params={
            "brand_id": 99,
            "metric": "geo_score",
            "from": "2026-05-11",
            "to": "2026-05-13",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["project_id"] == bestcoffer_project.id
    assert body["series"]
    assert {series["brand_id"] for series in body["series"]} == {99}
    points = body["series"][0]["points"]
    assert [point["date"] for point in points] == [
        "2026-05-11",
        "2026-05-12",
        "2026-05-13",
    ]
    assert all(not point["date"].startswith("D") for point in points)
