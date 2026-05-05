"""Phase K — Knowledge Graph 6 tables ORM tests."""

from __future__ import annotations

import os

import pytest
from genpano_models import (
    KgBrand,
    KgBrandRelation,
    KgCategory,
    KgProduct,
    KgProductRelation,
    KgRelationCandidate,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


@pytest.mark.asyncio
async def test_kg_categories_tree(db_session: AsyncSession) -> None:
    root = KgCategory(name_zh="Beauty", level=1)
    db_session.add(root)
    await db_session.commit()
    child = KgCategory(name_zh="Foundation", level=2, parent_id=root.id)
    db_session.add(child)
    await db_session.commit()
    assert child.parent_id == root.id


@pytest.mark.asyncio
async def test_kg_brand_unique_brand_id(db_session: AsyncSession) -> None:
    db_session.add(KgBrand(brand_id=42, primary_name="Test Brand"))
    await db_session.commit()
    # Trying to insert another with same brand_id should fail unique constraint
    db_session.add(KgBrand(brand_id=42, primary_name="Dup Brand"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_kg_product_basic(db_session: AsyncSession) -> None:
    db_session.add(KgProduct(product_id=100, brand_id=42, primary_name="ProductA"))
    await db_session.commit()
    from sqlalchemy import select

    row = (
        await db_session.execute(select(KgProduct).where(KgProduct.product_id == 100))
    ).scalar_one()
    assert row.primary_name == "ProductA"


@pytest.mark.asyncio
async def test_kg_brand_relation_order_constraint(db_session: AsyncSession) -> None:
    """ADR-012 enforces brand_a_id < brand_b_id to prevent dual edges."""
    # Valid: a < b
    db_session.add(
        KgBrandRelation(
            brand_a_id=10,
            brand_b_id=20,
            type="COMPETES_WITH",
            confidence=0.9,
            source="admin",
        )
    )
    await db_session.commit()

    # Invalid: a > b should fail check constraint
    db_session.add(
        KgBrandRelation(
            brand_a_id=30,
            brand_b_id=20,
            type="COMPETES_WITH",
            confidence=0.9,
            source="admin",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_kg_product_relation_pair_unique(db_session: AsyncSession) -> None:
    """Same (a, b, type) cannot be inserted twice."""
    db_session.add(KgProductRelation(product_a_id=100, product_b_id=200, type="SUBSTITUTES"))
    await db_session.commit()
    db_session.add(KgProductRelation(product_a_id=100, product_b_id=200, type="SUBSTITUTES"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_kg_relation_candidate_status_check(db_session: AsyncSession) -> None:
    db_session.add(
        KgRelationCandidate(
            entity_kind="brand",
            a_id=1,
            b_id=2,
            type="COMPETES_WITH",
            status="pending",
        )
    )
    await db_session.commit()

    # Invalid status
    db_session.add(
        KgRelationCandidate(
            entity_kind="brand",
            a_id=3,
            b_id=4,
            type="COMPETES_WITH",
            status="weird_status",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_kg_relation_candidate_kind_check(db_session: AsyncSession) -> None:
    """entity_kind must be brand or product."""
    db_session.add(
        KgRelationCandidate(
            entity_kind="unknown_kind",
            a_id=1,
            b_id=2,
            type="COMPETES_WITH",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
