"""anchor_actions section — aggregate open-diagnostic anchor questions
into a single per-reader "what to ask" surface, per PRD §4.8.4.

Reads from `Diagnostic.anchor_questions` (populated by the evaluator
via `app.diagnostics.anchor_questions.build_anchor_questions`). Output
groups questions by reader ('operator' / 'manager' / 'branding') so the
section can be displayed alongside the rest of the report.

Spec anchors:
  - PRD §4.7.2 / §4.8.4: this section is *direction-only*; it MUST NOT
    contain executable playbook steps. Each item is a question, not an
    instruction. Reuses the business-boundary rule of PRD §4.8.6.
  - PRD §4.7.4.6 / B2-3: section is period-aware; only diagnostics
    `detected_at` within [from_date, to_date) are surfaced. Matches the
    diagnostic_summary section's gate behavior fixed in #1046 B2-6.

Variants:
  - variant='p01_only' → only P0/P1 diagnostics contribute their
    anchor questions (weekly default — small, focused list)
  - variant='all'      → P0/P1/P2 contribute (monthly default)
  - any other value    → treated as 'all'
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Any

from genpano_models import Diagnostic
from sqlalchemy import select

from app.reports.sections.base import BaseSection, ReportContext, SectionData

_READER_LABEL_ZH = {
    "operator": "执行视角 (Operator)",
    "manager": "经营视角 (Manager)",
    "branding": "品牌视角 (Branding)",
}
_READER_LABEL_EN = {
    "operator": "Operator",
    "manager": "Manager",
    "branding": "Branding",
}


class AnchorActionsSection(BaseSection):
    section_type = "anchor_actions"

    async def render(self, ctx: ReportContext, *, variant: str) -> SectionData:
        # Period gate matches diagnostic_summary's window (B2-6).
        window_start = datetime.combine(ctx.from_date, time.min)
        window_end = datetime.combine(ctx.to_date + timedelta(days=1), time.min)

        if variant == "p01_only":
            severity_filter = {"P0", "P1"}
        else:
            severity_filter = {"P0", "P1", "P2"}

        stmt = (
            select(Diagnostic)
            .where(
                Diagnostic.project_id == ctx.project.id,
                Diagnostic.status == "open",
                Diagnostic.detected_at >= window_start,
                Diagnostic.detected_at < window_end,
                Diagnostic.severity.in_(severity_filter),
            )
            .order_by(Diagnostic.detected_at.desc())
        )
        rows = list((await ctx.session.execute(stmt)).scalars().all())

        # Group questions by reader. De-dup verbatim repeats so
        # five P1 outages don't surface the same operator question 5x.
        by_reader: dict[str, list[dict[str, Any]]] = {
            "operator": [],
            "manager": [],
            "branding": [],
        }
        seen: dict[str, set[str]] = {"operator": set(), "manager": set(), "branding": set()}
        for d in rows:
            anchor = d.anchor_questions
            if not isinstance(anchor, dict):
                continue
            for reader, questions in anchor.items():
                if reader not in by_reader:
                    continue
                if not isinstance(questions, list):
                    continue
                for q in questions:
                    if not isinstance(q, str) or not q.strip():
                        continue
                    if q in seen[reader]:
                        continue
                    seen[reader].add(q)
                    by_reader[reader].append(
                        {
                            "question": q,
                            "source_diagnostic_id": d.id,
                            "severity": d.severity,
                            "category": d.category,
                        }
                    )

        label_map = _READER_LABEL_ZH if ctx.locale.startswith("zh") else _READER_LABEL_EN
        tables = [
            {
                "name": f"anchor_questions_{reader}",
                "label": label_map[reader],
                "rows": by_reader[reader],
            }
            for reader in ("operator", "manager", "branding")
            if by_reader[reader]
        ]

        total = sum(len(v) for v in by_reader.values())
        title = "锚点问题集" if ctx.locale.startswith("zh") else "Anchor Questions"
        if total == 0:
            summary = (
                "本期无开放诊断,故无锚点问题。"
                if ctx.locale.startswith("zh")
                else "No open diagnostics this period; no anchor questions surfaced."
            )
        else:
            summary = (
                f"本期 {len(rows)} 条诊断产生 {total} 个锚点问题(按读者分组)。"
                if ctx.locale.startswith("zh")
                else (
                    f"{total} anchor question(s) surfaced from {len(rows)} "
                    "diagnostic(s) this period, grouped by reader."
                )
            )

        return SectionData(
            section_type=self.section_type,
            title=title,
            summary=summary,
            metrics={
                "total_questions": total,
                "diagnostic_count": len(rows),
                "by_reader_count": {r: len(v) for r, v in by_reader.items()},
            },
            tables=tables,
            chosen_variant=variant,
        )
