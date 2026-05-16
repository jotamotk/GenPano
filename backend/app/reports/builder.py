"""SECTION_MATRIX-driven report builder (Phase RP.2)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from genpano_models import Project, ProjectCompetitor
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.reports.narrator import narrate
from app.reports.sections.anchor_actions import AnchorActionsSection
from app.reports.sections.base import BaseSection, ReportContext, SectionData
from app.reports.sections.brand_performance import BrandPerformanceSection
from app.reports.sections.branding_narrative import BrandingNarrativeSection
from app.reports.sections.competitor_comparison import CompetitorComparisonSection
from app.reports.sections.cta import CtaSection
from app.reports.sections.diagnostic_summary import DiagnosticSummarySection
from app.reports.sections.executive_summary import ExecutiveSummarySection
from app.reports.sections.industry_landscape import IndustryLandscapeSection
from app.reports.sections.pano_score import PanoScoreSection
from app.reports.sections.product_competitiveness import ProductCompetitivenessSection

# PRD §4.7.2 — variants: 'full' | 'simple' | 'p01_only' | 'optional' |
# 'strengthened' | 'all'. Each cell is the chosen variant for
# (report_type, section_type). `null` (absent key) means the section is
# not part of that report type.
SECTION_MATRIX: dict[str, dict[str, str]] = {
    "weekly": {
        "executive_summary": "full",
        "pano_score": "full",
        "industry_landscape": "simple",
        "brand_performance": "full",
        "competitor_comparison": "full",
        "diagnostic_summary": "p01_only",
        "anchor_actions": "p01_only",
        "cta": "full",
    },
    "monthly": {
        "executive_summary": "full",
        "pano_score": "full",
        "industry_landscape": "full",
        "brand_performance": "full",
        "product_competitiveness": "full",
        "branding_narrative": "full",
        "competitor_comparison": "full",
        "diagnostic_summary": "full",
        "anchor_actions": "all",
        "cta": "full",
    },
    "on_demand": {
        "executive_summary": "simple",
        "pano_score": "simple",
        "industry_landscape": "optional",
        "brand_performance": "simple",
        "competitor_comparison": "optional",
        "diagnostic_summary": "full",
        "anchor_actions": "all",
        # Codex #1061 review: FE mock matrix has on_demand.cta=full; the
        # consulting CTA is part of the spec's conversion surface for
        # API/MCP-generated on-demand reports too.
        "cta": "full",
    },
    # lead_diagnostic uses dedicated lead_view; full SECTION_MATRIX bypassed
    "lead_diagnostic": {
        "executive_summary": "simple",
        "brand_performance": "focus",
        "branding_narrative": "full",
        "diagnostic_summary": "full",
        "cta": "strengthened",
    },
}

SECTION_ORDER: list[str] = [
    "executive_summary",
    "pano_score",
    "industry_landscape",
    "brand_performance",
    "product_competitiveness",
    "branding_narrative",
    "competitor_comparison",
    "diagnostic_summary",
    "anchor_actions",
    "cta",
]

_REGISTRY: dict[str, type[BaseSection]] = {
    "executive_summary": ExecutiveSummarySection,
    "pano_score": PanoScoreSection,
    "industry_landscape": IndustryLandscapeSection,
    "brand_performance": BrandPerformanceSection,
    "product_competitiveness": ProductCompetitivenessSection,
    "branding_narrative": BrandingNarrativeSection,
    "competitor_comparison": CompetitorComparisonSection,
    "diagnostic_summary": DiagnosticSummarySection,
    "anchor_actions": AnchorActionsSection,
    "cta": CtaSection,
}


def _default_window(report_type: str, today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    if report_type == "monthly":
        return today - timedelta(days=29), today
    return today - timedelta(days=6), today


def _apply_variant(rendered: SectionData, primary_brand_id: int | None) -> None:
    """Post-render variant projection. Each variant is documented in
    PRD §4.7.2:

      - `full`         → no-op (everything ships)
      - `simple`       → drop tables + charts; keep summary / narrative
                         / metrics. Used when the consumer wants a
                         glanceable card without the data grid.
      - `focus`        → narrow each table to rows where `is_primary=True`
                         OR `brand_id == primary_brand_id`. Used by
                         lead_diagnostic where the report is single-
                         brand-centric. Falls through to no-op when
                         primary_brand_id is None.
      - `p01_only` / `all` / `strengthened` / `top3` → handled inside
                         the section itself (where it can actually filter
                         the underlying query). No projection needed
                         here.

    Idempotent and safe on any SectionData shape.
    """
    variant = rendered.chosen_variant
    if variant == "simple":
        rendered.tables = []
        rendered.charts = []
        return
    if variant == "focus":
        if primary_brand_id is None:
            return
        kept_tables: list[dict[str, Any]] = []
        for table in rendered.tables or []:
            rows = table.get("rows") or []
            filtered = [
                r
                for r in rows
                if r.get("is_primary") is True or r.get("brand_id") == primary_brand_id
            ]
            # If filter would empty the table, drop it entirely rather
            # than leaving an empty-header artifact in the renderer.
            if filtered:
                new_table = dict(table)
                new_table["rows"] = filtered
                kept_tables.append(new_table)
        rendered.tables = kept_tables


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
        rendered = await cls().render(ctx, variant=variant)
        # B2-4 (PRD §4.7.3): after each section render, run the narrator
        # to produce an LLM-or-fallback prose paragraph distinct from
        # the section's stat-heavy `summary`. Narrator is best-effort —
        # failure leaves narrative=None, never raises.
        rendered.narrative = await narrate(rendered, ctx)
        # B2-10 (PRD §4.7.2 — section variant must actually change output):
        # `simple` drops tables + charts so a "simple" exec_summary on
        # an on_demand report doesn't look identical to "full". `focus`
        # narrows tables to the primary-brand row only — used by
        # lead_diagnostic where the report is single-brand-centric.
        _apply_variant(rendered, ctx.project.primary_brand_id)
        sections.append(rendered)

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
                "narrative": s.narrative,
                "metrics": s.metrics,
                "tables": s.tables,
                "charts": s.charts,
                "variant": s.chosen_variant,
            }
            for s in sections
        ],
    }
