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
from urllib.parse import urlparse

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.db.models import (
    AnalysisStatus,
    Brand,
    BrandMention,
    CitationSource,
    Competitor,
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


@dataclass(frozen=True)
class CompetitiveSpec:
    brand_id: int | None
    brand_name: str
    terms: tuple[str, ...]
    source: str


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
    competitive_brand_ids: set[int] | list[int] | None = None,
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
    competitive_specs = await _load_competitive_specs(
        session,
        target_brand=brand,
        competitive_brand_ids=competitive_brand_ids,
    )

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
        target_mention = existing
        if existing is not None:
            stats["mentions_existing"] += 1
        else:
            stats["mentions_inserted"] += 1

        competitor_hits = _find_competitor_hits(response.raw_text, competitive_specs)
        stats["competitive_mentions_matched"] += len(competitor_hits)
        existing_from_repair = (
            existing is not None
            and _has_repair_marker_for_existing(
                raw_analysis_json=await _raw_analysis_json_for_response(session, response.id),
                mention_id=existing.id,
            )
        )
        if existing is not None and not existing_from_repair:
            # Preserve hand-authored or full analyzer mentions. They should not
            # be relabeled as canonical repair output.
            continue
        if dry_run:
            for _spec, _hits in competitor_hits:
                stats["competitive_mentions_inserted"] += 1
            continue

        if target_mention is None:
            target_mention = BrandMention(
                response_id=response.id,
                brand_id=brand.id,
                brand_name=brand.name,
                is_target=(query.brand_id == brand.id),
                position_type="mentioned_only",
                position_rank=None,
                detail_level="passing",
                sentiment=None,
                sentiment_score=None,
                context_snippet=hits[0].snippet,
                mention_count=sum(hit.count for hit in hits),
            )
            session.add(target_mention)
            await session.flush()

        competitor_mentions = await _upsert_competitor_mentions(
            session,
            response=response,
            competitor_hits=competitor_hits,
            stats=stats,
        )
        repaired_mentions = [target_mention, *competitor_mentions]
        citation_stats = await _upsert_response_citations(
            session,
            response=response,
            mentions=repaired_mentions,
            terms_by_mention_id=_terms_by_mention_id(
                target_mention=target_mention,
                target_terms=terms,
                competitor_mentions=competitor_mentions,
                competitor_specs=competitive_specs,
            ),
        )
        for key, value in citation_stats.items():
            stats[key] += value
        await _annotate_analysis(
            session,
            response=response,
            query=query,
            brand=brand,
            hits=hits,
            create_partial=create_partial_analysis,
            inserted_mention_id=target_mention.id,
            repaired_mentions=repaired_mentions,
            citation_count=citation_stats["citations_seen"],
            attributed_citation_count=citation_stats["citations_attributed"],
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
    repaired_mentions: list[BrandMention],
    citation_count: int,
    attributed_citation_count: int,
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
            visibility_score=None,
            sentiment_score=None,
            sov_score=None,
            citation_score=None,
            geo_score=None,
            analyzer_model=REPAIR_SOURCE,
            raw_analysis_json={},
        )
        session.add(analysis)
        await session.flush()
        analysis.visibility_score = None
        analysis.sentiment_score = None
        analysis.sov_score = None
        analysis.citation_score = None
        analysis.geo_score = None
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
                "missing_sources": _canonical_missing_sources(
                    brand=brand,
                    repaired_mentions=repaired_mentions,
                    citation_count=citation_count,
                    attributed_citation_count=attributed_citation_count,
                ),
            }
        )
    raw["canonical_alias_repairs"] = repairs
    raw["brand_mention_facts"] = _merge_facts(
        raw.get("brand_mention_facts"),
        _brand_mention_facts(
            response=response,
            query=query,
            repaired_mentions=repaired_mentions,
        ),
    )
    raw["citation_facts"] = _merge_facts(
        raw.get("citation_facts"),
        _citation_facts(
            citation_count=citation_count,
            attributed_citation_count=attributed_citation_count,
        ),
    )
    raw["metric_input_status"] = {
        **_coerce_dict(raw.get("metric_input_status")),
        **_metric_input_status(
            brand=brand,
            repaired_mentions=repaired_mentions,
            citation_count=citation_count,
            attributed_citation_count=attributed_citation_count,
        ),
    }
    analysis.raw_analysis_json = raw


