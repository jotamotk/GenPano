"""DTOs for project-scoped App topic analysis.

These endpoints expose Admin fact data as read-only App analytics. They are
chart-ready by design so the frontend does not have to infer metric formulas
from raw Admin entities.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TopicMonitoringSummary(BaseModel):
    topic_count: int = 0
    prompt_count: int = 0
    query_count: int = 0
    response_count: int = 0
    analyzed_count: int = 0
    target_mention_count: int = 0
    citation_count: int = 0
    last_collected: str | None = None


class TopicMonitoringRow(BaseModel):
    topic_id: int
    topic_name: str
    dimension: str | None = None
    status: str | None = None
    prompt_count: int = 0
    query_count: int = 0
    response_count: int = 0
    success_rate: float | None = None
    engine_coverage: list[str] = Field(default_factory=list)
    mention_rate: float | None = None
    sov: float | None = None
    avg_rank: float | None = None
    avg_geo_score: float | None = None
    sentiment_distribution: dict[str, int] = Field(
        default_factory=lambda: {"positive": 0, "neutral": 0, "negative": 0}
    )
    citation_rate: float | None = None
    last_collected: str | None = None


class TopicIntentMatrixRow(BaseModel):
    topic_id: int | None = None
    topic_name: str | None = None
    intent: str
    prompt_count: int = 0
    query_count: int = 0
    response_count: int = 0


class TopicMonitoringOut(BaseModel):
    project_id: str
    brand_id: int | None
    summary: TopicMonitoringSummary
    topics: list[TopicMonitoringRow]
    intent_matrix: list[TopicIntentMatrixRow] = Field(default_factory=list)
    state: str = "ok"


class TopicPromptRow(BaseModel):
    prompt_id: int
    topic_id: int
    prompt_text: str | None = None
    intent: str | None = None
    language: str | None = None
    status: str | None = None
    query_count: int = 0
    response_count: int = 0
    success_rate: float | None = None
    engine_coverage: list[str] = Field(default_factory=list)
    mention_rate: float | None = None
    avg_rank: float | None = None
    avg_geo_score: float | None = None
    citation_rate: float | None = None
    last_collected: str | None = None


class TopicPromptsOut(BaseModel):
    project_id: str
    topic_id: int
    items: list[TopicPromptRow]
    total: int
    state: str = "ok"


class PromptQueryRow(BaseModel):
    query_id: int
    prompt_id: int | None = None
    query_text: str | None = None
    target_llm: str | None = None
    status: str | None = None
    profile_id: str | None = None
    created_at: str | None = None
    executed_at: str | None = None
    finished_at: str | None = None
    latency_ms: int | None = None
    response_id: int | None = None
    target_mentioned: bool = False
    citation_count: int = 0
    geo_score: float | None = None
    sentiment_score: float | None = None


class PromptQueriesOut(BaseModel):
    project_id: str
    prompt_id: int
    items: list[PromptQueryRow]
    total: int
    state: str = "ok"


class QueryDetail(BaseModel):
    query_id: int
    prompt_id: int | None = None
    topic_id: int | None = None
    query_text: str | None = None
    target_llm: str | None = None
    status: str | None = None
    profile_id: str | None = None
    created_at: str | None = None
    executed_at: str | None = None
    finished_at: str | None = None
    latency_ms: int | None = None


class ResponseDetail(BaseModel):
    response_id: int
    query_id: int | None = None
    prompt_id: int | None = None
    raw_text: str | None = None
    target_llm: str | None = None
    intent: str | None = None
    llm_version: str | None = None
    citations_json: Any | None = None
    created_at: str | None = None


class ResponseAnalysisDetail(BaseModel):
    analysis_id: int | None = None
    target_brand_mentioned: bool | None = None
    target_brand_rank: int | None = None
    target_brand_sentiment: str | None = None
    visibility_score: float | None = None
    sentiment_score: float | None = None
    sov_score: float | None = None
    citation_score: float | None = None
    geo_score: float | None = None
    analyzed_at: str | None = None


class BrandMentionDetail(BaseModel):
    mention_id: int
    response_id: int
    brand_id: int | None = None
    brand_name: str
    product_name: str | None = None
    is_target: bool | None = None
    position_rank: int | None = None
    sentiment: str | None = None
    sentiment_score: float | None = None
    context_snippet: str | None = None
    mention_count: int | None = None
    created_at: str | None = None


class CitationDetail(BaseModel):
    citation_id: int
    response_id: int
    mention_id: int | None = None
    url: str
    domain: str | None = None
    title: str | None = None
    citation_index: int | None = None
    source_type: str | None = None
    created_at: str | None = None


class QueryResponseDetailOut(BaseModel):
    project_id: str
    query: QueryDetail
    response: ResponseDetail | None = None
    analysis: ResponseAnalysisDetail | None = None
    brand_mentions: list[BrandMentionDetail] = Field(default_factory=list)
    citations: list[CitationDetail] = Field(default_factory=list)
    state: str = "ok"


class QueryActivityEngineRow(BaseModel):
    engine: str
    query_count: int = 0
    response_count: int = 0
    mention_rate: float | None = None
    avg_geo_score: float | None = None


class QueryActivityTopicRow(BaseModel):
    topic_id: int
    topic_name: str
    query_count: int = 0
    response_count: int = 0
    mention_rate: float | None = None


class QueryActivityDailyRow(BaseModel):
    date: str
    queries: int = 0
    responses: int = 0
    target_mentions: int = 0


class QueryActivityOut(BaseModel):
    project_id: str
    brand_id: int | None
    period: dict[str, str]
    totals: dict[str, int]
    by_status: dict[str, int] = Field(default_factory=dict)
    by_engine: list[QueryActivityEngineRow] = Field(default_factory=list)
    by_topic: list[QueryActivityTopicRow] = Field(default_factory=list)
    daily: list[QueryActivityDailyRow] = Field(default_factory=list)
    sentiment_distribution: dict[str, int] = Field(
        default_factory=lambda: {"positive": 0, "neutral": 0, "negative": 0}
    )
    position_distribution: dict[str, int] = Field(default_factory=dict)
    state: str = "ok"


class ProjectProfileRow(BaseModel):
    profile_id: str
    name: str
    status: str | None = None
    demographic: str | None = None
    need: str | None = None
    weight: float | None = None


class ProjectSegmentRow(BaseModel):
    segment_id: str
    code: str | None = None
    name: str
    status: str | None = None
    weight: float | None = None
    active_profile_count: int = 0
    profiles: list[ProjectProfileRow] = Field(default_factory=list)


class ProjectSegmentsOut(BaseModel):
    project_id: str
    items: list[ProjectSegmentRow]
    total: int
    state: str = "ok"
