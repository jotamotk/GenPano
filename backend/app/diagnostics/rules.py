"""Phase D — diagnostic rule engine (minimum 3 rule classes).

Each rule subclasses BaseRule + emits zero or more `DiagnosticPayload`. The
rule REGISTRY is consumed by `evaluator.evaluate_project(project)` which is
typically scheduled by Celery (Phase D wires Celery later).

The 3 implemented rules cover the highest-value categories per PRD §4.7.1.1.
The remaining 22+ rules listed in the PRD addendum are stubbed by category
name but not yet implemented (Phase D follow-up PR).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from genpano_models import BrandMention, GeoScoreDaily, Project
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class DiagnosticPayload:
    rule_id: str
    rule_version: str
    category: str
    severity: str
    type: str  # brand | product | industry
    title: str
    description: str | None
    focus_area: str | None
    direction: str | None
    reader_hints: list[str]
    evidence: dict[str, Any]
    if_untreated: str | None = None


class BaseRule:
    rule_id: str = ""
    rule_version: str = "v1"
    category: str = ""
    cooldown_days: int = 7

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        raise NotImplementedError


# ─────────────────────────────────────────────────────────────────


class VisibilityDeclineRule(BaseRule):
    rule_id = "visibility_decline_v1"
    category = "visibility_decline"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        cur_from = today - timedelta(days=29)
        prior_from = today - timedelta(days=59)
        prior_to = today - timedelta(days=30)

        async def _avg(date_lo: date, date_hi: date) -> float | None:
            stmt = select(func.avg(GeoScoreDaily.mention_rate)).where(
                and_(
                    GeoScoreDaily.brand_id == project.primary_brand_id,
                    GeoScoreDaily.date >= datetime.combine(date_lo, datetime.min.time()),
                    GeoScoreDaily.date <= datetime.combine(date_hi, datetime.max.time()),
                )
            )
            return (await session.execute(stmt)).scalar_one_or_none()

        cur = await _avg(cur_from, today)
        prior = await _avg(prior_from, prior_to)
        if cur is None or prior is None or prior == 0:
            return []
        change = (cur - prior) / prior * 100
        if change >= -15:
            return []
        severity = "P1" if change <= -30 else "P2"
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity=severity,
                type="brand",
                title=f"mention rate dropped {abs(change):.1f}% over 30d",
                description=(
                    "Mention rate trended down vs prior 30d. "
                    "Inspect topic coverage / prompt quality / citation attribution."
                ),
                focus_area="mention_rate",
                direction="Check whether top topics were overtaken; review PR campaigns.",
                reader_hints=["operator", "manager"],
                evidence={
                    "metric": "mention_rate",
                    "current_value": round(cur, 4),
                    "previous_value": round(prior, 4),
                    "change_percent": round(change, 2),
                },
                if_untreated=(
                    "Continued decline likely shifts share of voice to competitors "
                    "over the next 4 weeks."
                ),
            )
        ]


class NegativeSentimentGrowthRule(BaseRule):
    rule_id = "negative_sentiment_growth_v1"
    category = "negative_keyword_growth"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        from_d = today - timedelta(days=29)
        stmt = select(
            func.sum(case((BrandMention.sentiment == "negative", 1), else_=0)),
            func.count(),
        ).where(
            and_(
                BrandMention.brand_id == project.primary_brand_id,
                BrandMention.created_at >= datetime.combine(from_d, datetime.min.time()),
            )
        )
        try:
            row = (await session.execute(stmt)).one_or_none()
        except Exception:
            return []
        if not row or not row[1]:
            return []
        neg_count = row[0] or 0
        total = row[1]
        neg_pct = neg_count / total * 100
        if neg_pct < 25:
            return []
        severity = "P1" if neg_pct >= 40 else "P2"
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity=severity,
                type="brand",
                title=f"negative mention ratio {neg_pct:.1f}%",
                description=(
                    "Negative mentions crossed the alert threshold. "
                    "Pull sentiment_drivers top negative for review."
                ),
                focus_area="sentiment_distribution",
                direction=(
                    "Inspect sentiment_drivers top negative; "
                    "coordinate with PR to adjust messaging."
                ),
                reader_hints=["operator", "branding"],
                evidence={
                    "metric": "negative_rate",
                    "current_value": round(neg_pct, 2),
                    "negative_count": int(neg_count),
                    "total_mentions": int(total),
                },
                if_untreated="Negative perception risks compounding in 4-6 weeks.",
            )
        ]


class GeoScoreDropRule(BaseRule):
    rule_id = "geo_score_drop_v1"
    category = "pano_score_drop"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        cur_from = today - timedelta(days=29)
        prior_from = today - timedelta(days=59)
        prior_to = today - timedelta(days=30)

        async def _avg(date_lo: date, date_hi: date) -> float | None:
            stmt = select(func.avg(GeoScoreDaily.avg_geo_score)).where(
                and_(
                    GeoScoreDaily.brand_id == project.primary_brand_id,
                    GeoScoreDaily.date >= datetime.combine(date_lo, datetime.min.time()),
                    GeoScoreDaily.date <= datetime.combine(date_hi, datetime.max.time()),
                )
            )
            return (await session.execute(stmt)).scalar_one_or_none()

        cur = await _avg(cur_from, today)
        prior = await _avg(prior_from, prior_to)
        if cur is None or prior is None or prior == 0:
            return []
        change = (cur - prior) / prior * 100
        if change >= -15:
            return []
        severity = "P0" if change <= -30 else "P1"
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity=severity,
                type="brand",
                title=f"PANO/GEO score dropped {abs(change):.1f}% over 30d",
                description=(
                    "Composite GEO score trending down. Check sub-metric breakdown "
                    "in /v1/projects/:id/metrics."
                ),
                focus_area="geo_score",
                direction=(
                    "Drill into mention/sov/sentiment/citation_authority sub-metrics "
                    "to identify the dominant cause."
                ),
                reader_hints=["manager"],
                evidence={
                    "metric": "geo_score",
                    "current_value": round(cur, 2),
                    "previous_value": round(prior, 2),
                    "change_percent": round(change, 2),
                },
                if_untreated=(
                    "Severe drop without remediation typically takes 2-3 months to recover."
                ),
            )
        ]


_BASE_REGISTRY: list[type[BaseRule]] = [
    VisibilityDeclineRule,
    NegativeSentimentGrowthRule,
    GeoScoreDropRule,
]


def _full_registry() -> list[type[BaseRule]]:
    """Combine base 3 + extended 22 rules (Phase D.2)."""
    from app.diagnostics.rules_extended import REGISTRY_EXTENDED

    return _BASE_REGISTRY + REGISTRY_EXTENDED


REGISTRY: list[type[BaseRule]] = _full_registry()


# Stubbed categories for full PRD §4.7.1.1 coverage (Phase D follow-up wires)
PLANNED_CATEGORIES = [
    "sentiment_drop",
    "citation_attribution_mismatch",
    "competitor_overtake",
    "topic_loss",
    "narrative_drift",
    "persona_keyword_change",
    "content_gap",
    "citation_authority_low",
    "wiki_missing",
    "product_feature_negative",
    "product_remission",
    "industry_lag_top10",
    "same_group_share_low",
    "monitoring_outage",
    "llm_engine_anomaly",
    "geo_score_drop_severe",
    "competitor_radical_growth",
    "share_of_voice_minor",
    "attribution_anchor_low",
    "citation_diversity_low",
    "topic_emerging_missed",
    "category_rank_drop",
]
