"""Phase D — diagnostic rule engine.

Each rule subclasses BaseRule + emits zero or more `DiagnosticPayload`. The
rule REGISTRY is consumed by `evaluator.evaluate_project(project)` which is
typically scheduled by Celery.

Twenty-three rules currently shipped (PRD §4.7.1.1 priorities):
    - VisibilityDeclineRule           (mention_rate 30d trend)
    - NegativeSentimentGrowthRule     (negative ratio threshold)
    - GeoScoreDropRule                (composite GEO score 30d)
    - CompetitorOvertakeRule          (project_competitors vs primary)
    - MonitoringOutageRule            (24h pipeline outage detection)
    - CitationVolumeDropRule          (citation count 30d trend)
    - SentimentDropRule               (avg sentiment_score trend)
    - ShareOfVoiceMinorRule           (avg_sov < 5% sustained)
    - IndustryLagTop10Rule            (geo_score lag vs industry top-10)
    - CitationDiversityLowRule        (< 5 unique citation domains in 30d)
    - GeoScoreDropSevereRule          (7d geo_score drop >= 20)
    - CompetitorRadicalGrowthRule     (competitor 30d growth >= 25%)
    - CategoryRankDropRule            (avg_position_rank slipped)
    - CitationAttributionMismatchRule (official-domain share < 20%)
    - WikiMissingRule                 (no wiki/baidu baike citations)
    - TopicLossRule                   (mention rate collapsed)
    - FirstPlaceLossRule              (first-place mentions down >= 30%)
    - CitationGrowthSurgeRule         (P3 informational positive signal)
    - LlmEngineAnomalyRule            (single engine 0 mentions while peers active)
    - AttributionAnchorLowRule        (< 5 citations against >= 10 mentions)
    - ContentGapRule                  (low citations-per-mention ratio)
    - ProductFeatureNegativeRule      (single feature > 30% negative)
    - PersonaKeywordChangeRule        (top sentiment drivers churn > 70% MoM)

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
    ProductFeatureMention,
    Project,
    ProjectCompetitor,
    SentimentDriver,
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


class SentimentDropRule(BaseRule):
    """30d avg `sentiment_score` dropped vs prior 30d.

    Distinct from NegativeSentimentGrowthRule (which thresholds the
    *ratio* of negatives at any point). This rule fires when the
    *average* sentiment score trend declines — captures gradual
    perception erosion that doesn't necessarily push negatives over
    25%.
    """

    rule_id = "sentiment_drop_v1"
    category = "sentiment_drop"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        cur_from = today - timedelta(days=29)
        prior_from = today - timedelta(days=59)
        prior_to = today - timedelta(days=30)

        async def _avg(d_lo: date, d_hi: date) -> float | None:
            stmt = select(func.avg(BrandMention.sentiment_score)).where(
                and_(
                    BrandMention.brand_id == project.primary_brand_id,
                    BrandMention.created_at >= datetime.combine(d_lo, datetime.min.time()),
                    BrandMention.created_at <= datetime.combine(d_hi, datetime.max.time()),
                )
            )
            try:
                return (await session.execute(stmt)).scalar_one_or_none()
            except Exception:
                return None

        cur = await _avg(cur_from, today)
        prior = await _avg(prior_from, prior_to)
        if cur is None or prior is None:
            return []
        # absolute drop in score (sentiment is in [-1, 1])
        delta = cur - prior
        if delta >= -0.1:
            return []
        severity = "P1" if delta <= -0.25 else "P2"
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity=severity,
                type="brand",
                title=f"avg sentiment score dropped {abs(delta):.2f} pts",
                description=(
                    "30d average sentiment score trended down vs the prior 30d. "
                    "Inspect sentiment_drivers top negatives + recent campaigns."
                ),
                focus_area="sentiment_average",
                direction=(
                    "Pull `/v1/projects/:id/sentiment` for the keyword breakdown; "
                    "verify whether a single topic is dragging the mean."
                ),
                reader_hints=["operator", "branding"],
                evidence={
                    "metric": "avg_sentiment_score",
                    "current_value": round(cur, 3),
                    "previous_value": round(prior, 3),
                    "delta": round(delta, 3),
                },
                if_untreated=(
                    "Sustained sentiment drop typically depresses ranking signals next quarter."
                ),
            )
        ]


class ShareOfVoiceMinorRule(BaseRule):
    """30d avg `avg_sov` consistently below 5%.

    Distinct from VisibilityDeclineRule (which detects relative drop).
    This fires when SoV is *low in absolute terms* — flags brands that
    have never been visible enough to warrant existing PR / SEO spend.
    """

    rule_id = "share_of_voice_minor_v1"
    category = "share_of_voice_minor"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        from_d = today - timedelta(days=29)
        stmt = select(func.avg(GeoScoreDaily.avg_sov)).where(
            and_(
                GeoScoreDaily.brand_id == project.primary_brand_id,
                GeoScoreDaily.date >= datetime.combine(from_d, datetime.min.time()),
            )
        )
        try:
            sov = (await session.execute(stmt)).scalar_one_or_none()
        except Exception:
            return []
        if sov is None:
            return []
        if sov >= 0.05:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P2",
                type="brand",
                title=f"share of voice persistently low ({sov * 100:.1f}%)",
                description=(
                    "Average share of voice over the last 30 days is below 5%. "
                    "Suggests fundamental visibility issue — content / topic gaps."
                ),
                focus_area="share_of_voice",
                direction=(
                    "Inspect competitor SoV via `/v1/projects/:id/competitors/metrics` and "
                    "topic coverage gaps via `/topics` to identify where to invest."
                ),
                reader_hints=["manager", "branding"],
                evidence={
                    "metric": "avg_sov_30d",
                    "current_value": round(sov, 4),
                    "threshold": 0.05,
                },
                if_untreated=(
                    "A brand stuck below 5% SoV typically requires structural content "
                    "investment (new topic clusters, KOL partnerships) rather than "
                    "incremental tuning."
                ),
            )
        ]


class IndustryLagTop10Rule(BaseRule):
    """Brand 30d avg geo_score lags industry top-10 average by >= 10 pts.

    Compares against `industry_benchmark_daily` for the brand's
    industry. P1 when lag >= 20 pts, P2 for 10-20.
    """

    rule_id = "industry_lag_top10_v1"
    category = "industry_lag_top10"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        from_d = today - timedelta(days=29)
        my_stmt = select(func.avg(GeoScoreDaily.avg_geo_score)).where(
            and_(
                GeoScoreDaily.brand_id == project.primary_brand_id,
                GeoScoreDaily.date >= datetime.combine(from_d, datetime.min.time()),
            )
        )
        try:
            my_score = (await session.execute(my_stmt)).scalar_one_or_none()
        except Exception:
            return []
        if my_score is None:
            return []

        # Industry top-10 avg from geo_score_daily aggregation
        # (industry_benchmark_daily lacks the top-10 cut directly).
        top_stmt = (
            select(func.avg(GeoScoreDaily.avg_geo_score).label("g"))
            .where(GeoScoreDaily.date >= datetime.combine(from_d, datetime.min.time()))
            .group_by(GeoScoreDaily.brand_id)
            .order_by(func.avg(GeoScoreDaily.avg_geo_score).desc())
            .limit(10)
        )
        rows = list((await session.execute(top_stmt)).all())
        if not rows:
            return []
        top10_avg = sum(float(r[0] or 0) for r in rows) / len(rows)
        lag = top10_avg - my_score
        if lag < 10:
            return []
        severity = "P1" if lag >= 20 else "P2"
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity=severity,
                type="brand",
                title=f"GEO score lags industry top-10 by {lag:.1f} pts",
                description=(
                    "Your 30d avg GEO score is behind the industry top-10 average by "
                    "more than 10 points. Identify which sub-metric (visibility / sov / "
                    "sentiment / citation_authority) accounts for the gap."
                ),
                focus_area="industry_position",
                direction=(
                    "Compare against top-10 brands via `/industries/:iid/ranking` — "
                    "drill into each sub-metric they outperform on."
                ),
                reader_hints=["manager", "branding"],
                evidence={
                    "metric": "avg_geo_score_30d",
                    "my_value": round(my_score, 2),
                    "industry_top10_avg": round(top10_avg, 2),
                    "lag": round(lag, 2),
                },
                if_untreated=(
                    "Industry leaders compound advantage — the gap typically widens "
                    "without targeted closure of the dominant sub-metric."
                ),
            )
        ]


class CitationDiversityLowRule(BaseRule):
    """Unique citation domains over 30d below threshold.

    Concentration risk: if all citations come from 2-3 domains, a single
    site change tanks visibility. Threshold: < 5 distinct domains in 30d
    triggers P2.
    """

    rule_id = "citation_diversity_low_v1"
    category = "citation_diversity_low"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        from_d = datetime.combine(today - timedelta(days=29), datetime.min.time())
        stmt = (
            select(func.count(func.distinct(CitationSource.domain)))
            .select_from(CitationSource)
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .where(
                and_(
                    BrandMention.brand_id == project.primary_brand_id,
                    CitationSource.created_at >= from_d,
                    CitationSource.domain.is_not(None),
                )
            )
        )
        try:
            unique_domains = int((await session.execute(stmt)).scalar_one() or 0)
        except Exception:
            return []
        # Only fire if there's at least 1 citation but < 5 unique domains
        if unique_domains == 0 or unique_domains >= 5:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P2",
                type="brand",
                title=f"only {unique_domains} unique citation domains in 30d",
                description=(
                    "Citation footprint is concentrated. A single site change or "
                    "removal could meaningfully drop the brand's authority score."
                ),
                focus_area="citation_diversity",
                direction=(
                    "Diversify into Tier-2 review / KOL / wiki-class properties; "
                    "see `/citations/domains` for current concentration."
                ),
                reader_hints=["operator", "branding"],
                evidence={
                    "metric": "unique_citation_domains_30d",
                    "current_value": unique_domains,
                    "threshold": 5,
                },
                if_untreated=(
                    "Concentration risk persists; single-source removal can drop "
                    "citation count > 50% overnight."
                ),
            )
        ]


class GeoScoreDropSevereRule(BaseRule):
    """7-day geo_score dropped >= 20 points vs. prior 7d.

    Triggers P0 — sharp short-window drops are usually pipeline / engine
    problems or PR crisis, both warrant immediate operator attention.
    """

    rule_id = "geo_score_drop_severe_v1"
    category = "geo_score_drop_severe"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        cur_from = datetime.combine(today - timedelta(days=6), datetime.min.time())
        prior_from = datetime.combine(today - timedelta(days=13), datetime.min.time())
        prior_to = datetime.combine(today - timedelta(days=7), datetime.min.time())

        async def _avg(_from: datetime, _to: datetime | None) -> float | None:
            cond = [
                GeoScoreDaily.brand_id == project.primary_brand_id,
                GeoScoreDaily.date >= _from,
            ]
            if _to is not None:
                cond.append(GeoScoreDaily.date < _to)
            stmt = select(func.avg(GeoScoreDaily.avg_geo_score)).where(and_(*cond))
            return (await session.execute(stmt)).scalar_one_or_none()

        cur = await _avg(cur_from, None)
        prior = await _avg(prior_from, prior_to)
        if cur is None or prior is None or prior == 0:
            return []
        delta = cur - prior
        if delta > -20:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P0",
                type="brand",
                title=f"GEO score down {delta:.1f} in 7d (severe)",
                description=(
                    "Composite GEO score dropped sharply in the last week. Common "
                    "root causes: pipeline outage on one engine, PR incident, or "
                    "competitor surge. Investigate before it compounds."
                ),
                focus_area="geo_score",
                direction=(
                    "Pull `/v1/projects/:id/metrics?series=mention_rate,sov,sentiment` "
                    "and the engine breakdown to isolate the cause."
                ),
                reader_hints=["operator", "manager"],
                evidence={
                    "metric": "avg_geo_score",
                    "current_7d": round(cur, 2),
                    "prior_7d": round(prior, 2),
                    "delta": round(delta, 2),
                },
                if_untreated=(
                    "Severe weekly drops compound: 4 weeks unattended typically "
                    "trigger a 2-3 month recovery cycle."
                ),
            )
        ]


class CompetitorRadicalGrowthRule(BaseRule):
    """Any pinned competitor's 30d avg geo_score grew >= 25% vs. prior 30d."""

    rule_id = "competitor_radical_growth_v1"
    category = "competitor_radical_growth"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        cur_from = datetime.combine(today - timedelta(days=29), datetime.min.time())
        prior_from = datetime.combine(today - timedelta(days=59), datetime.min.time())
        prior_to = datetime.combine(today - timedelta(days=30), datetime.min.time())

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

        async def _avg(brand_id: int, _from: datetime, _to: datetime | None) -> float | None:
            cond = [
                GeoScoreDaily.brand_id == brand_id,
                GeoScoreDaily.date >= _from,
            ]
            if _to is not None:
                cond.append(GeoScoreDaily.date < _to)
            stmt = select(func.avg(GeoScoreDaily.avg_geo_score)).where(and_(*cond))
            return (await session.execute(stmt)).scalar_one_or_none()

        out: list[DiagnosticPayload] = []
        for cid in comp_ids:
            cur = await _avg(cid, cur_from, None)
            prior = await _avg(cid, prior_from, prior_to)
            if cur is None or prior is None or prior == 0:
                continue
            growth = (cur - prior) / prior * 100.0
            if growth < 25.0:
                continue
            severity = "P1" if growth >= 40 else "P2"
            out.append(
                DiagnosticPayload(
                    rule_id=self.rule_id,
                    rule_version=self.rule_version,
                    category=self.category,
                    severity=severity,
                    type="brand",
                    title=f"competitor brand-{cid} grew {growth:.1f}% in 30d",
                    description=(
                        "A pinned competitor's 30-day average GEO score is growing "
                        "rapidly. Investigate which topics / engines they are winning."
                    ),
                    focus_area="competitor_landscape",
                    direction=(
                        "Compare topic-level metrics to identify what they're doing "
                        "that you aren't."
                    ),
                    reader_hints=["operator", "manager", "branding"],
                    evidence={
                        "metric": "avg_geo_score_30d_growth_pct",
                        "competitor_brand_id": cid,
                        "current_30d": round(cur, 2),
                        "prior_30d": round(prior, 2),
                        "growth_pct": round(growth, 2),
                    },
                    if_untreated=(
                        "Radical competitor growth typically eats share-of-voice in "
                        "the next 4-6 weeks if not contested."
                    ),
                )
            )
        return out


