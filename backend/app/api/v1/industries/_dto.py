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


class IndustryOverviewOut(BaseModel):
    industry_id: int
    industry_name: str | None
    period: dict[str, str]
    kpi_cards: list[IndustryKpiCard]
    top_brands: list[TopBrandRow]
    events_30d: list[IndustryEvent]
    state: str = "ok"


class IndustryRankingRow(BaseModel):
    rank: int
    brand_id: int
    brand_name: str | None
    avg_geo_score: float | None
    avg_mention_rate: float | None
    avg_sov: float | None
    avg_sentiment: float | None


class IndustryRankingOut(BaseModel):
    industry_id: int
    period: dict[str, str]
    items: list[IndustryRankingRow]
    total: int
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
