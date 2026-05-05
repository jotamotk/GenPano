"""DTOs for /v1/projects/:id/exports + /v1/brands/submissions + simulator (Phase E)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ExportType = Literal[
    "mention_list",
    "sentiment_list",
    "citation_list",
    "competitor_matrix",
    "topic_coverage",
    "industry_ranking",
    "products_list",
    "report_data",
]


class ExportJobIn(BaseModel):
    export_type: ExportType
    scope: dict[str, Any] | None = None


class ExportJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    user_id: str
    export_type: str
    scope: dict[str, Any] | None
    status: str
    output_url: str | None
    row_count: int | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class BrandSubmissionIn(BaseModel):
    proposed_name: str = Field(..., min_length=1, max_length=256)
    proposed_industry_id: int | None = None
    proposed_aliases: list[str] | None = None
    proposed_official_domains: list[str] | None = None
    notes: str | None = None
    source_url: str | None = None


class BrandSubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    proposed_name: str
    proposed_industry_id: int | None
    proposed_aliases: list[str] | None
    proposed_official_domains: list[str] | None
    notes: str | None
    source_url: str | None
    status: str
    rejection_reason: str | None
    resulting_brand_id: int | None
    created_at: datetime


class SimulatorIn(BaseModel):
    """Authority boost simulation input.

    Per PRD §4.7.6 + ADR — `delta_by_tier` keys are tier numbers as strings.
    """

    brand_id: int
    delta_by_tier: dict[str, int] = Field(
        ..., description="{'1': delta_count, '2': delta_count, ...}"
    )
    confidence_override: float | None = Field(None, ge=0.5, le=1.0)


class SimulatorBreakdown(BaseModel):
    visibility: float = 0.0
    sov: float = 0.0
    sentiment: float = 0.0
    citation_authority: float = 0.0


class SimulatorOut(BaseModel):
    current_pano_a: float
    simulated_pano_a: float
    delta: float
    delta_breakdown: SimulatorBreakdown
    base_price_equivalent_cny: float
    confidence: float
