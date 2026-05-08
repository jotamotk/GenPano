"""Phase X — GET /api/admin/brands (topic-plan brand picker).

Regression for the bug where every admin brand dropdown (LLM 自动添加产品,
LLM 生成 Brand Segment, segment / product filter selects, etc.) silently
showed no data: the route was wired to ``current_admin_operator`` which
requires a Bearer JWT, while the admin SPA only sends the cookie session
set by ``current_admin``. The mismatch caused a 401 that the SPA caught
and rendered as an empty list.

Tests verify:
    * unauthenticated → 401
    * authenticated via the cookie-session admin → 200 + brand list
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def admin_operator(db_session: AsyncSession) -> AsyncGenerator[AdminUser, None]:
    from app.api.admin.auth.router import current_admin
    from app.main import app

    a = AdminUser(
        id=_new_id(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="$2b$04$dummyhashfortestsdummyhashfortestsdummyhashfortest",
        role="super_admin",
        status="active",
    )
    db_session.add(a)
    await db_session.commit()

    async def _override_current_admin() -> AdminUser:
        return a

    app.dependency_overrides[current_admin] = _override_current_admin
    try:
        yield a
    finally:
        app.dependency_overrides.pop(current_admin, None)


def _patch_brands(monkeypatch, brands):
    """Stub the schema-aware brand picker query."""
    import app.api.admin.router  # noqa: F401

    bm = sys.modules["app.api.admin.router"].brand_management_db
    monkeypatch.setattr(
        bm, "fetch_brand_options_with_topic_count", AsyncMock(return_value=list(brands))
    )


@pytest.mark.asyncio
async def test_admin_brands_unauth_401(client):
    resp = await client.get("/api/admin/brands")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_brands_returns_list_for_cookie_admin(client, admin_operator, monkeypatch):
    _patch_brands(
        monkeypatch,
        [
            {
                "id": 1,
                "name": "Brand A",
                "industry": "Beauty",
                "topic_count": 3,
            },
            {
                "id": 2,
                "name": "Brand B",
                "industry": "Tech",
                "topic_count": 0,
            },
        ],
    )
    resp = await client.get("/api/admin/brands")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["brands"]) == 2
    assert body["brands"][0]["name"] == "Brand A"


@pytest.mark.asyncio
async def test_admin_brands_empty_when_table_missing(client, admin_operator, monkeypatch):
    _patch_brands(monkeypatch, [])
    resp = await client.get("/api/admin/brands")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"success": True, "brands": []}