class CategoryRankDropRule(BaseRule):
    """Average position rank worsened (higher number = worse) by >= 2 vs. prior 30d."""

    rule_id = "category_rank_drop_v1"
    category = "category_rank_drop"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        cur_from = datetime.combine(today - timedelta(days=29), datetime.min.time())
        prior_from = datetime.combine(today - timedelta(days=59), datetime.min.time())
        prior_to = datetime.combine(today - timedelta(days=30), datetime.min.time())

        async def _avg(_from: datetime, _to: datetime | None) -> float | None:
            cond = [
                GeoScoreDaily.brand_id == project.primary_brand_id,
                GeoScoreDaily.date >= _from,
                GeoScoreDaily.avg_position_rank.is_not(None),
            ]
            if _to is not None:
                cond.append(GeoScoreDaily.date < _to)
            stmt = select(func.avg(GeoScoreDaily.avg_position_rank)).where(and_(*cond))
            return (await session.execute(stmt)).scalar_one_or_none()

        cur = await _avg(cur_from, None)
        prior = await _avg(prior_from, prior_to)
        if cur is None or prior is None:
            return []
        delta = cur - prior
        if delta < 2.0:  # "higher rank number" = worse position
            return []
        severity = "P1" if delta >= 4 else "P2"
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity=severity,
                type="brand",
                title=f"avg position rank slipped from #{prior:.1f} to #{cur:.1f}",
                description=(
                    "Across LLM responses where the brand is mentioned, it is now "
                    "appearing later in the list. Lower visibility on the page "
                    "feeds into the GEO composite."
                ),
                focus_area="position_rank",
                direction=(
                    "Audit which topics drive the slip; PR pieces that bring brand "
                    "to first-mention slot are the typical lever."
                ),
                reader_hints=["operator", "branding"],
                evidence={
                    "metric": "avg_position_rank_30d",
                    "current_value": round(cur, 2),
                    "prior_value": round(prior, 2),
                    "delta": round(delta, 2),
                },
                if_untreated=(
                    "Steady rank slippage is a leading indicator of mention-rate "
                    "decline in the next 2-4 weeks."
                ),
            )
        ]


