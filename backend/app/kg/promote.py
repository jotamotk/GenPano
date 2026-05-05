"""Phase K.5 follow-up — promote approved KG candidates to canonical tables.

The Phase K.5 review loop is:

    extractor (regex / LLM) → kg_relation_candidates (status='pending')
        → admin /api/admin/kg-candidates/{id}/approve (status='approved')
            → THIS MODULE → kg_brand_relations / kg_product_relations
                → candidate marked status='merged' with
                  merged_into_relation_id pointing at the new row.

Run as a one-shot or as a periodic Celery task (not yet wired). The
function `promote_approved_candidates` is idempotent:

    - candidates already in status='merged' (with merged_into_relation_id)
      are skipped
    - if a canonical relation already exists with the same
      (a_id, b_id, type) tuple, the candidate is reconciled to point at
      it (status='merged') rather than failing on the unique constraint

Brand relations have a CHECK constraint `brand_a_id < brand_b_id`, so we
canonicalize the ordering on insert. Product relations have no such
constraint — directional types (UPGRADES_TO / BUDGET_ALT_OF) preserve
the candidate's order; symmetric types (COMPETES_WITH / PAIRS_WITH) we
also canonicalize for dedup.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from genpano_models import (
    KgBrandRelation,
    KgProductRelation,
    KgRelationCandidate,
)
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)

SYMMETRIC_PRODUCT_TYPES = {"COMPETES_WITH", "PAIRS_WITH"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _canonical_brand_pair(a: int, b: int) -> tuple[int, int]:
    """Canonicalize brand pair to satisfy `brand_a_id < brand_b_id`."""
    return (a, b) if a < b else (b, a)


def _canonical_product_pair(a: int, b: int, *, type_: str) -> tuple[int, int]:
    """Canonicalize product pair only for symmetric types."""
    if type_ in SYMMETRIC_PRODUCT_TYPES:
        return (a, b) if a < b else (b, a)
    return (a, b)


async def _find_existing_brand_relation(
    session: AsyncSession,
    *,
    a_id: int,
    b_id: int,
    type_: str,
) -> KgBrandRelation | None:
    return (
        await session.execute(
            select(KgBrandRelation).where(
                and_(
                    KgBrandRelation.brand_a_id == a_id,
                    KgBrandRelation.brand_b_id == b_id,
                    KgBrandRelation.type == type_,
                )
            )
        )
    ).scalar_one_or_none()


async def _find_existing_product_relation(
    session: AsyncSession,
    *,
    a_id: int,
    b_id: int,
    type_: str,
) -> KgProductRelation | None:
    return (
        await session.execute(
            select(KgProductRelation).where(
                and_(
                    KgProductRelation.product_a_id == a_id,
                    KgProductRelation.product_b_id == b_id,
                    KgProductRelation.type == type_,
                )
            )
        )
    ).scalar_one_or_none()


async def promote_approved_candidates(
    session: AsyncSession,
    *,
    limit: int = 500,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Promote approved kg_relation_candidates to canonical tables.

    Returns a summary dict:
        {
            "scanned": int,
            "promoted": int,            # newly inserted canonical rows
            "reconciled": int,          # candidate matched a pre-existing row
            "skipped_invalid": int,     # bad type / source coercion / etc.
            "by_kind": {"brand": ..., "product": ...},
        }
    """
    stmt = (
        select(KgRelationCandidate)
        .where(
            and_(
                KgRelationCandidate.status == "approved",
                KgRelationCandidate.merged_into_relation_id.is_(None),
            )
        )
        .limit(limit)
    )
    candidates = list((await session.execute(stmt)).scalars().all())

    promoted = 0
    reconciled = 0
    skipped_invalid = 0
    by_kind: dict[str, int] = {"brand": 0, "product": 0}
    now = _now()

    for cand in candidates:
        if cand.entity_kind == "brand":
            if cand.type not in {"COMPETES_WITH", "SAME_GROUP"}:
                skipped_invalid += 1
                continue
            a_id, b_id = _canonical_brand_pair(cand.a_id, cand.b_id)
            if a_id == b_id:
                skipped_invalid += 1
                continue
            existing = await _find_existing_brand_relation(
                session, a_id=a_id, b_id=b_id, type_=cand.type
            )
            if existing is not None:
                cand.status = "merged"
                cand.merged_into_relation_id = existing.id
                cand.reviewed_at = cand.reviewed_at or now
                reconciled += 1
                by_kind["brand"] += 1
                continue
            if dry_run:
                promoted += 1
                by_kind["brand"] += 1
                continue
            new_row = KgBrandRelation(
                brand_a_id=a_id,
                brand_b_id=b_id,
                type=cand.type,
                confidence=cand.confidence or 0.5,
                source="analyzer",
                evidence=cand.evidence,
                reviewed_by=cand.reviewed_by,
                reviewed_at=cand.reviewed_at,
            )
            session.add(new_row)
            await session.flush()
            cand.status = "merged"
            cand.merged_into_relation_id = new_row.id
            promoted += 1
            by_kind["brand"] += 1

        elif cand.entity_kind == "product":
            if cand.type not in {
                "COMPETES_WITH",
                "SUBSTITUTES",
                "UPGRADES_TO",
                "BUDGET_ALT_OF",
                "PAIRS_WITH",
            }:
                skipped_invalid += 1
                continue
            a_id, b_id = _canonical_product_pair(cand.a_id, cand.b_id, type_=cand.type)
            if a_id == b_id:
                skipped_invalid += 1
                continue
            existing_p = await _find_existing_product_relation(
                session, a_id=a_id, b_id=b_id, type_=cand.type
            )
            if existing_p is not None:
                cand.status = "merged"
                cand.merged_into_relation_id = existing_p.id
                cand.reviewed_at = cand.reviewed_at or now
                reconciled += 1
                by_kind["product"] += 1
                continue
            if dry_run:
                promoted += 1
                by_kind["product"] += 1
                continue
            new_prow = KgProductRelation(
                product_a_id=a_id,
                product_b_id=b_id,
                type=cand.type,
                confidence=cand.confidence,
                source="analyzer",
                evidence=cand.evidence,
                reviewed_by=cand.reviewed_by,
                reviewed_at=cand.reviewed_at,
            )
            session.add(new_prow)
            await session.flush()
            cand.status = "merged"
            cand.merged_into_relation_id = new_prow.id
            promoted += 1
            by_kind["product"] += 1
        else:
            skipped_invalid += 1

    if dry_run:
        await session.rollback()
    else:
        await session.commit()

    summary: dict[str, Any] = {
        "scanned": len(candidates),
        "promoted": promoted,
        "reconciled": reconciled,
        "skipped_invalid": skipped_invalid,
        "by_kind": by_kind,
    }
    log.info("promote_approved_candidates: %s", summary)
    return summary