async def _load_competitive_specs(
    session: AsyncSession,
    *,
    target_brand: Brand,
    competitive_brand_ids: set[int] | list[int] | None,
) -> list[CompetitiveSpec]:
    specs: list[CompetitiveSpec] = []
    seen: set[str] = {_norm(target_brand.name)}
    seen.update(_norm(term) for term in _flatten_aliases(target_brand.aliases))

    for cid in sorted({int(value) for value in (competitive_brand_ids or [])}):
        if cid == target_brand.id:
            continue
        comp_brand = await session.get(Brand, cid)
        if comp_brand is None:
            continue
        terms = tuple(brand_alias_terms(comp_brand))
        key = _norm(comp_brand.name)
        if key and key not in seen:
            specs.append(
                CompetitiveSpec(
                    brand_id=comp_brand.id,
                    brand_name=comp_brand.name,
                    terms=terms,
                    source="competitive_brand_id",
                )
            )
            seen.add(key)
            seen.update(_norm(term) for term in terms)

    configured = (
        await session.execute(
            select(Competitor).where(Competitor.brand_id == target_brand.id)
        )
    ).scalars().all()
    for competitor in configured:
        terms = tuple(_dedupe_terms([competitor.name, *_flatten_aliases(competitor.aliases)]))
        key = _norm(competitor.name)
        if key and key not in seen:
            specs.append(
                CompetitiveSpec(
                    brand_id=None,
                    brand_name=competitor.name,
                    terms=terms,
                    source="configured_competitor_name",
                )
            )
            seen.add(key)
            seen.update(_norm(term) for term in terms)
    return specs


def _find_competitor_hits(
    text: str | None,
    specs: list[CompetitiveSpec],
) -> list[tuple[CompetitiveSpec, list[AliasHit]]]:
    hits: list[tuple[CompetitiveSpec, list[AliasHit]]] = []
    for spec in specs:
        spec_hits = find_alias_hits(text, list(spec.terms))
        if spec_hits:
            hits.append((spec, spec_hits))
    return hits


async def _upsert_competitor_mentions(
    session: AsyncSession,
    *,
    response: LLMResponse,
    competitor_hits: list[tuple[CompetitiveSpec, list[AliasHit]]],
    stats: dict[str, int],
) -> list[BrandMention]:
    mentions: list[BrandMention] = []
    for spec, hits in competitor_hits:
        existing = await _find_existing_mention(
            session,
            response_id=response.id,
            brand_id=spec.brand_id,
            brand_name=spec.brand_name,
        )
        if existing is not None:
            stats["competitive_mentions_existing"] += 1
            mentions.append(existing)
            continue
        mention = BrandMention(
            response_id=response.id,
            brand_id=spec.brand_id,
            brand_name=spec.brand_name,
            is_target=False,
            position_type="mentioned_only",
            position_rank=None,
            detail_level="passing",
            sentiment=None,
            sentiment_score=None,
            context_snippet=hits[0].snippet,
            mention_count=sum(hit.count for hit in hits),
        )
        session.add(mention)
        await session.flush()
        stats["competitive_mentions_inserted"] += 1
        mentions.append(mention)
    return mentions


async def _find_existing_mention(
    session: AsyncSession,
    *,
    response_id: int,
    brand_id: int | None,
    brand_name: str,
) -> BrandMention | None:
    conditions = [BrandMention.response_id == response_id]
    if brand_id is not None:
        conditions.append(BrandMention.brand_id == brand_id)
    else:
        conditions.append(BrandMention.brand_name == brand_name)
    return (
        await session.execute(select(BrandMention).where(and_(*conditions)))
    ).scalars().first()