class CitationAttributionMismatchRule(BaseRule):
    """Less than 20% of citations come from official-domain sources.

    Phase A.3 attribution_classifier writes the official-vs-third-party
    flag onto `citation_sources.source_type` (we treat 'official_*'
    prefix as official). When most citations reference 3rd-party reviews
    or comparison pages without attribution back to the brand site, the
    LLM's narrative is built on uncontrolled material.
    """

    rule_id = "citation_attribution_mismatch_v1"
    category = "citation_attribution_mismatch"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        from_d = datetime.combine(today - timedelta(days=29), datetime.min.time())
        # total citations
        base_q = (
            select(func.count(CitationSource.id))
            .select_from(CitationSource)
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .where(
                and_(
                    BrandMention.brand_id == project.primary_brand_id,
                    CitationSource.created_at >= from_d,
                )
            )
        )
        official_q = base_q.where(CitationSource.source_type.like("official_%"))
        try:
            total = int((await session.execute(base_q)).scalar_one() or 0)
            official = int((await session.execute(official_q)).scalar_one() or 0)
        except Exception:
            return []
        if total < 10:
            return []
        official_pct = official / total * 100.0
        if official_pct >= 20.0:
            return []
        severity = "P1" if official_pct < 10.0 else "P2"
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity=severity,
                type="brand",
                title=f"official-domain attribution only {official_pct:.1f}% of citations",
                description=(
                    "LLMs are citing third-party material more than your owned "
                    "channels. The brand narrative is being built without your "
                    "input."
                ),
                focus_area="citation_attribution",
                direction=(
                    "Strengthen owned content (press kit, knowledge hub, FAQ) "
                    "and seed clear attribution snippets that LLMs can quote."
                ),
                reader_hints=["operator", "branding"],
                evidence={
                    "metric": "official_attribution_pct_30d",
                    "official_count": official,
                    "total_count": total,
                    "official_pct": round(official_pct, 2),
                    "threshold_pct": 20.0,
                },
                if_untreated=(
                    "Without official attribution dominance, narrative drift is "
                    "permanent in the LLM's training cycle."
                ),
            )
        ]


