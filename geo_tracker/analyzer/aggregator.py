"""
每日聚合器 — 将 ResponseAnalysis 聚合为三张日维度表

1. GEOScoreDaily          — 品牌级每日聚合
2. IndustryBenchmarkDaily — 行业基准聚合
3. ProductScoreDaily      — 产品级每日聚合

使用 UPSERT 语义：同维度同日期重跑会更新而非重复插入。
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import datetime

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.db.models import (
    Brand, BrandMention, CitationSource, GEOScoreDaily,
    IndustryBenchmarkDaily, LLMResponse, ProductFeatureMention,
    ProductScoreDaily, Query, ResponseAnalysis, AnalysisStatus,
)

logger = logging.getLogger(__name__)


class Aggregator:
    """每日聚合统计"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def aggregate_daily(
        self,
        date: datetime,
        brand_id: int | None = None,
    ) -> dict:
        """
        聚合某天的分析结果到三张日维度表。

        Args:
            date: 聚合日期
            brand_id: 指定品牌 ID，None 则聚合所有品牌
        """
        stats = {"geo_score_daily": 0, "industry_benchmark": 0, "product_score": 0}

        # Get all analyzed responses for the given date
        stmt = (
            select(ResponseAnalysis)
            .join(LLMResponse, LLMResponse.id == ResponseAnalysis.response_id)
            .where(
                LLMResponse.analysis_status == AnalysisStatus.DONE.value,
                LLMResponse.collected_at >= date.replace(hour=0, minute=0, second=0),
                LLMResponse.collected_at < date.replace(hour=23, minute=59, second=59),
            )
        )
        if brand_id:
            stmt = stmt.join(Query, Query.id == LLMResponse.query_id).where(
                Query.brand_id == brand_id,
            )
        result = await self.session.execute(stmt)
        analyses = result.scalars().all()

        if not analyses:
            logger.info(f"No analyzed responses for {date.date()}")
            return stats

        # Get related data
        response_ids = [a.response_id for a in analyses]
        mentions = await self._get_mentions(response_ids)
        queries = await self._get_queries(response_ids)

        # Group by brand
        brand_analyses = defaultdict(list)
        for a in analyses:
            q = queries.get(a.response_id)
            if q:
                brand_analyses[q.brand_id].append(a)

        # 1. Aggregate GEOScoreDaily per brand
        for bid, brand_analyses_list in brand_analyses.items():
            count = await self._aggregate_brand_daily(
                bid, date, brand_analyses_list, mentions, queries,
            )
            stats["geo_score_daily"] += count

        # 2. Aggregate IndustryBenchmarkDaily
        stats["industry_benchmark"] = await self._aggregate_industry_daily(date)

        # 3. Aggregate ProductScoreDaily
        stats["product_score"] = await self._aggregate_product_daily(
            date, mentions, queries,
        )

        await self.session.commit()
        logger.info(f"Aggregation complete for {date.date()}: {stats}")
        return stats

    async def _aggregate_brand_daily(
        self,
        brand_id: int,
        date: datetime,
        analyses: list[ResponseAnalysis],
        mentions: dict[int, list[BrandMention]],
        queries: dict[int, Query],
    ) -> int:
        """Aggregate GEOScoreDaily for one brand on one day."""
        total_queries = len(analyses)
        if total_queries == 0:
            return 0

        target_mentions = []
        for a in analyses:
            for m in mentions.get(a.response_id, []):
                if m.is_target:
                    target_mentions.append(m)

        mention_count = len(target_mentions)
        mention_rate = mention_count / total_queries if total_queries else 0

        # Position stats
        ranks = [m.position_rank for m in target_mentions if m.position_rank]
        first_place = sum(
            1 for m in target_mentions
            if m.position_type == "first_recommendation"
        )

        # Sentiment stats
        sentiments = [m.sentiment_score for m in target_mentions if m.sentiment_score is not None]
        positives = sum(1 for m in target_mentions if m.sentiment == "positive")
        negatives = sum(1 for m in target_mentions if m.sentiment == "negative")

        # GEO Score averages
        vis_scores = [a.visibility_score for a in analyses if a.visibility_score]
        sent_scores = [a.sentiment_score for a in analyses if a.sentiment_score]
        sov_scores = [a.sov_score for a in analyses if a.sov_score]
        cit_scores = [a.citation_score for a in analyses if a.citation_score]
        geo_scores = [a.geo_score for a in analyses if a.geo_score]

        # Industry from first analysis that has it
        industry = next(
            (a.dimension_industry for a in analyses if a.dimension_industry),
            None,
        )

        # UPSERT: all-platform, all-intent, all-language aggregate
        row = GEOScoreDaily(
            brand_id=brand_id,
            date=date.replace(hour=0, minute=0, second=0, microsecond=0),
            target_llm=None,
            intent=None,
            language=None,
            total_queries=total_queries,
            mention_count=mention_count,
            mention_rate=round(mention_rate, 4),
            avg_position_rank=round(sum(ranks) / len(ranks), 2) if ranks else None,
            first_place_count=first_place,
            first_place_rate=round(first_place / total_queries, 4) if total_queries else 0,
            positive_rate=round(positives / mention_count, 4) if mention_count else 0,
            negative_rate=round(negatives / mention_count, 4) if mention_count else 0,
            avg_sentiment_score=round(sum(sentiments) / len(sentiments), 4) if sentiments else 0,
            citation_rate=0.0,  # TODO: compute from CitationSource
            avg_sov=round(sum(sov_scores) / len(sov_scores), 2) if sov_scores else 0,
            avg_visibility=round(sum(vis_scores) / len(vis_scores), 2) if vis_scores else 0,
            avg_sentiment=round(sum(sent_scores) / len(sent_scores), 2) if sent_scores else 0,
            avg_sov_score=round(sum(sov_scores) / len(sov_scores), 2) if sov_scores else 0,
            avg_citation_score=round(sum(cit_scores) / len(cit_scores), 2) if cit_scores else 0,
            avg_geo_score=round(sum(geo_scores) / len(geo_scores), 2) if geo_scores else 0,
            industry=industry,
        )

        # Check for existing row and update or insert
        existing = await self.session.execute(
            select(GEOScoreDaily).where(
                GEOScoreDaily.brand_id == brand_id,
                GEOScoreDaily.date == row.date,
                GEOScoreDaily.target_llm.is_(None),
                GEOScoreDaily.intent.is_(None),
                GEOScoreDaily.language.is_(None),
            )
        )
        existing_row = existing.scalar_one_or_none()

        if existing_row:
            # Update existing
            for col in [
                "total_queries", "mention_count", "mention_rate",
                "avg_position_rank", "first_place_count", "first_place_rate",
                "positive_rate", "negative_rate", "avg_sentiment_score",
                "avg_sov", "avg_visibility", "avg_sentiment",
                "avg_sov_score", "avg_citation_score", "avg_geo_score",
                "industry",
            ]:
                setattr(existing_row, col, getattr(row, col))
        else:
            self.session.add(row)

        return 1

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
            scores = sorted([r.avg_geo_score for r in rows])
            n = len(scores)

            # Top brands JSON
            sorted_rows = sorted(rows, key=lambda r: r.avg_geo_score, reverse=True)
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

                key = (q.brand_id, m.product_name)
                if key not in product_data:
                    product_data[key] = {
                        "brand_id": q.brand_id,
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
                avg_sentiment_score=(
                    round(sum(pd["sentiments"]) / len(pd["sentiments"]), 4)
                    if pd["sentiments"] else 0
                ),
                comparison_wins=pd["comp_wins"],
                comparison_total=pd["comp_total"],
                win_rate=(
                    round(pd["comp_wins"] / pd["comp_total"], 4)
                    if pd["comp_total"] else 0
                ),
                top_features_json=top_features,
                top_scenarios_json=top_scenarios,
                price_positioning=price_pos,
                price_positioning_json=pp_counts or None,
            )

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
