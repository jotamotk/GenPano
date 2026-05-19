"""DTOs for /v1/projects/:id/diagnostics (Phase D.7)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PlaceholderResponse(BaseModel):
    """Legacy placeholder kept for backward compatibility."""

    state: str = "phase_0_stub"
    message: str = "Diagnostics endpoint stub — superseded by Phase D.7 endpoints"


class DiagnosticOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    brand_id: int | None
    product_id: int | None
    industry_id: int | None
    category: str
    severity: str
    type: str
    title: str
    description: str | None
    focus_area: str | None
    direction: str | None
    reader_hints: list[str]
    evidence: dict[str, Any]
    causal_chain: dict[str, Any] | None
    industry_benchmark: dict[str, Any] | None
    anchor_questions: dict[str, Any] | None
    if_untreated: str | None
    rule_id: str
    rule_version: str | None
    status: str
    detected_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class DiagnosticListOut(BaseModel):
    items: list[DiagnosticOut]
    total: int
    state: str = "no_diagnostics"
    state_reason: str = "no_open_p0_p1_diagnostics"
    state_detail: str | None = None
    open_p0_p1_count: int = 0
    analytics_state: str | None = None
    analytics_state_reason: str | None = None
    formula_status: str | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    evidence_counts: dict[str, int] = Field(default_factory=dict)
    analytics_signals: dict[str, Any] = Field(default_factory=dict)


class DiagnosticPatchIn(BaseModel):
    status: Literal["acknowledged", "ignored", "resolved", "open"]


class DiagnosticRefreshOut(BaseModel):
    inserted: int
    project_id: str


class DiagnosticCountsOut(BaseModel):
    total: int
    by_status: dict[str, int]
    by_severity_open: dict[str, int]
    state: str = "no_diagnostics"
    state_reason: str = "no_open_p0_p1_diagnostics"
    state_detail: str | None = None
    open_p0_p1_count: int = 0
    analytics_state: str | None = None
    analytics_state_reason: str | None = None
    formula_status: str | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    evidence_counts: dict[str, int] = Field(default_factory=dict)
    analytics_signals: dict[str, Any] = Field(default_factory=dict)
