"""DTOs for the chart-data endpoints (Phase 5 — Chart Wiring).

Each new endpoint here serves a single FE chart on the brand-mode pages.
Shapes mirror the recharts/donut props the FE already consumes (see
`frontend/src/components/charts/`).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChartState(BaseModel):
    state: str = "ok"
    state_reason: str = "data_available"
    evidence_count: int = 0
    evidence_counts: dict[str, int] = Field(default_factory=dict)


# ── /metrics/by-engine ──────────────────────────────────────────────
class EngineMetricRow(BaseModel):
    engine: str
    mention_rate: float | None = None
    sov: float | None = None
    citation_rate: float | None = None
    sentiment: float | None = None


class EngineMetricsOut(ChartState):
    project_id: str
    period: dict[str, str]
    items: list[EngineMetricRow]


# ── /position-distribution ──────────────────────────────────────────
class PositionBucketRow(BaseModel):
    bucket: str  # "Top1" | "Top3" | "Top5" | "Top10" | "11+" | "Unmentioned"
    count: int
    pct: float


class PositionDistributionOut(ChartState):
    project_id: str
    period: dict[str, str]
    items: list[PositionBucketRow]
    total_mentions: int


# ── /topic-heatmap ──────────────────────────────────────────────────
class HeatmapCell(BaseModel):
    topic_id: int
    topic_label: str
    value: float | None  # mention_rate (0..1) or sentiment (-1..1)
    sample: int  # supporting sample size (mention_count)


class HeatmapRow(BaseModel):
    brand_id: int
    brand_name: str | None
    values: list[HeatmapCell]


class TopicHeatmapOut(ChartState):
    project_id: str
    metric: str  # "mention_rate" | "sentiment"
    rows: list[HeatmapRow]


# ── /sentiment/by-engine ────────────────────────────────────────────
class SentimentByEngineRow(BaseModel):
    engine: str
    positive: int = 0
    neutral: int = 0
    negative: int = 0


class SentimentByEngineOut(ChartState):
    project_id: str
    period: dict[str, str]
    items: list[SentimentByEngineRow]


# ── /sentiment/trend-by-engine ──────────────────────────────────────
class SentimentTrendByEngineRow(BaseModel):
    date: str  # ISO YYYY-MM-DD
    # Per-engine score (0..1 positive ratio); flexible dict so FE doesn't
    # have to know engine list ahead of time.
    by_engine: dict[str, float | None]


class SentimentTrendByEngineOut(ChartState):
    project_id: str
    period: dict[str, str]
    engines: list[str]
    items: list[SentimentTrendByEngineRow]


# ── /sentiment/topic-attribution ────────────────────────────────────
class TopicAttributionRow(BaseModel):
    topic_id: int
    topic_name: str
    negative_count: int
    negative_ratio: float  # 0..1
    sample_snippet: str | None = None


class TopicAttributionOut(ChartState):
    project_id: str
    items: list[TopicAttributionRow]


# ── /mention-samples ────────────────────────────────────────────────
class MentionSampleRow(BaseModel):
    mention_id: int
    response_id: int
    label: str  # "正面" | "负面" | "中性"
    polarity: str  # "positive" | "negative" | "neutral"
    summary: str | None = None
    snippet: str | None = None
    engine: str | None = None
    topic: str | None = None
    occurred_at: str | None = None


class MentionSamplesOut(ChartState):
    project_id: str
    items: list[MentionSampleRow]


# ── /citations/authority-trend ──────────────────────────────────────
class AuthorityTrendPoint(BaseModel):
    date: str
    tier1_pct: float = 0.0
    tier2_pct: float = 0.0
    tier3_pct: float = 0.0
    tier4_pct: float = 0.0
    untiered_pct: float = 0.0


class AuthorityTrendOut(ChartState):
    project_id: str
    period: dict[str, str]
    points: list[AuthorityTrendPoint]


# ── /citations/composition ──────────────────────────────────────────
class CitationCompositionRow(BaseModel):
    label: str  # "Tier 1 (官方)" | …
    tier: int | None
    count: int
    pct: float


class CitationCompositionOut(ChartState):
    project_id: str
    period: dict[str, str]
    segments: list[CitationCompositionRow]
    total: int


# ── /citations/content-gap ──────────────────────────────────────────
class ContentGapTopicRow(BaseModel):
    topic_id: int | None
    topic_name: str
    mention_rate: float
    citation_rate: float
    gap_score: float  # mention_rate - citation_rate
    suggestion: str | None = None


class ContentGapPageTypeRow(BaseModel):
    page_type: str
    count: int
    pct: float


class ContentGapOut(ChartState):
    project_id: str
    topics: list[ContentGapTopicRow]
    page_type_distribution: list[ContentGapPageTypeRow]


# ── /citations/pr-targets ───────────────────────────────────────────
class PrTargetRow(BaseModel):
    domain: str
    tier: int | None
    we_count: int
    competitors_count: int
    gap: int  # competitors - we
    suggestion: str | None = None


class KolScorecard(BaseModel):
    name: str
    platform: str | None = None
    audience_score: float | None = None  # 0..100 (heuristic)
    quality_score: float | None = None
    risk: str | None = None  # "low" | "med" | "high"
    notes: str | None = None


class Tier2MatrixRow(BaseModel):
    brand_id: int
    label: str
    counts: list[int]


class Tier2MatrixOut(BaseModel):
    domains: list[str]
    brands: list[Tier2MatrixRow]


class PrTargetsOut(ChartState):
    project_id: str
    targets: list[PrTargetRow]
    kol_scorecards: list[KolScorecard]
    tier2_matrix: Tier2MatrixOut


# ── /citations/simulator-baseline ───────────────────────────────────
class SimulatorTierWeight(BaseModel):
    tier: int
    weight: float
    confidence: float
    current_count: int


class SimulatorBaselineOut(ChartState):
    project_id: str
    current_pano: float
    industry_median: float | None
    industry_top3_avg: float | None
    tiers: list[SimulatorTierWeight]
    presets: list[dict[str, object]]


# ── /competitors/authority-radar ────────────────────────────────────
class AuthorityRadarRow(BaseModel):
    tier: str  # "Tier1" | "Tier2" | "Tier3" | "Tier4" | "总覆盖"
    me: float
    industry_median: float
    top_competitor: float
    top_competitor_id: int | None = None
    top_competitor_name: str | None = None


class AuthorityRadarOut(ChartState):
    project_id: str
    rows: list[AuthorityRadarRow]


# ── /group-shared-domains ───────────────────────────────────────────
class GroupSharedDomainEntry(BaseModel):
    domain: str
    tier: int | None
    brand_count: int
    total_mentions: int
    sister_brand_ids: list[int] = []
    sister_brand_names: list[str] = []


class GroupSharedDomainsOut(ChartState):
    project_id: str
    group_id: int | None
    group_name: str | None
    shared_ratio: float | None  # of total citations
    items: list[GroupSharedDomainEntry]


# ── /products/relations ─────────────────────────────────────────────
class ProductRelationRow(BaseModel):
    product_a_id: int
    product_a_name: str | None
    product_b_id: int
    product_b_name: str | None
    type: str  # COMPETES_WITH | SUBSTITUTES | PAIRS_WITH | UPGRADES_TO | BUDGET_ALT_OF
    confidence: float | None


class ProductRelationsOut(ChartState):
    project_id: str
    items: list[ProductRelationRow]
