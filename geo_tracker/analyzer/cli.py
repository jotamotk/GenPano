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
import logging
import sys
from datetime import datetime

from sqlalchemy import delete, select, update

from geo_tracker.config import create_task_engine, get_task_async_session
from geo_tracker.db.models import (
    AnalysisStatus, Brand, BrandMention, CitationSource,
    Competitor, LLMResponse, ProductFeatureMention, Prompt,
    Query, ResponseAnalysis, SentimentDriver,
)
from geo_tracker.analyzer.brand_detector import BrandDetector
from geo_tracker.analyzer.llm_analyzer import LLMAnalyzer
from geo_tracker.analyzer.citation_mapper import CitationMapper
from geo_tracker.analyzer.geo_scorer import GEOScorer
from geo_tracker.analyzer.aggregator import Aggregator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


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
    # Delete old mentions (cascade deletes sentiment_drivers)
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

        # Stage 3: Citation mapping
        citation_mappings = citation_mapper.map_citations(
            response.citations_json, detected, brand,
        )
        logger.info(f"  Stage 3: mapped {len(citation_mappings)} citations")

        # ── Write results to DB ──

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

        # First pass: match detected brands with LLM results
        for di, d in enumerate(detected):
            # Find ALL LLM entries for this brand (may have multiple products)
            matching_llm = [
                (k, b) for k, b in llm_brands.items()
                if k[0] == d.brand_name.lower()
            ]

            if not matching_llm:
                # No LLM match — create a brand-only mention
                matching_llm = [(None, None)]

            for key, llm_brand in matching_llm:
                if key:
                    processed_llm_keys.add(key)

                mention = BrandMention(
                    response_id=response.id,
                    brand_id=d.brand_id,
                    brand_name=d.brand_name,
                    product_name=llm_brand.product_name if llm_brand else None,
                    is_target=d.is_target,
                    position_type=(
                        llm_brand.position_type if llm_brand else "mentioned_only"
                    ),
                    position_rank=(
                        llm_brand.position_rank if llm_brand else None
                    ),
                    detail_level=(
                        llm_brand.detail_level if llm_brand else "passing"
                    ),
                    sentiment=(
                        llm_brand.sentiment if llm_brand else "neutral"
                    ),
                    sentiment_score=(
                        llm_brand.sentiment_score if llm_brand else 0.0
                    ),
                    context_snippet=(
                        d.context_snippets[0] if d.context_snippets else None
                    ),
                    mention_count=d.mention_count,
                )
                session.add(mention)
                await session.flush()

                total_mentions += d.mention_count
                all_mentions.append(mention)

                if d.is_target:
                    target_mentions.append(mention)

                # Create SentimentDriver records for each product entry
                if llm_brand:
                    for driver in llm_brand.sentiment_drivers:
                        session.add(SentimentDriver(
                            mention_id=mention.id,
                            response_id=response.id,
                            brand_name=d.brand_name,
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

            mention = BrandMention(
                response_id=response.id,
                brand_name=llm_brand.brand_name,
                product_name=llm_brand.product_name,
                is_target=False,
                position_type=llm_brand.position_type,
                position_rank=llm_brand.position_rank,
                detail_level=llm_brand.detail_level,
                sentiment="neutral",
                sentiment_score=0.0,
                mention_count=1,
            )
            session.add(mention)
            await session.flush()
            total_mentions += 1
            all_mentions.append(mention)

            for driver in llm_brand.sentiment_drivers:
                session.add(SentimentDriver(
                    mention_id=mention.id,
                    response_id=response.id,
                    brand_name=llm_brand.brand_name,
                    driver_text=driver.driver_text,
                    polarity=driver.polarity,
                    category=driver.category,
                    strength=driver.strength,
                    source_quote=driver.source_quote,
                ))

        # Create CitationSource records
        has_official = False
        for cm in citation_mappings:
            if cm.source_type == "official_site":
                has_official = True
            session.add(CitationSource(
                response_id=response.id,
                url=cm.url,
                domain=cm.domain,
                title=cm.title,
                citation_index=cm.citation_index,
                source_type=cm.source_type,
            ))

        # Calculate GEO Score
        # Use the best target mention (highest position) for scoring
        target_mention_count = sum(
            m.mention_count for m in target_mentions
        )
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
            raw_sentiment_score=(
                best_target.sentiment_score if best_target else 0.0
            ),
            detail_level=(
                best_target.detail_level if best_target else None
            ),
        )
        sov_score = GEOScorer.calc_sov(target_mention_count, total_mentions)
        citation_score = GEOScorer.calc_citations(
            len(citation_mappings), has_official,
        )
        geo_score = GEOScorer.calc_overall(
            visibility, sentiment_score, sov_score, citation_score,
        )

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
            sentiment_score=round(sentiment_score, 2),
            sov_score=round(sov_score, 2),
            citation_score=round(citation_score, 2),
            geo_score=geo_score,
            analyzer_model=llm_analyzer.model,
            raw_analysis_json=llm_result.raw_json,
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

    args = parser.parse_args()

    if args.command == "run-daily":
        asyncio.run(run_daily(args.date, args.brand_id))
    elif args.command == "aggregate":
        asyncio.run(run_aggregate(args.date))
    elif args.command == "reanalyze":
        asyncio.run(run_reanalyze(args.date))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
