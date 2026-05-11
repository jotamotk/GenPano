"""DTOs for Brand products / competitors metrics / diagnostics (Phase 2.3)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.projects._analytics_contract import (
    DataFreshness,
    FormulaDiagnostics,
    IdentityDiagnostics,
    MetricDefinition,
    ProjectScope,
)


# ── /products ─────────────────────────────────────────────────────
class ProductFeatureRow(BaseModel):
    feature_name: str
    feature_sentiment: str | None  # 'positive' | 'neutral' | 'negative'
    mention_count: int
    avg_score: float | None = None


class ProductScenarioRow(BaseModel):
    scenario: str
    mention_count: int


class ProductRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: int
    product_name: str
    brand_id: int | None
    sku: str | None = None
    category: str | None = None
    mention_count: int = 0
    mention_rate: float | None = None  # 0..1 decimal
    avg_position_rank: float | None = None
    avg_geo_score: float | None = None
    avg_sentiment: float | None = None  # 0..1
    sov: float | None = None  # 0..100 percent
    ranking: int | None = None
    win_rate: float | None = None
    trend_30d: float | None = None  # signed delta as decimal (e.g. +0.05 = +5%)
    sparkline: list[float] = []  # 30d daily mention_rate
    top_features: list[ProductFeatureRow] = []
    top_scenarios: list[ProductScenarioRow] = []


class ProductsOut(BaseModel):
    project_id: str
    items: list[ProductRow]
    total: int
    state: str = "ok"
    state_reason: str = "data_available"
    evidence_count: int = 0
    missing_inputs: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    missing_reasons: list[str] = Field(default_factory=list)
    evidence_counts: dict[str, int] = Field(default_factory=dict)
    formula_status: str = "no_evidence"
    formula_diagnostics: FormulaDiagnostics = Field(default_factory=FormulaDiagnostics)
    selected_filters: dict[str, object] = Field(default_factory=dict)
    source_provenance: list[str] = Field(default_factory=list)


# ── /competitors/metrics ──────────────────────────────────────────
class CompetitorBrandRow(BaseModel):
    brand_id: int | None
    brand_key: str | None = None
    brand_name: str | None
    avg_geo_score: float | None
    avg_mention_rate: float | None
    avg_sov: float | None
    avg_sentiment: float | None
    co_mention_count: int = 0
    delta_30d_pct: float | None = None


class CompetitorMetricsOut(BaseModel):
    project_id: str
    primary_brand_id: int | None
    period: dict[str, str]
    primary: CompetitorBrandRow | None
    competitors: list[CompetitorBrandRow]
    state: str = "ok"
    state_reason: str = "data_available"
    state_detail: str | None = None
    project_scope: ProjectScope | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    missing_reasons: list[str] = Field(default_factory=list)
    invalid_fields: list[str] = Field(default_factory=list)
    evidence_counts: dict[str, int] = Field(default_factory=dict)
    identity_diagnostics: IdentityDiagnostics = Field(default_factory=IdentityDiagnostics)
    formula_diagnostics: FormulaDiagnostics = Field(default_factory=FormulaDiagnostics)
    formula_status: str = "no_evidence"
    selected_filters: dict[str, object] = Field(default_factory=dict)
    source_provenance: list[str] = Field(default_factory=list)
    metric_definitions: dict[str, MetricDefinition] = Field(default_factory=dict)
    request_id: str | None = None
    data_freshness: DataFreshness = Field(default_factory=DataFreshness)


# ── /diagnostics ──────────────────────────────────────────────────
class DiagnosticEvidence(BaseModel):
    """Lightweight evidence row mirroring mock DIAGNOSTICS shape (Phase D fills full)."""

    metric: str
    current_value: float | None = None
    previous_value: float | None = None
    change_percent: float | None = None
    affected_engines: list[str] = []
    affected_queries: list[str] = []


class DiagnosticRow(BaseModel):
    """Phase 2.3 stub — returns derived diagnostics from existing tables.

    Phase D will wire the real `diagnostics` table; this endpoint already
    exposes the contract (FE can render today, BE evolves).
    """

    id: str
    category: str
    severity: str  # 'P0' | 'P1' | 'P2' | 'P3'
    type: str  # 'brand' | 'product' | 'industry'
    title: str
    description: str | None = None
    detected_at: str  # ISO
    engine: str | None = None
    focus_area: str | None = None
    direction: str | None = None
    reader_hints: list[str] = []
    evidence: DiagnosticEvidence
    status: str = "open"


class DiagnosticsOut(BaseModel):
    project_id: str
    period: dict[str, str]
    items: list[DiagnosticRow]
    counts_by_severity: dict[str, int]
    state: str = "ok"


class DiagnosticPatchIn(BaseModel):
    """PATCH /v1/projects/:id/diagnostics/:diag_id body."""

    status: str  # 'acknowledged' | 'ignored' | 'resolved'


class DateOverride(BaseModel):
    """Helper for tests / docs only."""

    from_date: date | None = None
    to_date: date | None = None


# ── /competitors/trends (new, Phase 5 sparkline coverage) ─────────
class CompetitorTrendPoint(BaseModel):
    date: str
    value: float | None = None


class CompetitorTrendSeries(BaseModel):
    brand_id: int
    brand_name: str | None
    is_primary: bool = False
    points: list[CompetitorTrendPoint]


class CompetitorTrendsOut(BaseModel):
    project_id: str
    metric: str
    period: dict[str, str]
    series: list[CompetitorTrendSeries]
    state: str = "ok"
    state_reason: str = "data_available"
    state_detail: str | None = None
    project_scope: ProjectScope | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    missing_reasons: list[str] = Field(default_factory=list)
    invalid_fields: list[str] = Field(default_factory=list)
    evidence_counts: dict[str, int] = Field(default_factory=dict)
    identity_diagnostics: IdentityDiagnostics = Field(default_factory=IdentityDiagnostics)
    formula_diagnostics: FormulaDiagnostics = Field(default_factory=FormulaDiagnostics)
    formula_status: str = "no_evidence"
    selected_filters: dict[str, object] = Field(default_factory=dict)
    source_provenance: list[str] = Field(default_factory=list)
    metric_definition: MetricDefinition | None = None
    request_id: str | None = None
    data_freshness: DataFreshness = Field(default_factory=DataFreshness)
