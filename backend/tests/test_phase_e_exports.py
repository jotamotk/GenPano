"""Phase E — exports + brand submissions + simulator endpoints."""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from genpano_models import IndustryPricingParams, Project, User
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
        email=f"e-{uuid.uuid4().hex[:6]}@example.com",
        name="Export User",
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
    p = Project(user_id=user.id, name="Export Proj", primary_brand_id=42, industry_id=7)
    db_session.add(p)
    # Pre-seed industry pricing for simulator
    db_session.add(
        IndustryPricingParams(
            industry_id=7,
            tier1_unit_price_cny=10000,
            tier2_unit_price_cny=5000,
            tier3_unit_price_cny=2000,
            tier4_unit_price_cny=500,
        )
    )
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p


# ── Exports ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_export_returns_202(client, user, project):
    resp = await client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=_bearer(user),
        json={"export_type": "mention_list"},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["export_type"] == "mention_list"


@pytest.mark.asyncio
async def test_export_status_polling(client, user, project):
    eid = (
        await client.post(
            f"/api/v1/projects/{project.id}/exports",
            headers=_bearer(user),
            json={"export_type": "citation_list"},
        )
    ).json()["id"]
    resp = await client.get(f"/api/v1/projects/{project.id}/exports/{eid}", headers=_bearer(user))
    assert resp.status_code == 200
    assert resp.json()["id"] == eid


@pytest.mark.asyncio
async def test_export_quota_exceeded_returns_429(client, user, project):
    """20/day quota — 21st 429."""
    for _ in range(20):
        resp = await client.post(
            f"/api/v1/projects/{project.id}/exports",
            headers=_bearer(user),
            json={"export_type": "topic_coverage"},
        )
        assert resp.status_code == 202
    resp = await client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=_bearer(user),
        json={"export_type": "mention_list"},
    )
    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "rate_limit_exceeded"


@pytest.mark.asyncio
async def test_export_invalid_type_returns_422(client, user, project):
    resp = await client.post(
        f"/api/v1/projects/{project.id}/exports",
        headers=_bearer(user),
        json={"export_type": "not_a_real_type"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_export_cross_tenant_returns_404(client, user, project, db_session):
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
        f"/api/v1/projects/{project.id}/exports",
        headers=_bearer(other),
        json={"export_type": "mention_list"},
    )
    assert resp.status_code == 404


# ── Brand Submission ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_brand_returns_201(client, user):
    resp = await client.post(
        "/api/v1/brands/submissions",
        headers=_bearer(user),
        json={
            "proposed_name": "NewBrand Inc",
            "proposed_industry_id": 1,
            "proposed_aliases": ["nb", "newbrand"],
            "notes": "Up-and-coming player",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "pending"
    assert body["proposed_name"] == "NewBrand Inc"
    assert body["user_id"] == user.id


@pytest.mark.asyncio
async def test_list_my_submissions(client, user):
    await client.post(
        "/api/v1/brands/submissions",
        headers=_bearer(user),
        json={"proposed_name": "First"},
    )
    await client.post(
        "/api/v1/brands/submissions",
        headers=_bearer(user),
        json={"proposed_name": "Second"},
    )
    resp = await client.get("/api/v1/brands/me/submissions", headers=_bearer(user))
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) >= 2


# ── Simulator ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_simulator_basic_run(client, user, project):
    resp = await client.post(
        f"/api/v1/projects/{project.id}/simulator/run",
        headers=_bearer(user),
        json={
            "brand_id": 42,
            "delta_by_tier": {"1": 5, "2": 10, "3": 0, "4": 0},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "current_pano_a" in body
    assert "simulated_pano_a" in body
    assert body["delta"] == round(body["simulated_pano_a"] - body["current_pano_a"], 2)
    # base price equivalent computed from industry_pricing_params
    # 5 * 10000 + 10 * 5000 = 100000
    assert body["base_price_equivalent_cny"] == 100000.0


@pytest.mark.asyncio
async def test_simulator_no_pricing_returns_zero_price(client, user, db_session):
    """Project with industry_id but no pricing seed → base_price = 0."""
    p = Project(user_id=user.id, name="No Pricing", primary_brand_id=99, industry_id=999)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    resp = await client.post(
        f"/api/v1/projects/{p.id}/simulator/run",
        headers=_bearer(user),
        json={"brand_id": 99, "delta_by_tier": {"1": 5}},
    )
    assert resp.status_code == 200
    assert resp.json()["base_price_equivalent_cny"] == 0.0


@pytest.mark.asyncio
async def test_simulator_invalid_confidence_422(client, user, project):
    resp = await client.post(
        f"/api/v1/projects/{project.id}/simulator/run",
        headers=_bearer(user),
        json={
            "brand_id": 42,
            "delta_by_tier": {"1": 1},
            "confidence_override": 1.5,  # > 1.0
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_simulator_cross_tenant_404(client, user, project, db_session):
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
        f"/api/v1/projects/{project.id}/simulator/run",
        headers=_bearer(other),
        json={"brand_id": 42, "delta_by_tier": {"1": 1}},
    )
    assert resp.status_code == 404
