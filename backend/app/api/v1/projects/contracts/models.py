"""Pydantic models for the analytics contract layer.

Phase 1 of splitting `_analytics_contract.py` (Epic #885, design #888).
Pure model definitions; no logic, no DB, no constants. The string default
on `AnalyticsContractContext.formula_status` matches the
`FORMULA_NO_EVIDENCE_STATUS` constant that still lives in
`_analytics_contract.py`; subsequent phases will centralize the constants.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class ValueRange(BaseModel):
    min: float
    max: float


class DataFreshness(BaseModel):
    generated_at: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )


class ProjectScope(BaseModel):
    exists: bool = True
    project_id: str
    primary_brand_id: int | None
    requested_brand_id: int | None
    competitor_brand_ids: list[int] = Field(default_factory=list)
    missing_reason: str | None = None


class MetricDefinition(BaseModel):
    metric_key: str
    unit: str
    value_scale: str
    value_range: ValueRange
    denominator_label: str | None = None
    numerator_label: str | None = None
    source: str | None = None
    formula_status: str | None = None


class MetricValue(BaseModel):
    value: float | None
    unit: str
    value_scale: str
    value_range: ValueRange
    source: str | None = None
    formula_status: str | None = None


class FormulaDiagnostics(BaseModel):
    status: str = "not_applicable"
    pending_sources: list[str] = Field(default_factory=list)
    details: list[str] = Field(default_factory=list)


class IdentityDiagnostics(BaseModel):
    canonical_brand_id: int | None = None
    normalized_brand_mention_count: int = 0
    brand_mentioned_response_count: int = 0
    response_analysis_count: int = 0
    canonical_alias_repair_count: int = 0
    raw_text_owner_brand_ids: list[int] = Field(default_factory=list)
    repair_missing_sources: list[str] = Field(default_factory=list)


class AnalyticsContractContext(BaseModel):
    project_scope: ProjectScope
    brand_aliases: list[str] = Field(default_factory=list)
    state: str
    state_reason: str
    state_detail: str | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    missing_reasons: list[str] = Field(default_factory=list)
    invalid_fields: list[str] = Field(default_factory=list)
    evidence_counts: dict[str, int] = Field(default_factory=dict)
    identity_diagnostics: IdentityDiagnostics = Field(default_factory=IdentityDiagnostics)
    formula_diagnostics: FormulaDiagnostics = Field(default_factory=FormulaDiagnostics)
    formula_status: str = "no_evidence"  # FORMULA_NO_EVIDENCE_STATUS
    metric_formula_evidence: dict[str, Any] = Field(default_factory=dict)
    selected_filters: dict[str, Any] = Field(default_factory=dict)
    source_provenance: list[str] = Field(default_factory=list)
    request_id: str | None = None
    data_freshness: DataFreshness = Field(default_factory=DataFreshness)
