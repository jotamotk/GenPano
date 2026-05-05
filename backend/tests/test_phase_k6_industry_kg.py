"""Phase K.6 — /v1/industries/:iid/kg pulls from kg_* tables."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    GeoScoreDaily,
    KgBrand,
    KgBrandRelation,
    KgCategory,
    KgProduct,
    KgProductRelation,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def auth_user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"k6-{uuid.uuid4().hex[:6]}@example.com",
        name="K6 User",
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
async def kg_seed(db_session: AsyncSession) -> str:
    """Seed kg_* tables + 30d geo_score_daily for two brands."""
    industry_name = "Beauty"
    today = datetime.now().date()

    # Two brands surfaced by 30d geo_score_daily
    for bid in (101, 102):
        for i in range(30):
            d = today - timedelta(days=29 - i)
            db_session.add(
                GeoScoreDaily(
                    brand_id=bid,
                    industry=industry_name,
                    date=datetime.combine(d, datetime.min.time()),
                    target_llm="chatgpt",
                    avg_geo_score=80.0 - (bid - 101) * 5 + i * 0.1,
                    mention_rate=0.6,
                    avg_sov=0.4,
                    avg_sentiment=0.7,
                    total_queries=100,
                )
            )

    # kg_brands rows for richer naming
    db_session.add_all(
        [
            KgBrand(
                brand_id=101,
                industry_id=42,
                primary_name="Acme",
                name_zh="艾克美",
                aliases={"variants": ["ACME", "Acme Inc."]},
                official_domains={"primary": "acme.com"},
                group_id=1,
                status="approved",
            ),
            KgBrand(
                brand_id=102,
                industry_id=42,
                primary_name="Beta",
                name_zh="贝塔",
                group_id=2,
                status="approved",
            ),
        ]
    )

    # kg_categories tree (root + child) under industry 42
    root_cat = KgCategory(
        industry_id=42,
        parent_id=None,
        name_zh="护肤",
        name_en="Skincare",
        level=1,
        slug="skincare",
        status="approved",
    )
    db_session.add(root_cat)
    await db_session.flush()
    child_cat = KgCategory(
        industry_id=42,
        parent_id=root_cat.id,
        name_zh="精华",
        level=2,
        slug="serum",
        status="approved",
    )
    db_session.add(child_cat)
    await db_session.flush()

    # kg_products under brand 101
    db_session.add_all(
        [
            KgProduct(
                product_id=901,
                brand_id=101,
                category_id=child_cat.id,
                primary_name="Acme Glow Serum",
                status="approved",
            ),
            KgProduct(
                product_id=902,
                brand_id=101,
                category_id=child_cat.id,
                primary_name="Acme Lite Serum",
                status="approved",
            ),
        ]
    )

    # kg_brand_relations COMPETES_WITH (101, 102)
    db_session.add(
        KgBrandRelation(
            id=_new_id(),
            brand_a_id=101,
            brand_b_id=102,
            type="COMPETES_WITH",
            confidence=0.85,
            source="admin",
            evidence={"snippets": ["Acme vs Beta"]},
        )
    )

    # kg_product_relations UPGRADES_TO (902, 901)
    db_session.add(
        KgProductRelation(
            id=_new_id(),
            product_a_id=902,
            product_b_id=901,
            type="UPGRADES_TO",
            confidence=0.8,
            source="admin",
        )
    )

    await db_session.commit()
    return industry_name


@pytest.mark.asyncio
async def test_kg_includes_kg_brand_names(client, auth_user, kg_seed):
    resp = await client.get(
        f"/api/v1/industries/42/kg?name={kg_seed}&depth=2",
        headers=_bearer(auth_user),
    )
    body = resp.json()
    brand_nodes = [n for n in body["nodes"] if n["type"] == "brand"]
    names = {n["name"] for n in brand_nodes}
    # primary_name from kg_brands instead of f"brand-{id}" fallback
    assert "Acme" in names
    assert "Beta" in names


@pytest.mark.asyncio
async def test_kg_includes_categories(client, auth_user, kg_seed):
    resp = await client.get(
        f"/api/v1/industries/42/kg?name={kg_seed}",
        headers=_bearer(auth_user),
    )
    body = resp.json()
    cat_nodes = [n for n in body["nodes"] if n["type"] == "category"]
    assert {n["name"] for n in cat_nodes} == {"护肤", "精华"}
    # child category points to root (BELONGS_TO with category as target,
    # category as source)
    cat_belongs = [
        e
        for e in body["edges"]
        if e["type"] == "BELONGS_TO" and e["target"].startswith("category-")
    ]
    assert len(cat_belongs) == 2


@pytest.mark.asyncio
async def test_kg_includes_brand_relations(client, auth_user, kg_seed):
    resp = await client.get(
        f"/api/v1/industries/42/kg?name={kg_seed}",
        headers=_bearer(auth_user),
    )
    body = resp.json()
    competes = [e for e in body["edges"] if e["type"] == "COMPETES_WITH"]
    assert len(competes) == 1
    assert {competes[0]["source"], competes[0]["target"]} == {"brand-101", "brand-102"}


@pytest.mark.asyncio
async def test_kg_depth_2_includes_products(client, auth_user, kg_seed):
    resp = await client.get(
        f"/api/v1/industries/42/kg?name={kg_seed}&depth=2",
        headers=_bearer(auth_user),
    )
    body = resp.json()
    prod_nodes = [n for n in body["nodes"] if n["type"] == "product"]
    assert len(prod_nodes) == 2
    of_brand = [e for e in body["edges"] if e["type"] == "OF_BRAND"]
    in_category = [e for e in body["edges"] if e["type"] == "IN_CATEGORY"]
    assert len(of_brand) == 2
    assert len(in_category) == 2
    upgrades = [e for e in body["edges"] if e["type"] == "UPGRADES_TO"]
    assert len(upgrades) == 1


@pytest.mark.asyncio
async def test_kg_depth_1_omits_products(client, auth_user, kg_seed):
    resp = await client.get(
        f"/api/v1/industries/42/kg?name={kg_seed}&depth=1",
        headers=_bearer(auth_user),
    )
    body = resp.json()
    prod_nodes = [n for n in body["nodes"] if n["type"] == "product"]
    assert prod_nodes == []


@pytest.mark.asyncio
async def test_kg_no_data_returns_empty_state(client, auth_user):
    resp = await client.get(
        "/api/v1/industries/999/kg?name=NotSeeded",
        headers=_bearer(auth_user),
    )
    body = resp.json()
    assert body["state"] == "empty"
    assert body["nodes"] == [
        {
            "id": "industry-999",
            "type": "industry",
            "name": "NotSeeded",
            "metadata": {"depth": 0},
        }
    ]
    assert body["edges"] == []
