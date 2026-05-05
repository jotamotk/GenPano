"""SECTION_MATRIX-driven report builder (Phase RP.2)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from genpano_models import Project, ProjectCompetitor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.reports.sections.base import BaseSection, ReportContext, SectionData
from app.reports.sections.competitor_comparison import CompetitorComparisonSection
from app.reports.sections.diagnostic_summary import DiagnosticSummarySection
from app.reports.sections.executive_summary import ExecutiveSummarySection
from app.reports.sections.pano_score import PanoScoreSection

# PRD §4.7.2 — variants: 'full' | 'simple' | 'p01_only' | 'optional'
# Each cell is the chosen variant for (report_type, section_type).
SECTION_MATRIX: dict[str, dict[str, str]] = {
    "weekly": {
        "executive_summary": "full",
        "pano_score": "full",
        "competitor_comparison": "full",
        "diagnostic_summary": "p01_only",
    },
    "monthly": {
        "executive_summary": "full",
        "pano_score": "full",
        "competitor_comparison": "full",
        "diagnostic_summary": "full",
    },
    "on_demand": {
        "executive_summary": "simple",
        "pano_score": "simple",
        "competitor_comparison": "optional",
        "diagnostic_summary": "full",
    },
    # lead_diagnostic uses dedicated lead_view; full SECTION_MATRIX bypassed
    "lead_diagnostic": {
        "executive_summary": "simple",
        "diagnostic_summary": "full",
    },
}

SECTION_ORDER: list[str] = [
    "executive_summary",
    "pano_score",
    "competitor_comparison",
    "diagnostic_summary",
]

_REGISTRY: dict[str, type[BaseSection]] = {
    "executive_summary": ExecutiveSummarySection,
    "pano_score": PanoScoreSection,
    "competitor_comparison": CompetitorComparisonSection,
    "diagnostic_summary": DiagnosticSummarySection,
}


def _default_window(report_type: str, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    if report_type == "monthly":
        return today - timedelta(days=29), today
    return today - timedelta(days=6), today


async def build_report(
    session: AsyncSession,
    *,
    project: Project,
    report_type: str = "weekly",
    locale: str = "zh-CN",
    reader_perspective: str = "manager",
    from_date: date | None = None,
    to_date: date | None = None,
) -> dict[str, Any]:
    """Render a full report payload (PRD §4.7.2 — SECTION_MATRIX driven).

    Returns a dict ready for JSON serialization. PDF/Markdown renderers
    consume the same payload (Phase RP.5; not in this PR).
    """
    if report_type not in SECTION_MATRIX:
        raise ValueError(f"unknown report_type: {report_type}")

    if from_date is None or to_date is None:
        from_date, to_date = _default_window(report_type)

    # Brand IDs in scope: primary + competitors
    brand_ids: list[int] = []
    if project.primary_brand_id:
        brand_ids.append(project.primary_brand_id)
    comp_stmt = select(ProjectCompetitor.brand_id).where(ProjectCompetitor.project_id == project.id)
    brand_ids.extend(r[0] for r in (await session.execute(comp_stmt)).all())
    brand_ids = list(dict.fromkeys(brand_ids))  # dedup, preserve order

    ctx = ReportContext(
        session=session,
        project=project,
        brand_ids=brand_ids,
        from_date=from_date,
        to_date=to_date,
        locale=locale,
        reader_perspective=reader_perspective,
    )

    matrix = SECTION_MATRIX[report_type]
    sections: list[SectionData] = []
    for stype in SECTION_ORDER:
        if stype not in matrix:
            continue
        variant = matrix[stype]
        if variant == "optional":
            continue
        cls = _REGISTRY.get(stype)
        if cls is None:
            continue
        sections.append(await cls().render(ctx, variant=variant))

    return {
        "report_type": report_type,
        "locale": locale,
        "reader_perspective": reader_perspective,
        "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
        "project_id": project.id,
        "brand_ids": brand_ids,
        "sections": [
            {
                "section_type": s.section_type,
                "title": s.title,
                "summary": s.summary,
                "metrics": s.metrics,
                "tables": s.tables,
                "charts": s.charts,
                "variant": s.chosen_variant,
            }
            for s in sections
        ],
    }