async def _upsert_response_citations(
    session: AsyncSession,
    *,
    response: LLMResponse,
    mentions: list[BrandMention],
    terms_by_mention_id: dict[int, list[str]],
) -> dict[str, int]:
    stats = {
        "citations_seen": 0,
        "citations_inserted": 0,
        "citations_existing": 0,
        "citations_attributed": 0,
        "citations_unattributed": 0,
    }
    citations = response.citations_json if isinstance(response.citations_json, list) else []
    if not citations:
        return stats

    for raw in citations:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url") or "").strip()
        if not url:
            continue
        title = str(raw.get("title") or "").strip()
        citation_index = raw.get("index")
        stats["citations_seen"] += 1
        existing = (
            await session.execute(
                select(CitationSource).where(
                    CitationSource.response_id == response.id,
                    CitationSource.url == url,
                    CitationSource.citation_index == citation_index,
                )
            )
        ).scalars().first()
        if existing is not None:
            stats["citations_existing"] += 1
            if existing.mention_id is not None:
                stats["citations_attributed"] += 1
            else:
                stats["citations_unattributed"] += 1
            continue

        mention = _match_citation_to_mention(
            title=title,
            domain=_extract_domain(url),
            mentions=mentions,
            terms_by_mention_id=terms_by_mention_id,
        )
        session.add(
            CitationSource(
                response_id=response.id,
                mention_id=mention.id if mention else None,
                url=url,
                domain=_extract_domain(url),
                title=title,
                citation_index=citation_index,
                source_type="other",
            )
        )
        stats["citations_inserted"] += 1
        if mention:
            stats["citations_attributed"] += 1
        else:
            stats["citations_unattributed"] += 1
    return stats


def _match_citation_to_mention(
    *,
    title: str,
    domain: str,
    mentions: list[BrandMention],
    terms_by_mention_id: dict[int, list[str]],
) -> BrandMention | None:
    haystack = f"{title} {domain}".lower()
    for mention in mentions:
        terms = terms_by_mention_id.get(mention.id, [mention.brand_name])
        if any(_norm(term) and _norm(term) in _norm(haystack) for term in terms):
            return mention
    return None


def _terms_by_mention_id(
    *,
    target_mention: BrandMention,
    target_terms: list[str],
    competitor_mentions: list[BrandMention],
    competitor_specs: list[CompetitiveSpec],
) -> dict[int, list[str]]:
    out = {target_mention.id: _dedupe_terms([target_mention.brand_name, *target_terms])}
    specs_by_key = {
        (spec.brand_id, spec.brand_name): spec
        for spec in competitor_specs
    }
    for mention in competitor_mentions:
        spec = specs_by_key.get((mention.brand_id, mention.brand_name))
        out[mention.id] = _dedupe_terms(
            [mention.brand_name, *(list(spec.terms) if spec else [])]
        )
    return out


def _metric_input_status(
    *,
    brand: Brand,
    repaired_mentions: list[BrandMention],
    citation_count: int,
    attributed_citation_count: int,
) -> dict[str, dict[str, Any]]:
    target_mentions = [
        mention for mention in repaired_mentions
        if mention.brand_id == brand.id
    ]
    competitive_mentions = [
        mention for mention in repaired_mentions
        if mention.brand_id != brand.id
    ]
    total_competitive_mentions = sum(m.mention_count or 1 for m in repaired_mentions)
    non_target_competitive_mentions = sum(m.mention_count or 1 for m in competitive_mentions)
    sov_missing = []
    if not non_target_competitive_mentions:
        sov_missing.append("brand_mentions.competitive_set")

    sentiment_missing = ["llm_brand_sentiment", "sentiment_drivers.source_quote"]
    citation_missing: list[str] = []
    if citation_count == 0:
        citation_state = "empty"
        citation_missing.append("citation_sources")
    elif attributed_citation_count < citation_count:
        citation_state = "partial"
        citation_missing.append("citation_sources.mention_id")
    else:
        citation_state = "ok"

    pano_missing = _dedupe_terms([
        "canonical_alias_repair.partial",
        "llm_brand_position",
        *sentiment_missing,
        *sov_missing,
        *citation_missing,
    ])
    return {
        "canonical_alias_repair": {
            "state": "partial",
            "source": REPAIR_SOURCE,
            "missing_inputs": [
                "canonical_alias_repair.partial",
                "llm_brand_position",
                "llm_brand_sentiment",
                "sentiment_drivers.source_quote",
            ],
            "target_mention_count": sum(m.mention_count or 1 for m in target_mentions),
            "competitive_mention_count": non_target_competitive_mentions,
        },
        "sov": {
            "state": "ok" if not sov_missing else "partial",
            "missing_inputs": sov_missing,
            "target_mentions": sum(m.mention_count or 1 for m in target_mentions),
            "competitive_mentions": total_competitive_mentions,
            "non_target_competitive_mentions": non_target_competitive_mentions,
        },
        "sentiment": {
            "state": "partial",
            "missing_inputs": sentiment_missing,
            "target_driver_count": 0,
            "quoted_target_driver_count": 0,
        },
        "citation": {
            "state": citation_state,
            "missing_inputs": citation_missing,
            "citation_count": citation_count,
            "attributed_citation_count": attributed_citation_count,
        },
        "pano_geo": {
            "state": "partial",
            "missing_inputs": pano_missing,
        },
    }


