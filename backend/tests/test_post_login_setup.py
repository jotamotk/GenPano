"""Post-login setup flow — needs_onboarding signal + brand search endpoint."""

from __future__ import annotations

import os
import uuid

import pytest
import pytest_asyncio
from genpano_models import Project, User
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
async def user_a(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"a-{uuid.uuid4().hex[:6]}@example.com",
        name="User A",
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
async def user_b(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"b-{uuid.uuid4().hex[:6]}@example.com",
        name="User B",
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
async def seeded_brands(db_session: AsyncSession) -> None:
    """Add the columns the search endpoint reads, then insert test brands.

    The `brands` table stub from `_upstream_stubs.py` only has `id`; production
    Postgres carries name/name_zh/name_en/industry that the search SQL targets.
    SQLite can ALTER TABLE … ADD COLUMN, so we emulate the prod schema here.
    """
    for col in (
        "name TEXT",
        "name_zh TEXT",
        "name_en TEXT",
        "industry TEXT",
    ):
        await db_session.execute(text(f"ALTER TABLE brands ADD COLUMN {col}"))
    await db_session.execute(
        text(
            "INSERT INTO brands (id, name, name_zh, name_en, industry) VALUES "
            "(:id1, :n1, :nz1, :ne1, :i1),"
            "(:id2, :n2, :nz2, :ne2, :i2),"
            "(:id3, :n3, :nz3, :ne3, :i3)"
        ),
        {
            "id1": 1,
            "n1": "Nike",
            "nz1": "耐克",
            "ne1": "Nike",
            "i1": "Sports",
            "id2": 2,
            "n2": "Adidas",
            "nz2": "阿迪达斯",
            "ne2": "Adidas",
            "i2": "Sports",
            "id3": 3,
            "n3": "Apple",
            "nz3": "苹果",
            "ne3": "Apple",
            "i3": "Tech",
        },
    )
    await db_session.commit()


@pytest_asyncio.fixture
async def seeded_name_only_brands(db_session: AsyncSession) -> None:
    """Emulate the legacy/admin brands table shape that only has name."""
    for col in (
        "name TEXT",
        "industry TEXT",
    ):
        await db_session.execute(text(f"ALTER TABLE brands ADD COLUMN {col}"))
    await db_session.execute(
        text("INSERT INTO brands (id, name, industry) VALUES (:id1, :n1, :i1),(:id2, :n2, :i2)"),
        {
            "id1": 12,
            "n1": "雅诗兰黛",
            "i1": "美妆个护",
            "id2": 18,
            "n2": "NIKE",
            "i2": "Sports",
        },
    )
    await db_session.commit()


# ── /api/auth/me — needs_onboarding signal ────────────────────────────────


@pytest.mark.asyncio
async def test_me_needs_onboarding_true_for_new_user(client, user_a):
    resp = await client.get("/api/auth/me", headers=_bearer(user_a))
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == user_a.email
    assert body["needsOnboarding"] is True


@pytest.mark.asyncio
async def test_me_needs_onboarding_false_after_project_created(
    client, user_a, db_session: AsyncSession
):
    db_session.add(
        Project(
            id=_new_id(),
            user_id=user_a.id,
            name="My Project",
            primary_brand_id=1,
        )
    )
    await db_session.commit()

    resp = await client.get("/api/auth/me", headers=_bearer(user_a))
    assert resp.status_code == 200
    assert resp.json()["needsOnboarding"] is False


@pytest.mark.asyncio
async def test_me_needs_onboarding_true_after_project_soft_deleted(
    client, user_a, db_session: AsyncSession
):
    """Soft-deleting the only project re-arms the onboarding guard."""
    from datetime import UTC, datetime

    pid = _new_id()
    db_session.add(
        Project(
            id=pid,
            user_id=user_a.id,
            name="Doomed",
            primary_brand_id=1,
            deleted_at=datetime.now(UTC).replace(tzinfo=None),
        )
    )
    await db_session.commit()

    resp = await client.get("/api/auth/me", headers=_bearer(user_a))
    assert resp.status_code == 200
    assert resp.json()["needsOnboarding"] is True


# ── /api/v1/brands/search ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_requires_auth(client, seeded_brands):
    resp = await client.get("/api/v1/brands/search", params={"q": "Nike"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_search_happy_path_english(client, user_a, seeded_brands):
    resp = await client.get(
        "/api/v1/brands/search",
        params={"q": "Nike"},
        headers=_bearer(user_a),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["brandId"] == 1
    assert items[0]["industry"] == "Sports"
    assert items[0]["isAlreadyMonitoring"] is False


@pytest.mark.asyncio
async def test_search_matches_chinese_name(client, user_a, seeded_brands):
    resp = await client.get(
        "/api/v1/brands/search",
        params={"q": "耐克"},
        headers=_bearer(user_a),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(it["brandId"] == 1 for it in items)


@pytest.mark.asyncio
async def test_search_supports_name_only_legacy_brands_table(
    client, user_a, seeded_name_only_brands
):
    resp = await client.get(
        "/api/v1/brands/search",
        params={"q": "雅诗兰黛"},
        headers=_bearer(user_a),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items == [
        {
            "brandId": 12,
            "brandName": "雅诗兰黛",
            "industry": "美妆个护",
            "isAlreadyMonitoring": False,
        }
    ]


@pytest.mark.asyncio
async def test_search_substring_match_returns_multiple(client, user_a, seeded_brands):
    resp = await client.get(
        "/api/v1/brands/search",
        params={"q": "ap"},  # matches Apple (case-insensitive)
        headers=_bearer(user_a),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert any(it["brandId"] == 3 for it in items)


@pytest.mark.asyncio
async def test_search_empty_query_400(client, user_a, seeded_brands):
    resp = await client.get(
        "/api/v1/brands/search",
        params={"q": ""},
        headers=_bearer(user_a),
    )
    # FastAPI validates min_length=1 → 422 (validation error)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_no_match_returns_empty(client, user_a, seeded_brands):
    resp = await client.get(
        "/api/v1/brands/search",
        params={"q": "nonexistentbrand"},
        headers=_bearer(user_a),
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []


@pytest.mark.asyncio
async def test_search_marks_already_monitoring(
    client, user_a, seeded_brands, db_session: AsyncSession
):
    db_session.add(
        Project(
            id=_new_id(),
            user_id=user_a.id,
            name="Nike Watch",
            primary_brand_id=1,
        )
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/brands/search",
        params={"q": "Nike"},
        headers=_bearer(user_a),
    )
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["brandId"] == 1
    assert items[0]["isAlreadyMonitoring"] is True


@pytest.mark.asyncio
async def test_search_already_monitoring_isolated_per_user(
    client, user_a, user_b, seeded_brands, db_session: AsyncSession
):
    """User B's project doesn't bleed `is_already_monitoring=True` into User A's view."""
    db_session.add(
        Project(
            id=_new_id(),
            user_id=user_b.id,
            name="B Nike",
            primary_brand_id=1,
        )
    )
    await db_session.commit()

    resp = await client.get(
        "/api/v1/brands/search",
        params={"q": "Nike"},
        headers=_bearer(user_a),
    )
    assert resp.status_code == 200
    assert resp.json()["items"][0]["isAlreadyMonitoring"] is False


@pytest.mark.asyncio
async def test_search_limit_respected(client, user_a, seeded_brands):
    resp = await client.get(
        "/api/v1/brands/search",
        params={"q": "a", "limit": 1},  # matches Adidas + Apple at minimum
        headers=_bearer(user_a),
    )
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1


@pytest.mark.asyncio
async def test_search_returns_empty_when_brands_table_lacks_columns(client, user_a):
    """No `seeded_brands` fixture → only `id` column exists; service returns []."""
    resp = await client.get(
        "/api/v1/brands/search",
        params={"q": "Nike"},
        headers=_bearer(user_a),
    )
    assert resp.status_code == 200
    assert resp.json()["items"] == []
