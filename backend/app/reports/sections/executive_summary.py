"""executive_summary section — top-line KPI for the period."""

from __future__ import annotations

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

        stmt = select(
            func.avg(GeoScoreDaily.avg_geo_score),
            func.avg(GeoScoreDaily.mention_rate),
            func.avg(GeoScoreDaily.avg_sov),
            func.count(GeoScoreDaily.id),
        ).where(
            and_(
                GeoScoreDaily.brand_id.in_(ctx.brand_ids),
                GeoScoreDaily.date >= ctx.from_date,
                GeoScoreDaily.date <= ctx.to_date,
            )
        )
        row = (await ctx.session.execute(stmt)).one()
        geo = round(row[0] or 0, 2)
        mr = round(row[1] or 0, 4)
        sov = round(row[2] or 0, 4)

        return SectionData(
            section_type=self.section_type,
            title=_title(ctx.locale),
            summary=_summary(ctx.locale, geo=geo, mention_rate=mr, sov=sov),
            metrics={
                "geo_score": geo,
                "mention_rate": mr,
                "sov": sov,
                "samples": int(row[3] or 0),
            },
            chosen_variant=variant,
        )


def _title(locale: str) -> str:
    return "执行摘要" if locale.startswith("zh") else "Executive Summary"


def _empty_msg(locale: str) -> str:
    if locale.startswith("zh"):
        return "本期暂无品牌数据, 请先创建项目并完成首次采集."
    return "No brand data this period; create a project and run a crawl first."


def _summary(locale: str, *, geo: float, mention_rate: float, sov: float) -> str:
    if locale.startswith("zh"):
        return f"GEO 总分 {geo}, 平均提及率 {mention_rate * 100:.2f}%, SoV {sov * 100:.2f}%."
    return (
        f"Avg GEO score {geo}, mention rate {mention_rate * 100:.2f}%, "
        f"share-of-voice {sov * 100:.2f}%."
    )
