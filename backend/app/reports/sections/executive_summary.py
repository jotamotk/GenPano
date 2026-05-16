"""executive_summary section — top-line KPI for the period + WoW delta.

Implements PRD §4.7.4.6 (period-over-period semantics) for this section:
audit #1044 B2-3. Each headline metric (geo_score, mention_rate, sov)
ships with `delta_*` against the immediately preceding equal-length
window. When prior window has zero samples the delta is `None` — the
front-end renders `—`, never `0` (which would mislead the reader into
thinking there was no change).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from genpano_models import GeoScoreDaily
from sqlalchemy import and_, func, select

from app.reports.sections.base import BaseSection, ReportContext, SectionData


class ExecutiveSummarySection(BaseSection):
    section_type = "executive_summary"

    async def render(self, ctx: ReportContext, *, variant: str) -> SectionData:
        if not ctx.brand_ids:
            return SectionData(
                section_type=self.section_type,
                title=_title(ctx.locale),
                summary=_empty_msg(ctx.locale),
                chosen_variant=variant,
            )

        cur = await _aggregate(
            ctx, brand_ids=ctx.brand_ids, from_date=ctx.from_date, to_date=ctx.to_date
        )
        if cur is None:
            return SectionData(
                section_type=self.section_type,
                title=_title(ctx.locale),
                summary=_empty_msg(ctx.locale),
                chosen_variant=variant,
            )

        window_days = (ctx.to_date - ctx.from_date).days + 1
        prior_to = ctx.from_date - timedelta(days=1)
        prior_from = prior_to - timedelta(days=window_days - 1)
        prev = await _aggregate(
            ctx,
            brand_ids=ctx.brand_ids,
            from_date=prior_from,
            to_date=prior_to,
        )

        delta = _delta_dict(cur, prev)
        metrics: dict[str, Any] = {
            **cur,
            "delta": delta,
            "prior_period": {
                "from": prior_from.isoformat(),
                "to": prior_to.isoformat(),
            },
        }
        return SectionData(
            section_type=self.section_type,
            title=_title(ctx.locale),
            summary=_summary(ctx.locale, current=cur, delta=delta),
            metrics=metrics,
            chosen_variant=variant,
        )


async def _aggregate(
    ctx: ReportContext, *, brand_ids: list[int], from_date: date, to_date: date
) -> dict[str, Any] | None:
    stmt = select(
        func.avg(GeoScoreDaily.avg_geo_score),
        func.avg(GeoScoreDaily.mention_rate),
        func.avg(GeoScoreDaily.avg_sov),
        func.count(GeoScoreDaily.id),
    ).where(
        and_(
            GeoScoreDaily.brand_id.in_(brand_ids),
            GeoScoreDaily.date >= from_date,
            GeoScoreDaily.date <= to_date,
        )
    )
    row = (await ctx.session.execute(stmt)).one()
    samples = int(row[3] or 0)
    if samples == 0:
        return None
    return {
        "geo_score": round(float(row[0] or 0), 2),
        "mention_rate": round(float(row[1] or 0), 4),
        "sov": round(float(row[2] or 0), 4),
        "samples": samples,
    }


def _delta_dict(cur: dict[str, Any], prev: dict[str, Any] | None) -> dict[str, float | None]:
    """Per-metric delta. None when prior is empty — PRD §4.7.4.6 mandates
    null, never 0, so the FE renders '—'."""
    if prev is None:
        return {"geo_score": None, "mention_rate": None, "sov": None}
    return {
        "geo_score": round(cur["geo_score"] - prev["geo_score"], 2),
        "mention_rate": round(cur["mention_rate"] - prev["mention_rate"], 4),
        "sov": round(cur["sov"] - prev["sov"], 4),
    }


def _title(locale: str) -> str:
    return "执行摘要" if locale.startswith("zh") else "Executive Summary"


def _empty_msg(locale: str) -> str:
    if locale.startswith("zh"):
        return "本期暂无品牌数据, 请先创建项目并完成首次采集."
    return "No brand data this period; create a project and run a crawl first."


def _summary(locale: str, *, current: dict[str, Any], delta: dict[str, float | None]) -> str:
    geo = current["geo_score"]
    mr = current["mention_rate"]
    sov = current["sov"]
    d = delta["geo_score"]
    if locale.startswith("zh"):
        base = f"GEO 总分 {geo}, 平均提及率 {mr * 100:.2f}%, SoV {sov * 100:.2f}%."
        if d is None:
            return base + " (环比无对照)"
        sign = "+" if d >= 0 else ""
        return base + f" 环比 {sign}{d}."
    base = f"Avg GEO score {geo}, mention rate {mr * 100:.2f}%, share-of-voice {sov * 100:.2f}%."
    if d is None:
        return base + " (no prior-period comparison)"
    sign = "+" if d >= 0 else ""
    return base + f" WoW {sign}{d}."
