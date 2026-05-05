"""DTOs for /v1/projects (Phase 1 — Pydantic v2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CompetitorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    brand_id: int
    pinned_at: datetime


class ProjectIn(BaseModel):
    """POST /v1/projects body."""

    name: str = Field(..., min_length=1, max_length=120)
    industry_id: int | None = None
    primary_brand_id: int | None = None
    preferred_engines: list[str] | None = None
    competitor_brand_ids: list[int] | None = Field(None, max_length=10)


class ProjectPatch(BaseModel):
    """PATCH /v1/projects/:id body — all fields optional."""

    name: str | None = Field(None, min_length=1, max_length=120)
    industry_id: int | None = None
    primary_brand_id: int | None = None
    is_active: bool | None = None
    preferred_engines: list[str] | None = None
    default_profile_group_id: str | None = None
    preferences: dict[str, Any] | None = None


class ProjectOut(BaseModel):
    """GET /v1/projects[/:id] response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    org_id: str | None
    name: str
    industry_id: int | None
    primary_brand_id: int | None
    is_active: bool
    preferred_engines: list[str] | None
    default_profile_group_id: str | None
    preferences: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    competitors: list[CompetitorOut] = []


class ProjectListOut(BaseModel):
    items: list[ProjectOut]
    total: int


class CompetitorIn(BaseModel):
    """POST /v1/projects/:id/competitors body."""

    brand_id: int
