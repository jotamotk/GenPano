"""Phase D — Diagnostics evaluator.

Runs all REGISTRY rules against a project, dedupes (cooldown_days), upserts
into `diagnostics` table. Returns the list of newly-created diagnostic IDs.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from genpano_models import Diagnostic, Project
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.anchor_questions import build_anchor_questions
from app.diagnostics.benchmark import build_industry_benchmark
from app.diagnostics.causal_chain import build_causal_chain
from app.diagnostics.rules import REGISTRY, DiagnosticPayload

log = logging.getLogger(__name__)

# PRD §4.8.8: cooldown ranks severities so a P2 already inside its
# cooldown window does NOT suppress a fresh P0 in the same category.
_SEVERITY_RANK = {"P3": 0, "P2": 1, "P1": 2, "P0": 3}


def _new_id() -> str:
    return str(uuid.uuid4())


async def _is_cooldown_active(
    session: AsyncSession,
    project: Project,
    payload: DiagnosticPayload,
    cooldown_days: int = 7,
) -> bool:
    """Return True when an active diagnostic in the same category exists
    AND its severity is >= the candidate's severity. PRD §4.8.8 /
    audit #1044 B1-15: cooldown is keyed by `(category, brand_id,
    severity)` triple — a higher-severity candidate ALWAYS bypasses
    cooldown, so we don't silently drop a P0 because a P2 in the same
    category is still open.
    """
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=cooldown_days)
    new_rank = _SEVERITY_RANK.get(payload.severity, 0)
    stmt = select(Diagnostic.severity).where(
        and_(
            Diagnostic.project_id == project.id,
            Diagnostic.category == payload.category,
            Diagnostic.brand_id == project.primary_brand_id,
            Diagnostic.detected_at >= cutoff,
            Diagnostic.status.in_(["open", "acknowledged"]),
        )
    )
    rows = (await session.execute(stmt)).all()
    if not rows:
        return False
    # Cooldown is active only when no existing row is at a STRICTLY LOWER
    # severity than the candidate. Equivalent: candidate severity must
    # exceed every existing row's severity to bypass cooldown.
    for (existing_sev,) in rows:
        if _SEVERITY_RANK.get(existing_sev, 0) >= new_rank:
            return True
    return False


async def evaluate_project(session: AsyncSession, project: Project) -> list[Diagnostic]:
    """Run all rules + persist non-cooldown payloads. Returns inserted rows."""
    inserted: list[Diagnostic] = []
    for RuleCls in REGISTRY:
        rule = RuleCls()
        try:
            payloads = await rule.evaluate(session, project)
        except Exception as exc:
            # PRD §4.8.8 + audit #1044 B1-14: rule failures must not block
            # the rest of the evaluator pass, but operators MUST see them
            # in logs/metrics — silently swallowing breaks alerting.
            log.warning(
                "diagnostic_rule.failed",
                extra={
                    "rule_id": getattr(rule, "rule_id", RuleCls.__name__),
                    "project_id": project.id,
                    "error": str(exc),
                },
            )
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
        # Phase D.8 — auto-create alerts for severity P0/P1. Best-effort:
        # a failure here MUST NOT roll back the diagnostic insert.
        try:
            from app.alerts.triggers import create_alert_from_diagnostic

            for r in inserted:
                if r.severity in {"P0", "P1"}:
                    await create_alert_from_diagnostic(session, r, autocommit=False)
            await session.commit()
        except Exception as exc:
            # Audit #1044 B1-14: structured log so operators see when
            # the diagnostic→alert path silently fails. Don't roll back
            # the diagnostic insert (already committed at line 110).
            log.warning(
                "diagnostic_alert_link.failed",
                extra={
                    "project_id": project.id,
                    "inserted_count": len(inserted),
                    "error": str(exc),
                },
            )
            try:
                await session.rollback()
            except Exception:
                pass
    return inserted
