"""DTOs for Brand metrics / topics / sentiment / citations (Phase 2.2)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.projects._analytics_contract import (
    DataFreshness,
    FormulaDiagnostics,
    IdentityDiagnostics,
    ProjectScope,
    ValueRange,
)


# ── /metrics ──────────────────────────────────────────────────────
class MetricSeriesPoint(BaseModel):
    date: date
    value: float


class MetricSeries(BaseModel):
    metric: str  # 'mention_rate' | 'sov' | 'rank' | 'sentiment' | 'citation'
    points: list[MetricSeriesPoint]
    unit: str | None = None
    value_scale: str | None = None
    value_range: ValueRange | None = None
    denominator_label: str | None = None
    numerator_label: str | None = None
    source: str | None = None
    formula_status: str | None = None
    state: str = "ok"
    state_reason: str = "data_available"
    evidence_count: int = 0


class MetricsOut(BaseModel):
    project_id: str
    brand_id: int | None
    period: dict[str, str]
    engines: list[str] | None
    series: list[MetricSeries]
    state: str = "ok"
    state_reason: str = "data_available"
    state_detail: str | None = None
    project_scope: ProjectScope | None = None
    brand_aliases: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    missing_reasons: list[str] = Field(default_factory=list)
    invalid_fields: list[str] = Field(default_factory=list)
    evidence_counts: dict[str, int] = Field(default_factory=dict)
    identity_diagnostics: IdentityDiagnostics = Field(default_factory=IdentityDiagnostics)
    formula_diagnostics: FormulaDiagnostics = Field(default_factory=FormulaDiagnostics)
    request_id: str | None = None
    data_freshness: DataFreshness = Field(default_factory=DataFreshness)


# ── /topics ───────────────────────────────────────────────────────
class TopicRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    topic_id: int
    topic_name: str
    state: str = "tracked"  # 'tracked' | 'ignored' | 'unpinned'
    mention_count: int = 0
    avg_sentiment: float | None = None
    avg_position_rank: float | None = None
    last_seen_at: str | None = None


class TopicsOut(BaseModel):
    project_id: str
    items: list[TopicRow]
    total: int
    state: str = "ok"
    state_reason: str = "data_available"
    evidence_count: int = 0


# ── /sentiment ────────────────────────────────────────────────────
class SentimentDistribution(BaseModel):
    positive_count: int
    neutral_count: int
    negative_count: int
    positive_pct: float
    neutral_pct: float
    negative_pct: float
    avg_sentiment_score: float


class SentimentKeywordRow(BaseModel):
    keyword: str
    polarity: str  # 'positive' | 'negative'
    count: int
    avg_strength: float | None = None


class SentimentDriverRow(BaseModel):
    driver_text: str
    polarity: str
    category: str | None = None
    count: int
    avg_strength: float | None = None


class SentimentTrendPoint(BaseModel):
    date: date
    positive_pct: float
    negative_pct: float
    avg_score: float


class SentimentOut(BaseModel):
    project_id: str
    brand_id: int | None
    period: dict[str, str]
    distribution: SentimentDistribution
    trend_30d: list[SentimentTrendPoint]
    top_keywords: list[SentimentKeywordRow]
    top_drivers: list[SentimentDriverRow]
    state: str = "ok"
    state_reason: str = "data_available"
    evidence_count: int = 0


# ── /citations ────────────────────────────────────────────────────
class CitationRow(BaseModel):
    citation_id: int
    response_id: int
    url: str
    domain: str | None
    title: str | None
    source_type: str | None
    occurred_at: str | None  # ISO


class CitationDomainRow(BaseModel):
    domain: str
    count: int
    tier: int | None = None


class CitationsOut(BaseModel):
    project_id: str
    brand_id: int | None
    period: dict[str, str]
    items: list[CitationRow]
    next_cursor: str | None = None
    total: int
    by_domain_top: list[CitationDomainRow]
    state: str = "ok"
    state_reason: str = "data_available"
    evidence_count: int = 0