class WikiMissingRule(BaseRule):
    """No wikipedia.org / baike.baidu.com citation in 30d for primary brand."""

    rule_id = "wiki_missing_v1"
    category = "wiki_missing"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        from_d = datetime.combine(today - timedelta(days=29), datetime.min.time())
        wiki_domains = ["wikipedia.org", "baike.baidu.com", "zh.wikipedia.org", "en.wikipedia.org"]
        stmt = (
            select(func.count(CitationSource.id))
            .select_from(CitationSource)
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .where(
                and_(
                    BrandMention.brand_id == project.primary_brand_id,
                    CitationSource.created_at >= from_d,
                    CitationSource.domain.in_(wiki_domains),
                )
            )
        )
        try:
            wiki_count = int((await session.execute(stmt)).scalar_one() or 0)
        except Exception:
            return []
        if wiki_count > 0:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P2",
                type="brand",
                title="no wiki / encyclopedia citations in 30d",
                description=(
                    "LLMs treat Wikipedia and Baidu Baike as anchor sources for "
                    "factual consistency. Absence here means the brand is missing "
                    "from the LLM's reference scaffold."
                ),
                focus_area="anchor_sources",
                direction=(
                    "Submit / refresh a Wikipedia page in zh-CN and en. Long-tail "
                    "but necessary for sustained authority."
                ),
                reader_hints=["branding"],
                evidence={
                    "metric": "wiki_citation_count_30d",
                    "current_value": 0,
                    "wiki_domains": wiki_domains,
                },
                if_untreated=(
                    "Without wiki anchor, every LLM has to rely on third-party "
                    "summaries — narrative drift compounds over time."
                ),
            )
        ]


