"""Phase RP.2 — section matrix builder + report endpoints."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import GeoScoreDaily, Project, ReportShareToken, User
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
        email=f"rp-{uuid.uuid4().hex[:6]}@example.com",
        name="Reports User",
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
async def project(db_session: AsyncSession, user: User) -> Project:
    p = Project(
        user_id=user.id,
        name="RP Project",
        primary_brand_id=42,
        industry_id=1,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    today = datetime.now().date()
    for i in range(7):
        d = today - timedelta(days=6 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=80.0 + i,
                mention_rate=0.6,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=100,
            )
        )
    await db_session.commit()
    return p


# ── builder unit ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_section_matrix_known_keys() -> None:
    from app.reports import SECTION_MATRIX

    assert set(SECTION_MATRIX.keys()) == {
        "weekly",
        "monthly",
        "on_demand",
        "lead_diagnostic",
    }


@pytest.mark.asyncio
async def test_build_report_weekly_returns_sections(db_session, project) -> None:
    from app.reports import build_report

    payload = await build_report(db_session, project=project, report_type="weekly")
    assert payload["report_type"] == "weekly"
    assert payload["project_id"] == project.id
    types = [s["section_type"] for s in payload["sections"]]
    assert "executive_summary" in types
    assert "pano_score" in types


@pytest.mark.asyncio
async def test_build_report_invalid_type_raises(db_session, project) -> None:
    from app.reports import build_report

    with pytest.raises(ValueError):
        await build_report(db_session, project=project, report_type="not_a_type")


# ── endpoints ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_report_returns_payload(client, user, project) -> None:
    resp = await client.post(
        f"/api/v1/projects/{project.id}/reports",
        headers=_bearer(user),
        json={"report_type": "weekly", "locale": "zh-CN"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "done"
    assert body["payload"] is not None
    assert body["payload"]["report_type"] == "weekly"
    assert any(s["section_type"] == "executive_summary" for s in body["payload"]["sections"])


@pytest.mark.asyncio
async def test_list_reports_after_create(client, user, project) -> None:
    await client.post(
        f"/api/v1/projects/{project.id}/reports",
        headers=_bearer(user),
        json={"report_type": "weekly"},
    )
    resp = await client.get(
        f"/api/v1/projects/{project.id}/reports",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


@pytest.mark.asyncio
async def test_create_report_unknown_type_422(client, user, project) -> None:
    resp = await client.post(
        f"/api/v1/projects/{project.id}/reports",
        headers=_bearer(user),
        json={"report_type": "foobar"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_report_cross_tenant_404(client, user, project, db_session) -> None:
    """Another user must not be able to create a report on this project."""
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

    resp = await client.post(
        f"/api/v1/projects/{project.id}/reports",
        headers=_bearer(other),
        json={"report_type": "weekly"},
    )
    assert resp.status_code == 404


# ── share token lifecycle ──────────────────────────────────────


@pytest.mark.asyncio
async def test_share_token_create_and_public_read(client, user, project) -> None:
    rid = (
        await client.post(
            f"/api/v1/projects/{project.id}/reports",
            headers=_bearer(user),
            json={"report_type": "weekly"},
        )
    ).json()["id"]

    share = await client.post(
        f"/api/v1/projects/{project.id}/reports/{rid}/share",
        headers=_bearer(user),
        json={"expires_in_hours": 24},
    )
    assert share.status_code == 201
    token = share.json()["token"]

    # Public read — no auth header
    pub = await client.get(f"/reports/public/{token}")
    assert pub.status_code == 200
    assert pub.json()["payload"]["report_type"] == "weekly"
    assert pub.json()["view_count"] == 1

    # Hitting again increments view_count
    pub2 = await client.get(f"/reports/public/{token}")
    assert pub2.status_code == 200
    assert pub2.json()["view_count"] == 2


@pytest.mark.asyncio
async def test_share_token_revoke_returns_410(client, user, project) -> None:
    rid = (
        await client.post(
            f"/api/v1/projects/{project.id}/reports",
            headers=_bearer(user),
            json={"report_type": "weekly"},
        )
    ).json()["id"]

    token = (
        await client.post(
            f"/api/v1/projects/{project.id}/reports/{rid}/share",
            headers=_bearer(user),
            json={"expires_in_hours": 24},
        )
    ).json()["token"]

    revoke = await client.delete(
        f"/api/v1/projects/{project.id}/reports/{rid}/share/{token}",
        headers=_bearer(user),
    )
    assert revoke.status_code == 204

    pub = await client.get(f"/reports/public/{token}")
    assert pub.status_code == 410


@pytest.mark.asyncio
async def test_share_token_expired_returns_410(client, user, project, db_session) -> None:
    rid = (
        await client.post(
            f"/api/v1/projects/{project.id}/reports",
            headers=_bearer(user),
            json={"report_type": "weekly"},
        )
    ).json()["id"]

    # Create token with extremely short expiry — manipulate expires_at directly
    token = (
        await client.post(
            f"/api/v1/projects/{project.id}/reports/{rid}/share",
            headers=_bearer(user),
            json={"expires_in_hours": 1},
        )
    ).json()["token"]

    from sqlalchemy import select

    row = (
        await db_session.execute(select(ReportShareToken).where(ReportShareToken.token == token))
    ).scalar_one()
    row.expires_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=1)
    await db_session.commit()

    pub = await client.get(f"/reports/public/{token}")
    assert pub.status_code == 410


@pytest.mark.asyncio
async def test_public_unknown_token_404(client) -> None:
    pub = await client.get("/reports/public/totally_invalid_xyz")
    assert pub.status_code == 404


# ── B2-1: from_date/to_date must round-trip through scope ───────


@pytest.mark.asyncio
async def test_on_demand_report_period_persists_across_reads(client, user, project) -> None:
    """On-demand report stores from_date/to_date and re-reads use them.

    Regression: previously scope.from_date / to_date were written but
    discarded on read — every detail / public view rebuilt with today's
    default window.
    """
    create = await client.post(
        f"/api/v1/projects/{project.id}/reports",
        headers=_bearer(user),
        json={
            "report_type": "on_demand",
            "from_date": "2026-01-01",
            "to_date": "2026-01-31",
        },
    )
    assert create.status_code == 201
    body = create.json()
    rid = body["id"]
    assert body["payload"]["period"] == {"from": "2026-01-01", "to": "2026-01-31"}

    # Detail re-read
    detail = await client.get(
        f"/api/v1/projects/{project.id}/reports/{rid}",
        headers=_bearer(user),
    )
    assert detail.status_code == 200
    assert detail.json()["payload"]["period"] == {
        "from": "2026-01-01",
        "to": "2026-01-31",
    }

    # Public share read
    share = (
        await client.post(
            f"/api/v1/projects/{project.id}/reports/{rid}/share",
            headers=_bearer(user),
            json={"expires_in_hours": 24},
        )
    ).json()
    pub = await client.get(f"/reports/public/{share['token']}")
    assert pub.status_code == 200
    assert pub.json()["payload"]["period"] == {
        "from": "2026-01-01",
        "to": "2026-01-31",
    }
