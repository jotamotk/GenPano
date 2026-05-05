"""Phase K.5 — promote approved candidates to canonical relation tables."""

from __future__ import annotations

import os
import uuid

import pytest
from genpano_models import (
    KgBrandRelation,
    KgProductRelation,
    KgRelationCandidate,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kg.promote import promote_approved_candidates

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest.mark.asyncio
async def test_promote_brand_candidate_inserts_relation(db_session: AsyncSession):
    cand = KgRelationCandidate(
        id=_new_id(),
        entity_kind="brand",
        a_id=10,
        b_id=20,
        type="COMPETES_WITH",
        confidence=0.85,
        status="approved",
    )
    db_session.add(cand)
    await db_session.commit()

    summary = await promote_approved_candidates(db_session)
    assert summary["promoted"] == 1
    assert summary["by_kind"]["brand"] == 1

    rel = (
        await db_session.execute(select(KgBrandRelation).where(KgBrandRelation.brand_a_id == 10))
    ).scalar_one()
    assert rel.brand_b_id == 20
    assert rel.type == "COMPETES_WITH"

    await db_session.refresh(cand)
    assert cand.status == "merged"
    assert cand.merged_into_relation_id == rel.id


@pytest.mark.asyncio
async def test_promote_canonicalizes_brand_order(db_session: AsyncSession):
    """Brand relations have CHECK brand_a_id < brand_b_id; candidate may be reversed."""
    cand = KgRelationCandidate(
        id=_new_id(),
        entity_kind="brand",
        a_id=42,
        b_id=11,
        type="SAME_GROUP",
        confidence=0.9,
        status="approved",
    )
    db_session.add(cand)
    await db_session.commit()

    await promote_approved_candidates(db_session)
    rel = (
        await db_session.execute(
            select(KgBrandRelation).where(KgBrandRelation.type == "SAME_GROUP")
        )
    ).scalar_one()
    assert rel.brand_a_id == 11
    assert rel.brand_b_id == 42


@pytest.mark.asyncio
async def test_promote_idempotent_skips_already_merged(db_session: AsyncSession):
    cand = KgRelationCandidate(
        id=_new_id(),
        entity_kind="brand",
        a_id=1,
        b_id=2,
        type="COMPETES_WITH",
        confidence=0.7,
        status="approved",
    )
    db_session.add(cand)
    await db_session.commit()

    s1 = await promote_approved_candidates(db_session)
    s2 = await promote_approved_candidates(db_session)
    assert s1["promoted"] == 1
    assert s2["scanned"] == 0  # nothing left to process


@pytest.mark.asyncio
async def test_promote_reconciles_with_existing_relation(db_session: AsyncSession):
    """If canonical row already exists (manual admin entry), candidate
    should reconcile (status='merged') without raising on the unique key.
    """
    pre_existing = KgBrandRelation(
        id=_new_id(),
        brand_a_id=5,
        brand_b_id=6,
        type="COMPETES_WITH",
        confidence=1.0,
        source="admin",
    )
    db_session.add(pre_existing)
    await db_session.commit()

    cand = KgRelationCandidate(
        id=_new_id(),
        entity_kind="brand",
        a_id=5,
        b_id=6,
        type="COMPETES_WITH",
        confidence=0.7,
        status="approved",
    )
    db_session.add(cand)
    await db_session.commit()

    summary = await promote_approved_candidates(db_session)
    assert summary["reconciled"] == 1
    assert summary["promoted"] == 0

    await db_session.refresh(cand)
    assert cand.status == "merged"
    assert cand.merged_into_relation_id == pre_existing.id


@pytest.mark.asyncio
async def test_promote_product_directional_preserves_order(db_session: AsyncSession):
    """UPGRADES_TO is directional — promoter must NOT reorder."""
    cand = KgRelationCandidate(
        id=_new_id(),
        entity_kind="product",
        a_id=200,
        b_id=100,
        type="UPGRADES_TO",
        confidence=0.8,
        status="approved",
    )
    db_session.add(cand)
    await db_session.commit()

    await promote_approved_candidates(db_session)
    rel = (
        await db_session.execute(
            select(KgProductRelation).where(KgProductRelation.type == "UPGRADES_TO")
        )
    ).scalar_one()
    # Direction preserved
    assert rel.product_a_id == 200
    assert rel.product_b_id == 100


@pytest.mark.asyncio
async def test_promote_product_symmetric_canonicalizes(db_session: AsyncSession):
    """COMPETES_WITH between products is symmetric → canonical (lo, hi) order."""
    cand = KgRelationCandidate(
        id=_new_id(),
        entity_kind="product",
        a_id=999,
        b_id=111,
        type="COMPETES_WITH",
        confidence=0.7,
        status="approved",
    )
    db_session.add(cand)
    await db_session.commit()

    await promote_approved_candidates(db_session)
    rel = (
        await db_session.execute(
            select(KgProductRelation).where(KgProductRelation.type == "COMPETES_WITH")
        )
    ).scalar_one()
    assert rel.product_a_id == 111
    assert rel.product_b_id == 999


@pytest.mark.asyncio
async def test_promote_skips_invalid_type(db_session: AsyncSession):
    cand = KgRelationCandidate(
        id=_new_id(),
        entity_kind="brand",
        a_id=1,
        b_id=2,
        type="UNKNOWN_TYPE",
        confidence=0.5,
        status="approved",
    )
    db_session.add(cand)
    await db_session.commit()

    summary = await promote_approved_candidates(db_session)
    assert summary["skipped_invalid"] == 1
    assert summary["promoted"] == 0


@pytest.mark.asyncio
async def test_promote_skips_self_pair(db_session: AsyncSession):
    cand = KgRelationCandidate(
        id=_new_id(),
        entity_kind="brand",
        a_id=7,
        b_id=7,
        type="COMPETES_WITH",
        confidence=0.5,
        status="approved",
    )
    db_session.add(cand)
    await db_session.commit()

    summary = await promote_approved_candidates(db_session)
    assert summary["skipped_invalid"] == 1


@pytest.mark.asyncio
async def test_promote_dry_run_does_not_persist(db_session: AsyncSession):
    cand = KgRelationCandidate(
        id=_new_id(),
        entity_kind="brand",
        a_id=30,
        b_id=40,
        type="COMPETES_WITH",
        confidence=0.6,
        status="approved",
    )
    db_session.add(cand)
    await db_session.commit()

    summary = await promote_approved_candidates(db_session, dry_run=True)
    assert summary["promoted"] == 1

    # Nothing actually inserted
    rels = (
        await db_session.execute(select(KgBrandRelation).where(KgBrandRelation.brand_a_id == 30))
    ).all()
    assert len(rels) == 0
    # Candidate still pending-merge
    await db_session.refresh(cand)
    assert cand.status == "approved"
    assert cand.merged_into_relation_id is None


@pytest.mark.asyncio
async def test_promote_only_processes_approved(db_session: AsyncSession):
    """Pending / rejected / merged candidates are ignored."""
    db_session.add_all(
        [
            KgRelationCandidate(
                id=_new_id(),
                entity_kind="brand",
                a_id=1,
                b_id=2,
                type="COMPETES_WITH",
                confidence=0.5,
                status="pending",
            ),
            KgRelationCandidate(
                id=_new_id(),
                entity_kind="brand",
                a_id=3,
                b_id=4,
                type="COMPETES_WITH",
                confidence=0.5,
                status="rejected",
            ),
            KgRelationCandidate(
                id=_new_id(),
                entity_kind="brand",
                a_id=5,
                b_id=6,
                type="COMPETES_WITH",
                confidence=0.5,
                status="approved",
            ),
        ]
    )
    await db_session.commit()

    summary = await promote_approved_candidates(db_session)
    assert summary["scanned"] == 1
    assert summary["promoted"] == 1
