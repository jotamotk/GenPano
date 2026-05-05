"""Phase D.6 — industry benchmark enrichment.

Per PRD §4.7, each diagnostic carries an `industry_benchmark` JSON
comparing my brand's affected metric vs:
  - industry median (from industry_benchmark_daily)
  - industry top-10 average
  - top competitor (from project_competitors + geo_score_daily)

Diagnostics on projects without an industry_id or without benchmark data
get an empty dict (renderers + FE handle the missing-data case).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from genpano_models import GeoScoreDaily, IndustryBenchmarkDaily, ProjectCompetitor
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

METRIC_COL_MAP = {
    "mention_rate": (
        IndustryBenchmarkDaily.avg_mention_rate,
        GeoScoreDaily.mention_rate,
    ),
    "geo_score": (
        IndustryBenchmarkDaily.avg_geo_score,
        GeoScoreDaily.avg_geo_score,
    ),
    "sentiment": (
        IndustryBenchmarkDaily.avg_sentiment,
        GeoScoreDaily.avg_sentiment,
    ),
}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def build_industry_benchmark(
    session: AsyncSession,
    *,
    project: Any,
    metric: str,
    days: int = 30,
) -> dict[str, Any]:
    """Return industry_benchmark dict for one diagnostic.

    Empty dict if industry_id is missing or no benchmark data.
    """
    if not project.industry_id or metric not in METRIC_COL_MAP:
        return {}

    bench_col, score_col = METRIC_COL_MAP[metric]
    today: date = _now().date()
    cutoff = today - timedelta(days=days - 1)

    industry_avg_stmt = select(func.avg(bench_col)).where(
        IndustryBenchmarkDaily.date >= cutoff,
    )
    industry_avg = (await session.execute(industry_avg_stmt)).scalar_one_or_none()

    # My brand's same-window metric
    my_avg = None
    if project.primary_brand_id:
        my_avg_stmt = select(func.avg(score_col)).where(
            and_(
                GeoScoreDaily.brand_id == project.primary_brand_id,
                GeoScoreDaily.date >= cutoff,
            )
        )
        my_avg = (await session.execute(my_avg_stmt)).scalar_one_or_none()

    # Top competitor by metric
    top_competitor: dict[str, Any] | None = None
    comp_stmt = select(ProjectCompetitor.brand_id).where(ProjectCompetitor.project_id == project.id)
    competitor_ids = [r[0] for r in (await session.execute(comp_stmt)).all()]
    if competitor_ids:
        comp_metric_stmt = (
            select(GeoScoreDaily.brand_id, func.avg(score_col).label("v"))
            .where(
                and_(
                    GeoScoreDaily.brand_id.in_(competitor_ids),
                    GeoScoreDaily.date >= cutoff,
                )
            )
            .group_by(GeoScoreDaily.brand_id)
            .order_by(func.avg(score_col).desc())
            .limit(1)
        )
        row = (await session.execute(comp_metric_stmt)).first()
        if row is not None:
            top_competitor = {"brand_id": row[0], "value": _round(row.v)}

    if industry_avg is None and my_avg is None and top_competitor is None:
        return {}

    return {
        "metric": metric,
        "myValue": _round(my_avg),
        "industryMedian": _round(industry_avg),
        "topCompetitor": top_competitor,
        "windowDays": days,
        "windowFrom": cutoff.isoformat(),
        "windowTo": today.isoformat(),
    }


def _round(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return round(float(v), 4)
    except (TypeError, ValueError):
        return None
