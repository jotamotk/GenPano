"""DTOs for the chart-data endpoints (Phase 5 — Chart Wiring).

Each new endpoint here serves a single FE chart on the brand-mode pages.
Shapes mirror the recharts/donut props the FE already consumes (see
`frontend/src/components/charts/`).
"""

from __future__ import annotations

from pydantic import BaseModel


# ── /metrics/by-engine ──────────────────────────────────────────────
class EngineMetricRow(BaseModel):
    engine: str
    mention_rate: float | None = None
    sov: float | None = None
    citation_rate: float | None = None
    sentiment: float | None = None


class EngineMetricsOut(BaseModel):
    project_id: str
    period: dict[str, str]
    items: list[EngineMetricRow]
    state: str = "ok"


# ── /position-distribution ──────────────────────────────────────────
class PositionBucketRow(BaseModel):
    bucket: str  # "Top1" | "Top3" | "Top5" | "Top10" | "11+" | "Unmentioned"
    count: int
    pct: float


class PositionDistributionOut(BaseModel):
    project_id: str
    period: dict[str, str]
    items: list[PositionBucketRow]
    total_mentions: int
    state: str = "ok"


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


class TopicHeatmapOut(BaseModel):
    project_id: str
    metric: str  # "mention_rate" | "sentiment"
    rows: list[HeatmapRow]
    state: str = "ok"


# ── /sentiment/by-engine ────────────────────────────────────────────
class SentimentByEngineRow(BaseModel):
    engine: str
    positive: int = 0
    neutral: int = 0
    negative: int = 0


class SentimentByEngineOut(BaseModel):
    project_id: str
    period: dict[str, str]
    items: list[SentimentByEngineRow]
    state: str = "ok"


# ── /sentiment/trend-by-engine ──────────────────────────────────────
class SentimentTrendByEngineRow(BaseModel):
    date: str  # ISO YYYY-MM-DD
    # Per-engine score (0..1 positive ratio); flexible dict so FE doesn't
    # have to know engine list ahead of time.
    by_engine: dict[str, float | None]


class SentimentTrendByEngineOut(BaseModel):
    project_id: str
    period: dict[str, str]
    engines: list[str]
    items: list[SentimentTrendByEngineRow]
    state: str = "ok"


# ── /sentiment/topic-attribution ────────────────────────────────────
class TopicAttributionRow(BaseModel):
    topic_id: int
    topic_name: str
    negative_count: int
    negative_ratio: float  # 0..1
    sample_snippet: str | None = None


class TopicAttributionOut(BaseModel):
    project_id: str
    items: list[TopicAttributionRow]
    state: str = "ok"


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


class MentionSamplesOut(BaseModel):
    project_id: str
    items: list[MentionSampleRow]
    state: str = "ok"


# ── /citations/authority-trend ──────────────────────────────────────
class AuthorityTrendPoint(BaseModel):
    date: str
    tier1_pct: float = 0.0
    tier2_pct: float = 0.0
    tier3_pct: float = 0.0
    tier4_pct: float = 0.0
    untiered_pct: float = 0.0


class AuthorityTrendOut(BaseModel):
    project_id: str
    period: dict[str, str]
    points: list[AuthorityTrendPoint]
    state: str = "ok"


# ── /citations/composition ──────────────────────────────────────────
class CitationCompositionRow(BaseModel):
    label: str  # "Tier 1 (官方)" | …
    tier: int | None
    count: int
    pct: float


class CitationCompositionOut(BaseModel):
    project_id: str
    period: dict[str, str]
    segments: list[CitationCompositionRow]
    total: int
    state: str = "ok"


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


class ContentGapOut(BaseModel):
    project_id: str
    topics: list[ContentGapTopicRow]
    page_type_distribution: list[ContentGapPageTypeRow]
    state: str = "ok"


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


class PrTargetsOut(BaseModel):
    project_id: str
    targets: list[PrTargetRow]
    kol_scorecards: list[KolScorecard]
    tier2_matrix: Tier2MatrixOut
    state: str = "ok"


# ── /citations/simulator-baseline ───────────────────────────────────
class SimulatorTierWeight(BaseModel):
    tier: int
    weight: float
    confidence: float
    current_count: int


class SimulatorBaselineOut(BaseModel):
    project_id: str
    current_pano: float
    industry_median: float | None
    industry_top3_avg: float | None
    tiers: list[SimulatorTierWeight]
    presets: list[dict[str, object]]
    state: str = "ok"


# ── /competitors/authority-radar ────────────────────────────────────
class AuthorityRadarRow(BaseModel):
    tier: str  # "Tier1" | "Tier2" | "Tier3" | "Tier4" | "总覆盖"
    me: float
    industry_median: float
    top_competitor: float
    top_competitor_id: int | None = None
    top_competitor_name: str | None = None


class AuthorityRadarOut(BaseModel):
    project_id: str
    rows: list[AuthorityRadarRow]
    state: str = "ok"


# ── /group-shared-domains ───────────────────────────────────────────
class GroupSharedDomainEntry(BaseModel):
    domain: str
    tier: int | None
    brand_count: int
    total_mentions: int
    sister_brand_ids: list[int] = []
    sister_brand_names: list[str] = []


class GroupSharedDomainsOut(BaseModel):
    project_id: str
    group_id: int | None
    group_name: str | None
    shared_ratio: float | None  # of total citations
    items: list[GroupSharedDomainEntry]
    state: str = "ok"


# ── /products/relations ─────────────────────────────────────────────
class ProductRelationRow(BaseModel):
    product_a_id: int
    product_a_name: str | None
    product_b_id: int
    product_b_name: str | None
    type: str  # COMPETES_WITH | SUBSTITUTES | PAIRS_WITH | UPGRADES_TO | BUDGET_ALT_OF
    confidence: float | None


class ProductRelationsOut(BaseModel):
    project_id: str
    items: list[ProductRelationRow]
    state: str = "ok"
