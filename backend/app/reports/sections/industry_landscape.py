"""industry_landscape section (PRD §4.7.2 / audit #1044 B2-5).

Surfaces where the project's primary brand sits in its industry over
the report window:

  - industry rank (from `geo_score_daily.industry_rank`, averaged)
  - industry median GEO score (from `industry_benchmark_daily`)
  - distance from median + percentile band
  - total brands measured in the industry

The `industry_benchmark_daily` table is keyed by `industry` (string
name), but `Project.industry_id` is an integer position assigned by
`list_industries`. We resolve id → name via the existing helper in
`app/api/v1/industries/service` so multi-industry deployments don't
silently average benchmarks across unrelated industries (Codex review
on #1064).

Falls back to a sparse-but-honest payload when industry data is
absent — never invents a rank for a brand that has no industry-level
samples.
"""

from __future__ import annotations

from typing import Any

from genpano_models import GeoScoreDaily, IndustryBenchmarkDaily
from sqlalchemy import and_, func, select

from app.reports.sections.base import BaseSection, ReportContext, SectionData


class IndustryLandscapeSection(BaseSection):
    section_type = "industry_landscape"

    async def render(self, ctx: ReportContext, *, variant: str) -> SectionData:
        if ctx.project.primary_brand_id is None:
            return _empty(ctx, variant, reason="no_primary_brand")

        my_stmt = select(
            func.avg(GeoScoreDaily.avg_geo_score),
            func.avg(GeoScoreDaily.industry_rank),
            func.count(GeoScoreDaily.id),
        ).where(
            and_(
                GeoScoreDaily.brand_id == ctx.project.primary_brand_id,
                GeoScoreDaily.date >= ctx.from_date,
                GeoScoreDaily.date <= ctx.to_date,
            )
        )
        my_row = (await ctx.session.execute(my_stmt)).one()
        my_samples = int(my_row[2] or 0)
        if my_samples == 0:
            return _empty(ctx, variant, reason="no_brand_data")

        my_score = round(float(my_row[0] or 0), 2)
        my_rank = float(my_row[1]) if my_row[1] is not None else None

        # Resolve project's industry name so the benchmark query is
        # scoped to a single industry (Codex review #1064). When the
        # project has no industry_id OR the resolver returns None
        # (industry has no benchmark rows yet), we skip the filter and
        # tag the payload so callers know the comparison is broad.
        industry_name = await _resolve_industry_name_safe(ctx, ctx.project.industry_id)
        ind_filters: list[Any] = [
            IndustryBenchmarkDaily.date >= ctx.from_date,
            IndustryBenchmarkDaily.date <= ctx.to_date,
        ]
        if industry_name:
            ind_filters.append(IndustryBenchmarkDaily.industry == industry_name)
        ind_stmt = select(
            func.avg(IndustryBenchmarkDaily.score_p50),
            func.avg(IndustryBenchmarkDaily.score_p25),
            func.avg(IndustryBenchmarkDaily.score_p75),
            func.avg(IndustryBenchmarkDaily.avg_geo_score),
            func.avg(IndustryBenchmarkDaily.total_brands),
            func.count(IndustryBenchmarkDaily.id),
        ).where(and_(*ind_filters))
        ind_row = (await ctx.session.execute(ind_stmt)).one()
        ind_samples = int(ind_row[5] or 0)

        median = round(float(ind_row[0]), 2) if ind_row[0] is not None else None
        p25 = round(float(ind_row[1]), 2) if ind_row[1] is not None else None
        p75 = round(float(ind_row[2]), 2) if ind_row[2] is not None else None
        ind_avg = round(float(ind_row[3]), 2) if ind_row[3] is not None else None
        total_brands = int(ind_row[4]) if ind_row[4] is not None else None

        position = _percentile_band(my_score, p25=p25, p50=median, p75=p75)

        metrics: dict[str, Any] = {
            "my_geo_score": my_score,
            "my_rank": round(my_rank, 1) if my_rank is not None else None,
            "industry_name": industry_name,
            "industry_filter_applied": industry_name is not None,
            "industry_samples": ind_samples,
            "industry_total_brands": total_brands,
            "industry_median": median,
            "industry_p25": p25,
            "industry_p75": p75,
            "industry_avg": ind_avg,
            "position_band": position,
        }
        if median is not None:
            metrics["distance_from_median"] = round(my_score - median, 2)

        summary = _summary(ctx.locale, metrics)
        return SectionData(
            section_type=self.section_type,
            title=_title(ctx.locale),
            summary=summary,
            metrics=metrics,
            chosen_variant=variant,
        )