def _canonical_missing_sources(
    *,
    brand: Brand,
    repaired_mentions: list[BrandMention],
    citation_count: int,
    attributed_citation_count: int,
) -> list[str]:
    status = _metric_input_status(
        brand=brand,
        repaired_mentions=repaired_mentions,
        citation_count=citation_count,
        attributed_citation_count=attributed_citation_count,
    )
    missing: list[str] = []
    for item in status.values():
        missing.extend(item.get("missing_inputs", []))
    return _dedupe_terms(missing)


def _brand_mention_facts(
    *,
    response: LLMResponse,
    query: Query,
    repaired_mentions: list[BrandMention],
) -> list[dict[str, Any]]:
    return [
        {
            "mention_id": mention.id,
            "response_id": response.id,
            "query_id": response.query_id,
            "prompt_id": query.prompt_id,
            "brand_name": mention.brand_name,
            "canonical_brand_id": mention.brand_id,
            "product_name": mention.product_name,
            "provenance": REPAIR_SOURCE,
            "confidence": 0.6,
            "position_type": mention.position_type,
            "position_rank": mention.position_rank,
            "mention_count": mention.mention_count,
            "evidence_snippet": mention.context_snippet,
            "missing_inputs": ["llm_brand_position", "llm_brand_sentiment"],
        }
        for mention in repaired_mentions
    ]


def _citation_facts(
    *,
    citation_count: int,
    attributed_citation_count: int,
) -> list[dict[str, Any]]:
    if citation_count == 0:
        return [
            {
                "provenance": REPAIR_SOURCE,
                "state": "empty",
                "missing_inputs": ["citation_sources"],
                "citation_count": 0,
                "attributed_citation_count": 0,
            }
        ]
    missing = [] if attributed_citation_count == citation_count else ["citation_sources.mention_id"]
    return [
        {
            "provenance": REPAIR_SOURCE,
            "state": "ok" if not missing else "partial",
            "missing_inputs": missing,
            "citation_count": citation_count,
            "attributed_citation_count": attributed_citation_count,
        }
    ]


def _merge_facts(existing: Any, additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = list(existing) if isinstance(existing, list) else []
    seen = {
        json.dumps(item, sort_keys=True, default=str)
        for item in out
        if isinstance(item, dict)
    }
    for item in additions:
        key = json.dumps(item, sort_keys=True, default=str)
        if key not in seen:
            out.append(item)
            seen.add(key)
    return out


async def _raw_analysis_json_for_response(
    session: AsyncSession,
    response_id: int,
) -> dict[str, Any]:
    analysis = (
        await session.execute(
            select(ResponseAnalysis).where(ResponseAnalysis.response_id == response_id)
        )
    ).scalar_one_or_none()
    return _coerce_dict(analysis.raw_analysis_json) if analysis is not None else {}


def _has_repair_marker_for_existing(
    *,
    raw_analysis_json: dict[str, Any],
    mention_id: int,
) -> bool:
    for item in raw_analysis_json.get("canonical_alias_repairs") or []:
        if isinstance(item, dict) and item.get("inserted_mention_id") == mention_id:
            return True
    return False


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


def _dedupe_terms(values: list[str | None]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = str(value or "").strip()
        key = _norm(normalized)
        if normalized and key not in seen:
            seen.add(key)
            out.append(normalized)
    return out


def _norm(value: str | None) -> str:
    return re.sub(r"[\s\W_]+", "", str(value or "").lower())


def _extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        domain = parsed.hostname or ""
        return domain[4:].lower() if domain.startswith("www.") else domain.lower()
    except Exception:
        return ""


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
        "competitive_mentions_matched": 0,
        "competitive_mentions_inserted": 0,
        "competitive_mentions_existing": 0,
        "citations_seen": 0,
        "citations_inserted": 0,
        "citations_existing": 0,
        "citations_attributed": 0,
        "citations_unattributed": 0,
    }


__all__ = [
    "REPAIR_SOURCE",
    "brand_alias_terms",
    "find_alias_hits",
    "repair_canonical_brand_mentions",
]
