"""Phase 1 — /v1/projects CRUD + multi-tenant isolation tests.

Per ADR-005: cross-tenant access returns 404 (not 403).
"""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from genpano_models import User
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

# Ensure JWT secret is set for tests
os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def two_users(db_session: AsyncSession) -> tuple[User, User]:
    """Create two distinct users to exercise cross-tenant isolation."""
    user_a = User(
        id=_new_id(),
        email=f"a-{uuid.uuid4().hex[:6]}@example.com",
        name="User A",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    user_b = User(
        id=_new_id(),
        email=f"b-{uuid.uuid4().hex[:6]}@example.com",
        name="User B",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add_all([user_a, user_b])
    await db_session.commit()
    return user_a, user_b


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_list_projects_empty_for_new_user(client, two_users):
    user_a, _ = two_users
    resp = await client.get("/api/v1/projects/", headers=_bearer(user_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"items": [], "total": 0}


@pytest.mark.asyncio
async def test_create_and_list_project(client, two_users):
    user_a, _ = two_users
    resp = await client.post(
        "/api/v1/projects/",
        headers=_bearer(user_a),
        json={"name": "My Project", "industry_id": 1},
    )
    assert resp.status_code == 201
    project = resp.json()
    assert project["name"] == "My Project"
    assert project["user_id"] == user_a.id
    assert project["is_active"] is True
    assert project["competitors"] == []

    # Verify in list
    resp = await client.get("/api/v1/projects/", headers=_bearer(user_a))
    assert resp.json()["total"] == 1


@pytest.mark.asyncio
async def test_create_project_duplicate_name_409(client, two_users):
    user_a, _ = two_users
    headers = _bearer(user_a)
    await client.post("/api/v1/projects/", headers=headers, json={"name": "Dup"})
    resp = await client.post("/api/v1/projects/", headers=headers, json={"name": "Dup"})
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "project_name_taken"


@pytest.mark.asyncio
async def test_no_auth_returns_401(client):
    resp = await client.get("/api/v1/projects/")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_cross_tenant_returns_404_not_403(client, two_users):
    """ADR-005: cross-tenant access deny via 404, not 403."""
    user_a, user_b = two_users
    # User A creates a project
    resp = await client.post(
        "/api/v1/projects/", headers=_bearer(user_a), json={"name": "A's"}
    )
    project_id = resp.json()["id"]

    # User B tries to access — must 404, not 403
    resp = await client.get(
        f"/api/v1/projects/{project_id}", headers=_bearer(user_b)
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_patch_project_name(client, two_users):
    user_a, _ = two_users
    headers = _bearer(user_a)
    resp = await client.post("/api/v1/projects/", headers=headers, json={"name": "old"})
    pid = resp.json()["id"]

    resp = await client.patch(
        f"/api/v1/projects/{pid}", headers=headers, json={"name": "new"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "new"


@pytest.mark.asyncio
async def test_soft_delete_project(client, two_users):
    user_a, _ = two_users
    headers = _bearer(user_a)
    pid = (
        await client.post("/api/v1/projects/", headers=headers, json={"name": "x"})
    ).json()["id"]

    resp = await client.delete(f"/api/v1/projects/{pid}", headers=headers)
    assert resp.status_code == 204

    # Listing now empty (soft-deleted excluded)
    resp = await client.get("/api/v1/projects/", headers=headers)
    assert resp.json()["total"] == 0

    # Direct GET → 404
    resp = await client.get(f"/api/v1/projects/{pid}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_add_remove_competitor(client, two_users):
    user_a, _ = two_users
    headers = _bearer(user_a)
    pid = (
        await client.post(
            "/api/v1/projects/", headers=headers, json={"name": "comp"}
        )
    ).json()["id"]

    resp = await client.post(
        f"/api/v1/projects/{pid}/competitors",
        headers=headers,
        json={"brand_id": 42},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert any(c["brand_id"] == 42 for c in body["competitors"])

    # Idempotent: re-add same brand → still 201, no duplicate
    resp = await client.post(
        f"/api/v1/projects/{pid}/competitors",
        headers=headers,
        json={"brand_id": 42},
    )
    assert resp.status_code == 201
    assert sum(1 for c in resp.json()["competitors"] if c["brand_id"] == 42) == 1

    # Remove
    resp = await client.delete(
        f"/api/v1/projects/{pid}/competitors/42", headers=headers
    )
    assert resp.status_code == 204

    # Verify gone
    resp = await client.get(f"/api/v1/projects/{pid}", headers=headers)
    assert all(c["brand_id"] != 42 for c in resp.json()["competitors"])


@pytest.mark.asyncio
async def test_competitor_capacity_409(client, two_users):
    user_a, _ = two_users
    headers = _bearer(user_a)
    pid = (
        await client.post(
            "/api/v1/projects/", headers=headers, json={"name": "cap"}
        )
    ).json()["id"]

    for brand_id in range(1, 11):
        resp = await client.post(
            f"/api/v1/projects/{pid}/competitors",
            headers=headers,
            json={"brand_id": brand_id},
        )
        assert resp.status_code == 201

    # 11th should 409
    resp = await client.post(
        f"/api/v1/projects/{pid}/competitors",
        headers=headers,
        json={"brand_id": 11},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "competitor_capacity_full"
