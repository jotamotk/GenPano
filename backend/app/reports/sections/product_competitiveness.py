"""product_competitiveness section (PRD §4.7.2 / audit #1044 B2-5).

Per-product breakdown for the primary brand: mention rate, average
position, category rank, sentiment, comparison wins. Aggregated from
`product_score_daily` over the report window.

The renderer surfaces a ranked table — top performers + the weakest
positions for the period. Useful for product marketing to spot which
SKU is over/under-performing in the AI engines' answers.

Sort key: `mention_rate DESC` (tiebreak `first_place_rate DESC`). We
cannot sort by `avg_geo_score` because the canonical aggregator
(`geo_tracker/analyzer/aggregator.py::_aggregate_product_daily`) does
not populate that column today — every row carries the default 0.0
and the ranking would be arbitrary. `mention_rate` is reliably written
on every aggregation pass (Codex review on #1064).
"""

from __future__ import annotations

from typing import Any

from genpano_models import ProductScoreDaily
from sqlalchemy import and_, func, select

from app.reports.sections.base import BaseSection, ReportContext, SectionData

_TOP_K = 10


class ProductCompetitivenessSection(BaseSection):
    section_type = "product_competitiveness"

    async def render(self, ctx: ReportContext, *, variant: str) -> SectionData:
        if ctx.project.primary_brand_id is None:
            return _empty(ctx, variant, "no_primary_brand")

        stmt = (
            select(
                ProductScoreDaily.product_name,
                ProductScoreDaily.category,
                func.avg(ProductScoreDaily.mention_rate),
                func.avg(ProductScoreDaily.first_place_rate),
                func.avg(ProductScoreDaily.avg_sentiment_score),
                func.avg(ProductScoreDaily.avg_geo_score),
                func.avg(ProductScoreDaily.category_rank),
                func.sum(ProductScoreDaily.comparison_wins),
                func.count(ProductScoreDaily.id),
            )
            .where(
                and_(
                    ProductScoreDaily.brand_id == ctx.project.primary_brand_id,
                    ProductScoreDaily.date >= ctx.from_date,
                    ProductScoreDaily.date <= ctx.to_date,
                )
            )
            .group_by(ProductScoreDaily.product_name, ProductScoreDaily.category)
            .order_by(
                func.avg(ProductScoreDaily.mention_rate).desc(),
                func.avg(ProductScoreDaily.first_place_rate).desc(),
            )
            .limit(_TOP_K)
        )
        result = (await ctx.session.execute(stmt)).all()
        if not result:
            return _empty(ctx, variant, "no_product_data")

        rows: list[dict[str, Any]] = []
        for r in result:
            rows.append(
                {
                    "product_name": r[0],
                    "category": r[1],
                    "samples": int(r[8] or 0),
                    "mention_rate": round(float(r[2] or 0), 4),
                    "first_place_rate": round(float(r[3] or 0), 4),
                    "avg_sentiment": round(float(r[4] or 0), 3),
                    "avg_geo_score": round(float(r[5] or 0), 2),
                    "avg_category_rank": (round(float(r[6]), 1) if r[6] is not None else None),
                    "comparison_wins": int(r[7] or 0),
                }
            )

        top = rows[0]
        weakest = rows[-1] if len(rows) > 1 else None
        metrics: dict[str, Any] = {
            "product_count": len(rows),
            "top_product": top,
        }
        if weakest is not None and weakest is not top:
            metrics["weakest_product"] = weakest

        return SectionData(
            section_type=self.section_type,
            title=_title(ctx.locale),
            summary=_summary(ctx.locale, top=top, weakest=weakest, total=len(rows)),
            metrics=metrics,
            tables=[{"name": "product_ranking", "rows": rows}],
            chosen_variant=variant,
        )


def _empty(ctx: ReportContext, variant: str, reason: str) -> SectionData:
    is_zh = ctx.locale.startswith("zh")
    return SectionData(
        section_type="product_competitiveness",
        title=_title(ctx.locale),
        summary=(
            "本期无产品级数据(可能尚未导入产品列表或品牌无产品维度数据)。"
            if is_zh
            else "No product-level data this period (no product roster or no signals collected)."
        ),
        metrics={"empty_reason": reason},
        chosen_variant=variant,
    )


def _title(locale: str) -> str:
    return "产品竞争力" if locale.startswith("zh") else "Product Competitiveness"


def _summary(
    locale: str,
    *,
    top: dict[str, Any],
    weakest: dict[str, Any] | None,
    total: int,
) -> str:
    is_zh = locale.startswith("zh")
    top_mr = (top.get("mention_rate") or 0) * 100
    if is_zh:
        head = f"本期共 {total} 个产品有数据;领先:'{top['product_name']}'(提及率 {top_mr:.2f}%)。"
        if weakest is not None and weakest is not top:
            weak_mr = (weakest.get("mention_rate") or 0) * 100
            head += f" 表现最弱:'{weakest['product_name']}'(提及率 {weak_mr:.2f}%)。"
        return head
    head = (
        f"This period: {total} product(s) with data; top "
        f"'{top['product_name']}' (mention rate {top_mr:.2f}%)."
    )
    if weakest is not None and weakest is not top:
        weak_mr = (weakest.get("mention_rate") or 0) * 100
        head += f" Weakest: '{weakest['product_name']}' (mention rate {weak_mr:.2f}%)."
    return head