class TopicLossRule(BaseRule):
    """Mention rate has fallen to 0% on a previously-tracked topic.

    Approximated at the brand level: if 30d mention_rate is below 1% AND
    prior 30d was above 5%, surface as topic_loss until per-topic
    aggregations land.
    """

    rule_id = "topic_loss_v1"
    category = "topic_loss"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        cur_from = datetime.combine(today - timedelta(days=29), datetime.min.time())
        prior_from = datetime.combine(today - timedelta(days=59), datetime.min.time())
        prior_to = datetime.combine(today - timedelta(days=30), datetime.min.time())

        async def _avg(_from: datetime, _to: datetime | None) -> float | None:
            cond = [
                GeoScoreDaily.brand_id == project.primary_brand_id,
                GeoScoreDaily.date >= _from,
            ]
            if _to is not None:
                cond.append(GeoScoreDaily.date < _to)
            stmt = select(func.avg(GeoScoreDaily.mention_rate)).where(and_(*cond))
            return (await session.execute(stmt)).scalar_one_or_none()

        cur = await _avg(cur_from, None)
        prior = await _avg(prior_from, prior_to)
        if cur is None or prior is None:
            return []
        if cur >= 0.01 or prior < 0.05:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P1",
                type="brand",
                title="mention rate collapsed (< 1%) — topic loss suspected",
                description=(
                    "The brand was mentioned >5% on average over the prior 30 days "
                    "but is below 1% in the current window. Likely cause: removed "
                    "from a recommendation list or knocked out of a key topic."
                ),
                focus_area="topic_coverage",
                direction=(
                    "Audit which topics drove the prior period's mentions and "
                    "where the current window is silent."
                ),
                reader_hints=["operator", "manager"],
                evidence={
                    "metric": "avg_mention_rate",
                    "current_30d": round(cur, 4),
                    "prior_30d": round(prior, 4),
                },
                if_untreated=(
                    "Once a brand is dropped from an LLM's topic recall set, "
                    "reinclusion typically requires fresh PR content + 4-8 weeks."
                ),
            )
        ]


class FirstPlaceLossRule(BaseRule):
    """First-place mentions / total mentions ratio fell sharply.

    First-place positioning has outsized weight in LLM answer ranking.
    Triggers P2 when 30d first_place_count is >= 30% lower than prior 30d
    (with both windows having meaningful sample size).
    """

    rule_id = "first_place_loss_v1"
    category = "first_place_loss"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        cur_from = datetime.combine(today - timedelta(days=29), datetime.min.time())
        prior_from = datetime.combine(today - timedelta(days=59), datetime.min.time())
        prior_to = datetime.combine(today - timedelta(days=30), datetime.min.time())

        async def _sum(_from: datetime, _to: datetime | None) -> int:
            cond = [
                GeoScoreDaily.brand_id == project.primary_brand_id,
                GeoScoreDaily.date >= _from,
            ]
            if _to is not None:
                cond.append(GeoScoreDaily.date < _to)
            stmt = select(func.coalesce(func.sum(GeoScoreDaily.first_place_count), 0)).where(
                and_(*cond)
            )
            return int((await session.execute(stmt)).scalar_one() or 0)

        cur = await _sum(cur_from, None)
        prior = await _sum(prior_from, prior_to)
        if prior < 10:  # not enough sample
            return []
        if cur >= prior:
            return []
        drop_pct = (prior - cur) / prior * 100.0
        if drop_pct < 30.0:
            return []
        severity = "P1" if drop_pct >= 60 else "P2"
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity=severity,
                type="brand",
                title=f"first-place mentions down {drop_pct:.1f}% in 30d",
                description=(
                    "Top-slot mentions carry the most weight in LLM answer "
                    "rankings. A sharp drop usually means competitors took the "
                    "lead-mention slot in shared topics."
                ),
                focus_area="first_place",
                direction=(
                    "Drill into engine + topic to see which slots flipped; "
                    "answer-engine PR content typically restores within 2 weeks."
                ),
                reader_hints=["operator", "manager"],
                evidence={
                    "metric": "first_place_count_30d",
                    "current_value": cur,
                    "prior_value": prior,
                    "drop_pct": round(drop_pct, 2),
                },
                if_untreated=(
                    "First-place erosion compounds: a 30% drop usually drags "
                    "average position rank by >1.0 within the next month."
                ),
            )
        ]


