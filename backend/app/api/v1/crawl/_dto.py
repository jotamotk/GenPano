"""DTOs for /v1/projects/:id/crawl-requests (Phase 4 — Pydantic v2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CrawlRequestIn(BaseModel):
    """POST body."""

    brand_id: int | None = None
    scope: dict[str, Any] | None = None  # {engines: [...], prompts: [...]}


class CrawlRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    brand_id: int | None
    scope: dict[str, Any] | None
    status: str
    attempts: int
    result_summary: dict[str, Any] | None
    created_by: str | None
    created_at: datetime
    finished_at: datetime | None
