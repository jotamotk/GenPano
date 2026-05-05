"""Phase D — Diagnostics evaluator.

Runs all REGISTRY rules against a project, dedupes (cooldown_days), upserts
into `diagnostics` table. Returns the list of newly-created diagnostic IDs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from genpano_models import Diagnostic, Project
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.anchor_questions import build_anchor_questions
from app.diagnostics.benchmark import build_industry_benchmark
from app.diagnostics.causal_chain import build_causal_chain
from app.diagnostics.rules import REGISTRY, DiagnosticPayload


def _new_id() -> str:
    return str(uuid.uuid4())


async def _is_cooldown_active(
    session: AsyncSession,
    project: Project,
    payload: DiagnosticPayload,
    cooldown_days: int = 7,
) -> bool:
    """True if a similar diagnostic exists within cooldown window."""
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=cooldown_days)
    stmt = select(Diagnostic).where(
        and_(
            Diagnostic.project_id == project.id,
            Diagnostic.category == payload.category,
            Diagnostic.brand_id == project.primary_brand_id,
            Diagnostic.detected_at >= cutoff,
            Diagnostic.status.in_(["open", "acknowledged"]),
        )
    )
    return (await session.execute(stmt)).first() is not None


async def evaluate_project(session: AsyncSession, project: Project) -> list[Diagnostic]:
    """Run all rules + persist non-cooldown payloads. Returns inserted rows."""
    inserted: list[Diagnostic] = []
    for RuleCls in REGISTRY:
        rule = RuleCls()
        try:
            payloads = await rule.evaluate(session, project)
        except Exception:
            # Don't let one rule block others
            continue
        for p in payloads:
            if await _is_cooldown_active(session, project, p, rule.cooldown_days):
                continue

            # Phase D.4 / D.5 / D.6 enrichment — fields are nullable so any
            # exception here must not block the diagnostic from being saved.
            try:
                causal = build_causal_chain(rule_id=p.rule_id, evidence=p.evidence)
            except Exception:
                causal = None
            try:
                anchor = build_anchor_questions(
                    category=p.category,
                    reader_hints=p.reader_hints,
                    evidence=p.evidence,
                )
            except Exception:
                anchor = None
            metric_for_benchmark = (p.evidence or {}).get("metric")
            benchmark: dict[str, object] | None = None
            if metric_for_benchmark:
                try:
                    benchmark = (
                        await build_industry_benchmark(
                            session, project=project, metric=metric_for_benchmark
                        )
                        or None
                    )
                except Exception:
                    benchmark = None

            row = Diagnostic(
                id=_new_id(),
                project_id=project.id,
                brand_id=project.primary_brand_id,
                category=p.category,
                severity=p.severity,
                type=p.type,
                title=p.title,
                description=p.description,
                focus_area=p.focus_area,
                direction=p.direction,
                reader_hints=p.reader_hints,
                evidence=p.evidence,
                causal_chain=causal,
                industry_benchmark=benchmark,
                anchor_questions=anchor,
                if_untreated=p.if_untreated,
                rule_id=p.rule_id,
                rule_version=p.rule_version,
                status="open",
            )
            session.add(row)
            inserted.append(row)
    if inserted:
        await session.commit()
        for r in inserted:
            await session.refresh(r)
    return inserted
