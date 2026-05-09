"""Brand context attachment for Prompt Matrix generation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from genpano_models import BrandContextSnapshot
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.brand_context import (
    assemble_brand_context_pack,
    enrich_context_pack_with_approved_extractions,
    persist_brand_context_snapshot,
    topic_context_refs,
)
from app.admin.prompt_matrix.lib import PromptMatrixError
from app.admin.topic_plan.lib import TopicPlanLLMError
from app.admin.topic_plan.llm import DoubaoTopicPlanClient


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _brand_lookup(brands: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(brand["id"]): brand for brand in brands if brand.get("id") is not None}


async def _latest_snapshots(
    session: AsyncSession, brand_ids: set[int]
) -> dict[int, BrandContextSnapshot]:
    if not brand_ids:
        return {}
    rows = (
        (
            await session.execute(
                select(BrandContextSnapshot)
                .where(
                    BrandContextSnapshot.brand_id.in_(brand_ids),
                    BrandContextSnapshot.status == "active",
                )
                .order_by(BrandContextSnapshot.brand_id, desc(BrandContextSnapshot.created_at))
            )
        )
        .scalars()
        .all()
    )
    latest: dict[int, BrandContextSnapshot] = {}
    now = _now()
    for row in rows:
        brand_id = int(row.brand_id)
        if brand_id in latest:
            continue
        if row.expires_at and row.expires_at < now:
            continue
        latest[brand_id] = row
    return latest


async def _snapshots_by_version(
    session: AsyncSession, versions: set[str]
) -> dict[str, BrandContextSnapshot]:
    if not versions:
        return {}
    rows = (
        (
            await session.execute(
                select(BrandContextSnapshot).where(
                    BrandContextSnapshot.version.in_(versions),
                    BrandContextSnapshot.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    return {str(row.version): row for row in rows}


def _attach_topic_context(topic: dict[str, Any], version: str, payload: dict[str, Any]) -> None:
    topic["brand_context_version"] = version
    topic["brand_context_pack"] = payload
    if not isinstance(topic.get("context_refs"), dict) or not topic.get("context_refs"):
        axis, refs = topic_context_refs(
            topic_dimension=str(topic.get("topic_axis") or topic.get("dimension_key") or ""),
            product_name=topic.get("product_name"),
            context_pack=payload,
        )
        topic["topic_axis"] = topic.get("topic_axis") or axis
        topic["context_refs"] = refs


async def attach_brand_context_to_topics(
    session: AsyncSession,
    *,
    topics: list[dict[str, Any]],
    known_brands: list[dict[str, Any]],
    run_id: str,
) -> dict[str, str]:
    """Ensure selected topics carry a versioned search-backed context pack.

    Topic Plan-approved rows may already have a context version. Legacy topics
    first reuse the latest active brand snapshot; if none exists, Prompt Matrix
    performs the same search-backed brand research and persists a fresh snapshot.
    """
    if not topics:
        return {}

    versions: dict[str, str] = {}
    brand_ids = {int(t["brand_id"]) for t in topics if t.get("brand_id") is not None}
    version_values = {
        str(t.get("brand_context_version"))
        for t in topics
        if str(t.get("brand_context_version") or "").strip()
    }
    by_version = await _snapshots_by_version(session, version_values)
    latest = await _latest_snapshots(session, brand_ids)

    for topic in topics:
        if topic.get("brand_context_version") and isinstance(topic.get("brand_context_pack"), dict):
            topic["brand_context_pack"] = await enrich_context_pack_with_approved_extractions(
                session,
                brand_id=int(topic["brand_id"]),
                payload=topic["brand_context_pack"],
            )
            versions[str(topic["brand_id"])] = str(topic["brand_context_version"])
            continue
        brand_id = int(topic["brand_id"])
        snapshot = by_version.get(str(topic.get("brand_context_version") or "")) or latest.get(
            brand_id
        )
        if snapshot is not None:
            payload = await enrich_context_pack_with_approved_extractions(
                session,
                brand_id=brand_id,
                payload=snapshot.payload_json or {},
            )
            _attach_topic_context(topic, snapshot.version, payload)
            versions[str(brand_id)] = snapshot.version

    missing_brand_ids = {
        int(topic["brand_id"])
        for topic in topics
        if topic.get("brand_id") is not None and not topic.get("brand_context_version")
    }
    if not missing_brand_ids:
        return versions

    by_brand_id = _brand_lookup(known_brands)
    missing_brands = [by_brand_id[bid] for bid in missing_brand_ids if bid in by_brand_id]
    if len(missing_brands) != len(missing_brand_ids):
        raise PromptMatrixError(
            "brand_context_missing",
            "Prompt Matrix could not resolve selected topic brand context.",
        )

    industry = (
        ", ".join(
            sorted(
                {
                    str(brand.get("industry_name") or brand.get("industry_id") or "").strip()
                    for brand in missing_brands
                    if str(brand.get("industry_name") or brand.get("industry_id") or "").strip()
                }
            )
        )
        or "All industries"
    )
    try:
        research = await DoubaoTopicPlanClient().research_brand_context(
            industry=industry,
            category="All categories",
            brands=missing_brands,
        )
    except TopicPlanLLMError as error:
        raise PromptMatrixError(error.code, error.message) from error

    search_by_name = {str(item.get("name") or ""): item for item in research}
    for brand in missing_brands:
        brand_id = int(brand["id"])
        payload = assemble_brand_context_pack(
            brand=brand,
            search_context=search_by_name.get(str(brand.get("name") or "")),
        )
        payload = await enrich_context_pack_with_approved_extractions(
            session,
            brand_id=brand_id,
            payload=payload,
        )
        version = await persist_brand_context_snapshot(
            session,
            brand_id=brand_id,
            payload=payload,
            created_from_run_id=run_id,
        )
        versions[str(brand_id)] = version
        for topic in topics:
            if int(topic.get("brand_id") or 0) == brand_id:
                _attach_topic_context(topic, version, payload)
    return versions
