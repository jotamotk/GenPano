"""DTOs for /v1/projects/:id/overview (Phase 2.1 — Pydantic v2)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.projects._analytics_contract import (
    DataFreshness,
    FormulaDiagnostics,
    IdentityDiagnostics,
    MetricValue,
    ProjectScope,
    ValueRange,
)


class KpiCard(BaseModel):
    """One KPI tile on Brand Overview."""

    model_config = ConfigDict(from_attributes=True)

    label_zh: str
    label_en: str
    metric_key: str | None = None
    value: float | int | None
    unit: str | None = None
    value_scale: str | None = None
    value_range: ValueRange | None = None
    denominator_label: str | None = None
    numerator_label: str | None = None
    source: str | None = None
    formula_status: str | None = None
    state: str = "ok"
    state_reason: str = "data_available"
    delta_30d_pct: float | None = None
    direction: str | None = None  # 'up' | 'down' | 'flat'


class TrendPoint(BaseModel):
    date: date
    value: float


class TopPromptRow(BaseModel):
    """Top-mentioning prompt over the period."""

    prompt_id: int | None = None
    prompt_text: str
    mention_count: int
    avg_position_rank: float | None = None
    avg_sentiment_score: float | None = None


class GroupSharedDomainRow(BaseModel):
    domain: str
    brand_count: int
    total_mentions: int


class BrandOverviewOut(BaseModel):
    """Composite response for `GET /v1/projects/:id/overview`.

    Mirrors the FE `DashboardPage` mock shape so the FE can be flipped to
    real data with minimal changes.
    """

    project_id: str
    brand_id: int | None
    brand_name: str | None
    industry_id: int | None
    period: dict[str, str]  # {"from": "...", "to": "..."}

    kpi_cards: list[KpiCard]
    geo_score_30d: list[TrendPoint]
    sov_30d: list[TrendPoint]
    sentiment_30d: list[TrendPoint]
    top_prompts: list[TopPromptRow]
    same_group_shared_domains: list[GroupSharedDomainRow]
    state: str = "ok"  # 'ok' | 'empty' | 'partial'
    state_reason: str = "data_available"
    state_detail: str | None = None
    project_scope: ProjectScope | None = None
    brand_aliases: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    missing_reasons: list[str] = Field(default_factory=list)
    invalid_fields: list[str] = Field(default_factory=list)
    evidence_counts: dict[str, int] = Field(default_factory=dict)
    identity_diagnostics: IdentityDiagnostics = Field(default_factory=IdentityDiagnostics)
    formula_diagnostics: FormulaDiagnostics = Field(default_factory=FormulaDiagnostics)
    formula_status: str = "no_evidence"
    metric_formula_evidence: dict[str, object] = Field(default_factory=dict)
    selected_filters: dict[str, object] = Field(default_factory=dict)
    source_provenance: list[str] = Field(default_factory=list)
    score_components: dict[str, MetricValue] = Field(default_factory=dict)
    request_id: str | None = None
    data_freshness: DataFreshness = Field(default_factory=DataFreshness)
