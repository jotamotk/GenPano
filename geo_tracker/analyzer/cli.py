"""
手动触发分析的 CLI 工具（测试阶段用）

用法:
  python -m geo_tracker.analyzer.cli run-daily --date 2026-04-09
  python -m geo_tracker.analyzer.cli run-daily --date 2026-04-09 --brand-id 1
  python -m geo_tracker.analyzer.cli aggregate --date 2026-04-09
  python -m geo_tracker.analyzer.cli reanalyze --date 2026-04-09
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime

from sqlalchemy import and_, delete, or_, select, update

from geo_tracker.config import create_task_engine, get_task_async_session
from geo_tracker.db.models import (
    AnalysisStatus, Brand, BrandMention, CitationSource,
    Competitor, LLMResponse, ProductFeatureMention, Prompt,
    Query, ResponseAnalysis, SentimentDriver,
)
from geo_tracker.analyzer.brand_detector import BrandDetector
from geo_tracker.analyzer.llm_analyzer import LLMAnalyzer
from geo_tracker.analyzer.citation_mapper import CitationMapper
from geo_tracker.analyzer.fact_contract import (
    AnalyzerCitationInput,
    AnalyzerMentionInput,
    AnalyzerResponseInput,
    build_response_fact_package_v3,
    build_response_fact_packages,
)
from geo_tracker.analyzer.geo_scorer import GEOScorer
from geo_tracker.analyzer.aggregator import Aggregator
from geo_tracker.analyzer.canonical_brand_repair import repair_canonical_brand_mentions
from geo_tracker.analyzer.position_type import normalize_position_type

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _normalize_brand_key(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _brand_terms(name: str | None, aliases: list[str] | None = None) -> list[str]:
    terms = [name] if name else []
    terms.extend(aliases or [])
    return [term for term in terms if term and term.strip()]


async def _load_brand_identity_index(session) -> dict[str, tuple[int, str]]:
    """Map known brand names and aliases to canonical (brand_id, brand_name)."""
    rows = (await session.execute(select(Brand))).scalars().all()
    index: dict[str, tuple[int, str]] = {}
    for row in rows:
        for term in _brand_terms(row.name, row.aliases or []):
            key = _normalize_brand_key(term)
            if key and key not in index:
                index[key] = (row.id, row.name)
    return index


def _resolve_brand_identity(
    brand_name: str,
    explicit_brand_id: int | None,
    brand_index: dict[str, tuple[int, str]],
) -> tuple[int | None, str]:
    if explicit_brand_id is not None:
        for _key, (indexed_id, indexed_name) in brand_index.items():
            if indexed_id == explicit_brand_id:
                return indexed_id, indexed_name
        return explicit_brand_id, brand_name
    return brand_index.get(_normalize_brand_key(brand_name), (None, brand_name))


def _same_brand_identity(
    left_name: str,
    left_id: int | None,
    right_name: str,
    right_id: int | None,
    brand_index: dict[str, tuple[int, str]],
) -> bool:
    left_canonical_id, left_canonical_name = _resolve_brand_identity(
        left_name,
        left_id,
        brand_index,
    )
    right_canonical_id, right_canonical_name = _resolve_brand_identity(
        right_name,
        right_id,
        brand_index,
    )
    if left_canonical_id is not None and right_canonical_id is not None:
        return left_canonical_id == right_canonical_id
    return _normalize_brand_key(left_canonical_name) == _normalize_brand_key(right_canonical_name)


def _extract_context_snippet(
    response_text: str | None,
    terms: list[str],
    radius: int = 120,
) -> str | None:
    if not response_text:
        return None
    lowered = response_text.lower()
    for term in terms:
        key = term.strip().lower()
        if not key:
            continue
        idx = lowered.find(key)
        if idx < 0:
            continue
        start = max(0, idx - radius)
        end = min(len(response_text), idx + len(term) + radius)
        return response_text[start:end]
    return None


def _count_text_mentions(response_text: str | None, terms: list[str]) -> int:
    if not response_text:
        return 0
    lowered = response_text.lower()
    count = 0
    for term in terms:
        key = term.strip().lower()
        if key:
            count += lowered.count(key)
    return count


def _citation_brand_hints(
    detected_brands,
    llm_brands,
) -> list:
    hints = list(detected_brands)
    seen = {_normalize_brand_key(d.brand_name) for d in detected_brands}
    for brand in llm_brands:
        key = _normalize_brand_key(brand.brand_name)
        if key and key not in seen:
            hints.append(
                type(detected_brands[0] if detected_brands else object)(
                    brand_name=brand.brand_name,
                    brand_id=None,
                    is_target=False,
                    mention_count=1,
                    context_snippets=[],
                )
                if detected_brands
                else _CitationBrandHint(brand.brand_name)
            )
            seen.add(key)
    return hints


class _CitationBrandHint:
    def __init__(self, brand_name: str):
        self.brand_name = brand_name
        self.brand_id = None
        self.is_target = False
        self.mention_count = 1
        self.context_snippets: list[str] = []


def _find_mention_for_brand(
    mentions: list[BrandMention],
    brand_name: str | None,
    brand_index: dict[str, tuple[int, str]],
) -> BrandMention | None:
    key = _normalize_brand_key(brand_name)
    if not key:
        return None
    for mention in mentions:
        if _same_brand_identity(
            mention.brand_name,
            mention.brand_id,
            brand_name,
            None,
            brand_index,
        ):
            return mention
    return None


def _competitor_contracts_from_competitors(competitors: list[Competitor]) -> list[dict]:
    return [
        {
            "brand_id": None,
            "brand_name": competitor.name,
            "aliases": competitor.aliases or [],
            "source": "configured_competitor",
        }
        for competitor in competitors
    ]


def _competitor_contracts_from_brands(brands: list[Brand]) -> list[dict]:
    return [
        {
            "brand_id": brand.id,
            "brand_name": brand.name,
            "aliases": brand.aliases or [],
            "source": "competitive_brand_id",
        }
        for brand in brands
    ]


def _response_input_from_pipeline(
    *,
    response: LLMResponse,
    query: Query | None,
    prompt_id: int | None,
    topic_id: int | None,
    has_analysis: bool,
    mentions: list[BrandMention],
    raw_names_by_mention_id: dict[int, str],
    drivers_by_mention_id: dict[int, list[dict]],
    citation_facts: list[dict],
) -> AnalyzerResponseInput:
    return AnalyzerResponseInput(
        response_id=response.id,
        query_id=response.query_id,
        prompt_id=prompt_id,
        topic_id=topic_id,
        project_brand_id=query.brand_id if query else None,
        engine=query.target_llm if query else None,
        profile_id=query.profile_id if query else None,
        collected_at=response.collected_at.isoformat() if response.collected_at else None,
        analysis_status=response.analysis_status,
        has_analysis=has_analysis,
        raw_text=response.raw_text,
        mentions=[
            AnalyzerMentionInput(
                mention_id=mention.id,
                response_id=mention.response_id,
                brand_id=mention.brand_id,
                brand_name=mention.brand_name,
                raw_name=raw_names_by_mention_id.get(mention.id, mention.brand_name),
                is_target=bool(mention.is_target),
                mention_count=mention.mention_count,
                context_snippet=mention.context_snippet,
                sentiment=mention.sentiment,
                sentiment_score=mention.sentiment_score,
                sentiment_drivers=drivers_by_mention_id.get(mention.id, []),
                product_name=mention.product_name,
                position_type=mention.position_type,
                position_rank=mention.position_rank,
                provenance="analyzer_pipeline",
                confidence=None,
            )
            for mention in mentions
        ],
        citations=[
            AnalyzerCitationInput(
                citation_id=fact.get("citation_id"),
                response_id=response.id,
                mention_id=fact.get("mention_id"),
                url=fact["url"],
                domain=fact.get("domain"),
                source_type=fact.get("source_type"),
                tier=fact.get("tier"),
                title=fact.get("title"),
                brand_name=fact.get("brand_name"),
            )
            for fact in citation_facts
        ],
    )


def _scope_raw_relation_evidence(
    raw_analysis_json: dict,
    *,
    response_id: int,
    query_id: int | None,
    prompt_id: int | None,
    topic_id: int | None,
) -> dict:
    relation_keys = (
        "relations",
        "response_relations",
        "brand_relations",
        "product_relations",
        "relation_facts",
    )
    scoped = dict(raw_analysis_json)
    for key in relation_keys:
        value = scoped.get(key)
        if not isinstance(value, list):
            continue
        scoped_items = []
        for item in value:
            if not isinstance(item, dict):
                scoped_items.append(item)
                continue
            relation = dict(item)
            relation["response_id"] = response_id
            for field, scoped_id in (
                ("query_id", query_id),
                ("prompt_id", prompt_id),
                ("topic_id", topic_id),
            ):
                if scoped_id is None:
                    relation.pop(field, None)
                else:
                    relation[field] = scoped_id
            relation["source"] = "current_response_analyzer"
            scoped_items.append(relation)
        scoped[key] = scoped_items
    return scoped


async def analyze_single_response(
    session,
    response: LLMResponse,
    brand: Brand,
    competitors: list[Competitor],
    intent: str,
) -> dict:
    """Run the 3-stage analysis pipeline on a single LLMResponse."""
    detector = BrandDetector()
    llm_analyzer = LLMAnalyzer()
    citation_mapper = CitationMapper()

    # Clean up any old analysis data for this response (supports re-analysis)
    old_analysis = (await session.execute(
        select(ResponseAnalysis).where(ResponseAnalysis.response_id == response.id)
    )).scalar_one_or_none()
    if old_analysis:
        await session.execute(
            delete(ProductFeatureMention).where(
                ProductFeatureMention.analysis_id == old_analysis.id
            )
        )
        await session.execute(
            delete(ResponseAnalysis).where(
                ResponseAnalysis.response_id == response.id
            )
        )
    old_mention_ids = select(BrandMention.id).where(
        BrandMention.response_id == response.id
    )
    await session.execute(
        delete(SentimentDriver).where(
            or_(
                SentimentDriver.response_id == response.id,
                SentimentDriver.mention_id.in_(old_mention_ids),
            )
        )
    )
    # Delete old mention dependents before old mentions; production FKs do not
    # cascade for this bulk delete path.
    await session.execute(
        delete(CitationSource).where(CitationSource.response_id == response.id)
    )
    await session.execute(
        delete(BrandMention).where(BrandMention.response_id == response.id)
    )

    # Mark as running
    response.analysis_status = AnalysisStatus.RUNNING.value
    await session.commit()

    try:
        # Stage 1: Brand pre-detection
        detected = detector.detect(response.raw_text, brand, competitors)
        logger.info(
            f"  Stage 1: detected {len(detected)} brands: "
            f"{[d.brand_name for d in detected]}"
        )

        # Stage 2: LLM analysis (includes sentiment)
        llm_result = await llm_analyzer.analyze(
            response_text=response.raw_text,
            detected_brands=detected,
            intent=intent,
            target_brand=brand.name,
            target_aliases=brand.aliases or [],
            competitors=[c.name for c in competitors],
        )
        logger.info(
            f"  Stage 2: LLM found {len(llm_result.brands)} brands, "
            f"dimension={llm_result.dimension.industry}"
        )

        # Stage 3: Citation mapping. Use both rule-detected and LLM-only
        # brands so unconfigured competitors can still receive attribution.
        citation_mappings = citation_mapper.map_citations(
            response.citations_json,
            _citation_brand_hints(detected, llm_result.brands),
            brand,
        )
        logger.info(f"  Stage 3: mapped {len(citation_mappings)} citations")

        # ── Write results to DB ──
        brand_index = await _load_brand_identity_index(session)
        query = await session.get(Query, response.query_id)
        prompt_id = query.prompt_id if query else None
        topic_id = None
        if prompt_id is not None:
            prompt = await session.get(Prompt, prompt_id)
            topic_id = prompt.topic_id if prompt else None

        # Build brand analysis lookup from LLM result
        # Key: (brand_name_lower, product_name) to support multiple products per brand
        llm_brands = {}
        for b in llm_result.brands:
            key = (b.brand_name.lower(), (b.product_name or "").lower())
            llm_brands[key] = b

        # Create BrandMention records — one per (brand, product) from LLM
        total_mentions = 0
        target_mentions = []   # all mentions where is_target=True
        all_mentions = []
        processed_llm_keys = set()
        mention_facts: list[dict] = []
        raw_names_by_mention_id: dict[int, str] = {}
        drivers_by_mention_id: dict[int, list[dict]] = defaultdict(list)

        # First pass: match detected brands with LLM results
        for di, d in enumerate(detected):
            # Find ALL LLM entries for this brand (may have multiple products)
            matching_llm = [
                (k, b) for k, b in llm_brands.items()
                if _same_brand_identity(
                    d.brand_name,
                    d.brand_id,
                    b.brand_name,
                    None,
                    brand_index,
                )
            ]

            if not matching_llm:
                # No LLM match — create a brand-only mention
                matching_llm = [(None, None)]

            for key, llm_brand in matching_llm:
                if key:
                    processed_llm_keys.add(key)
                canonical_brand_id, canonical_brand_name = _resolve_brand_identity(
                    d.brand_name,
                    d.brand_id,
                    brand_index,
                )
                is_target = d.is_target or canonical_brand_id == brand.id
                product_name = llm_brand.product_name if llm_brand else None
                context_snippet = (
                    d.context_snippets[0]
                    if d.context_snippets
                    else _extract_context_snippet(
                        response.raw_text,
                        _brand_terms(d.brand_name)
                        + _brand_terms(llm_brand.brand_name if llm_brand else None)
                        + _brand_terms(product_name),
                    )
                )
                provenance = "detector_llm" if llm_brand else "rule_detector"
                raw_brand_name = llm_brand.brand_name if llm_brand else d.brand_name

                mention = BrandMention(
                    response_id=response.id,
                    brand_id=canonical_brand_id,
                    brand_name=canonical_brand_name,
                    product_name=product_name,
                    is_target=is_target,
                    position_type=normalize_position_type(
                        llm_brand.position_type if llm_brand else None
                    ),
                    position_rank=(
                        llm_brand.position_rank if llm_brand else None
                    ),
                    detail_level=(
                        llm_brand.detail_level if llm_brand else "passing"
                    ),
                    sentiment=(llm_brand.sentiment if llm_brand else None),
                    sentiment_score=(llm_brand.sentiment_score if llm_brand else None),
                    context_snippet=context_snippet,
                    mention_count=d.mention_count,
                )
                session.add(mention)
                await session.flush()
                raw_names_by_mention_id[mention.id] = raw_brand_name

                total_mentions += d.mention_count
                all_mentions.append(mention)
                mention_facts.append({
                    "mention_id": mention.id,
                    "response_id": response.id,
                    "query_id": response.query_id,
                    "prompt_id": prompt_id,
                    "topic_id": topic_id,
                    "brand_name": canonical_brand_name,
                    "raw_brand_name": raw_brand_name,
                    "canonical_brand_id": canonical_brand_id,
                    "product_name": product_name,
                    "provenance": provenance,
                    "confidence": 0.95 if llm_brand else 0.6,
                    "position_type": mention.position_type,
                    "position_rank": mention.position_rank,
                    "mention_count": mention.mention_count,
                    "evidence_snippet": context_snippet,
                    "missing_inputs": [] if llm_brand else ["llm_brand_analysis"],
                })

                if is_target:
                    target_mentions.append(mention)

                # Create SentimentDriver records for each product entry
                if llm_brand:
                    for driver in llm_brand.sentiment_drivers:
                        driver_fact = {
                            "driver_text": driver.driver_text,
                            "polarity": driver.polarity,
                            "category": driver.category,
                            "strength": driver.strength,
                            "source_quote": driver.source_quote,
                        }
                        drivers_by_mention_id[mention.id].append(driver_fact)
                        session.add(SentimentDriver(
                            mention_id=mention.id,
                            response_id=response.id,
                            brand_name=canonical_brand_name,
                            driver_text=driver.driver_text,
                            polarity=driver.polarity,
                            category=driver.category,
                            strength=driver.strength,
                            source_quote=driver.source_quote,
                        ))

        # Second pass: add LLM-only brands/products not matched above
        for key, llm_brand in llm_brands.items():
            if key in processed_llm_keys:
                continue
            canonical_brand_id, canonical_brand_name = _resolve_brand_identity(
                llm_brand.brand_name,
                None,
                brand_index,
            )
            is_target = canonical_brand_id == brand.id
            context_snippet = _extract_context_snippet(
                response.raw_text,
                _brand_terms(llm_brand.brand_name)
                + _brand_terms(llm_brand.product_name)
                + [driver.source_quote for driver in llm_brand.sentiment_drivers],
            )
            mention_count = _count_text_mentions(
                response.raw_text,
                _brand_terms(llm_brand.brand_name) + _brand_terms(llm_brand.product_name),
            ) or 1

            mention = BrandMention(
                response_id=response.id,
                brand_id=canonical_brand_id,
                brand_name=canonical_brand_name,
                product_name=llm_brand.product_name,
                is_target=is_target,
                position_type=normalize_position_type(llm_brand.position_type),
                position_rank=llm_brand.position_rank,
                detail_level=llm_brand.detail_level,
                sentiment=llm_brand.sentiment,
                sentiment_score=llm_brand.sentiment_score,
                context_snippet=context_snippet,
                mention_count=mention_count,
            )
            session.add(mention)
            await session.flush()
            raw_names_by_mention_id[mention.id] = llm_brand.brand_name
            total_mentions += mention_count
            all_mentions.append(mention)
            mention_facts.append({
                "mention_id": mention.id,
                "response_id": response.id,
                "query_id": response.query_id,
                "prompt_id": prompt_id,
                "topic_id": topic_id,
                "brand_name": canonical_brand_name,
                "raw_brand_name": llm_brand.brand_name,
                "canonical_brand_id": canonical_brand_id,
                "product_name": llm_brand.product_name,
                "provenance": "llm_extraction",
                "confidence": 0.8,
                "position_type": mention.position_type,
                "position_rank": mention.position_rank,
                "mention_count": mention.mention_count,
                "evidence_snippet": context_snippet,
                "missing_inputs": [],
            })
            if is_target:
                target_mentions.append(mention)

            for driver in llm_brand.sentiment_drivers:
                driver_fact = {
                    "driver_text": driver.driver_text,
                    "polarity": driver.polarity,
                    "category": driver.category,
                    "strength": driver.strength,
                    "source_quote": driver.source_quote,
                }
                drivers_by_mention_id[mention.id].append(driver_fact)
                session.add(SentimentDriver(
                    mention_id=mention.id,
                    response_id=response.id,
                    brand_name=canonical_brand_name,
                    driver_text=driver.driver_text,
                    polarity=driver.polarity,
                    category=driver.category,
                    strength=driver.strength,
                    source_quote=driver.source_quote,
                ))

        # Create CitationSource records
        has_official = False
        citation_facts: list[dict] = []
        for cm in citation_mappings:
            if cm.source_type == "official_site":
                has_official = True
            citation_mention = _find_mention_for_brand(
                all_mentions,
                cm.brand_name,
                brand_index,
            )
            citation = CitationSource(
                response_id=response.id,
                mention_id=citation_mention.id if citation_mention else None,
                url=cm.url,
                domain=cm.domain,
                title=cm.title,
                citation_index=cm.citation_index,
                source_type=cm.source_type,
            )
            session.add(citation)
            citation_facts.append({
                "url": cm.url,
                "domain": cm.domain,
                "title": cm.title,
                "citation_index": cm.citation_index,
                "source_type": cm.source_type,
                "brand_name": cm.brand_name,
                "mention_id": citation_mention.id if citation_mention else None,
                "provenance": "citation_mapper",
                "missing_inputs": [] if citation_mention else ["citation_sources.mention_id"],
            })

        # Calculate GEO Score
        # Use the best target mention (highest position) for scoring
        target_mention_count = sum(
            m.mention_count or 0 for m in target_mentions
        )
        non_target_mentions = [
            m for m in all_mentions
            if not (m.is_target or (m.brand_id is not None and m.brand_id == brand.id))
        ]
        best_target = None
        if target_mentions:
            # Pick the best-positioned target mention
            position_priority = {
                "first_recommendation": 0, "comparison_winner": 1,
                "listed": 2, "mentioned_only": 3, "comparison_loser": 4,
            }
            best_target = min(
                target_mentions,
                key=lambda m: (
                    position_priority.get(m.position_type, 99),
                    m.position_rank or 999,
                ),
            )

        # mention_rate_pct: target brand's share of all mentions in this response
        mention_rate_pct = (
            (target_mention_count / total_mentions * 100)
            if total_mentions > 0 and best_target else 0.0
        )

        visibility = GEOScorer.calc_visibility(
            is_mentioned=best_target is not None,
            position_type=best_target.position_type if best_target else None,
            position_rank=best_target.position_rank if best_target else None,
            mention_rate_pct=mention_rate_pct,
        )
        sentiment_score = GEOScorer.calc_sentiment(
            raw_sentiment_score=best_target.sentiment_score,
            detail_level=best_target.detail_level,
        ) if best_target and best_target.sentiment_score is not None else None
        sov_score = (
            GEOScorer.calc_sov(target_mention_count, total_mentions)
            if target_mention_count and non_target_mentions
            else None
        )
        citation_score = (
            GEOScorer.calc_citations(len(citation_mappings), has_official)
            if citation_mappings
            else None
        )
        geo_score = (
            GEOScorer.calc_overall(visibility, sentiment_score, sov_score, citation_score)
            if best_target
            and sentiment_score is not None
            and sov_score is not None
            and citation_score is not None
            else None
        )

        target_drivers = [
            driver
            for llm_brand in llm_result.brands
            if _resolve_brand_identity(llm_brand.brand_name, None, brand_index)[0] == brand.id
            for driver in llm_brand.sentiment_drivers
        ]
        target_driver_count = len(target_drivers)
        quoted_target_driver_count = sum(
            1 for driver in target_drivers if (driver.source_quote or "").strip()
        )
        attributed_citation_count = sum(
            1 for fact in citation_facts if fact["mention_id"] is not None
        )
        metric_input_status = {
            "sov": {
                "state": "ok" if non_target_mentions else "partial",
                "missing_inputs": [] if non_target_mentions else ["brand_mentions.competitive_set"],
                "target_mentions": target_mention_count,
                "competitive_mentions": total_mentions,
            },
            "sentiment": {
                "state": (
                    "ok"
                    if best_target
                    and best_target.sentiment_score is not None
                    and quoted_target_driver_count
                    else "partial"
                ),
                "missing_inputs": [
                    missing for missing, present in (
                        (
                            "brand_mentions.sentiment_score",
                            best_target and best_target.sentiment_score is not None,
                        ),
                        ("sentiment_drivers.source_quote", bool(quoted_target_driver_count)),
                    )
                    if not present
                ],
                "target_driver_count": target_driver_count,
                "quoted_target_driver_count": quoted_target_driver_count,
            },
            "citation": {
                "state": (
                    "empty"
                    if not citation_mappings
                    else "ok"
                    if attributed_citation_count == len(citation_mappings)
                    else "partial"
                ),
                "missing_inputs": (
                    ["citation_sources"]
                    if not citation_mappings
                    else []
                    if attributed_citation_count == len(citation_mappings)
                    else ["citation_sources.mention_id"]
                ),
                "citation_count": len(citation_mappings),
                "attributed_citation_count": attributed_citation_count,
            },
            "topic": {
                "state": "ok" if topic_id is not None else "partial",
                "missing_inputs": [] if topic_id is not None else ["prompts.topic_id"],
                "prompt_id": prompt_id,
                "topic_id": topic_id,
            },
        }
        analyzer_fact_packages = build_response_fact_packages(
            [
                _response_input_from_pipeline(
                    response=response,
                    query=query,
                    prompt_id=prompt_id,
                    topic_id=topic_id,
                    has_analysis=True,
                    mentions=all_mentions,
                    raw_names_by_mention_id=raw_names_by_mention_id,
                    drivers_by_mention_id=drivers_by_mention_id,
                    citation_facts=citation_facts,
                )
            ],
            target_brand_id=brand.id,
            target_brand_name=brand.name,
            target_aliases=brand.aliases or [],
            configured_competitors=_competitor_contracts_from_competitors(competitors),
        )
        analyzer_fact_package_v3 = build_response_fact_package_v3(
            _response_input_from_pipeline(
                response=response,
                query=query,
                prompt_id=prompt_id,
                topic_id=topic_id,
                has_analysis=True,
                mentions=all_mentions,
                raw_names_by_mention_id=raw_names_by_mention_id,
                drivers_by_mention_id=drivers_by_mention_id,
                citation_facts=citation_facts,
            ),
            target_brand_id=brand.id,
            target_brand_name=brand.name,
            target_aliases=brand.aliases or [],
            configured_competitors=_competitor_contracts_from_competitors(competitors),
            source_brand_id=query.brand_id if query else None,
            provider=getattr(llm_analyzer, "provider", None),
            model=llm_analyzer.model,
            prompt_version=getattr(llm_analyzer, "prompt_version", None),
            raw_output=llm_result.raw_json or {},
            parse_status="ok",
            analysis_completed_at=datetime.utcnow().isoformat(),
        )
        raw_analysis_json = _scope_raw_relation_evidence(
            dict(llm_result.raw_json or {}),
            response_id=response.id,
            query_id=response.query_id,
            prompt_id=prompt_id,
            topic_id=topic_id,
        )
        raw_analysis_json["brand_mention_facts"] = mention_facts
        raw_analysis_json["citation_facts"] = citation_facts
        raw_analysis_json["metric_input_status"] = metric_input_status
        raw_analysis_json["analyzer_fact_packages"] = analyzer_fact_packages
        raw_analysis_json["analyzer_fact_package_v3"] = analyzer_fact_package_v3

        # Create ResponseAnalysis
        analysis = ResponseAnalysis(
            response_id=response.id,
            dimension_industry=llm_result.dimension.industry,
            dimension_company=llm_result.dimension.company,
            dimension_product=llm_result.dimension.product,
            dimension_category=llm_result.dimension.category,
            total_brands_mentioned=len(all_mentions),
            target_brand_mentioned=best_target is not None,
            target_brand_position=(
                best_target.position_type if best_target else None
            ),
            target_brand_rank=(
                best_target.position_rank if best_target else None
            ),
            target_brand_sentiment=(
                best_target.sentiment if best_target else None
            ),
            target_brand_detail=(
                best_target.detail_level if best_target else None
            ),
            visibility_score=round(visibility, 2),
            sentiment_score=round(sentiment_score, 2) if sentiment_score is not None else None,
            sov_score=round(sov_score, 2) if sov_score is not None else None,
            citation_score=round(citation_score, 2) if citation_score is not None else None,
            geo_score=geo_score,
            analyzer_model=llm_analyzer.model,
            raw_analysis_json=raw_analysis_json,
        )
        session.add(analysis)
        await session.flush()

        # Create ProductFeatureMention records from LLM result
        for llm_brand in llm_result.brands:
            for feat in llm_brand.product_features:
                if feat.feature_name:
                    session.add(ProductFeatureMention(
                        analysis_id=analysis.id,
                        brand_name=llm_brand.brand_name,
                        product_name=llm_brand.product_name or llm_brand.brand_name,
                        feature_name=feat.feature_name,
                        feature_sentiment=feat.feature_sentiment,
                        context_snippet=feat.context_snippet,
                        scenario=feat.scenario,
                        price_positioning=feat.price_positioning,
                    ))

        # Mark as done
        response.analysis_status = AnalysisStatus.DONE.value
        response.analyzed_at = datetime.utcnow()
        await session.commit()

        return {
            "response_id": response.id,
            "status": "done",
            "geo_score": geo_score,
            "brands_found": len(all_mentions),
            "target_mentioned": best_target is not None,
        }

    except Exception as e:
        logger.exception(f"Analysis failed for response {response.id}: {e}")
        try:
            await session.rollback()
            response.analysis_status = AnalysisStatus.FAILED.value
            await session.commit()
        except Exception:
            logger.warning(f"Could not mark response {response.id} as failed")
        return {"response_id": response.id, "status": "failed", "error": str(e)}


async def run_daily(date_str: str, brand_id: int | None = None) -> None:
    """Run analysis for all pending responses on a given date."""
    date = datetime.strptime(date_str, "%Y-%m-%d")
    engine = create_task_engine()

    async with get_task_async_session(engine) as session:
        # Find pending responses for the date
        stmt = (
            select(LLMResponse)
            .join(Query, Query.id == LLMResponse.query_id)
            .where(
                LLMResponse.analysis_status == AnalysisStatus.PENDING.value,
                LLMResponse.collected_at >= date.replace(hour=0, minute=0, second=0),
                LLMResponse.collected_at < date.replace(hour=23, minute=59, second=59),
            )
        )
        if brand_id:
            stmt = stmt.where(Query.brand_id == brand_id)

        result = await session.execute(stmt)
        responses = result.scalars().all()

        logger.info(
            f"Found {len(responses)} pending responses for {date_str}"
            + (f" (brand_id={brand_id})" if brand_id else "")
        )

        done = 0
        failed = 0
        for i, resp in enumerate(responses):
            logger.info(f"Analyzing response {i+1}/{len(responses)} (id={resp.id})")
            try:
                # Load related data
                query = await session.get(Query, resp.query_id)
                brand = await session.get(Brand, query.brand_id)

                comp_result = await session.execute(
                    select(Competitor).where(Competitor.brand_id == brand.id)
                )
                competitors = comp_result.scalars().all()

                # Get intent from prompt
                intent = "non_brand"
                if query.prompt_id:
                    prompt = await session.get(Prompt, query.prompt_id)
                    if prompt and prompt.intent:
                        intent = prompt.intent

                result = await analyze_single_response(
                    session, resp, brand, competitors, intent,
                )
                logger.info(f"  Result: {result}")
                if result.get("status") == "done":
                    done += 1
                else:
                    failed += 1
            except Exception as e:
                logger.exception(f"  Unexpected error for response {resp.id}: {e}")
                failed += 1

        logger.info(f"Analysis complete: {done} done, {failed} failed out of {len(responses)}")

        # Aggregate
        logger.info("Running daily aggregation...")
        aggregator = Aggregator(session)
        stats = await aggregator.aggregate_daily(date, brand_id)
        logger.info(f"Aggregation stats: {stats}")

    await engine.dispose()


async def run_aggregate(date_str: str) -> None:
    """Run aggregation only (skip analysis)."""
    date = datetime.strptime(date_str, "%Y-%m-%d")
    engine = create_task_engine()

    async with get_task_async_session(engine) as session:
        aggregator = Aggregator(session)
        stats = await aggregator.aggregate_daily(date)
        logger.info(f"Aggregation stats: {stats}")

    await engine.dispose()


def _parse_day(value: str, *, end_of_day: bool = False) -> datetime:
    day = datetime.strptime(value, "%Y-%m-%d")
    if end_of_day:
        return day.replace(hour=23, minute=59, second=59)
    return day.replace(hour=0, minute=0, second=0)


async def run_canonical_brand_repair(
    *,
    brand_id: int,
    date_str: str | None,
    date_from: str | None,
    date_to: str | None,
    source_brand_id: int | None,
    aliases: list[str] | None,
    competitive_brand_ids: list[int] | None,
    write: bool,
    aggregate: bool,
) -> None:
    """Repair canonical brand mentions from raw text. Dry-run unless write=True."""
    if date_str:
        start_at = _parse_day(date_str)
        end_at = _parse_day(date_str, end_of_day=True)
    else:
        start_at = _parse_day(date_from) if date_from else None
        end_at = _parse_day(date_to, end_of_day=True) if date_to else None

    engine = create_task_engine()
    try:
        async with get_task_async_session(engine) as session:
            stats = await repair_canonical_brand_mentions(
                session,
                brand_id=brand_id,
                start_at=start_at,
                end_at=end_at,
                source_brand_id=source_brand_id,
                extra_aliases=aliases or [],
                competitive_brand_ids=set(competitive_brand_ids or []),
                dry_run=not write,
            )
            logger.info(
                "canonical brand repair complete dry_run=%s brand_id=%s stats=%s",
                not write,
                brand_id,
                stats,
            )
            if write and aggregate:
                if date_str:
                    agg_stats = await Aggregator(session).aggregate_daily(
                        start_at,
                        brand_id,
                        competitive_brand_ids=set(competitive_brand_ids or []),
                    )
                    logger.info("canonical brand aggregate stats=%s", agg_stats)
                else:
                    logger.warning(
                        "--aggregate currently requires --date; skipping aggregation"
                    )
    finally:
        await engine.dispose()


async def run_app_chart_fact_diagnostics(
    *,
    brand_id: int,
    date_str: str | None,
    date_from: str | None,
    date_to: str | None,
    source_brand_id: int | None,
    competitive_brand_ids: list[int] | None,
) -> dict:
    """Dry-run analyzer fact counters for App chart readiness.

    This command performs SELECT-only diagnostics from the pipeline tables. It
    does not repair, backfill, aggregate, or update production data.
    """
    if date_str:
        start_at = _parse_day(date_str)
        end_at = _parse_day(date_str, end_of_day=True)
    else:
        start_at = _parse_day(date_from) if date_from else None
        end_at = _parse_day(date_to, end_of_day=True) if date_to else None

    engine = create_task_engine()
    try:
        async with get_task_async_session(engine) as session:
            brand = await session.get(Brand, brand_id)
            if brand is None:
                raise ValueError(f"brand_id {brand_id} not found")

            competitor_brands = []
            for cid in sorted({int(value) for value in (competitive_brand_ids or [])}):
                competitor = await session.get(Brand, cid)
                if competitor is not None:
                    competitor_brands.append(competitor)

            conditions = [LLMResponse.raw_text.isnot(None)]
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
            response_ids = [response.id for response, _query in rows]

            analyses_by_response: dict[int, ResponseAnalysis] = {}
            mentions_by_response: dict[int, list[BrandMention]] = defaultdict(list)
            citations_by_response: dict[int, list[CitationSource]] = defaultdict(list)
            drivers_by_mention_id: dict[int, list[dict]] = defaultdict(list)
            raw_names_by_mention_id: dict[int, str] = {}

            if response_ids:
                analyses = (
                    await session.execute(
                        select(ResponseAnalysis).where(ResponseAnalysis.response_id.in_(response_ids))
                    )
                ).scalars().all()
                analyses_by_response = {analysis.response_id: analysis for analysis in analyses}
                for analysis in analyses:
                    raw = analysis.raw_analysis_json if isinstance(analysis.raw_analysis_json, dict) else {}
                    for fact in raw.get("brand_mention_facts") or []:
                        if isinstance(fact, dict) and fact.get("mention_id") is not None:
                            raw_names_by_mention_id[int(fact["mention_id"])] = (
                                fact.get("raw_brand_name")
                                or fact.get("raw_name")
                                or fact.get("brand_name")
                            )

                mention_rows = (
                    await session.execute(
                        select(BrandMention).where(BrandMention.response_id.in_(response_ids))
                    )
                ).scalars().all()
                mention_ids = [mention.id for mention in mention_rows]
                for mention in mention_rows:
                    mentions_by_response[mention.response_id].append(mention)

                if mention_ids:
                    driver_rows = (
                        await session.execute(
                            select(SentimentDriver).where(SentimentDriver.mention_id.in_(mention_ids))
                        )
                    ).scalars().all()
                    for driver in driver_rows:
                        drivers_by_mention_id[driver.mention_id].append(
                            {
                                "driver_text": driver.driver_text,
                                "polarity": driver.polarity,
                                "category": driver.category,
                                "strength": driver.strength,
                                "source_quote": driver.source_quote,
                            }
                        )

                citation_rows = (
                    await session.execute(
                        select(CitationSource).where(CitationSource.response_id.in_(response_ids))
                    )
                ).scalars().all()
                for citation in citation_rows:
                    citations_by_response[citation.response_id].append(citation)

            inputs = [
                AnalyzerResponseInput(
                    response_id=response.id,
                    query_id=response.query_id,
                    prompt_id=query.prompt_id if query else None,
                    topic_id=(await _topic_id_for_query(session, query)),
                    project_brand_id=query.brand_id if query else None,
                    engine=query.target_llm if query else None,
                    profile_id=query.profile_id if query else None,
                    collected_at=response.collected_at.isoformat() if response.collected_at else None,
                    analysis_status=response.analysis_status,
                    has_analysis=response.id in analyses_by_response,
                    raw_text=response.raw_text,
                    mentions=[
                        AnalyzerMentionInput(
                            mention_id=mention.id,
                            response_id=mention.response_id,
                            brand_id=mention.brand_id,
                            brand_name=mention.brand_name,
                            raw_name=raw_names_by_mention_id.get(mention.id, mention.brand_name),
                            is_target=bool(mention.is_target),
                            mention_count=mention.mention_count,
                            context_snippet=mention.context_snippet,
                            sentiment=mention.sentiment,
                            sentiment_score=mention.sentiment_score,
                            sentiment_drivers=drivers_by_mention_id.get(mention.id, []),
                            product_name=mention.product_name,
                            position_type=mention.position_type,
                            position_rank=mention.position_rank,
                            provenance="brand_mentions",
                        )
                        for mention in mentions_by_response.get(response.id, [])
                    ],
                    citations=[
                        AnalyzerCitationInput(
                            citation_id=citation.id,
                            response_id=citation.response_id,
                            mention_id=citation.mention_id,
                            url=citation.url,
                            domain=citation.domain,
                            source_type=citation.source_type,
                            title=citation.title,
                        )
                        for citation in citations_by_response.get(response.id, [])
                    ],
                )
                for response, query in rows
            ]
            packages = build_response_fact_packages(
                inputs,
                target_brand_id=brand.id,
                target_brand_name=brand.name,
                target_aliases=brand.aliases or [],
                configured_competitors=_competitor_contracts_from_brands(competitor_brands),
            )
            out = _diagnostic_summary(
                packages,
                brand_id=brand.id,
                brand_name=brand.name,
                start_at=start_at,
                end_at=end_at,
                source_brand_id=source_brand_id,
                competitive_brand_ids=[brand.id for brand in competitor_brands],
            )
            logger.info(
                "app chart fact diagnostics dry_run=true\n%s",
                json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True),
            )
            return out
    finally:
        await engine.dispose()


async def _topic_id_for_query(session, query: Query | None) -> int | None:
    if query is None or query.prompt_id is None:
        return None
    prompt = await session.get(Prompt, query.prompt_id)
    return prompt.topic_id if prompt else None


def _diagnostic_summary(
    packages: dict,
    *,
    brand_id: int,
    brand_name: str,
    start_at: datetime | None,
    end_at: datetime | None,
    source_brand_id: int | None,
    competitive_brand_ids: list[int],
) -> dict:
    entities = packages["entities"]["facts"]
    return {
        "dry_run": True,
        "write_performed": False,
        "brand": {"brand_id": brand_id, "brand_name": brand_name},
        "window": {
            "from": start_at.isoformat() if start_at else None,
            "to": end_at.isoformat() if end_at else None,
            "source_brand_id": source_brand_id,
            "competitive_brand_ids": competitive_brand_ids,
        },
        "response_coverage": {
            "status": packages["coverage"]["status"],
            "eligible": packages["coverage"]["eligible_count"],
            "analyzed": packages["coverage"]["analyzed_count"],
            "failed": packages["coverage"]["failed_count"],
            "missing": packages["coverage"]["missing_analyzer_count"],
            "reason_codes": packages["coverage"]["reason_codes"],
        },
        "competitor_extraction": {
            "structured_competitors": sum(
                1
                for fact in entities
                if fact["entity_role"] in {"configured_competitor", "response_named_competitor"}
                and fact["source"] == "brand_mentions"
            ),
            "text_only_competitors": sum(
                1 for fact in entities if fact["source"] == "text_configured_competitor"
            ),
            "competitor_names": sorted(
                {
                    fact["brand_name"] or fact["raw_name"]
                    for fact in entities
                    if fact["entity_role"] in {"configured_competitor", "response_named_competitor"}
                }
            ),
        },
        "sov": packages["sov"],
        "sentiment": {
            "status": packages["sentiment"]["status"],
            "score_count": packages["sentiment"]["score_count"],
            "label_count": packages["sentiment"]["label_count"],
            "driver_count": packages["sentiment"]["driver_count"],
            "quote_count": packages["sentiment"]["quote_count"],
            "reason_codes": packages["sentiment"]["reason_codes"],
        },
        "citations": packages["citations"],
        "topic_product_pano": {
            "topic_product": packages["topic_product"],
            "pano_geo": packages["pano_geo"],
        },
        "aggregate_rows": {
            "not_recomputed": True,
            "reason": "diagnostics command is SELECT-only and performs no production writes",
        },
        "rollback": "No rollback required for this dry-run diagnostics command; it performs no writes.",
    }


async def run_reanalyze(date_str: str) -> None:
    """Reset analysis status and re-run for a date."""
    date = datetime.strptime(date_str, "%Y-%m-%d")
    engine = create_task_engine()

    async with get_task_async_session(engine) as session:
        # Reset analysis_status to PENDING
        stmt = (
            update(LLMResponse)
            .where(
                LLMResponse.collected_at >= date.replace(hour=0, minute=0, second=0),
                LLMResponse.collected_at < date.replace(hour=23, minute=59, second=59),
            )
            .values(analysis_status=AnalysisStatus.PENDING.value)
        )
        result = await session.execute(stmt)
        await session.commit()
        logger.info(f"Reset {result.rowcount} responses to PENDING")

    await engine.dispose()

    # Now run analysis
    await run_daily(date_str)


def main():
    parser = argparse.ArgumentParser(description="GEN Analyzer CLI")
    subparsers = parser.add_subparsers(dest="command")

    # run-daily
    p_daily = subparsers.add_parser("run-daily", help="Run daily analysis pipeline")
    p_daily.add_argument("--date", required=True, help="Date to analyze (YYYY-MM-DD)")
    p_daily.add_argument("--brand-id", type=int, help="Specific brand ID")

    # aggregate
    p_agg = subparsers.add_parser("aggregate", help="Run aggregation only")
    p_agg.add_argument("--date", required=True, help="Date to aggregate (YYYY-MM-DD)")

    # reanalyze
    p_re = subparsers.add_parser("reanalyze", help="Reset and re-analyze")
    p_re.add_argument("--date", required=True, help="Date to reanalyze (YYYY-MM-DD)")

    # canonical brand repair
    p_repair = subparsers.add_parser(
        "repair-canonical-brand",
        help="Dry-run-safe canonical brand mention repair from raw response text",
    )
    p_repair.add_argument("--brand-id", type=int, required=True, help="Canonical brand ID")
    p_repair.add_argument("--date", help="Single date to repair (YYYY-MM-DD)")
    p_repair.add_argument("--from", dest="date_from", help="Start date (YYYY-MM-DD)")
    p_repair.add_argument("--to", dest="date_to", help="End date (YYYY-MM-DD)")
    p_repair.add_argument("--source-brand-id", type=int, help="Optional owner brand filter")
    p_repair.add_argument("--alias", action="append", default=[], help="Extra alias term")
    p_repair.add_argument(
        "--competitive-brand-id",
        action="append",
        type=int,
        default=[],
        help="Project competitive brand ID for SoV denominator; repeatable.",
    )
    p_repair.add_argument(
        "--write",
        action="store_true",
        help="Apply writes. Omit for dry-run.",
    )
    p_repair.add_argument(
        "--aggregate",
        action="store_true",
        help="After --write, aggregate the repaired single --date for the canonical brand.",
    )

    # app chart fact diagnostics
    p_diag = subparsers.add_parser(
        "diagnose-app-chart-facts",
        help="SELECT-only dry-run counters for #602 App chart analyzer facts",
    )
    p_diag.add_argument("--brand-id", type=int, required=True, help="Canonical target brand ID")
    p_diag.add_argument("--date", help="Single date to inspect (YYYY-MM-DD)")
    p_diag.add_argument("--from", dest="date_from", help="Start date (YYYY-MM-DD)")
    p_diag.add_argument("--to", dest="date_to", help="End date (YYYY-MM-DD)")
    p_diag.add_argument("--source-brand-id", type=int, help="Optional owner/source brand filter")
    p_diag.add_argument(
        "--competitive-brand-id",
        action="append",
        type=int,
        default=[],
        help="Competitive canonical brand ID for denominator hints; repeatable.",
    )

    args = parser.parse_args()

    if args.command == "run-daily":
        asyncio.run(run_daily(args.date, args.brand_id))
    elif args.command == "aggregate":
        asyncio.run(run_aggregate(args.date))
    elif args.command == "reanalyze":
        asyncio.run(run_reanalyze(args.date))
    elif args.command == "repair-canonical-brand":
        asyncio.run(
            run_canonical_brand_repair(
                brand_id=args.brand_id,
                date_str=args.date,
                date_from=args.date_from,
                date_to=args.date_to,
                source_brand_id=args.source_brand_id,
                aliases=args.alias,
                competitive_brand_ids=args.competitive_brand_id,
                write=args.write,
                aggregate=args.aggregate,
            )
        )
    elif args.command == "diagnose-app-chart-facts":
        asyncio.run(
            run_app_chart_fact_diagnostics(
                brand_id=args.brand_id,
                date_str=args.date,
                date_from=args.date_from,
                date_to=args.date_to,
                source_brand_id=args.source_brand_id,
                competitive_brand_ids=args.competitive_brand_id,
            )
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
