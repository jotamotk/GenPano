"""pano_score section — per-brand PANO score breakdown."""

from __future__ import annotations

from genpano_models import GeoScoreDaily
from sqlalchemy import and_, func, select

from app.reports.sections.base import BaseSection, ReportContext, SectionData


class PanoScoreSection(BaseSection):
    section_type = "pano_score"

    async def render(self, ctx: ReportContext, *, variant: str) -> SectionData:
        rows: list[dict[str, float | int | None]] = []
        for bid in ctx.brand_ids:
            stmt = select(
                func.avg(GeoScoreDaily.avg_geo_score),
                func.avg(GeoScoreDaily.mention_rate),
                func.avg(GeoScoreDaily.avg_sov),
                func.avg(GeoScoreDaily.avg_sentiment),
            ).where(
                and_(
                    GeoScoreDaily.brand_id == bid,
                    GeoScoreDaily.date >= ctx.from_date,
                    GeoScoreDaily.date <= ctx.to_date,
                )
            )
            r = (await ctx.session.execute(stmt)).one_or_none()
            if r is None:
                continue
            rows.append(
                {
                    "brand_id": bid,
                    "geo_score": round(r[0] or 0, 2),
                    "mention_rate": round(r[1] or 0, 4),
                    "sov": round(r[2] or 0, 4),
                    "sentiment": round(r[3] or 0, 3),
                }
            )

        title = "PANO 评分" if ctx.locale.startswith("zh") else "PANO Score"
        return SectionData(
            section_type=self.section_type,
            title=title,
            summary=f"{len(rows)} brand(s) measured.",
            tables=[{"name": "pano_by_brand", "rows": rows}],
            chosen_variant=variant,
        )