async def _resolve_industry_name_safe(ctx: ReportContext, industry_id: int | None) -> str | None:
    """Defer to the canonical resolver in `industries/service.py` so this
    section matches the rest of the v1 industries API (`overview`,
    `ranking`, `avg-geo-score`). Returns None when:
      - project has no industry_id
      - the resolver itself errors (import / DB)
    Callers then fall back to a no-filter benchmark query and flag the
    payload so consumers know the comparison was not industry-scoped.
    """
    if industry_id is None:
        return None
    try:
        from app.api.v1.industries.service import _resolve_industry_name

        return await _resolve_industry_name(ctx.session, industry_id)
    except Exception:
        return None


def _percentile_band(
    my: float, *, p25: float | None, p50: float | None, p75: float | None
) -> str | None:
    """Coarse band — useful for the narrative without overclaiming a
    precise rank (which would require the full distribution)."""
    if p75 is not None and my >= p75:
        return "top_quartile"
    if p50 is not None and my >= p50:
        return "above_median"
    if p25 is not None and my >= p25:
        return "below_median"
    if p25 is not None and my < p25:
        return "bottom_quartile"
    return None


def _empty(ctx: ReportContext, variant: str, *, reason: str) -> SectionData:
    is_zh = ctx.locale.startswith("zh")
    msg = (
        "暂无行业基准数据可供比较。"
        if is_zh
        else "No industry benchmark data available for comparison."
    )
    return SectionData(
        section_type="industry_landscape",
        title=_title(ctx.locale),
        summary=msg,
        metrics={"empty_reason": reason},
        chosen_variant=variant,
    )


def _title(locale: str) -> str:
    return "行业格局" if locale.startswith("zh") else "Industry Landscape"


def _summary(locale: str, metrics: dict[str, Any]) -> str:
    is_zh = locale.startswith("zh")
    my = metrics.get("my_geo_score")
    median = metrics.get("industry_median")
    dist = metrics.get("distance_from_median")
    total = metrics.get("industry_total_brands")
    band = metrics.get("position_band")
    rank = metrics.get("my_rank")
    if my is None:
        return ""
    if median is None:
        if is_zh:
            return f"本品牌 GEO 总分 {my},暂无行业中位数对照。"
        return f"Brand GEO score {my}; industry median unavailable."
    band_zh = {
        "top_quartile": "Top 25%",
        "above_median": "中位之上",
        "below_median": "中位之下",
        "bottom_quartile": "后 25%",
    }.get(band or "", "")
    band_en = {
        "top_quartile": "top quartile",
        "above_median": "above median",
        "below_median": "below median",
        "bottom_quartile": "bottom quartile",
    }.get(band or "", "")
    rank_str_zh = f",行业内日均排名 #{rank}" if rank is not None else ""
    rank_str_en = f", avg daily rank #{rank}" if rank is not None else ""
    total_str = f"(共 {total} 个品牌)" if total else ""
    total_str_en = f" ({total} brands total)" if total else ""
    sign = "+" if (dist or 0) >= 0 else ""
    if is_zh:
        return (
            f"本品牌 GEO 总分 {my},较行业中位 {median} 相差 "
            f"{sign}{dist}{rank_str_zh}{total_str};"
            f"目前位置:{band_zh or '—'}。"
        )
    return (
        f"Brand GEO score {my} vs industry median {median} "
        f"({sign}{dist}){rank_str_en}{total_str_en}; position: "
        f"{band_en or 'n/a'}."
    )
