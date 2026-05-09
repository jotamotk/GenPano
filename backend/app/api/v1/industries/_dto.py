"""DTOs for /v1/industries (Phase 3 — Pydantic v2)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class IndustryRow(BaseModel):
    industry_id: int
    name: str
    brand_count: int = 0


class IndustriesListOut(BaseModel):
    items: list[IndustryRow]
    total: int


class IndustryKpiCard(BaseModel):
    label_zh: str
    label_en: str
    value: float | int
    unit: str | None = None
    delta_30d_pct: float | None = None


class TopBrandRow(BaseModel):
    brand_id: int
    brand_name: str | None = None
    avg_geo_score: float | None
    rank: int


class IndustryEvent(BaseModel):
    date: date
    event_type: str
    description: str
    brand_id: int | None = None


class IndustryHeroCounts(BaseModel):
    brand_count: int = 0
    topic_count: int = 0
    category_count: int = 0
    response_count: int = 0


class IndustryOverviewOut(BaseModel):
    industry_id: int
    industry_name: str | None
    period: dict[str, str]
    kpi_cards: list[IndustryKpiCard]
    top_brands: list[TopBrandRow]
    events_30d: list[IndustryEvent]
    hero_counts: IndustryHeroCounts | None = None
    state: str = "ok"


class IndustryRankingRow(BaseModel):
    rank: int
    brand_id: int
    brand_name: str | None
    avg_geo_score: float | None
    avg_mention_rate: float | None
    avg_sov: float | None
    avg_sentiment: float | None
    avg_citation_rate: float | None = None
    sparkline: list[float] = []  # 30d avg_geo_score per day


class IndustryRankingOut(BaseModel):
    industry_id: int
    period: dict[str, str]
    items: list[IndustryRankingRow]
    total: int
    my_rank: int | None = None  # rank of primary_brand_id when supplied
    state: str = "ok"


class IndustryTopicRow(BaseModel):
    topic_id: int | None
    topic_name: str
    mention_count: int
    unique_brand_count: int = 0
    hot_score: float | None = None


class IndustryTopicsOut(BaseModel):
    industry_id: int
    period: dict[str, str]
    items: list[IndustryTopicRow]
    total: int
    state: str = "ok"


class KGNode(BaseModel):
    id: str
    type: str
    name: str
    metadata: dict[str, object] | None = None


class KGEdge(BaseModel):
    source: str
    target: str
    type: str
    weight: float | None = None


class IndustryKgOut(BaseModel):
    industry_id: int
    focus: str
    depth: int
    nodes: list[KGNode]
    edges: list[KGEdge]
    state: str = "ok"


# ── /avg-geo-score (Phase 5 sparkline coverage) ────────────────────
class IndustryAvgGeoPoint(BaseModel):
    date: str
    avg_geo_score: float | None = None
    industry_median: float | None = None
    top10_avg: float | None = None
    total_brands: int | None = None


class IndustryAvgGeoOut(BaseModel):
    industry_id: int
    industry_name: str | None
    period: dict[str, str]
    points: list[IndustryAvgGeoPoint]
    summary: dict[str, float | None] = {}
    state: str = "ok"


# ── /industries/:id/distribution (5-KPI IQR boxplots) ───────────────
class IndustryDistributionStats(BaseModel):
    metric: str  # "mention_rate" | "sov" | "sentiment" | "citation" | "rank"
    values: list[float]
    p25: float | None = None
    p50: float | None = None
    p75: float | None = None
    min: float | None = None
    max: float | None = None
    n: int = 0


class IndustryDistributionOut(BaseModel):
    industry_id: int
    industry_name: str | None
    period: dict[str, str]
    stats: list[IndustryDistributionStats]
    state: str = "ok"


# ── /industries/:id/movers ──────────────────────────────────────────
class IndustryMoverRow(BaseModel):
    brand_id: int
    brand_name: str | None
    delta_pct: float
    current_pano: float | None
    sparkline: list[float] = []
    driver: str | None = None  # "mention_rate" | "sov" | "sentiment" | …


class IndustryMoversOut(BaseModel):
    industry_id: int
    period: dict[str, str]
    gainers: list[IndustryMoverRow]
    losers: list[IndustryMoverRow]
    state: str = "ok"


# ── /industries/:id/groups ──────────────────────────────────────────
class IndustryGroupRow(BaseModel):
    group_id: int
    group_name: str
    parent_company: str | None = None
    member_brand_ids: list[int]
    member_brand_names: list[str]
    aggregate_geo_score: float | None
    aggregate_sov: float | None


class IndustryGroupsOut(BaseModel):
    industry_id: int
    items: list[IndustryGroupRow]
    state: str = "ok"


# ── /industries/:id/top-domains ─────────────────────────────────────
class IndustryTopDomainRow(BaseModel):
    domain: str
    tier: int | None
    total_citations: int
    top_brand_id: int | None = None
    top_brand_name: str | None = None
    top_brand_share: float | None = None


class IndustryTopDomainsOut(BaseModel):
    industry_id: int
    period: dict[str, str]
    items: list[IndustryTopDomainRow]
    state: str = "ok"


# ── /industries/:id/segments ────────────────────────────────────────
class IndustrySegmentRow(BaseModel):
    segment: str  # "luxury_intl" | "mass_premium" | "niche_emerging"
    label_zh: str
    items: list[IndustryRankingRow]


class IndustrySegmentsOut(BaseModel):
    industry_id: int
    items: list[IndustrySegmentRow]
    state: str = "ok"


# ── /industries/:id/ranking-by-engine ───────────────────────────────
class IndustryRankingByEngineCell(BaseModel):
    engine: str
    rank: int | None
    avg_geo_score: float | None


class IndustryRankingByEngineRow(BaseModel):
    brand_id: int
    brand_name: str | None
    overall_rank: int
    cells: list[IndustryRankingByEngineCell]
    delta_max: float | None = None  # max engine delta_geo


class IndustryRankingByEngineOut(BaseModel):
    industry_id: int
    period: dict[str, str]
    engines: list[str]
    items: list[IndustryRankingByEngineRow]
    state: str = "ok"


# ── /industries/:id/topic-intent-matrix ─────────────────────────────
class TopicIntentCell(BaseModel):
    intent: str
    count: int
    pct: float


class TopicIntentRow(BaseModel):
    topic_id: int
    topic_name: str
    total_count: int
    cells: list[TopicIntentCell]


class TopicIntentMatrixOut(BaseModel):
    industry_id: int
    intents: list[str]
    rows: list[TopicIntentRow]
    state: str = "ok"


# ── /industries/:id/topics/:topic_id  Topic Detail ──────────────────
class IndustryTopicDetailOut(BaseModel):
    industry_id: int
    topic_id: int
    topic_name: str
    mention_count: int
    unique_brand_count: int
    avg_sentiment: float | None
    top_brands: list[TopBrandRow]
    sparkline: list[float] = []
    intents: list[TopicIntentCell] = []
    state: str = "ok"


class IndustryTopicsExtendedOut(IndustryTopicsOut):
    """Adds per-topic emerging/declining classification + avg_sentiment."""

    emerging: list[IndustryTopicRow] = []
    declining: list[IndustryTopicRow] = []
    avg_sentiment: float | None = None
