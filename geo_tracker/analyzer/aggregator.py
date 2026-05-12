"""
每日聚合器 — 将 ResponseAnalysis 聚合为三张日维度表

1. GEOScoreDaily          — 品牌级每日聚合
2. IndustryBenchmarkDaily — 行业基准聚合
3. ProductScoreDaily      — 产品级每日聚合

使用 UPSERT 语义：同维度同日期重跑会更新而非重复插入。
"""
from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import select, and_, delete, null
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.db.models import (
    Brand, BrandMention, CitationSource, GEOScoreDaily,
    IndustryBenchmarkDaily, LLMResponse, ProductFeatureMention,
    ProductScoreDaily, Prompt, Query, ResponseAnalysis, AnalysisStatus, Topic,
    TopicScoreDaily,
)
from geo_tracker.analyzer.geo_scorer import GEOScorer

logger = logging.getLogger(__name__)

PRD_CATEGORY_DIMENSIONS = {"品类", "category"}
PRD_NON_BRAND_INTENTS = {"nonbrand", "nonbranded", "informational"}
PRD_NON_BRAND_SCOPES = {"nonbrand", "nonbranded", "category"}


def _nullable_metric(value):
    return value if value is not None else null()


class Aggregator:
    """每日聚合统计"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def aggregate_daily(
        self,
        date: datetime,
        brand_id: int | None = None,
        competitive_brand_ids: set[int] | None = None,
    ) -> dict:
        """
        聚合某天的分析结果到三张日维度表。

        Args:
            date: 聚合日期
            brand_id: 指定品牌 ID，None 则聚合所有品牌
        """
        competitive_brand_ids = set(competitive_brand_ids or [])
        if brand_id is not None and competitive_brand_ids:
            competitive_brand_ids.add(brand_id)

        stats = {
            "geo_score_daily": 0,
            "industry_benchmark": 0,
            "product_score": 0,
            "topic_score": 0,
        }
        date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_end = date.replace(hour=23, minute=59, second=59)
        stats.update(
            await self._clear_existing_daily_aggregates(date_start, brand_id)
        )

        # Get all analyzed responses for the given date
        stmt = (
            select(ResponseAnalysis)
            .join(LLMResponse, LLMResponse.id == ResponseAnalysis.response_id)
            .where(
                LLMResponse.analysis_status == AnalysisStatus.DONE.value,
                LLMResponse.collected_at >= date_start,
                LLMResponse.collected_at < date_end,
            )
        )
        result = await self.session.execute(stmt)
        analyses = result.scalars().all()

        if not analyses:
            logger.info(f"No analyzed responses for {date.date()}")
            await self.session.commit()
            return stats

        # Get related data
        response_ids = [a.response_id for a in analyses]
        mentions = await self._get_mentions(response_ids)
        queries = await self._get_queries(response_ids)
        citation_response_ids_by_brand = await self._get_citation_response_ids_by_brand(
            response_ids
        )
        prompts_by_query = await self._get_prompts_for_queries(queries.values())

        source_owners_by_fact_brand = self._source_owners_by_fact_brand(mentions, queries)
        brand_ids = self._brand_ids_for_aggregation(queries, mentions, brand_id)

        # 1. Aggregate GEOScoreDaily per brand
        for bid in brand_ids:
            denominator_owner_ids = {bid}
            denominator_owner_ids.update(source_owners_by_fact_brand.get(bid, set()))
            brand_analyses_list = [
                a for a in analyses
                if (q := queries.get(a.response_id)) is not None
                and q.brand_id in denominator_owner_ids
            ]
            if not brand_analyses_list:
                continue
            count = await self._aggregate_brand_daily(
                bid, date, brand_analyses_list, mentions, queries,
                citation_response_ids_by_brand, prompts_by_query, competitive_brand_ids,
            )
            stats["geo_score_daily"] += count

        # 2. Aggregate IndustryBenchmarkDaily
        stats["industry_benchmark"] = await self._aggregate_industry_daily(date)

        # 3. Aggregate ProductScoreDaily
        stats["product_score"] = await self._aggregate_product_daily(
            date, mentions, queries, brand_id,
        )

        # 4. Aggregate TopicScoreDaily — backs projects/:id/topics endpoint
        stats["topic_score"] = await self._aggregate_topic_daily(
            date, analyses, mentions, queries, brand_id,
        )

        await self.session.commit()
        logger.info(f"Aggregation complete for {date.date()}: {stats}")
        return stats

    async def _clear_existing_daily_aggregates(
        self,
        date_start: datetime,
        brand_id: int | None,
    ) -> dict[str, int]:
        """Remove stale aggregate rows before recomputing a date/brand scope."""
        stats: dict[str, int] = {}
        scoped_tables = [
            ("geo_score_daily_removed", GEOScoreDaily),
            ("product_score_removed", ProductScoreDaily),
            ("topic_score_removed", TopicScoreDaily),
        ]
        for stat_key, model in scoped_tables:
            stmt = delete(model).where(model.date == date_start)
            if brand_id is not None:
                stmt = stmt.where(model.brand_id == brand_id)
            result = await self.session.execute(stmt)
            stats[stat_key] = max(result.rowcount or 0, 0)

        if brand_id is None:
            result = await self.session.execute(
                delete(IndustryBenchmarkDaily).where(
                    IndustryBenchmarkDaily.date == date_start,
                )
            )
            stats["industry_benchmark_removed"] = max(result.rowcount or 0, 0)

        return stats

    async def _aggregate_brand_daily(
        self,
        brand_id: int,
        date: datetime,
        analyses: list[ResponseAnalysis],
        mentions: dict[int, list[BrandMention]],
        queries: dict[int, Query],
        citation_response_ids_by_brand: dict[int, set[int]],
        prompts_by_query: dict[int, tuple[str | None, str | None, str | None, Any]],
        competitive_brand_ids: set[int],
    ) -> int:
        """Aggregate GEOScoreDaily for one brand on one day.

        Writes the all-NULL rollup row (preserving prior behavior so
        IndustryBenchmarkDaily and other consumers that filter on all-NULL
        keep working), plus one row per (target_llm, intent, language)
        combination so analyzer-quality + frontend can drill into dimensions.
        """
        total_queries = len(analyses)
        if total_queries == 0:
            return 0

        date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)

        # all-NULL rollup (existing behavior, plus citation_rate)
        rows_written = 0
        if await self._upsert_brand_daily_row(
            brand_id, date_start, analyses, mentions,
            queries, citation_response_ids_by_brand, prompts_by_query, competitive_brand_ids,
            target_llm=None, intent=None, language=None,
        ):
            rows_written += 1

        # Group analyses by (target_llm, intent, language) — only writing a
        # dimension row when the tuple has at least one non-None value, to avoid
        # duplicating the all-NULL rollup.
        groups: dict[tuple[str | None, str | None, str | None], list[ResponseAnalysis]] = defaultdict(list)
        for a in analyses:
            q = queries.get(a.response_id)
            if not q:
                continue
            intent, language, _category, _tags = prompts_by_query.get(
                q.id,
                (None, None, None, None),
            )
            key = (q.target_llm, intent, language)
            if key == (None, None, None):
                continue
            groups[key].append(a)

        for (llm, intent, language), group_analyses in groups.items():
            if not group_analyses:
                continue
            if await self._upsert_brand_daily_row(
                brand_id, date_start, group_analyses, mentions,
                queries, citation_response_ids_by_brand, prompts_by_query, competitive_brand_ids,
                target_llm=llm, intent=intent, language=language,
            ):
                rows_written += 1

        return rows_written

    async def _upsert_brand_daily_row(
        self,
        brand_id: int,
        date_start: datetime,
        analyses: list[ResponseAnalysis],
        mentions: dict[int, list[BrandMention]],
        queries: dict[int, Query],
        citation_response_ids_by_brand: dict[int, set[int]],
        prompts_by_query: dict[int, tuple[str | None, str | None, str | None, Any]],
        competitive_brand_ids: set[int],
        target_llm: str | None,
        intent: str | None,
        language: str | None,
    ) -> bool:
        default_eligible_analyses = [
            a for a in analyses
            if (q := queries.get(a.response_id)) is not None
            and self._is_default_mention_rate_eligible(q, prompts_by_query)
        ]
        eligible_analyses = default_eligible_analyses
        total_queries = len(eligible_analyses)
        if total_queries == 0:
            return False

        target_mentions = []
        for a in eligible_analyses:
            for m in mentions.get(a.response_id, []):
                if self._mention_matches_brand(m, brand_id):
                    target_mentions.append(m)

        target_mention_response_ids = {m.response_id for m in target_mentions}
        mention_count = len(target_mention_response_ids)
        mention_rate = mention_count / total_queries if total_queries else 0
        competitive_mentions = self._competitive_mentions_for_sov(
            eligible_analyses,
            mentions,
            brand_id,
            competitive_brand_ids,
        )
        competitive_mention_count = sum(m.mention_count or 1 for m in competitive_mentions)
        target_competitive_mention_count = sum(
            m.mention_count or 1
            for m in competitive_mentions
            if self._mention_matches_brand(m, brand_id)
        )
        non_target_competitive_mention_count = (
            competitive_mention_count - target_competitive_mention_count
        )
        avg_sov = (
            target_competitive_mention_count / competitive_mention_count
            if competitive_mention_count and non_target_competitive_mention_count
            else None
        )

        # Position stats
        ranks = [m.position_rank for m in target_mentions if m.position_rank]
        first_place = sum(
            1 for m in target_mentions
            if m.position_type == "first_recommendation"
        )

        # Sentiment stats
        sentiments = [m.sentiment_score for m in target_mentions if m.sentiment_score is not None]
        has_sentiment_evidence = bool(sentiments)
        positives = sum(1 for m in target_mentions if m.sentiment == "positive")
        negatives = sum(1 for m in target_mentions if m.sentiment == "negative")

        mention_rate_pct = mention_rate * 100
        vis_scores = [
            GEOScorer.calc_visibility(
                True,
                m.position_type,
                m.position_rank,
                mention_rate_pct,
            )
            for m in target_mentions
        ]
        sent_scores = [
            GEOScorer.calc_sentiment(m.sentiment_score, m.detail_level)
            for m in target_mentions
            if m.sentiment_score is not None
        ]
        target_attributed_citation_response_ids = citation_response_ids_by_brand.get(
            brand_id,
            set(),
        )
        citation_evidence_available = bool(target_attributed_citation_response_ids)
        target_cited_responses = target_mention_response_ids.intersection(
            target_attributed_citation_response_ids
        )
        citation_rate = (
            len(target_cited_responses) / len(target_mention_response_ids)
            if target_mention_response_ids and citation_evidence_available else None
        )
        citation_component = (
            GEOScorer.calc_citations(len(target_cited_responses), False)
            if citation_evidence_available else None
        )
        visibility_component = (
            round(sum(vis_scores) / len(vis_scores), 2) if vis_scores else 0
        )
        sentiment_component = (
            round(sum(sent_scores) / len(sent_scores), 2) if sent_scores else None
        )
        sov_component = round(avg_sov * 100, 2) if avg_sov is not None else None
        geo_score = (
            GEOScorer.calc_overall(
                visibility_component,
                sentiment_component,
                sov_component,
                citation_component,
            )
            if target_mentions
            and sentiment_component is not None
            and sov_component is not None
            and citation_component is not None
            else None
        )

        # Industry from first analysis that has it
        industry = next(
            (a.dimension_industry for a in analyses if a.dimension_industry),
            None,
        )

        row = GEOScoreDaily(
            brand_id=brand_id,
            date=date_start,
            target_llm=target_llm,
            intent=intent,
            language=language,
            total_queries=total_queries,
            mention_count=mention_count,
            mention_rate=round(mention_rate, 4),
            avg_position_rank=round(sum(ranks) / len(ranks), 2) if ranks else None,
            first_place_count=first_place,
            first_place_rate=round(first_place / total_queries, 4) if total_queries else 0,
            positive_rate=(
                round(positives / mention_count, 4)
                if mention_count and has_sentiment_evidence else None
            ),
            negative_rate=(
                round(negatives / mention_count, 4)
                if mention_count and has_sentiment_evidence else None
            ),
            avg_sentiment_score=(
                round(sum(sentiments) / len(sentiments), 4) if sentiments else None
            ),
            citation_rate=round(citation_rate, 4) if citation_rate is not None else None,
            avg_sov=round(avg_sov, 4) if avg_sov is not None else None,
            avg_visibility=visibility_component,
            avg_sentiment=sentiment_component,
            avg_sov_score=sov_component,
            avg_citation_score=citation_component,
            avg_geo_score=geo_score,
            industry=industry,
        )
        # SQLAlchemy client defaults on legacy score columns can coerce absent
        # values to 0.0 on INSERT. Reassign after construction so missing
        # upstream evidence remains NULL instead of becoming fake zeros.
        row.positive_rate = _nullable_metric(
            round(positives / mention_count, 4)
            if mention_count and has_sentiment_evidence else None
        )
        row.negative_rate = _nullable_metric(
            round(negatives / mention_count, 4)
            if mention_count and has_sentiment_evidence else None
        )
        row.avg_sentiment_score = _nullable_metric(
            round(sum(sentiments) / len(sentiments), 4) if sentiments else None
        )
        row.citation_rate = _nullable_metric(
            round(citation_rate, 4) if citation_rate is not None else None
        )
        row.avg_sov = _nullable_metric(round(avg_sov, 4) if avg_sov is not None else None)
        row.avg_sentiment = _nullable_metric(sentiment_component)
        row.avg_sov_score = _nullable_metric(sov_component)
        row.avg_citation_score = _nullable_metric(citation_component)
        row.avg_geo_score = _nullable_metric(geo_score)

        # Check existing row for this exact dimension tuple
        # Use is_() for None comparisons (NULL = NULL would never match in SQL)
        conditions = [
            GEOScoreDaily.brand_id == brand_id,
            GEOScoreDaily.date == date_start,
        ]
        for col, val in (
            (GEOScoreDaily.target_llm, target_llm),
            (GEOScoreDaily.intent, intent),
            (GEOScoreDaily.language, language),
        ):
            conditions.append(col.is_(None) if val is None else col == val)

        existing = await self.session.execute(
            select(GEOScoreDaily).where(and_(*conditions))
        )
        existing_row = existing.scalar_one_or_none()

        if existing_row:
            for col in [
                "total_queries", "mention_count", "mention_rate",
                "avg_position_rank", "first_place_count", "first_place_rate",
                "positive_rate", "negative_rate", "avg_sentiment_score",
                "citation_rate",
                "avg_sov", "avg_visibility", "avg_sentiment",
                "avg_sov_score", "avg_citation_score", "avg_geo_score",
                "industry",
            ]:
                setattr(existing_row, col, getattr(row, col))
        else:
            self.session.add(row)

        return True

    async def _aggregate_industry_daily(self, date: datetime) -> int:
        """Aggregate IndustryBenchmarkDaily from GEOScoreDaily rows."""
        date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)

        result = await self.session.execute(
            select(GEOScoreDaily).where(
                GEOScoreDaily.date == date_start,
                GEOScoreDaily.target_llm.is_(None),
                GEOScoreDaily.intent.is_(None),
                GEOScoreDaily.industry.isnot(None),
            )
        )
        daily_rows = result.scalars().all()

        # Group by industry
        by_industry: dict[str, list[GEOScoreDaily]] = defaultdict(list)
        for r in daily_rows:
            if r.industry:
                by_industry[r.industry].append(r)

        count = 0
        for industry, rows in by_industry.items():
            scored_rows = [r for r in rows if r.avg_geo_score is not None]
            if not scored_rows:
                continue
            scores = sorted([r.avg_geo_score for r in scored_rows])
            n = len(scores)

            # Top brands JSON
            sorted_rows = sorted(scored_rows, key=lambda r: r.avg_geo_score, reverse=True)
            top_brands = []
            for rank, r in enumerate(sorted_rows[:5], 1):
                brand = await self.session.get(Brand, r.brand_id)
                top_brands.append({
                    "rank": rank,
                    "name": brand.name if brand else f"brand_{r.brand_id}",
                    "geo_score": r.avg_geo_score,
                    "sov_pct": r.industry_sov_pct or 0,
                    "mention_rate": r.mention_rate,
                    "sentiment": r.avg_sentiment_score,
                })

            # Update industry ranks and SOV on GEOScoreDaily
            total_mentions = sum(r.mention_count for r in rows)
            for rank, r in enumerate(sorted_rows, 1):
                r.industry_rank = rank
                r.industry_sov_pct = round(
                    r.mention_count / total_mentions * 100, 2,
                ) if total_mentions else 0

            benchmark = IndustryBenchmarkDaily(
                industry=industry,
                date=date_start,
                target_llm=None,
                total_brands=n,
                total_queries=sum(r.total_queries for r in rows),
                avg_mention_rate=round(sum(r.mention_rate for r in rows) / n, 4) if n else 0,
                avg_geo_score=round(sum(scores) / n, 2) if n else 0,
                avg_sentiment=round(
                    sum(r.avg_sentiment_score for r in rows) / n, 4,
                ) if n else 0,
                score_p25=scores[n // 4] if n >= 4 else (scores[0] if scores else None),
                score_p50=scores[n // 2] if n >= 2 else (scores[0] if scores else None),
                score_p75=scores[3 * n // 4] if n >= 4 else (scores[-1] if scores else None),
                top_brands_json=top_brands,
            )

            # UPSERT
            existing = await self.session.execute(
                select(IndustryBenchmarkDaily).where(
                    IndustryBenchmarkDaily.industry == industry,
                    IndustryBenchmarkDaily.date == date_start,
                    IndustryBenchmarkDaily.target_llm.is_(None),
                )
            )
            existing_row = existing.scalar_one_or_none()
            if existing_row:
                for col in [
                    "total_brands", "total_queries", "avg_mention_rate",
                    "avg_geo_score", "avg_sentiment", "score_p25", "score_p50",
                    "score_p75", "top_brands_json",
                ]:
                    setattr(existing_row, col, getattr(benchmark, col))
            else:
                self.session.add(benchmark)

            count += 1

        return count

    async def _aggregate_product_daily(
        self,
        date: datetime,
        mentions: dict[int, list[BrandMention]],
        queries: dict[int, Query],
        selected_brand_id: int | None = None,
    ) -> int:
        """Aggregate ProductScoreDaily from BrandMention + ProductFeatureMention."""
        date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Collect product-level data from mentions
        product_data: dict[tuple[int, str], dict] = {}  # (brand_id, product_name) -> stats

        for resp_id, mention_list in mentions.items():
            q = queries.get(resp_id)
            if not q:
                continue

            for m in mention_list:
                if not m.product_name:
                    continue

                bid = m.brand_id or (q.brand_id if m.is_target else None)
                if bid is None:
                    continue
                if selected_brand_id is not None and bid != selected_brand_id:
                    continue
                key = (bid, m.product_name)
                if key not in product_data:
                    product_data[key] = {
                        "brand_id": bid,
                        "product_name": m.product_name,
                        "mention_count": 0,
                        "total_queries": 0,
                        "positions": [],
                        "first_place": 0,
                        "sentiments": [],
                        "comp_wins": 0,
                        "comp_total": 0,
                        "features": Counter(),
                        "scenarios": Counter(),
                        "price_positions": Counter(),
                    }

                pd = product_data[key]
                pd["mention_count"] += 1
                pd["total_queries"] += 1
                if m.position_rank:
                    pd["positions"].append(m.position_rank)
                if m.position_type == "first_recommendation":
                    pd["first_place"] += 1
                if m.sentiment_score is not None:
                    pd["sentiments"].append(m.sentiment_score)
                if m.position_type == "comparison_winner":
                    pd["comp_wins"] += 1
                    pd["comp_total"] += 1
                elif m.position_type == "comparison_loser":
                    pd["comp_total"] += 1

        # Get ProductFeatureMention data for today's analyses
        result = await self.session.execute(
            select(ProductFeatureMention)
            .join(ResponseAnalysis)
            .where(ResponseAnalysis.analyzed_at >= date_start)
        )
        feature_mentions = result.scalars().all()

        for fm in feature_mentions:
            # Find matching product key — we need brand_id from mentions context
            for key, pd in product_data.items():
                if pd["product_name"] == fm.product_name and pd["brand_id"]:
                    if fm.feature_name:
                        pd["features"][fm.feature_name] += 1
                    if fm.scenario:
                        pd["scenarios"][fm.scenario] += 1
                    if fm.price_positioning:
                        pd["price_positions"][fm.price_positioning] += 1
                    break

        # Write ProductScoreDaily rows
        count = 0
        for (bid, pname), pd in product_data.items():
            mc = pd["mention_count"]
            tq = pd["total_queries"]

            top_features = [
                {"feature": f, "count": c, "pct": round(c / mc, 2) if mc else 0}
                for f, c in pd["features"].most_common(5)
            ] or None

            top_scenarios = [
                {"scenario": s, "count": c, "pct": round(c / mc, 2) if mc else 0}
                for s, c in pd["scenarios"].most_common(5)
            ] or None

            pp_counts = dict(pd["price_positions"])
            price_pos = (
                max(pp_counts, key=pp_counts.get) if pp_counts else None
            )

            avg_sentiment_score = (
                round(sum(pd["sentiments"]) / len(pd["sentiments"]), 4)
                if pd["sentiments"] else None
            )
            win_rate = (
                round(pd["comp_wins"] / pd["comp_total"], 4)
                if pd["comp_total"] else None
            )

            row = ProductScoreDaily(
                brand_id=bid,
                product_name=pname,
                date=date_start,
                target_llm=None,
                total_queries=tq,
                mention_count=mc,
                mention_rate=round(mc / tq, 4) if tq else 0,
                avg_position_rank=(
                    round(sum(pd["positions"]) / len(pd["positions"]), 2)
                    if pd["positions"] else None
                ),
                first_place_count=pd["first_place"],
                first_place_rate=round(pd["first_place"] / tq, 4) if tq else 0,
                avg_sentiment_score=avg_sentiment_score,
                comparison_wins=pd["comp_wins"],
                comparison_total=pd["comp_total"],
                win_rate=win_rate,
                top_features_json=top_features,
                top_scenarios_json=top_scenarios,
                price_positioning=price_pos,
                price_positioning_json=pp_counts or None,
            )
            row.avg_sentiment_score = _nullable_metric(avg_sentiment_score)
            row.win_rate = _nullable_metric(win_rate)

            # UPSERT
            existing = await self.session.execute(
                select(ProductScoreDaily).where(
                    ProductScoreDaily.brand_id == bid,
                    ProductScoreDaily.product_name == pname,
                    ProductScoreDaily.date == date_start,
                    ProductScoreDaily.target_llm.is_(None),
                )
            )
            existing_row = existing.scalar_one_or_none()
            if existing_row:
                for col in [
                    "total_queries", "mention_count", "mention_rate",
                    "avg_position_rank", "first_place_count", "first_place_rate",
                    "avg_sentiment_score", "comparison_wins", "comparison_total",
                    "win_rate", "top_features_json", "top_scenarios_json",
                    "price_positioning", "price_positioning_json",
                ]:
                    setattr(existing_row, col, getattr(row, col))
            else:
                self.session.add(row)

            count += 1

        return count

    async def _aggregate_topic_daily(
        self,
        date: datetime,
        analyses: list[ResponseAnalysis],
        mentions: dict[int, list[BrandMention]],
        queries: dict[int, Query],
        selected_brand_id: int | None = None,
    ) -> int:
        """Aggregate per-(brand, topic, date) mention stats from BrandMention.

        Joins: BrandMention.response_id → Query.prompt_id → Prompt.topic_id.
        Backs the projects /topics endpoint.
        """
        date_start = date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Map prompt_id -> topic_id for the prompts referenced by today's queries
        prompt_ids = {q.prompt_id for q in queries.values() if q.prompt_id is not None}
        if not prompt_ids:
            return 0
        result = await self.session.execute(
            select(Prompt.id, Prompt.topic_id).where(Prompt.id.in_(prompt_ids))
        )
        topic_by_prompt = {row[0]: row[1] for row in result.all() if row[1] is not None}

        # Bucket by (brand_id, topic_id)
        # response_count[(brand, topic)]: # responses where the brand was queried under this topic
        # mention_count[(brand, topic)]: # of those responses where target brand actually mentioned
        # rank/sentiment/geo aggregates collected from target mentions / analyses
        groups: dict[tuple[int, int], dict] = defaultdict(lambda: {
            "response_count": 0,
            "mention_count": 0,
            "ranks": [],
            "sentiments": [],
            "geo_scores": [],
        })

        # Index analyses by response_id for quick GEO lookup
        analysis_by_resp = {a.response_id: a for a in analyses}
        source_owners_by_fact_brand = self._source_owners_by_fact_brand(mentions, queries)

        for resp_id, q in queries.items():
            topic_id = topic_by_prompt.get(q.prompt_id)
            if topic_id is None:
                continue
            candidate_brand_ids = {q.brand_id}
            for bid, owner_ids in source_owners_by_fact_brand.items():
                if q.brand_id in owner_ids:
                    candidate_brand_ids.add(bid)
            if selected_brand_id is not None:
                candidate_brand_ids = {
                    bid for bid in candidate_brand_ids if bid == selected_brand_id
                }

            for bid in candidate_brand_ids:
                key = (bid, topic_id)
                g = groups[key]
                g["response_count"] += 1

                target_mentions = [
                    m for m in mentions.get(resp_id, [])
                    if self._mention_matches_brand(m, bid)
                ]
                if target_mentions:
                    g["mention_count"] += 1
                    for m in target_mentions:
                        if m.position_rank:
                            g["ranks"].append(m.position_rank)
                        if m.sentiment_score is not None:
                            g["sentiments"].append(m.sentiment_score)
                a = analysis_by_resp.get(resp_id)
                if a and a.geo_score:
                    g["geo_scores"].append(a.geo_score)

        count = 0
        for (brand_id, topic_id), g in groups.items():
            total = g["response_count"]
            mc = g["mention_count"]
            row = TopicScoreDaily(
                brand_id=brand_id,
                topic_id=topic_id,
                date=date_start,
                mention_count=mc,
                total_responses=total,
                mention_rate=round(mc / total, 4) if total else 0,
                avg_position_rank=(
                    round(sum(g["ranks"]) / len(g["ranks"]), 2) if g["ranks"] else None
                ),
                avg_sentiment_score=(
                    round(sum(g["sentiments"]) / len(g["sentiments"]), 4)
                    if g["sentiments"] else None
                ),
                avg_geo_score=(
                    round(sum(g["geo_scores"]) / len(g["geo_scores"]), 2)
                    if g["geo_scores"] else None
                ),
            )

            existing = await self.session.execute(
                select(TopicScoreDaily).where(
                    TopicScoreDaily.brand_id == brand_id,
                    TopicScoreDaily.topic_id == topic_id,
                    TopicScoreDaily.date == date_start,
                )
            )
            existing_row = existing.scalar_one_or_none()
            if existing_row:
                for col in [
                    "mention_count", "total_responses", "mention_rate",
                    "avg_position_rank", "avg_sentiment_score", "avg_geo_score",
                ]:
                    setattr(existing_row, col, getattr(row, col))
            else:
                self.session.add(row)
            count += 1

        return count

    async def _get_mentions(
        self, response_ids: list[int],
    ) -> dict[int, list[BrandMention]]:
        """Load all BrandMentions for given response IDs, grouped by response_id."""
        if not response_ids:
            return {}
        result = await self.session.execute(
            select(BrandMention).where(BrandMention.response_id.in_(response_ids))
        )
        mentions_by_resp: dict[int, list[BrandMention]] = defaultdict(list)
        for m in result.scalars().all():
            mentions_by_resp[m.response_id].append(m)
        return mentions_by_resp

    async def _get_queries(
        self, response_ids: list[int],
    ) -> dict[int, Query]:
        """Load Queries for given response IDs, keyed by response_id."""
        if not response_ids:
            return {}
        result = await self.session.execute(
            select(LLMResponse.id, LLMResponse.query_id)
            .where(LLMResponse.id.in_(response_ids))
        )
        resp_query_map = {row[0]: row[1] for row in result.all()}

        query_ids = list(resp_query_map.values())
        result = await self.session.execute(
            select(Query).where(Query.id.in_(query_ids))
        )
        queries_by_id = {q.id: q for q in result.scalars().all()}

        return {
            resp_id: queries_by_id[qid]
            for resp_id, qid in resp_query_map.items()
            if qid in queries_by_id
        }

    async def _get_citation_response_ids_by_brand(
        self,
        response_ids: list[int],
    ) -> dict[int, set[int]]:
        """Return response IDs with citation rows attributed to each brand.

        App analytics citation-rate/share evidence must be tied to a persisted
        brand mention. Response-level citation presence is not enough because a
        citation can support a competitor or remain unattributed.
        """
        if not response_ids:
            return {}
        result = await self.session.execute(
            select(CitationSource.response_id, BrandMention.brand_id)
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .where(
                CitationSource.response_id.in_(response_ids),
                BrandMention.brand_id.isnot(None),
            )
            .distinct()
        )
        by_brand: dict[int, set[int]] = defaultdict(set)
        for response_id, brand_id in result.all():
            by_brand[int(brand_id)].add(int(response_id))
        return by_brand

    async def _get_prompts_for_queries(
        self, queries,
    ) -> dict[int, tuple[str | None, str | None, str | None, Any]]:
        """Map query.id -> (intent, language, topic_category, tags) by joining Prompt.

        Used to drive the dimension split when writing per-(llm/intent/language)
        rows in geo_score_daily and to keep default KPI denominators in PRD
        category/non-brand scope.
        """
        prompt_ids = {q.prompt_id for q in queries if q.prompt_id is not None}
        if not prompt_ids:
            return {}
        result = await self.session.execute(
            select(Prompt.id, Prompt.intent, Prompt.language, Topic.category, Prompt.tags)
            .join(Topic, Topic.id == Prompt.topic_id)
            .where(Prompt.id.in_(prompt_ids))
        )
        prompt_attrs = {row[0]: (row[1], row[2], row[3], row[4]) for row in result.all()}
        return {
            q.id: prompt_attrs.get(q.prompt_id, (None, None, None, None))
            for q in queries
            if q.prompt_id is not None
        }

    @staticmethod
    def _is_default_mention_rate_eligible(
        query: Query,
        prompts_by_query: dict[int, tuple[str | None, str | None, str | None, Any]],
    ) -> bool:
        intent, _language, topic_category, tags = prompts_by_query.get(
            query.id,
            (None, None, None, None),
        )
        prompt_scope = _prompt_scope_from_tags(tags)
        topic_dimension = _topic_dimension_from_tags(tags)
        return (
            (
                _normalize_dimension(intent) in PRD_NON_BRAND_INTENTS
                or prompt_scope in PRD_NON_BRAND_SCOPES
            )
            and (
                _is_prd_category_dimension(topic_category)
                or topic_dimension in PRD_CATEGORY_DIMENSIONS
            )
        )

    @staticmethod
    def _competitive_mentions_for_sov(
        analyses: list[ResponseAnalysis],
        mentions: dict[int, list[BrandMention]],
        brand_id: int,
        competitive_brand_ids: set[int],
    ) -> list[BrandMention]:
        """Return mention rows eligible for SoV denominator evidence.

        Configured competitors constrain known canonical brand IDs, but
        unresolved LLM-only brands are still evidence that the extraction
        universe is broader than the target brand.
        """
        denominator_ids = set(competitive_brand_ids or [])
        denominator_ids.add(brand_id)
        use_all_canonical = not competitive_brand_ids
        out: list[BrandMention] = []
        for analysis in analyses:
            for mention in mentions.get(analysis.response_id, []):
                if mention.brand_id is None:
                    out.append(mention)
                    continue
                if use_all_canonical or int(mention.brand_id) in denominator_ids:
                    out.append(mention)
        return out

    @staticmethod
    def _mention_matches_brand(mention: BrandMention, brand_id: int) -> bool:
        return mention.brand_id == brand_id

    @staticmethod
    def _source_owners_by_fact_brand(
        mentions: dict[int, list[BrandMention]],
        queries: dict[int, Query],
    ) -> dict[int, set[int]]:
        source_owners: dict[int, set[int]] = defaultdict(set)
        for response_id, mention_list in mentions.items():
            query = queries.get(response_id)
            if query is None:
                continue
            for mention in mention_list:
                if mention.brand_id is not None:
                    source_owners[int(mention.brand_id)].add(query.brand_id)
        return source_owners

    @staticmethod
    def _brand_ids_for_aggregation(
        queries: dict[int, Query],
        mentions: dict[int, list[BrandMention]],
        selected_brand_id: int | None,
    ) -> list[int]:
        if selected_brand_id is not None:
            return [selected_brand_id]
        brand_ids = {q.brand_id for q in queries.values() if q.brand_id is not None}
        for mention_list in mentions.values():
            for mention in mention_list:
                if mention.brand_id is not None:
                    brand_ids.add(int(mention.brand_id))
        return sorted(brand_ids)


def _normalize_dimension(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    return "".join(ch for ch in normalized if ch not in {" ", "-", "_"})


def _is_prd_category_dimension(value: str | None) -> bool:
    normalized = _normalize_dimension(value)
    if normalized in PRD_CATEGORY_DIMENSIONS:
        return True
    raw = str(value or "").strip().lower()
    return "品类" in raw or "category" in raw


def _prompt_scope_from_tags(tags: Any) -> str | None:
    payload = _coerce_tags(tags)
    candidates: list[Any] = []
    if isinstance(payload, dict):
        candidates.extend(
            payload.get(key)
            for key in ("prompt_scope", "scope", "query_scope", "intent")
        )
    elif isinstance(payload, list | tuple | set):
        candidates.extend(payload)
    elif payload:
        candidates.append(payload)
    for candidate in candidates:
        normalized = _normalize_dimension(str(candidate)) if candidate is not None else None
        if normalized:
            return normalized
    return None


def _topic_dimension_from_tags(tags: Any) -> str | None:
    payload = _coerce_tags(tags)
    if not isinstance(payload, dict):
        return None
    for key in ("topic_dimension", "topicDimension", "dimension", "category_dimension"):
        value = payload.get(key)
        normalized = _normalize_dimension(str(value)) if value is not None else None
        if normalized:
            return normalized
    return None


def _coerce_tags(tags: Any) -> Any:
    if isinstance(tags, str):
        text = tags.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            return text
    return tags
