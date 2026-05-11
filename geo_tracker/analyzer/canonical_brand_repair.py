"""Canonical brand alias repair for raw analyzer evidence.

This module backfills brand_mentions from raw LLM response text when the
response belongs to one source brand path but contains another canonical brand
name or alias. It deliberately does not rewrite queries.brand_id.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.db.models import (
    AnalysisStatus,
    Brand,
    BrandMention,
    LLMResponse,
    Query,
    ResponseAnalysis,
)

SNIPPET_RADIUS = 80
REPAIR_SOURCE = "canonical_alias_repair_v1"


@dataclass(frozen=True)
class AliasHit:
    term: str
    count: int
    snippet: str | None


def brand_alias_terms(brand: Brand, extra_aliases: list[str] | None = None) -> list[str]:
    terms: list[str] = [brand.name]
    terms.extend(_flatten_aliases(brand.aliases))
    terms.extend(extra_aliases or [])
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        normalized = str(term or "").strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            out.append(normalized)
    return out


def find_alias_hits(text: str | None, terms: list[str]) -> list[AliasHit]:
    if not text:
        return []
    hits: list[AliasHit] = []
    text_lower = text.lower()
    for term in terms:
        positions = _find_all(text_lower, term.lower())
        if not positions:
            continue
        snippet = _snippet(text, positions[0][0], positions[0][1])
        hits.append(AliasHit(term=term, count=len(positions), snippet=snippet))
    return hits


async def repair_canonical_brand_mentions(
    session: AsyncSession,
    *,
    brand_id: int,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    source_brand_id: int | None = None,
    extra_aliases: list[str] | None = None,
    dry_run: bool = True,
    create_partial_analysis: bool = True,
) -> dict[str, int]:
    """Create canonical BrandMention rows from raw text alias hits.

    The write path is idempotent per response/canonical brand. Existing
    ResponseAnalysis rows are annotated with source-quality metadata; missing
    analyses can be created as partial repair evidence so aggregation has a
    denominator without pretending a full LLM analyzer pass happened.
    """
    brand = await session.get(Brand, brand_id)
    if brand is None:
        raise ValueError(f"brand_id {brand_id} not found")

    terms = brand_alias_terms(brand, extra_aliases)
    if not terms:
        return _empty_stats()

    conditions = []
    if start_at is not None:
        conditions.append(LLMResponse.collected_at >= start_at)
    if end_at is not None:
        conditions.append(LLMResponse.collected_at <= end_at)
    if source_brand_id is not None:
        conditions.append(Query.brand_id == source_brand_id)

    stmt = select(LLMResponse, Query).join(Query, Query.id == LLMResponse.query_id)
    if conditions:
        stmt = stmt.where(and_(*conditions))

    rows = (await session.execute(stmt)).all()
    stats = _empty_stats()
    stats["responses_scanned"] = len(rows)

    for response, query in rows:
        hits = find_alias_hits(response.raw_text, terms)
        if not hits:
            continue
        stats["responses_matched"] += 1

        existing = (
            await session.execute(
                select(BrandMention).where(
                    BrandMention.response_id == response.id,
                    BrandMention.brand_id == brand.id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            stats["mentions_existing"] += 1
            continue

        stats["mentions_inserted"] += 1
        if dry_run:
            continue

        mention = BrandMention(
            response_id=response.id,
            brand_id=brand.id,
            brand_name=brand.name,
            is_target=(query.brand_id == brand.id),
            position_type="mentioned_only",
            position_rank=None,
            detail_level="passing",
            sentiment="neutral",
            sentiment_score=0.0,
            context_snippet=hits[0].snippet,
            mention_count=sum(hit.count for hit in hits),
        )
        session.add(mention)
        await session.flush()
        await _annotate_analysis(
            session,
            response=response,
            query=query,
            brand=brand,
            hits=hits,
            create_partial=create_partial_analysis,
            inserted_mention_id=mention.id,
        )

    if not dry_run:
        await session.commit()
    return stats


async def _annotate_analysis(
    session: AsyncSession,
    *,
    response: LLMResponse,
    query: Query,
    brand: Brand,
    hits: list[AliasHit],
    create_partial: bool,
    inserted_mention_id: int,
) -> None:
    analysis = (
        await session.execute(
            select(ResponseAnalysis).where(ResponseAnalysis.response_id == response.id)
        )
    ).scalar_one_or_none()
    if analysis is None:
        if not create_partial:
            return
        analysis = ResponseAnalysis(
            response_id=response.id,
            target_brand_mentioned=False,
            total_brands_mentioned=1,
            visibility_score=0.0,
            sentiment_score=50.0,
            sov_score=0.0,
            citation_score=0.0,
            geo_score=0.0,
            analyzer_model=REPAIR_SOURCE,
            raw_analysis_json={},
        )
        session.add(analysis)
        response.analysis_status = AnalysisStatus.DONE.value

    raw = _coerce_dict(analysis.raw_analysis_json)
    repairs = list(raw.get("canonical_alias_repairs") or [])
    if not any(
        item.get("inserted_mention_id") == inserted_mention_id
        for item in repairs
        if isinstance(item, dict)
    ):
        repairs.append(
            {
                "source": REPAIR_SOURCE,
                "inserted_by_repair": True,
                "inserted_mention_id": inserted_mention_id,
                "state": "partial",
                "brand_id": brand.id,
                "brand_name": brand.name,
                "owner_brand_id": query.brand_id,
                "matched_terms": [hit.term for hit in hits],
                "mention_count": sum(hit.count for hit in hits),
                "missing_sources": ["llm_brand_position", "llm_brand_sentiment"],
            }
        )
    raw["canonical_alias_repairs"] = repairs
    analysis.raw_analysis_json = raw


def _flatten_aliases(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except Exception:
            return [value]
        return _flatten_aliases(loaded)
    if isinstance(value, list | tuple | set):
        out: list[str] = []
        for item in value:
            out.extend(_flatten_aliases(item))
        return out
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_flatten_aliases(item))
        return out
    return [str(value)]


def _find_all(text_lower: str, term: str) -> list[tuple[int, int]]:
    if not term:
        return []
    is_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in term)
    if is_cjk:
        positions: list[tuple[int, int]] = []
        start = 0
        while True:
            idx = text_lower.find(term, start)
            if idx == -1:
                break
            positions.append((idx, idx + len(term)))
            start = idx + 1
        return positions
    pattern = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
    return [(m.start(), m.end()) for m in pattern.finditer(text_lower)]


def _snippet(text: str, start: int, end: int) -> str:
    return text[max(0, start - SNIPPET_RADIUS): min(len(text), end + SNIPPET_RADIUS)]


def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except Exception:
            return {}
        return dict(loaded) if isinstance(loaded, dict) else {}
    return {}


def _empty_stats() -> dict[str, int]:
    return {
        "responses_scanned": 0,
        "responses_matched": 0,
        "mentions_inserted": 0,
        "mentions_existing": 0,
    }


__all__ = [
    "REPAIR_SOURCE",
    "brand_alias_terms",
    "find_alias_hits",
    "repair_canonical_brand_mentions",
]
