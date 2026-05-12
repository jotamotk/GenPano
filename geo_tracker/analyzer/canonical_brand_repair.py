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
    SentimentDriver,
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
        if target_mention is None:
            target_mention = _build_target_mention(
                response=response,
                query=query,
                brand=brand,
                hits=hits,
                virtual_id=-1,
            )
            if not dry_run:
                target_mention.id = None
                session.add(target_mention)
                await session.flush()

        if dry_run:
            competitor_mentions = await _inspect_competitor_mentions(
                session,
                response=response,
                competitor_hits=competitor_hits,
                stats=stats,
            )
        else:
            competitor_mentions = await _upsert_competitor_mentions(
                session,
                response=response,
                competitor_hits=competitor_hits,
                stats=stats,
            )
        repaired_mentions = [target_mention, *competitor_mentions]
        raw_analysis_json = await _raw_analysis_json_for_response(session, response.id)
        terms_by_mention_id = _terms_by_mention_id(
            target_mention=target_mention,
            target_terms=terms,
            competitor_mentions=competitor_mentions,
            competitor_specs=competitive_specs,
        )
        citation_stats = await _upsert_response_citations(
            session,
            response=response,
            mentions=repaired_mentions,
            terms_by_mention_id=terms_by_mention_id,
            dry_run=dry_run,
        )
        for key, value in citation_stats.items():
            stats[key] += value
        sentiment_stats = await _repair_sentiment_evidence(
            session,
            raw_analysis_json=raw_analysis_json,
            brand=brand,
            target_terms=terms,
            repaired_mentions=repaired_mentions,
            dry_run=dry_run,
        )
        for key, value in sentiment_stats.items():
            stats[key] += value
        if dry_run:
            continue
        await _annotate_analysis(
            session,
            response=response,
            query=query,
            brand=brand,
            hits=hits,
            create_partial=create_partial_analysis,
            inserted_mention_id=target_mention.id,
            repaired_mentions=repaired_mentions,
            citation_stats=citation_stats,
            sentiment_evidence=sentiment_stats,
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
    citation_stats: dict[str, int],
    sentiment_evidence: dict[str, int],
) -> None:
    citation_count = citation_stats["citations_seen"]
    attributed_citation_count = citation_stats["citations_attributed"]
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
                    citation_stats=citation_stats,
                    sentiment_evidence=sentiment_evidence,
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
            citation_stats=citation_stats,
        ),
    )
    raw["metric_input_status"] = {
        **_coerce_dict(raw.get("metric_input_status")),
        **_metric_input_status(
            brand=brand,
            repaired_mentions=repaired_mentions,
            citation_stats=citation_stats,
            sentiment_evidence=sentiment_evidence,
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


def _build_target_mention(
    *,
    response: LLMResponse,
    query: Query,
    brand: Brand,
    hits: list[AliasHit],
    virtual_id: int | None = None,
) -> BrandMention:
    return BrandMention(
        id=virtual_id,
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


def _build_competitor_mention(
    *,
    response: LLMResponse,
    spec: CompetitiveSpec,
    hits: list[AliasHit],
    virtual_id: int | None = None,
) -> BrandMention:
    return BrandMention(
        id=virtual_id,
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


async def _inspect_competitor_mentions(
    session: AsyncSession,
    *,
    response: LLMResponse,
    competitor_hits: list[tuple[CompetitiveSpec, list[AliasHit]]],
    stats: dict[str, int],
) -> list[BrandMention]:
    mentions: list[BrandMention] = []
    virtual_id = -2
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
        stats["competitive_mentions_inserted"] += 1
        mentions.append(
            _build_competitor_mention(
                response=response,
                spec=spec,
                hits=hits,
                virtual_id=virtual_id,
            )
        )
        virtual_id -= 1
    return mentions


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
        mention = _build_competitor_mention(
            response=response,
            spec=spec,
            hits=hits,
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
    dry_run: bool = False,
) -> dict[str, int]:
    stats = {
        "citations_seen": 0,
        "citations_inserted": 0,
        "citations_existing": 0,
        "citations_repairable": 0,
        "citations_repaired": 0,
        "citations_attributed": 0,
        "citations_unattributed": 0,
        "citations_attributed_by_alias": 0,
        "citations_attributed_by_context": 0,
        "citations_context_ambiguous": 0,
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
        citation_text = _citation_payload_text(raw)
        citation_index = raw.get("index")
        stats["citations_seen"] += 1
        mention, method = _match_citation_to_mention(
            title=title,
            domain=_extract_domain(url),
            citation_text=citation_text,
            response_text=response.raw_text,
            citation_index=citation_index,
            mentions=mentions,
            terms_by_mention_id=terms_by_mention_id,
        )
        if method == "ambiguous_response_marker_context":
            stats["citations_context_ambiguous"] += 1
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
            elif mention is not None:
                stats["citations_repairable"] += 1
                stats["citations_attributed"] += 1
                _count_citation_method(stats, method)
                if not dry_run and mention.id is not None:
                    existing.mention_id = mention.id
                    stats["citations_repaired"] += 1
            else:
                stats["citations_unattributed"] += 1
            continue

        if not dry_run:
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
            _count_citation_method(stats, method)
        else:
            stats["citations_unattributed"] += 1
    return stats


def _match_citation_to_mention(
    *,
    title: str,
    domain: str,
    citation_text: str,
    response_text: str | None,
    citation_index: Any,
    mentions: list[BrandMention],
    terms_by_mention_id: dict[int, list[str]],
) -> tuple[BrandMention | None, str | None]:
    haystack = f"{title} {domain} {citation_text}".lower()
    for mention in mentions:
        terms = terms_by_mention_id.get(mention.id, [mention.brand_name])
        if any(_norm(term) and _norm(term) in _norm(haystack) for term in terms):
            return mention, "title_domain_alias"

    context = _citation_marker_context(response_text, citation_index)
    if context:
        matches = _mentions_matching_text(
            context,
            mentions=mentions,
            terms_by_mention_id=terms_by_mention_id,
        )
        if len(matches) == 1:
            return matches[0], "response_marker_context"
        if len(matches) > 1:
            return None, "ambiguous_response_marker_context"

    return None, None


def _count_citation_method(stats: dict[str, int], method: str | None) -> None:
    if method == "title_domain_alias":
        stats["citations_attributed_by_alias"] += 1
    elif method == "response_marker_context":
        stats["citations_attributed_by_context"] += 1


def _citation_payload_text(raw: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("snippet", "context", "quote", "text", "description", "summary"):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return " ".join(values)


def _citation_marker_context(
    response_text: str | None,
    citation_index: Any,
    *,
    radius: int = SNIPPET_RADIUS,
) -> str | None:
    if not response_text or citation_index is None:
        return None
    index = str(citation_index).strip()
    if not index:
        return None
    patterns = [
        rf"\[\s*{re.escape(index)}\s*\]",
        rf"【\s*{re.escape(index)}\s*】",
        rf"［\s*{re.escape(index)}\s*］",
        rf"\(\s*{re.escape(index)}\s*\)",
    ]
    for pattern in patterns:
        match = re.search(pattern, response_text)
        if match:
            start = max(0, match.start() - radius)
            end = min(len(response_text), match.end() + radius)
            return response_text[start:end]
    return None


def _mentions_matching_text(
    text: str,
    *,
    mentions: list[BrandMention],
    terms_by_mention_id: dict[int, list[str]],
) -> list[BrandMention]:
    matches: list[BrandMention] = []
    seen: set[tuple[int | None, int | None, str]] = set()
    for mention in mentions:
        terms = terms_by_mention_id.get(mention.id, [mention.brand_name])
        if not any(_term_in_text(text, term) for term in terms):
            continue
        key = (mention.id, mention.brand_id, mention.brand_name)
        if key in seen:
            continue
        seen.add(key)
        matches.append(mention)
    return matches


def _term_in_text(text: str, term: str | None) -> bool:
    normalized = str(term or "").strip()
    if not normalized:
        return False
    return bool(_find_all(text.lower(), normalized.lower()))


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


async def _repair_sentiment_evidence(
    session: AsyncSession,
    *,
    raw_analysis_json: dict[str, Any],
    brand: Brand,
    target_terms: list[str],
    repaired_mentions: list[BrandMention],
    dry_run: bool,
) -> dict[str, int]:
    stats = _empty_sentiment_stats()
    target_mentions = [
        mention for mention in repaired_mentions
        if mention.brand_id == brand.id
    ]
    if not target_mentions:
        return stats

    existing_drivers = await _load_sentiment_drivers(session, target_mentions)
    existing_keys = {
        mention_id: {
            _driver_key(
                driver_text=driver.driver_text,
                source_quote=driver.source_quote,
                polarity=driver.polarity,
            )
            for driver in drivers
        }
        for mention_id, drivers in existing_drivers.items()
    }
    candidates = _sentiment_candidates_for_brand(
        raw_analysis_json,
        brand=brand,
        target_terms=target_terms,
    )
    candidate = candidates[0] if candidates else None
    inserted_driver_count = 0
    inserted_quoted_driver_count = 0

    for mention in target_mentions:
        has_sentiment = mention.sentiment is not None or mention.sentiment_score is not None
        if candidate is not None:
            sentiment = _clean_text(candidate.get("sentiment"))
            sentiment_score = _coerce_float(candidate.get("sentiment_score"))
            if (
                (mention.sentiment is None and sentiment)
                or (mention.sentiment_score is None and sentiment_score is not None)
            ):
                stats["sentiment_mentions_updated"] += 1
                if not dry_run:
                    if mention.sentiment is None and sentiment:
                        mention.sentiment = sentiment
                    if mention.sentiment_score is None and sentiment_score is not None:
                        mention.sentiment_score = sentiment_score
            has_sentiment = has_sentiment or bool(sentiment) or sentiment_score is not None

            for driver in _driver_candidates(candidate):
                stats["sentiment_drivers_seen"] += 1
                driver_text = _clean_text(driver.get("driver_text"))
                source_quote = _clean_text(driver.get("source_quote"))
                if not driver_text or not source_quote:
                    stats["sentiment_drivers_missing_source_quote"] += 1
                    continue
                polarity = _clean_text(driver.get("polarity")) or sentiment or _polarity_from_score(sentiment_score)
                key = _driver_key(
                    driver_text=driver_text,
                    source_quote=source_quote,
                    polarity=polarity,
                )
                mention_existing_keys = existing_keys.setdefault(mention.id, set())
                if key in mention_existing_keys:
                    stats["sentiment_drivers_existing"] += 1
                    continue
                stats["sentiment_drivers_inserted"] += 1
                inserted_driver_count += 1
                inserted_quoted_driver_count += 1
                mention_existing_keys.add(key)
                if not dry_run:
                    session.add(
                        SentimentDriver(
                            mention_id=mention.id,
                            response_id=mention.response_id,
                            brand_name=mention.brand_name,
                            driver_text=driver_text[:512],
                            polarity=(polarity or "neutral")[:8],
                            category=_clean_text(driver.get("category")) or "other",
                            strength=_coerce_float(driver.get("strength")) or 0.5,
                            source_quote=source_quote,
                        )
                    )

        if has_sentiment:
            stats["target_sentiment_rows"] += 1

    existing_driver_count = sum(len(drivers) for drivers in existing_drivers.values())
    existing_quoted_driver_count = sum(
        1
        for drivers in existing_drivers.values()
        for driver in drivers
        if _clean_text(driver.source_quote)
    )
    stats["target_driver_count"] = existing_driver_count + inserted_driver_count
    stats["quoted_target_driver_count"] = (
        existing_quoted_driver_count + inserted_quoted_driver_count
    )
    return stats


async def _load_sentiment_drivers(
    session: AsyncSession,
    mentions: list[BrandMention],
) -> dict[int, list[SentimentDriver]]:
    mention_ids = [mention.id for mention in mentions if mention.id is not None]
    if not mention_ids:
        return {}
    rows = (
        await session.execute(
            select(SentimentDriver).where(SentimentDriver.mention_id.in_(mention_ids))
        )
    ).scalars().all()
    out: dict[int, list[SentimentDriver]] = {}
    for row in rows:
        out.setdefault(row.mention_id, []).append(row)
    return out


def _sentiment_candidates_for_brand(
    raw_analysis_json: dict[str, Any],
    *,
    brand: Brand,
    target_terms: list[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for key in ("brands", "brand_mentions", "brand_analyses"):
        for item in _coerce_list(raw_analysis_json.get(key)):
            if _brand_payload_matches(item, brand=brand, target_terms=target_terms):
                candidates.append(item)
    for item in _coerce_list(raw_analysis_json.get("brand_mention_facts")):
        if _brand_payload_matches(item, brand=brand, target_terms=target_terms):
            candidates.append(item)
    return candidates


def _brand_payload_matches(
    item: Any,
    *,
    brand: Brand,
    target_terms: list[str],
) -> bool:
    if not isinstance(item, dict):
        return False
    canonical_id = item.get("canonical_brand_id") or item.get("brand_id")
    if canonical_id is not None:
        try:
            if int(canonical_id) == brand.id:
                return True
        except (TypeError, ValueError):
            pass
    names = [
        item.get("brand_name"),
        item.get("raw_brand_name"),
        item.get("target_brand"),
    ]
    term_keys = {_norm(term) for term in [brand.name, *target_terms] if _norm(term)}
    return any(_norm(str(name)) in term_keys for name in names if name)


def _driver_candidates(item: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key in ("sentiment_drivers", "drivers"):
        for driver in _coerce_list(item.get(key)):
            if isinstance(driver, dict):
                out.append(driver)
    return out


def _driver_key(
    *,
    driver_text: str | None,
    source_quote: str | None,
    polarity: str | None,
) -> tuple[str, str, str]:
    return (_norm(driver_text), _norm(source_quote), _norm(polarity))


def _polarity_from_score(score: float | None) -> str:
    if score is None:
        return "neutral"
    if score > 0.05:
        return "positive"
    if score < -0.05:
        return "negative"
    return "neutral"


def _metric_input_status(
    *,
    brand: Brand,
    repaired_mentions: list[BrandMention],
    citation_stats: dict[str, int],
    sentiment_evidence: dict[str, int] | None = None,
) -> dict[str, dict[str, Any]]:
    citation_count = citation_stats["citations_seen"]
    attributed_citation_count = citation_stats["citations_attributed"]
    sentiment_evidence = sentiment_evidence or {}
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

    target_sentiment_rows = sentiment_evidence.get(
        "target_sentiment_rows",
        sum(
            1
            for mention in target_mentions
            if mention.sentiment is not None or mention.sentiment_score is not None
        ),
    )
    target_driver_count = sentiment_evidence.get("target_driver_count", 0)
    quoted_target_driver_count = sentiment_evidence.get("quoted_target_driver_count", 0)
    sentiment_missing = []
    if not target_sentiment_rows:
        sentiment_missing.append("llm_brand_sentiment")
    if not quoted_target_driver_count:
        sentiment_missing.append("sentiment_drivers.source_quote")
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
                *sentiment_missing,
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
            "state": "ok" if target_sentiment_rows and quoted_target_driver_count else "partial",
            "missing_inputs": sentiment_missing,
            "target_sentiment_rows": target_sentiment_rows,
            "target_driver_count": target_driver_count,
            "quoted_target_driver_count": quoted_target_driver_count,
        },
        "citation": {
            "state": citation_state,
            "missing_inputs": citation_missing,
            "citation_count": citation_count,
            "attributed_citation_count": attributed_citation_count,
            "attribution_methods": {
                "title_domain_alias": citation_stats.get("citations_attributed_by_alias", 0),
                "response_marker_context": citation_stats.get("citations_attributed_by_context", 0),
            },
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
    citation_stats: dict[str, int],
    sentiment_evidence: dict[str, int],
) -> list[str]:
    status = _metric_input_status(
        brand=brand,
        repaired_mentions=repaired_mentions,
        citation_stats=citation_stats,
        sentiment_evidence=sentiment_evidence,
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
    citation_stats: dict[str, int],
) -> list[dict[str, Any]]:
    citation_count = citation_stats["citations_seen"]
    attributed_citation_count = citation_stats["citations_attributed"]
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
            "repairable_citation_count": citation_stats.get("citations_repairable", 0),
            "attribution_methods": {
                "title_domain_alias": citation_stats.get("citations_attributed_by_alias", 0),
                "response_marker_context": citation_stats.get("citations_attributed_by_context", 0),
            },
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


def _coerce_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple | set):
        return list(value)
    return []


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
        "citations_repairable": 0,
        "citations_repaired": 0,
        "citations_attributed": 0,
        "citations_unattributed": 0,
        "citations_attributed_by_alias": 0,
        "citations_attributed_by_context": 0,
        "citations_context_ambiguous": 0,
        "target_sentiment_rows": 0,
        "sentiment_mentions_updated": 0,
        "sentiment_drivers_seen": 0,
        "sentiment_drivers_inserted": 0,
        "sentiment_drivers_existing": 0,
        "sentiment_drivers_missing_source_quote": 0,
        "target_driver_count": 0,
        "quoted_target_driver_count": 0,
    }


def _empty_sentiment_stats() -> dict[str, int]:
    return {
        "target_sentiment_rows": 0,
        "sentiment_mentions_updated": 0,
        "sentiment_drivers_seen": 0,
        "sentiment_drivers_inserted": 0,
        "sentiment_drivers_existing": 0,
        "sentiment_drivers_missing_source_quote": 0,
        "target_driver_count": 0,
        "quoted_target_driver_count": 0,
    }


__all__ = [
    "REPAIR_SOURCE",
    "brand_alias_terms",
    "find_alias_hits",
    "repair_canonical_brand_mentions",
]