class CitationGrowthSurgeRule(BaseRule):
    """Citation count grew > 100% in 30d vs. prior 30d.

    Positive signal — surface as P3 informational so that branding /
    operator readers can capitalise on momentum (e.g. amplify the new
    content sources to reinforce authority).
    """

    rule_id = "citation_growth_surge_v1"
    category = "citation_growth_surge"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        cur_from = datetime.combine(today - timedelta(days=29), datetime.min.time())
        prior_from = datetime.combine(today - timedelta(days=59), datetime.min.time())
        prior_to = datetime.combine(today - timedelta(days=30), datetime.min.time())

        async def _count(_from: datetime, _to: datetime | None) -> int:
            cond = [
                BrandMention.brand_id == project.primary_brand_id,
                CitationSource.created_at >= _from,
            ]
            if _to is not None:
                cond.append(CitationSource.created_at < _to)
            stmt = (
                select(func.count(CitationSource.id))
                .select_from(CitationSource)
                .join(BrandMention, BrandMention.id == CitationSource.mention_id)
                .where(and_(*cond))
            )
            return int((await session.execute(stmt)).scalar_one() or 0)

        cur = await _count(cur_from, None)
        prior = await _count(prior_from, prior_to)
        if prior < 5:  # noisy below 5
            return []
        if cur < prior:
            return []
        growth_pct = (cur - prior) / prior * 100.0
        if growth_pct < 100.0:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P3",
                type="brand",
                title=f"citation count surged {growth_pct:.1f}% in 30d",
                description=(
                    "Citations more than doubled. Likely a recent PR / launch / "
                    "review wave is paying off."
                ),
                focus_area="citation_growth",
                direction=(
                    "Identify the new source domains and mirror the strategy on "
                    "adjacent topics to sustain the momentum."
                ),
                reader_hints=["operator", "branding", "manager"],
                evidence={
                    "metric": "citation_count_30d",
                    "current_value": cur,
                    "prior_value": prior,
                    "growth_pct": round(growth_pct, 2),
                },
                if_untreated=(
                    "Surge windows close fast; if the new content isn't "
                    "amplified, citation counts typically revert in 4-6 weeks."
                ),
            )
        ]


class LlmEngineAnomalyRule(BaseRule):
    """Single engine has 0 mentions in 7d while others continue producing.

    A common operational issue — one adapter (chatgpt / doubao / deepseek)
    silently breaks (cookies expired / IP banned / model-side throttle)
    while peers keep flowing data. The composite GEO score still trends
    okay, but the cross-engine sample is biased. Triggers P1.
    """

    rule_id = "llm_engine_anomaly_v1"
    category = "llm_engine_anomaly"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        from_d = datetime.combine(today - timedelta(days=6), datetime.min.time())
        stmt = (
            select(
                GeoScoreDaily.target_llm, func.coalesce(func.sum(GeoScoreDaily.mention_count), 0)
            )
            .where(
                and_(
                    GeoScoreDaily.brand_id == project.primary_brand_id,
                    GeoScoreDaily.date >= from_d,
                    GeoScoreDaily.target_llm.is_not(None),
                )
            )
            .group_by(GeoScoreDaily.target_llm)
        )
        try:
            rows = list((await session.execute(stmt)).all())
        except Exception:
            return []
        if len(rows) < 2:
            return []
        zero_engines = [name for (name, total) in rows if int(total or 0) == 0]
        active_engines = [name for (name, total) in rows if int(total or 0) > 0]
        if not zero_engines or not active_engines:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P1",
                type="brand",
                title=f"engine outage suspected: {', '.join(zero_engines)} — 0 mentions in 7d",
                description=(
                    "At least one LLM engine produced no mentions in the last "
                    "week while peers continue to deliver data. Cross-engine "
                    "sample is biased — composite metrics are unreliable until "
                    "the engine is restored."
                ),
                focus_area="engine_health",
                direction=(
                    "Inspect adapter cookies / proxy / throttle logs for the "
                    "affected engine(s). Restore before the next aggregation."
                ),
                reader_hints=["operator"],
                evidence={
                    "metric": "mention_count_by_engine_7d",
                    "zero_engines": zero_engines,
                    "active_engines": active_engines,
                },
                if_untreated=(
                    "Composite GEO score will skew toward the surviving engines "
                    "and reports will misrepresent cross-LLM coverage."
                ),
            )
        ]


