"""diagnostic_summary section — top open diagnostics for the period."""

from __future__ import annotations

from genpano_models import Diagnostic
from sqlalchemy import select

from app.reports.sections.base import BaseSection, ReportContext, SectionData


class DiagnosticSummarySection(BaseSection):
    section_type = "diagnostic_summary"

    async def render(self, ctx: ReportContext, *, variant: str) -> SectionData:
        stmt = (
            select(Diagnostic)
            .where(
                Diagnostic.project_id == ctx.project.id,
                Diagnostic.status == "open",
            )
            .order_by(Diagnostic.detected_at.desc())
            .limit(10 if variant == "full" else 3)
        )
        rows = list((await ctx.session.execute(stmt)).scalars().all())

        items = [
            {
                "id": d.id,
                "category": d.category,
                "severity": d.severity,
                "title": d.title,
                "direction": d.direction,
            }
            for d in rows
        ]

        title = "诊断摘要" if ctx.locale.startswith("zh") else "Diagnostic Summary"
        if not items:
            summary = (
                "本期未触发开放诊断。" if ctx.locale.startswith("zh") else "No open diagnostics."
            )
        else:
            sev_counts: dict[str, int] = {}
            for d in rows:
                sev_counts[d.severity] = sev_counts.get(d.severity, 0) + 1
            parts = ", ".join(f"{k}={v}" for k, v in sorted(sev_counts.items()))
            summary = f"{len(rows)} open: {parts}."

        return SectionData(
            section_type=self.section_type,
            title=title,
            summary=summary,
            tables=[{"name": "open_diagnostics", "rows": items}],
            chosen_variant=variant,
        )
