"""brand_performance section (PRD §4.7.2 / audit #1044 B2-5).

Per-brand sub-metric breakdown for every brand in scope (primary +
competitors). Aggregates `geo_score_daily` over the report window and
surfaces:

  - mention_rate (%)
  - SoV (%)
  - first_place_rate (%)
  - avg_sentiment (raw -1..1)
  - avg_geo_score
  - sample count + engine count

Unlike `competitor_comparison` (which is rank-focused), this section
is a per-brand drill-down — each brand gets a row that the renderer
can stack as cards.

Skip-on-no-samples (B2-9 consistency) is preserved.
"""

from __future__ import annotations

from typing import Any

from genpano_models import GeoScoreDaily
from sqlalchemy import and_, func, select

from app.reports.sections.base import BaseSection, ReportContext, SectionData


class BrandPerformanceSection(BaseSection):
    section_type = "brand_performance"

    async def render(self, ctx: ReportContext, *, variant: str) -> SectionData:
        if not ctx.brand_ids:
            return SectionData(
                section_type=self.section_type,
                title=_title(ctx.locale),
                summary=_empty_msg(ctx.locale),
                chosen_variant=variant,
            )

        rows: list[dict[str, Any]] = []
        skipped: list[int] = []
        for bid in ctx.brand_ids:
            agg = select(
                func.count(GeoScoreDaily.id),
                func.avg(GeoScoreDaily.mention_rate),
                func.avg(GeoScoreDaily.avg_sov),
                func.avg(GeoScoreDaily.first_place_rate),
                func.avg(GeoScoreDaily.avg_sentiment),
                func.avg(GeoScoreDaily.avg_geo_score),
                func.count(func.distinct(GeoScoreDaily.target_llm)),
            ).where(
                and_(
                    GeoScoreDaily.brand_id == bid,
                    GeoScoreDaily.date >= ctx.from_date,
                    GeoScoreDaily.date <= ctx.to_date,
                )
            )
            r = (await ctx.session.execute(agg)).one()
            samples = int(r[0] or 0)
            if samples == 0:
                skipped.append(bid)
                continue
            rows.append(
                {
                    "brand_id": bid,
                    "is_primary": bid == ctx.project.primary_brand_id,
                    "samples": samples,
                    "engines": int(r[6] or 0),
                    "mention_rate": round(float(r[1] or 0), 4),
                    "sov": round(float(r[2] or 0), 4),
                    "first_place_rate": round(float(r[3] or 0), 4),
                    "avg_sentiment": round(float(r[4] or 0), 3),
                    "avg_geo_score": round(float(r[5] or 0), 2),
                }
            )

        rows.sort(key=lambda r: (0 if r["is_primary"] else 1, -r["avg_geo_score"]))

        primary = next((r for r in rows if r["is_primary"]), None)
        metrics: dict[str, Any] = {"brand_count": len(rows)}
        if primary is not None:
            metrics["primary"] = primary
        if skipped:
            metrics["skipped_no_data_brand_ids"] = skipped

        return SectionData(
            section_type=self.section_type,
            title=_title(ctx.locale),
            summary=_summary(ctx.locale, primary=primary, total=len(rows), skipped=skipped),
            metrics=metrics,
            tables=[{"name": "brand_performance", "rows": rows}],
            chosen_variant=variant,
        )


def _title(locale: str) -> str:
    return "品牌表现" if locale.startswith("zh") else "Brand Performance"


def _empty_msg(locale: str) -> str:
    return (
        "本期无可衡量品牌(项目尚未配置主品牌或竞品)。"
        if locale.startswith("zh")
        else "No measurable brands this period (no primary brand / competitors configured)."
    )


def _summary(
    locale: str,
    *,
    primary: dict[str, Any] | None,
    total: int,
    skipped: list[int],
) -> str:
    is_zh = locale.startswith("zh")
    if primary is None:
        if is_zh:
            return f"本期 {total} 个品牌有数据;主品牌无数据。"
        return f"This period: {total} brand(s) with data; primary brand has no data."
    mr = primary["mention_rate"] * 100
    sov = primary["sov"] * 100
    if is_zh:
        skip_note = f" 跳过 {len(skipped)} 个无数据品牌。" if skipped else ""
        return (
            f"主品牌提及率 {mr:.2f}%、SoV {sov:.2f}%、GEO "
            f"{primary['avg_geo_score']}(基于 {primary['samples']} 个采样)。" + skip_note
        )
    skip_note = f" Skipped {len(skipped)} brand(s) with no data." if skipped else ""
    return (
        f"Primary: mention {mr:.2f}%, SoV {sov:.2f}%, GEO "
        f"{primary['avg_geo_score']} ({primary['samples']} samples)." + skip_note
    )
