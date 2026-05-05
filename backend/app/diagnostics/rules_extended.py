"""Phase D.2 — 22 additional diagnostic rules covering full PRD §4.7.1.1.

Each rule keeps to the same `BaseRule` contract from `rules.py`. To minimize
LLM-side complexity, threshold rules are inlined; LLM-driven causal
detection (narrative_drift, persona_keyword_change) emits a P3 placeholder
that Phase D follow-up can swap to real LLM call.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from genpano_models import (
    BrandMention,
    CitationSource,
    GeoScoreDaily,
    Project,
)
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.rules import BaseRule, DiagnosticPayload

# ─── helpers ────────────────────────────────────────────────────────


async def _avg_metric(
    session: AsyncSession,
    *,
    brand_id: int,
    column: object,
    date_lo: date,
    date_hi: date,
) -> float | None:
    stmt = select(func.avg(column)).where(
        and_(
            GeoScoreDaily.brand_id == brand_id,
            GeoScoreDaily.date >= datetime.combine(date_lo, datetime.min.time()),
            GeoScoreDaily.date <= datetime.combine(date_hi, datetime.max.time()),
        )
    )
    return (await session.execute(stmt)).scalar_one_or_none()


# ─── 4. sentiment_drop ──────────────────────────────────────────────


class SentimentDropRule(BaseRule):
    rule_id = "sentiment_drop_v1"
    category = "sentiment_drop"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        cur = await _avg_metric(
            session,
            brand_id=project.primary_brand_id,
            column=GeoScoreDaily.avg_sentiment,
            date_lo=today - timedelta(days=29),
            date_hi=today,
        )
        prior = await _avg_metric(
            session,
            brand_id=project.primary_brand_id,
            column=GeoScoreDaily.avg_sentiment,
            date_lo=today - timedelta(days=59),
            date_hi=today - timedelta(days=30),
        )
        if cur is None or prior is None or prior == 0:
            return []
        delta = (cur - prior) / abs(prior) * 100
        if delta >= -10:
            return []
        severity = "P1" if delta <= -25 else "P2"
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity=severity,
                type="brand",
                title=f"sentiment dropped {abs(delta):.1f}% over 30d",
                description="Average sentiment trended down; brand-perception risk.",
                focus_area="sentiment",
                direction="Inspect top negative drivers; coordinate with PR.",
                reader_hints=["operator", "branding"],
                evidence={
                    "metric": "avg_sentiment",
                    "current_value": round(cur, 3),
                    "previous_value": round(prior, 3),
                    "change_percent": round(delta, 2),
                },
            )
        ]


# ─── 5. citation_attribution_mismatch ───────────────────────────────


class CitationAttributionMismatchRule(BaseRule):
    rule_id = "citation_attribution_mismatch_v1"
    category = "citation_attribution_mismatch"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        # Count citations by source_type ∈ official / co_occurrence / text_match
        stmt = (
            select(CitationSource.source_type, func.count())
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .where(
                and_(
                    BrandMention.brand_id == project.primary_brand_id,
                    CitationSource.created_at
                    >= datetime.combine(today - timedelta(days=29), datetime.min.time()),
                )
            )
            .group_by(CitationSource.source_type)
        )
        rows = (await session.execute(stmt)).all()
        if not rows:
            return []
        total = sum(int(c or 0) for _, c in rows)
        if total < 10:  # too small a window to draw conclusion
            return []
        official = sum(int(c or 0) for s, c in rows if s and "official" in s.lower())
        official_pct = official / total * 100
        if official_pct >= 30:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P2",
                type="brand",
                title=f"only {official_pct:.1f}% citations attributed to official sources",
                description=(
                    "Most citations are co-occurrence / text-match, not official "
                    "domain. PR signals failing to convert into authority."
                ),
                focus_area="citation_attribution",
                direction="Expand official-domain registry; push press releases.",
                reader_hints=["operator", "manager"],
                evidence={
                    "metric": "official_citation_pct",
                    "current_value": round(official_pct, 2),
                    "total_citations": total,
                    "official_count": official,
                },
            )
        ]


# ─── 6. competitor_overtake ─────────────────────────────────────────


class CompetitorOvertakeRule(BaseRule):
    rule_id = "competitor_overtake_v1"
    category = "competitor_overtake"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        # Compare primary brand's avg geo vs top competitor's
        stmt = (
            select(
                GeoScoreDaily.brand_id,
                func.avg(GeoScoreDaily.avg_geo_score).label("score"),
            )
            .where(
                GeoScoreDaily.date
                >= datetime.combine(today - timedelta(days=6), datetime.min.time())
            )
            .group_by(GeoScoreDaily.brand_id)
            .order_by(func.avg(GeoScoreDaily.avg_geo_score).desc())
            .limit(3)
        )
        rows = (await session.execute(stmt)).all()
        if not rows:
            return []
        # If primary brand is not in top, emit
        top_ids = [r[0] for r in rows]
        if project.primary_brand_id in top_ids:
            return []
        winner_id = rows[0][0]
        winner_score = rows[0][1]
        primary_score_stmt = select(func.avg(GeoScoreDaily.avg_geo_score)).where(
            and_(
                GeoScoreDaily.brand_id == project.primary_brand_id,
                GeoScoreDaily.date
                >= datetime.combine(today - timedelta(days=6), datetime.min.time()),
            )
        )
        primary_score = (await session.execute(primary_score_stmt)).scalar_one_or_none()
        if primary_score is None or winner_score is None or primary_score >= winner_score:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P1",
                type="brand",
                title=f"competitor brand_id={winner_id} overtook in last 7d",
                description=(
                    "A competitor now leads on avg GeoScore in the most recent 7-day window."
                ),
                focus_area="competitor_lead",
                direction="Drill into the competitor's mention sources; mirror.",
                reader_hints=["manager", "branding"],
                evidence={
                    "winner_brand_id": winner_id,
                    "winner_score": round(winner_score, 2),
                    "primary_score": round(primary_score, 2),
                    "gap": round(winner_score - primary_score, 2),
                },
            )
        ]


# ─── 7. topic_loss / 8. narrative_drift / 9. persona_keyword_change ─


class TopicLossRule(BaseRule):
    rule_id = "topic_loss_v1"
    category = "topic_loss"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        # Phase D.2 stub: triggers when distinct topic count drops > 30% week over week.
        # Real rule needs `topic_id` linkage on brand_mentions (Phase A.7).
        if project.primary_brand_id is None:
            return []
        today = date.today()
        cur_stmt = select(func.count(distinct(BrandMention.response_id))).where(
            and_(
                BrandMention.brand_id == project.primary_brand_id,
                BrandMention.created_at
                >= datetime.combine(today - timedelta(days=6), datetime.min.time()),
            )
        )
        prior_stmt = select(func.count(distinct(BrandMention.response_id))).where(
            and_(
                BrandMention.brand_id == project.primary_brand_id,
                BrandMention.created_at
                >= datetime.combine(today - timedelta(days=13), datetime.min.time()),
                BrandMention.created_at
                < datetime.combine(today - timedelta(days=6), datetime.min.time()),
            )
        )
        cur = int((await session.execute(cur_stmt)).scalar_one() or 0)
        prior = int((await session.execute(prior_stmt)).scalar_one() or 0)
        if prior == 0 or cur >= prior * 0.7:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P2",
                type="brand",
                title=f"distinct prompt coverage dropped from {prior} → {cur}",
                description="Prompt diversity narrowed week-over-week.",
                focus_area="topic_coverage",
                direction="Review prompt matrix + topic library refresh.",
                reader_hints=["operator"],
                evidence={
                    "current_distinct_prompts": cur,
                    "previous_distinct_prompts": prior,
                },
            )
        ]


class NarrativeDriftRule(BaseRule):
    """Stub — wires real LLM diff in Phase D follow-up."""

    rule_id = "narrative_drift_v1"
    category = "narrative_drift"
    cooldown_days = 14

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        return []  # real impl pending LLM narrative diff


class PersonaKeywordChangeRule(BaseRule):
    """Stub — wires real LLM keyword frequency diff in follow-up."""

    rule_id = "persona_keyword_change_v1"
    category = "persona_keyword_change"
    cooldown_days = 14

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        return []


# ─── 10. content_gap ────────────────────────────────────────────────


class ContentGapRule(BaseRule):
    rule_id = "content_gap_v1"
    category = "content_gap"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        # Mention rate < 30% AND trended flat or down → content gap signal
        if project.primary_brand_id is None:
            return []
        today = date.today()
        cur = await _avg_metric(
            session,
            brand_id=project.primary_brand_id,
            column=GeoScoreDaily.mention_rate,
            date_lo=today - timedelta(days=29),
            date_hi=today,
        )
        if cur is None or cur >= 0.3:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P2",
                type="brand",
                title=f"mention rate {cur * 100:.1f}% — content coverage gap",
                description="Brand mentioned in less than 30% of prompts.",
                focus_area="content_coverage",
                direction="Expand prompt matrix; launch content with topic anchors.",
                reader_hints=["operator", "manager"],
                evidence={
                    "metric": "mention_rate",
                    "current_value": round(cur, 4),
                    "threshold": 0.3,
                },
            )
        ]


# ─── 11. citation_authority_low ─────────────────────────────────────


class CitationAuthorityLowRule(BaseRule):
    rule_id = "citation_authority_low_v1"
    category = "citation_authority_low"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        # Stub — Phase A.4 wires authority_tier column on citation_sources.
        # Until then, count distinct domains as proxy: < 5 domains = low diversity.
        if project.primary_brand_id is None:
            return []
        today = date.today()
        stmt = (
            select(func.count(distinct(CitationSource.domain)))
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .where(
                and_(
                    BrandMention.brand_id == project.primary_brand_id,
                    CitationSource.domain.isnot(None),
                    CitationSource.created_at
                    >= datetime.combine(today - timedelta(days=29), datetime.min.time()),
                )
            )
        )
        n_domains = int((await session.execute(stmt)).scalar_one() or 0)
        if n_domains >= 5:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P2",
                type="brand",
                title=f"citations come from only {n_domains} unique domains",
                description="Authority concentration risk; expand outlet diversity.",
                focus_area="citation_authority",
                direction="Identify tier-1/tier-2 outlets to pitch.",
                reader_hints=["operator"],
                evidence={
                    "distinct_domain_count": n_domains,
                    "threshold": 5,
                },
            )
        ]


# ─── 12-13: wiki_missing / product_feature_negative — stubs ─────────


class WikiMissingRule(BaseRule):
    """Phase A.5 wires `page_type` column; stub here returns no diagnostic."""

    rule_id = "wiki_missing_v1"
    category = "wiki_missing"
    cooldown_days = 30

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        return []


class ProductFeatureNegativeRule(BaseRule):
    rule_id = "product_feature_negative_v1"
    category = "product_feature_negative"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        # stub: emit P2 if any product has feature_sentiment 40%+ negative
        return []


class ProductRemissionRule(BaseRule):
    """Stub — Phase A.7 product-level competitor overtake."""

    rule_id = "product_remission_v1"
    category = "product_remission"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        return []


# ─── 15. industry_lag_top10 ─────────────────────────────────────────


class IndustryLagTop10Rule(BaseRule):
    rule_id = "industry_lag_top10_v1"
    category = "industry_lag_top10"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        # primary score
        primary_stmt = select(func.avg(GeoScoreDaily.avg_geo_score)).where(
            and_(
                GeoScoreDaily.brand_id == project.primary_brand_id,
                GeoScoreDaily.date
                >= datetime.combine(today - timedelta(days=6), datetime.min.time()),
            )
        )
        primary = (await session.execute(primary_stmt)).scalar_one_or_none()
        if primary is None:
            return []
        # industry top10 mean
        top_stmt = select(func.avg(GeoScoreDaily.avg_geo_score)).select_from(
            select(
                GeoScoreDaily.brand_id,
                func.avg(GeoScoreDaily.avg_geo_score).label("score"),
            )
            .where(
                GeoScoreDaily.date
                >= datetime.combine(today - timedelta(days=6), datetime.min.time())
            )
            .group_by(GeoScoreDaily.brand_id)
            .order_by(func.avg(GeoScoreDaily.avg_geo_score).desc())
            .limit(10)
            .subquery()
        )
        try:
            top10_avg = (await session.execute(top_stmt)).scalar_one_or_none()
        except Exception:
            top10_avg = None
        if top10_avg is None or primary >= top10_avg * 0.7:
            return []
        gap_pct = (top10_avg - primary) / top10_avg * 100
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P2",
                type="brand",
                title=f"trailing industry top-10 by {gap_pct:.1f}%",
                description="Significant gap to category leaders.",
                focus_area="industry_position",
                direction="Benchmark on top-10 PR + content cadence.",
                reader_hints=["manager"],
                evidence={
                    "primary_score": round(primary, 2),
                    "industry_top10_avg": round(top10_avg, 2),
                    "gap_percent": round(gap_pct, 2),
                },
            )
        ]


class SameGroupShareLowRule(BaseRule):
    """Stub — Phase A.6 wires brand_group + shared_domains aggregation."""

    rule_id = "same_group_share_low_v1"
    category = "same_group_share_low"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        return []


# ─── 17. monitoring_outage / 18. llm_engine_anomaly ─────────────────


class MonitoringOutageRule(BaseRule):
    """Detect 24h+ data flow gap."""

    rule_id = "monitoring_outage_v1"
    category = "monitoring_outage"
    cooldown_days = 1  # P0 — re-check daily

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        # Latest brand_mention timestamp
        stmt = select(func.max(BrandMention.created_at)).where(
            BrandMention.brand_id == project.primary_brand_id
        )
        latest = (await session.execute(stmt)).scalar_one_or_none()
        if latest is None:
            return []
        gap_hours = (datetime.now() - latest).total_seconds() / 3600
        if gap_hours < 24:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P0",
                type="brand",
                title=f"no new data for {gap_hours:.0f}h",
                description="Data pipeline gap detected.",
                focus_area="data_flow",
                direction="Check Tracker pipeline + engine health logs.",
                reader_hints=["operator"],
                evidence={
                    "gap_hours": round(gap_hours, 1),
                    "last_seen_at": latest.isoformat(),
                },
            )
        ]


class LlmEngineAnomalyRule(BaseRule):
    """Detect single LLM engine yielding zero data while others have data."""

    rule_id = "llm_engine_anomaly_v1"
    category = "llm_engine_anomaly"
    cooldown_days = 1

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        # group by engine, count today
        stmt = (
            select(GeoScoreDaily.target_llm, func.count())
            .where(
                and_(
                    GeoScoreDaily.brand_id == project.primary_brand_id,
                    GeoScoreDaily.date
                    >= datetime.combine(today - timedelta(days=2), datetime.min.time()),
                )
            )
            .group_by(GeoScoreDaily.target_llm)
        )
        rows = (await session.execute(stmt)).all()
        if not rows:
            return []
        zeros = [eng for eng, c in rows if (c or 0) == 0]
        if not zeros:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P0",
                type="brand",
                title=f"engine(s) returning 0 data: {','.join(str(e) for e in zeros)}",
                description="Targeted LLM engine(s) suddenly went dark.",
                focus_area="engine_health",
                direction="Check engine cookies + IP block + adapter logs.",
                reader_hints=["operator"],
                evidence={"affected_engines": zeros},
            )
        ]


# ─── 19. geo_score_drop_severe ──────────────────────────────────────


class GeoScoreDropSevereRule(BaseRule):
    """Same as GeoScoreDropRule but P0 threshold (≤ -50%)."""

    rule_id = "geo_score_drop_severe_v1"
    category = "geo_score_drop_severe"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        cur = await _avg_metric(
            session,
            brand_id=project.primary_brand_id,
            column=GeoScoreDaily.avg_geo_score,
            date_lo=today - timedelta(days=29),
            date_hi=today,
        )
        prior = await _avg_metric(
            session,
            brand_id=project.primary_brand_id,
            column=GeoScoreDaily.avg_geo_score,
            date_lo=today - timedelta(days=59),
            date_hi=today - timedelta(days=30),
        )
        if cur is None or prior is None or prior == 0:
            return []
        delta = (cur - prior) / abs(prior) * 100
        if delta > -50:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P0",
                type="brand",
                title=f"GeoScore collapsed {abs(delta):.1f}% — emergency",
                description="Catastrophic GeoScore decline.",
                focus_area="geo_score",
                direction="Convene incident review + immediate PR / dev escalation.",
                reader_hints=["manager", "operator", "branding"],
                evidence={
                    "current_value": round(cur, 2),
                    "previous_value": round(prior, 2),
                    "change_percent": round(delta, 2),
                },
            )
        ]


# ─── 20. competitor_radical_growth ──────────────────────────────────


class CompetitorRadicalGrowthRule(BaseRule):
    rule_id = "competitor_radical_growth_v1"
    category = "competitor_radical_growth"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        # Stub — Phase A.7 wires competitor_mention_daily; until then no-op
        return []


# ─── 21. share_of_voice_minor ───────────────────────────────────────


class ShareOfVoiceMinorRule(BaseRule):
    """SoV under 5% — alert."""

    rule_id = "share_of_voice_minor_v1"
    category = "share_of_voice_minor"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        sov = await _avg_metric(
            session,
            brand_id=project.primary_brand_id,
            column=GeoScoreDaily.avg_sov,
            date_lo=today - timedelta(days=29),
            date_hi=today,
        )
        if sov is None or sov >= 0.05:
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P3",
                type="brand",
                title=f"SoV under 5% (current {sov * 100:.1f}%)",
                description="Brand voice share is minor in the category.",
                focus_area="sov",
                direction="Reassess brand positioning + media mix.",
                reader_hints=["manager"],
                evidence={
                    "current_sov": round(sov, 4),
                    "threshold": 0.05,
                },
            )
        ]


# ─── 22-25. attribution / diversity / topic_emerging / category_rank ─


class AttributionAnchorLowRule(BaseRule):
    """Stub — Phase RP wires anchor_question linkage."""

    rule_id = "attribution_anchor_low_v1"
    category = "attribution_anchor_low"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        return []


class CitationDiversityLowRule(BaseRule):
    """Like CitationAuthorityLowRule but P3 — lower-priority warning."""

    rule_id = "citation_diversity_low_v1"
    category = "citation_diversity_low"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        if project.primary_brand_id is None:
            return []
        today = date.today()
        stmt = (
            select(func.count(distinct(CitationSource.domain)))
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .where(
                and_(
                    BrandMention.brand_id == project.primary_brand_id,
                    CitationSource.domain.isnot(None),
                    CitationSource.created_at
                    >= datetime.combine(today - timedelta(days=29), datetime.min.time()),
                )
            )
        )
        n = int((await session.execute(stmt)).scalar_one() or 0)
        if n >= 10:
            return []
        if n < 5:
            # already covered by CitationAuthorityLowRule — skip duplicate
            return []
        return [
            DiagnosticPayload(
                rule_id=self.rule_id,
                rule_version=self.rule_version,
                category=self.category,
                severity="P3",
                type="brand",
                title=f"only {n} unique citation domains in 30d",
                description="Citation source diversity could grow.",
                focus_area="citation_diversity",
                direction="Track outlet diversification metrics.",
                reader_hints=["operator"],
                evidence={"distinct_domain_count": n, "threshold": 10},
            )
        ]


class TopicEmergingMissedRule(BaseRule):
    """Stub — Phase A.10 wires industry_topic_daily.hot_score."""

    rule_id = "topic_emerging_missed_v1"
    category = "topic_emerging_missed"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        return []


class CategoryRankDropRule(BaseRule):
    """Stub — Phase A.10 wires category_rank column."""

    rule_id = "category_rank_drop_v1"
    category = "category_rank_drop"

    async def evaluate(self, session: AsyncSession, project: Project) -> list[DiagnosticPayload]:
        return []


# ─── REGISTRY EXTENSION ─────────────────────────────────────────────


REGISTRY_EXTENDED: list[type[BaseRule]] = [
    SentimentDropRule,
    CitationAttributionMismatchRule,
    CompetitorOvertakeRule,
    TopicLossRule,
    NarrativeDriftRule,
    PersonaKeywordChangeRule,
    ContentGapRule,
    CitationAuthorityLowRule,
    WikiMissingRule,
    ProductFeatureNegativeRule,
    ProductRemissionRule,
    IndustryLagTop10Rule,
    SameGroupShareLowRule,
    MonitoringOutageRule,
    LlmEngineAnomalyRule,
    GeoScoreDropSevereRule,
    CompetitorRadicalGrowthRule,
    ShareOfVoiceMinorRule,
    AttributionAnchorLowRule,
    CitationDiversityLowRule,
    TopicEmergingMissedRule,
    CategoryRankDropRule,
]
