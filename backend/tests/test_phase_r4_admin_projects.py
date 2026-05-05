"""Phase R.4 — admin projects sub-router (cross-tenant view)."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import Project, ProjectCompetitor, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def admin_operator(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        name="Admin",
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
async def regular_user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"u-{uuid.uuid4().hex[:6]}@example.com",
        name="Regular",
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
async def two_users_with_projects(
    db_session: AsyncSession,
) -> tuple[User, User, list[Project]]:
    u_a = User(
        id=_new_id(),
        email=f"a-{uuid.uuid4().hex[:6]}@example.com",
        name="A",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    u_b = User(
        id=_new_id(),
        email=f"b-{uuid.uuid4().hex[:6]}@example.com",
        name="B",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add_all([u_a, u_b])
    await db_session.commit()

    projects = [
        Project(user_id=u_a.id, name="A1", primary_brand_id=10, industry_id=1),
        Project(user_id=u_a.id, name="A2", primary_brand_id=11, industry_id=2),
        Project(user_id=u_b.id, name="B1", primary_brand_id=20, industry_id=1),
        Project(
            user_id=u_b.id,
            name="B-deleted",
            primary_brand_id=21,
            industry_id=1,
            deleted_at=_now() - timedelta(days=1),
        ),
        Project(user_id=u_b.id, name="B-no-brand", industry_id=1),
    ]
    db_session.add_all(projects)
    await db_session.commit()
    for p in projects:
        await db_session.refresh(p, ["competitors"])
    return u_a, u_b, projects


# ── /list ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_returns_active_only_by_default(client, admin_operator, two_users_with_projects):
    resp = await client.get("/api/admin/projects/", headers=_bearer(admin_operator))
    assert resp.status_code == 200
    body = resp.json()
    # 4 active (excludes 1 soft-deleted)
    assert body["returned"] == 4
    names = {it["name"] for it in body["items"]}
    assert "B-deleted" not in names


@pytest.mark.asyncio
async def test_list_include_deleted(client, admin_operator, two_users_with_projects):
    resp = await client.get(
        "/api/admin/projects/?include_deleted=true",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert body["returned"] == 5
    deleted = [it for it in body["items"] if it["name"] == "B-deleted"]
    assert len(deleted) == 1
    assert deleted[0]["deleted_at"] is not None


@pytest.mark.asyncio
async def test_list_filter_by_user_id(client, admin_operator, two_users_with_projects):
    u_a, _u_b, _ = two_users_with_projects
    resp = await client.get(
        f"/api/admin/projects/?user_id={u_a.id}",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    assert body["returned"] == 2  # A1 + A2
    for it in body["items"]:
        assert it["user_id"] == u_a.id


@pytest.mark.asyncio
async def test_list_filter_by_industry_id(client, admin_operator, two_users_with_projects):
    resp = await client.get(
        "/api/admin/projects/?industry_id=1",
        headers=_bearer(admin_operator),
    )
    body = resp.json()
    # active projects with industry_id=1: A1, B1, B-no-brand (3)
    assert body["returned"] == 3
    for it in body["items"]:
        assert it["industry_id"] == 1


@pytest.mark.asyncio
async def test_list_pagination(client, admin_operator, two_users_with_projects):
    resp = await client.get("/api/admin/projects/?limit=2", headers=_bearer(admin_operator))
    assert resp.json()["returned"] == 2


@pytest.mark.asyncio
async def test_list_non_admin_403(client, regular_user):
    resp = await client.get("/api/admin/projects/", headers=_bearer(regular_user))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_unauth_401(client):
    resp = await client.get("/api/admin/projects/")
    assert resp.status_code == 401


# ── /stats ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stats_zero_state(client, admin_operator):
    resp = await client.get("/api/admin/projects/stats", headers=_bearer(admin_operator))
    body = resp.json()
    counters = body["counters"]
    assert counters["total"] == 0
    assert counters["active"] == 0
    assert counters["soft_deleted"] == 0
    assert counters["missing_primary_brand"] == 0
    assert body["top_users_by_project_count"] == []


@pytest.mark.asyncio
async def test_stats_with_fixture(client, admin_operator, two_users_with_projects):
    resp = await client.get("/api/admin/projects/stats", headers=_bearer(admin_operator))
    body = resp.json()
    counters = body["counters"]
    # 5 total = 4 active + 1 soft-deleted
    assert counters["total"] == 5
    assert counters["active"] == 4
    assert counters["soft_deleted"] == 1
    # missing_primary_brand counts B-no-brand (active; primary_brand_id is null)
    # plus we COULD count soft-deleted ones; aggregate spans whole table
    assert counters["missing_primary_brand"] >= 1
    # Top users (excludes soft-deleted): A has 2 active, B has 2 active
    top = body["top_users_by_project_count"]
    assert len(top) == 2
    counts = sorted(t["project_count"] for t in top)
    assert counts == [2, 2]


# ── /{id} detail ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_detail_includes_competitors(
    client, admin_operator, two_users_with_projects, db_session: AsyncSession
):
    _, _, projects = two_users_with_projects
    p = projects[0]  # A1
    db_session.add_all(
        [
            ProjectCompetitor(project_id=p.id, brand_id=99),
            ProjectCompetitor(project_id=p.id, brand_id=100),
        ]
    )
    await db_session.commit()

    resp = await client.get(f"/api/admin/projects/{p.id}", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["id"] == p.id
    assert len(body["competitors"]) == 2
    brand_ids = {c["brand_id"] for c in body["competitors"]}
    assert brand_ids == {99, 100}


@pytest.mark.asyncio
async def test_detail_includes_soft_deleted(client, admin_operator, two_users_with_projects):
    _, _, projects = two_users_with_projects
    deleted = next(p for p in projects if p.name == "B-deleted")
    resp = await client.get(f"/api/admin/projects/{deleted.id}", headers=_bearer(admin_operator))
    body = resp.json()
    assert body["deleted_at"] is not None


@pytest.mark.asyncio
async def test_detail_unknown_404(client, admin_operator):
    resp = await client.get("/api/admin/projects/no-such-id", headers=_bearer(admin_operator))
    assert resp.status_code == 404


# ── audit gate ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_gate_with_admin_projects_no_writes():
    """projects sub-router has only GET endpoints — gate must still pass."""
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
