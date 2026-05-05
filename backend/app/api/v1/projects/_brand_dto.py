"""DTOs for Brand products / competitors metrics / diagnostics (Phase 2.3)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


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
    avg_position_rank: float | None = None
    avg_geo_score: float | None = None
    win_rate: float | None = None
    top_features: list[ProductFeatureRow] = []
    top_scenarios: list[ProductScenarioRow] = []


class ProductsOut(BaseModel):
    project_id: str
    items: list[ProductRow]
    total: int
    state: str = "ok"


# ── /competitors/metrics ──────────────────────────────────────────
class CompetitorBrandRow(BaseModel):
    brand_id: int
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
