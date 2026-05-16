"""competitor_comparison section — primary brand vs project competitors.

Implements:
  - audit #1044 B2-9: skip brands with zero samples (don't rank at 0)
  - audit #1044 B2-3: each row carries per-metric delta against the prior
    equal-length window; null when prior has no data (PRD §4.7.4.6).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from genpano_models import GeoScoreDaily, ProjectCompetitor
from sqlalchemy import and_, func, select

from app.reports.sections.base import BaseSection, ReportContext, SectionData


class CompetitorComparisonSection(BaseSection):
    section_type = "competitor_comparison"

    async def render(self, ctx: ReportContext, *, variant: str) -> SectionData:
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

        window_days = (ctx.to_date - ctx.from_date).days + 1
        prior_to = ctx.from_date - timedelta(days=1)
        prior_from = prior_to - timedelta(days=window_days - 1)

        rows: list[dict[str, Any]] = []
        skipped_no_data: list[int] = []
        for bid in all_ids:
            cur = await _aggregate(ctx, brand_id=bid, from_date=ctx.from_date, to_date=ctx.to_date)
            if cur is None:
                # Audit B2-9: don't rank zero-sample brands at score 0;
                # absence of data ≠ score of 0.
                skipped_no_data.append(bid)
                continue
            prev = await _aggregate(ctx, brand_id=bid, from_date=prior_from, to_date=prior_to)
            rows.append(
                {
                    "brand_id": bid,
                    "is_primary": bid == ctx.project.primary_brand_id,
                    "samples": cur["samples"],
                    "geo_score": cur["geo_score"],
                    "sov": cur["sov"],
                    "delta": _delta_dict(cur, prev),
                }
            )

        rows.sort(key=lambda r: r["geo_score"] or 0, reverse=True)
        compared_summary = (
            f"{len(rows)} brand(s) compared, {len(skipped_no_data)} skipped (no data)."
            if skipped_no_data
            else f"{len(rows)} brand(s) compared."
        )
        metrics: dict[str, Any] = {
            "prior_period": {
                "from": prior_from.isoformat(),
                "to": prior_to.isoformat(),
            },
        }
        if skipped_no_data:
            metrics["skipped_no_data_brand_ids"] = skipped_no_data
        return SectionData(
            section_type=self.section_type,
            title=_title(ctx.locale),
            summary=compared_summary,
            tables=[{"name": "competitor_ranking", "rows": rows}],
            metrics=metrics,
            chosen_variant=variant,
        )


async def _aggregate(
    ctx: ReportContext, *, brand_id: int, from_date: date, to_date: date
) -> dict[str, Any] | None:
    stmt = select(
        func.count(GeoScoreDaily.id),
        func.avg(GeoScoreDaily.avg_geo_score),
        func.avg(GeoScoreDaily.avg_sov),
    ).where(
        and_(
            GeoScoreDaily.brand_id == brand_id,
            GeoScoreDaily.date >= from_date,
            GeoScoreDaily.date <= to_date,
        )
    )
    row = (await ctx.session.execute(stmt)).one()
    samples = int(row[0] or 0)
    if samples == 0:
        return None
    return {
        "samples": samples,
        "geo_score": round(float(row[1] or 0), 2),
        "sov": round(float(row[2] or 0), 4),
    }


def _delta_dict(cur: dict[str, Any], prev: dict[str, Any] | None) -> dict[str, float | None]:
    """Per-metric delta. None when prior is empty (PRD §4.7.4.6 — never 0)."""
    if prev is None:
        return {"geo_score": None, "sov": None}
    return {
        "geo_score": round(cur["geo_score"] - prev["geo_score"], 2),
        "sov": round(cur["sov"] - prev["sov"], 4),
    }


def _title(locale: str) -> str:
    return "竞品对比" if locale.startswith("zh") else "Competitor Comparison"
