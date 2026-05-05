"""DTOs for /v1/leads (Phase 4 — Pydantic v2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LeadIn(BaseModel):
    """POST /v1/leads body. Multi-source: diagnostics / simulator / cta_modal /
    brand_submission / lead_diagnostic."""

    source: str = Field(..., min_length=1, max_length=64)
    project_id: str | None = None
    context: dict[str, Any] | None = None


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str | None
    source: str
    project_id: str | None
    context: dict[str, Any] | None
    status: str
    created_at: datetime