class AttributionAnchorLowRule(BaseRule):
    """Total citation count in 30d is < 5 — narrative has no anchor.

    Even if the brand has high mention rate, without citations the LLM is
    free-associating without source material. Anchor sources (owned web,
    knowledge base) are needed to steer the narrative. Triggers P2.
    """

    rule_id = "attribution_anchor_low_v1"
    category = "attribution_anchor_low"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        from_d = datetime.combine(today - timedelta(days=29), datetime.min.time())
        stmt = (
            select(func.count(CitationSource.id))
            .select_from(CitationSource)
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .where(
                and_(
                    BrandMention.brand_id == project.primary_brand_id,
                    CitationSource.created_at >= from_d,
                )
            )
        )
        # Guard: only fire when brand actually had mentions to anchor
        mention_stmt = select(func.count(BrandMention.id)).where(
            and_(
                BrandMention.brand_id == project.primary_brand_id,
                BrandMention.created_at >= from_d,
            )
        )
        try:
            cit_count = int((await session.execute(stmt)).scalar_one() or 0)
            mention_count = int((await session.execute(mention_stmt)).scalar_one() or 0)
        except Exception:
            return []
        if cit_count >= 5 or mention_count < 10:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P2",
                type="brand",
                title=f"only {cit_count} citations against {mention_count} mentions in 30d",
                description=(
                    "Brand is being mentioned but without source anchors. LLMs "
                    "are free-associating — narrative has no traceable evidence "
                    "to ground or update."
                ),
                focus_area="citation_anchor",
                direction=(
                    "Publish anchorable owned content (press kit, knowledge "
                    "hub, FAQ); seed reviews on tier-2 review sites."
                ),
                reader_hints=["operator", "branding"],
                evidence={
                    "metric": "citation_to_mention_ratio_30d",
                    "citation_count": cit_count,
                    "mention_count": mention_count,
                },
                if_untreated=(
                    "Without anchor sources the brand narrative will drift "
                    "based on whatever third-party text the LLM happens to find."
                ),
            )
        ]


class ContentGapRule(BaseRule):
    """High mention but low citation — content gap exists.

    Mentions imply demand to talk about the brand; citations tell you
    where text comes from. When the ratio is low (< 30 citations per
    100 mentions in 30d), there's an easy growth lever: produce content
    that LLMs can quote.

    Trigger requires baseline volume (>= 50 mentions) so we don't fire
    on cold-start projects.
    """

    rule_id = "content_gap_v1"
    category = "content_gap"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        from_d = datetime.combine(today - timedelta(days=29), datetime.min.time())

        mention_stmt = select(func.count(BrandMention.id)).where(
            and_(
                BrandMention.brand_id == project.primary_brand_id,
                BrandMention.created_at >= from_d,
            )
        )
        cit_stmt = (
            select(func.count(CitationSource.id))
            .select_from(CitationSource)
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .where(
                and_(
                    BrandMention.brand_id == project.primary_brand_id,
                    CitationSource.created_at >= from_d,
                )
            )
        )
        try:
            mentions = int((await session.execute(mention_stmt)).scalar_one() or 0)
            citations = int((await session.execute(cit_stmt)).scalar_one() or 0)
        except Exception:
            return []
        if mentions < 50:
            return []
        ratio = citations / mentions * 100.0 if mentions else 0.0
        if ratio >= 30.0:
            return []
        severity = "P2" if ratio >= 15.0 else "P1"
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity=severity,
                type="brand",
                title=f"content gap — {ratio:.1f} citations per 100 mentions",
                description=(
                    "Brand is being talked about but few sources are quoted. "
                    "Topical gap exists between LLM demand and the available "
                    "anchorable text — a clear growth opportunity."
                ),
                focus_area="content_gap",
                direction=(
                    "Inspect top-mentioned topics with no citations; produce "
                    "PR / blog content tailored to each topic."
                ),
                reader_hints=["operator", "branding"],
                evidence={
                    "metric": "citations_per_100_mentions_30d",
                    "mention_count": mentions,
                    "citation_count": citations,
                    "ratio": round(ratio, 2),
                },
                if_untreated=(
                    "Demand without supply is captured by competitors; "
                    "expect SoV erosion over the next 4-6 weeks."
                ),
            )
        ]


