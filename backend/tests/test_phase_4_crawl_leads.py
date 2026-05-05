"""Phase 4 — crawl-requests + commercial leads endpoints."""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from genpano_models import Project, User
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
        email=f"c-{uuid.uuid4().hex[:6]}@example.com",
        name="Crawl User",
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
    p = Project(user_id=user.id, name="Crawl Project", primary_brand_id=42)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p


# ── crawl ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_crawl_returns_202(client, user, project):
    resp = await client.post(
        f"/api/v1/projects/{project.id}/crawl-requests",
        headers=_bearer(user),
        json={"brand_id": 42, "scope": {"engines": ["chatgpt", "doubao"]}},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert body["brand_id"] == 42
    assert body["created_by"] == user.id


@pytest.mark.asyncio
async def test_get_crawl_status(client, user, project):
    cr = (
        await client.post(
            f"/api/v1/projects/{project.id}/crawl-requests",
            headers=_bearer(user),
            json={},
        )
    ).json()
    crawl_id = cr["id"]

    resp = await client.get(
        f"/api/v1/projects/{project.id}/crawl-requests/{crawl_id}",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == crawl_id


@pytest.mark.asyncio
async def test_crawl_quota_exceeded_returns_429(client, user, project):
    """5/day quota — 6th request 429."""
    for _ in range(5):
        resp = await client.post(
            f"/api/v1/projects/{project.id}/crawl-requests",
            headers=_bearer(user),
            json={},
        )
        assert resp.status_code == 202

    resp = await client.post(
        f"/api/v1/projects/{project.id}/crawl-requests",
        headers=_bearer(user),
        json={},
    )
    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "rate_limit_exceeded"


@pytest.mark.asyncio
async def test_crawl_cross_tenant_returns_404(client, user, project, db_session):
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
        f"/api/v1/projects/{project.id}/crawl-requests",
        headers=_bearer(other),
        json={},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_crawl_get_unknown_id_returns_404(client, user, project):
    resp = await client.get(
        f"/api/v1/projects/{project.id}/crawl-requests/nonexistent-id",
        headers=_bearer(user),
    )
    assert resp.status_code == 404


# ── leads ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_lead_returns_201(client, user, project):
    resp = await client.post(
        "/api/v1/leads/",
        headers=_bearer(user),
        json={
            "source": "diagnostics",
            "project_id": project.id,
            "context": {"brand": "Test", "concern": "visibility"},
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["source"] == "diagnostics"
    assert body["status"] == "new"
    assert body["user_id"] == user.id
    assert body["project_id"] == project.id


@pytest.mark.asyncio
async def test_create_lead_minimal_body(client, user):
    resp = await client.post(
        "/api/v1/leads/",
        headers=_bearer(user),
        json={"source": "cta_modal"},
    )
    assert resp.status_code == 201
    assert resp.json()["source"] == "cta_modal"


@pytest.mark.asyncio
async def test_create_lead_no_auth_returns_401(client):
    resp = await client.post(
        "/api/v1/leads/",
        json={"source": "anonymous"},
    )
    assert resp.status_code == 401
