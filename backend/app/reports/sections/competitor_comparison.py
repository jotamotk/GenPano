"""competitor_comparison section — primary brand vs project competitors."""

from __future__ import annotations

from genpano_models import GeoScoreDaily, ProjectCompetitor
from sqlalchemy import and_, func, select

from app.reports.sections.base import BaseSection, ReportContext, SectionData


class CompetitorComparisonSection(BaseSection):
    section_type = "competitor_comparison"

    async def render(self, ctx: ReportContext, *, variant: str) -> SectionData:
        # Pull project competitors
        stmt = select(ProjectCompetitor.brand_id).where(
            ProjectCompetitor.project_id == ctx.project.id
        )
        competitor_ids = [r[0] for r in (await ctx.session.execute(stmt)).all()]
        all_ids = list({ctx.project.primary_brand_id, *competitor_ids} - {None})
        if not all_ids:
            return SectionData(
                section_type=self.section_type,
                title=_title(ctx.locale),
                summary="(no competitors configured)",
                chosen_variant=variant,
            )

        rows: list[dict[str, float | int | bool | None]] = []
        skipped_no_data: list[int] = []
        for bid in all_ids:
            agg = select(
                func.count(GeoScoreDaily.id),
                func.avg(GeoScoreDaily.avg_geo_score),
                func.avg(GeoScoreDaily.avg_sov),
            ).where(
                and_(
                    GeoScoreDaily.brand_id == bid,
                    GeoScoreDaily.date >= ctx.from_date,
                    GeoScoreDaily.date <= ctx.to_date,
                )
            )
            r = (await ctx.session.execute(agg)).one()
            samples = int(r[0] or 0)
            # A brand with zero samples must not be ranked at score 0 —
            # absence of data ≠ score of 0. Defaming uncollected competitors
            # is a visible trust violation.
            if samples == 0:
                skipped_no_data.append(bid)
                continue
            rows.append(
                {
                    "brand_id": bid,
                    "is_primary": bid == ctx.project.primary_brand_id,
                    "samples": samples,
                    "geo_score": round(r[1] or 0, 2),
                    "sov": round(r[2] or 0, 4),
                }
            )

        rows.sort(key=lambda r: r["geo_score"] or 0, reverse=True)
        compared_summary = (
            f"{len(rows)} brand(s) compared, {len(skipped_no_data)} skipped (no data)."
            if skipped_no_data
            else f"{len(rows)} brand(s) compared."
        )
        return SectionData(
            section_type=self.section_type,
            title=_title(ctx.locale),
            summary=compared_summary,
            tables=[{"name": "competitor_ranking", "rows": rows}],
            metrics={"skipped_no_data_brand_ids": skipped_no_data} if skipped_no_data else {},
            chosen_variant=variant,
        )


def _title(locale: str) -> str:
    return "竞品对比" if locale.startswith("zh") else "Competitor Comparison"