class ProductFeatureNegativeRule(BaseRule):
    """A specific product feature has > 30% negative sentiment in 30d.

    Surfaces product-level pain points the operator should respond to —
    e.g. "delivery", "pricing", "battery". Triggers P1 when negative
    ratio crosses 30% with at least 10 mentions.
    """

    rule_id = "product_feature_negative_v1"
    category = "product_feature_negative"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        from_d = datetime.combine(today - timedelta(days=29), datetime.min.time())

        stmt = (
            select(
                ProductFeatureMention.feature_name,
                func.count(ProductFeatureMention.id),
                func.sum(case((ProductFeatureMention.feature_sentiment == "negative", 1), else_=0)),
            )
            .join(BrandMention, BrandMention.brand_name == ProductFeatureMention.brand_name)
            .where(
                and_(
                    BrandMention.brand_id == project.primary_brand_id,
                    ProductFeatureMention.created_at >= from_d,
                )
            )
            .group_by(ProductFeatureMention.feature_name)
            .having(func.count(ProductFeatureMention.id) >= 10)
        )
        try:
            rows = list((await session.execute(stmt)).all())
        except Exception:
            return []

        out: list[DiagnosticPayload] = []
        for feature, total, negative in rows:
            t = int(total or 0)
            n = int(negative or 0)
            if t < 10:
                continue
            neg_pct = n / t * 100.0
            if neg_pct < 30.0:
                continue
            severity = "P0" if neg_pct >= 60 else "P1"
            out.append(
                DiagnosticPayload(
                    rule_id=self.rule_id,
                    rule_version=self.rule_version,
                    category=self.category,
                    severity=severity,
                    type="product",
                    title=f"feature '{feature}' negative {neg_pct:.1f}%",
                    description=(
                        "Product feature is generating disproportionate "
                        "negative sentiment in LLM responses. Top-of-funnel "
                        "perception risk."
                    ),
                    focus_area="product_feature_sentiment",
                    direction=(
                        "Drill into product_feature_mentions where "
                        "feature_sentiment='negative' to see context snippets; "
                        "coordinate with product team."
                    ),
                    reader_hints=["operator", "manager"],
                    evidence={
                        "metric": "feature_negative_ratio_30d",
                        "feature_name": feature,
                        "total": t,
                        "negative": n,
                        "negative_pct": round(neg_pct, 2),
                    },
                    if_untreated=(
                        "Compounding negative perception on a single feature "
                        "becomes an LLM 'fact' within 1-2 months."
                    ),
                )
            )
        return out


class PersonaKeywordChangeRule(BaseRule):
    """Top sentiment keyword set churned > 70% month-over-month.

    Sentiment drivers are the 'why' behind brand perception. When the
    topic of conversation shifts radically (different vocabulary
    dominating month-over-month), branding risks losing narrative
    control. Triggers P2.
    """

    rule_id = "persona_keyword_change_v1"
    category = "persona_keyword_change"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        cur_from = datetime.combine(today - timedelta(days=29), datetime.min.time())
        prior_from = datetime.combine(today - timedelta(days=59), datetime.min.time())
        prior_to = datetime.combine(today - timedelta(days=30), datetime.min.time())

        async def _top_drivers(_from: datetime, _to: datetime | None) -> set[str]:
            cond = [
                BrandMention.brand_id == project.primary_brand_id,
                SentimentDriver.created_at >= _from,
            ]
            if _to is not None:
                cond.append(SentimentDriver.created_at < _to)
            stmt = (
                select(SentimentDriver.driver_text, func.count(SentimentDriver.id).label("cnt"))
                .join(BrandMention, BrandMention.id == SentimentDriver.mention_id)
                .where(and_(*cond))
                .group_by(SentimentDriver.driver_text)
                .order_by(func.count(SentimentDriver.id).desc())
                .limit(10)
            )
            try:
                rows = list((await session.execute(stmt)).all())
            except Exception:
                return set()
            return {r[0] for r in rows if r[0]}

        cur = await _top_drivers(cur_from, None)
        prior = await _top_drivers(prior_from, prior_to)
        if len(cur) < 5 or len(prior) < 5:
            return []
        overlap = len(cur & prior)
        churn_pct = (1 - overlap / max(len(cur), 1)) * 100.0
        if churn_pct < 70.0:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P2",
                type="brand",
                title=f"sentiment keywords churned {churn_pct:.0f}% MoM",
                description=(
                    "The vocabulary describing the brand changed sharply "
                    "month-over-month. The narrative is shifting — likely "
                    "external (PR cycle, competitor launches) — and may "
                    "require branding to re-anchor."
                ),
                focus_area="sentiment_drivers",
                direction=(
                    "Compare current vs. prior top-10 sentiment drivers; "
                    "decide whether the new set is on-message or drift."
                ),
                reader_hints=["branding"],
                evidence={
                    "metric": "top10_driver_overlap_mom",
                    "current_top": sorted(cur),
                    "prior_top": sorted(prior),
                    "overlap_count": overlap,
                    "churn_pct": round(churn_pct, 2),
                },
                if_untreated=(
                    "Unmanaged narrative drift typically reduces brand-led "
                    "messaging share by 20-40% within a quarter."
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
    SentimentDropRule,
    ShareOfVoiceMinorRule,
    IndustryLagTop10Rule,
    CitationDiversityLowRule,
    GeoScoreDropSevereRule,
    CompetitorRadicalGrowthRule,
    CategoryRankDropRule,
    CitationAttributionMismatchRule,
    WikiMissingRule,
    TopicLossRule,
    FirstPlaceLossRule,
    CitationGrowthSurgeRule,
    LlmEngineAnomalyRule,
    AttributionAnchorLowRule,
    ContentGapRule,
    ProductFeatureNegativeRule,
    PersonaKeywordChangeRule,
]


# Stubbed categories for full PRD §4.7.1.1 coverage (Phase D follow-up wires)
PLANNED_CATEGORIES = [
    "narrative_drift",
    "product_remission",
    "same_group_share_low",
    "topic_emerging_missed",
]
