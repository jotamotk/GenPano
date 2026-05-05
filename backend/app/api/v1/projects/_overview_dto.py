"""DTOs for /v1/projects/:id/overview (Phase 2.1 — Pydantic v2)."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict


class KpiCard(BaseModel):
    """One KPI tile on Brand Overview."""

    model_config = ConfigDict(from_attributes=True)

    label_zh: str
    label_en: str
    value: float | int
    unit: str | None = None
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
