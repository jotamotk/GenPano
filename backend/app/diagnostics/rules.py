"""Phase D — diagnostic rule engine.

Each rule subclasses BaseRule + emits zero or more `DiagnosticPayload`. The
rule REGISTRY is consumed by `evaluator.evaluate_project(project)` which is
typically scheduled by Celery.

Six rules currently shipped (PRD §4.7.1.1 priorities):
    - VisibilityDeclineRule    (mention_rate 30d trend)
    - NegativeSentimentGrowthRule
    - GeoScoreDropRule         (composite GEO score)
    - CompetitorOvertakeRule   (project_competitors vs primary)
    - MonitoringOutageRule     (24h pipeline outage detection)
    - CitationVolumeDropRule   (citation count 30d trend)

The remaining categories listed in PLANNED_CATEGORIES are still stubbed
by name and queued for Phase D follow-up PRs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from genpano_models import (
    BrandMention,
    CitationSource,
    GeoScoreDaily,
    Project,
    ProjectCompetitor,
)
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


class CompetitorOvertakeRule(BaseRule):
    """A pinned competitor's 30d avg geo_score now exceeds primary brand's.

    Triggers P1 if any competitor's score > primary by >= 5 points;
    P2 for 1-5 point gap. Uses project_competitors as the watch list.
    """

    rule_id = "competitor_overtake_v1"
    category = "competitor_overtake"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        from_d = today - timedelta(days=29)

        comp_ids = [
            r[0]
            for r in (
                await session.execute(
                    select(ProjectCompetitor.brand_id).where(
                        ProjectCompetitor.project_id == project.id
                    )
                )
            ).all()
        ]
        if not comp_ids:
            return []

        async def _avg(brand_id: int) -> float | None:
            stmt = select(func.avg(GeoScoreDaily.avg_geo_score)).where(
                and_(
                    GeoScoreDaily.brand_id == brand_id,
                    GeoScoreDaily.date >= datetime.combine(from_d, datetime.min.time()),
                )
            )
            return (await session.execute(stmt)).scalar_one_or_none()

        my = await _avg(project.primary_brand_id)
        if my is None:
            return []
        out: list[DiagnosticPayload] = []
        for cid in comp_ids:
            comp = await _avg(cid)
            if comp is None or comp <= my:
                continue
            gap = comp - my
            severity = "P1" if gap >= 5 else "P2"
            out.append(
                DiagnosticPayload(
                    rule_id=self.rule_id,
                    rule_version=self.rule_version,
                    category=self.category,
                    severity=severity,
                    type="brand",
                    title=f"competitor brand-{cid} now leads by {gap:.1f} pts",
                    description=(
                        "A pinned competitor surpassed your primary brand on the 30d "
                        "avg geo_score window. Inspect their winning topics."
                    ),
                    focus_area="competitor_landscape",
                    direction=(
                        "Pull `/v1/projects/:id/competitors/metrics` for breakdown "
                        "by topic / engine."
                    ),
                    reader_hints=["operator", "manager"],
                    evidence={
                        "metric": "avg_geo_score_30d",
                        "competitor_brand_id": cid,
                        "my_value": round(my, 2),
                        "competitor_value": round(comp, 2),
                        "gap": round(gap, 2),
                    },
                    if_untreated=(
                        "Sustained gap typically means competitor steals share-of-voice "
                        "in the next 4-8 weeks."
                    ),
                )
            )
        return out


class MonitoringOutageRule(BaseRule):
    """No new BrandMention rows for the primary brand in the last 24h.

    Always P0 when triggered — pipeline isn't producing data, all other
    metrics will become stale.
    """

    rule_id = "monitoring_outage_v1"
    category = "monitoring_outage"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        # Did we see any data in the last 14 days at all? If never seeded,
        # don't fire — that's an onboarding state, not an outage.
        cutoff_window = datetime.now() - timedelta(days=14)
        cutoff_24h = datetime.now() - timedelta(hours=24)
        recent_window_stmt = select(func.count(BrandMention.id)).where(
            and_(
                BrandMention.brand_id == project.primary_brand_id,
                BrandMention.created_at >= cutoff_window,
            )
        )
        last_24h_stmt = select(func.count(BrandMention.id)).where(
            and_(
                BrandMention.brand_id == project.primary_brand_id,
                BrandMention.created_at >= cutoff_24h,
            )
        )
        try:
            total_14d = (await session.execute(recent_window_stmt)).scalar_one() or 0
            total_24h = (await session.execute(last_24h_stmt)).scalar_one() or 0
        except Exception:
            return []
        if total_14d == 0 or total_24h > 0:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P0",
                type="brand",
                title="no new mentions captured in last 24h",
                description=(
                    "Pipeline produced zero new BrandMention rows in 24h while the "
                    "prior 14d window was non-empty. Likely a collector / engine "
                    "outage."
                ),
                focus_area="pipeline_health",
                direction=(
                    "Check `/api/admin/engine-health` + retry-center for failed "
                    "executions; verify proxy + cookies."
                ),
                reader_hints=["operator"],
                evidence={
                    "metric": "brand_mention_count_24h",
                    "current_value": int(total_24h),
                    "prior_window_14d_count": int(total_14d),
                },
                if_untreated=(
                    "Every metric on this brand will go stale within 1-2 days; "
                    "downstream diagnostics will misfire."
                ),
            )
        ]


class CitationVolumeDropRule(BaseRule):
    """30d citation count dropped >= 30% vs prior 30d.

    Often paired with visibility_decline but separately actionable: PR /
    SEO content was pulled or rewritten, or LLMs stopped surfacing
    references.
    """

    rule_id = "citation_volume_drop_v1"
    category = "citation_authority_low"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        cur_from = datetime.combine(today - timedelta(days=29), datetime.min.time())
        prior_from = datetime.combine(today - timedelta(days=59), datetime.min.time())
        prior_to = datetime.combine(today - timedelta(days=30), datetime.max.time())

        async def _count(date_lo: datetime, date_hi: datetime) -> int:
            stmt = (
                select(func.count(CitationSource.id))
                .select_from(CitationSource)
                .join(BrandMention, BrandMention.id == CitationSource.mention_id)
                .where(
                    and_(
                        BrandMention.brand_id == project.primary_brand_id,
                        CitationSource.created_at >= date_lo,
                        CitationSource.created_at <= date_hi,
                    )
                )
            )
            try:
                return int((await session.execute(stmt)).scalar_one() or 0)
            except Exception:
                return 0

        cur = await _count(cur_from, datetime.combine(today, datetime.max.time()))
        prior = await _count(prior_from, prior_to)
        if prior == 0 or cur >= prior:
            return []
        change = (cur - prior) / prior * 100
        if change >= -30:
            return []
        severity = "P1" if change <= -50 else "P2"
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity=severity,
                type="brand",
                title=f"citation volume dropped {abs(change):.1f}% over 30d",
                description=(
                    "Citation count attached to this brand fell vs the prior 30d "
                    "window. Likely fewer indexed PR mentions or content removal."
                ),
                focus_area="citation_volume",
                direction=(
                    "Pull `/v1/projects/:id/citations/domains` to see which sources "
                    "stopped citing; check site removals / 404s."
                ),
                reader_hints=["operator", "branding"],
                evidence={
                    "metric": "citation_count",
                    "current_value": cur,
                    "previous_value": prior,
                    "change_percent": round(change, 2),
                },
                if_untreated=(
                    "Authority and trust signals erode within 6-8 weeks of citation decline."
                ),
            )
        ]


REGISTRY: list[type[BaseRule]] = [
    VisibilityDeclineRule,
    NegativeSentimentGrowthRule,
    GeoScoreDropRule,
    CompetitorOvertakeRule,
    MonitoringOutageRule,
    CitationVolumeDropRule,
]


# Stubbed categories for full PRD §4.7.1.1 coverage (Phase D follow-up wires)
PLANNED_CATEGORIES = [
    "sentiment_drop",
    "citation_attribution_mismatch",
    "topic_loss",
    "narrative_drift",
    "persona_keyword_change",
    "content_gap",
    "wiki_missing",
    "product_feature_negative",
    "product_remission",
    "industry_lag_top10",
    "same_group_share_low",
    "llm_engine_anomaly",
    "geo_score_drop_severe",
    "competitor_radical_growth",
    "share_of_voice_minor",
    "attribution_anchor_low",
    "citation_diversity_low",
    "topic_emerging_missed",
    "category_rank_drop",
]
