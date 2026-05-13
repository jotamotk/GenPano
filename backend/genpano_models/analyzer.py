"""ORM models for GEN Analyzer baseline (migrations/001_analyzer_tables.sql).

Strict 1:1 with the SQL truth source: VARCHAR(N) -> String(N), TIMESTAMP ->
DateTime(timezone=False) (naive, matching original SQL), JSONB ->
JSONB().with_variant(JSON, 'sqlite') (Postgres prod, SQLite dev fallback).

Upstream tables referenced by ForeignKey strings (llm_responses, brands,
competitors, prompts) are intentionally NOT modelled here -- they belong to an
earlier migration (pre-Python-pivot TS schema) and are out of scope for the
Step 6 baseline. ForeignKey targets resolve at DDL emission time only.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import expression
from sqlalchemy.types import JSON

from genpano_models.base import Base


def _jsonb() -> Any:
    """JSONB on Postgres, JSON on SQLite (dev). See commit message JSONB note."""
    return JSONB().with_variant(JSON(), "sqlite")


class BrandMention(Base):
    __tablename__ = "brand_mentions"
    __table_args__ = (
        UniqueConstraint(
            "response_id",
            "brand_name",
            "product_name",
            name="uq_mention_response_brand_product",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    response_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("llm_responses.id"), nullable=False
    )
    brand_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("brands.id"), nullable=True)
    brand_name: Mapped[str] = mapped_column(String(256), nullable=False)
    product_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_target: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, server_default=expression.false()
    )
    position_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    position_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail_level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    context_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    mention_count: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default="1")
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )


class SentimentDriver(Base):
    __tablename__ = "sentiment_drivers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mention_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("brand_mentions.id"), nullable=False
    )
    response_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("llm_responses.id"), nullable=False
    )
    brand_name: Mapped[str] = mapped_column(String(256), nullable=False)
    driver_text: Mapped[str] = mapped_column(String(512), nullable=False)
    polarity: Mapped[str] = mapped_column(String(8), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strength: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.5")
    source_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )


class CitationSource(Base):
    __tablename__ = "citation_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    response_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("llm_responses.id"), nullable=False
    )
    mention_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("brand_mentions.id"), nullable=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    domain: Mapped[str | None] = mapped_column(String(256), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    citation_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )


class ResponseAnalysis(Base):
    __tablename__ = "response_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    response_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("llm_responses.id"), unique=True, nullable=True
    )
    dimension_industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dimension_company: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dimension_product: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dimension_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total_brands_mentioned: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default="0"
    )
    target_brand_mentioned: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, server_default=expression.false()
    )
    target_brand_position: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_brand_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_brand_sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    target_brand_detail: Mapped[str | None] = mapped_column(String(16), nullable=True)
    visibility_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, server_default="0.0"
    )
    sentiment_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, server_default="0.0"
    )
    sov_score: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    citation_score: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    geo_score: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )
    analyzer_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_analysis_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )


class ProductFeatureMention(Base):
    __tablename__ = "product_feature_mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("response_analyses.id"), nullable=False
    )
    brand_name: Mapped[str] = mapped_column(String(256), nullable=False)
    product_name: Mapped[str] = mapped_column(String(256), nullable=False)
    feature_name: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_sentiment: Mapped[str | None] = mapped_column(String(16), nullable=True)
    context_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    scenario: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price_positioning: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )


class AnalyzerRun(Base):
    __tablename__ = "analyzer_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    response_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("llm_responses.id"), nullable=False
    )
    schema_version: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="analyzer_v4"
    )
    prompt_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="running")
    trigger_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    batch_item_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_output_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validator_summary_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AnalyzerBatch(Base):
    __tablename__ = "analyzer_batches"

    batch_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    trigger_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dry_run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    preview_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    submitted_response_ids_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    skipped_counts_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    skipped_reasons_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    submitted_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class AnalyzerBatchItem(Base):
    __tablename__ = "analyzer_batch_items"
    __table_args__ = (
        UniqueConstraint("batch_id", "response_id", name="uq_analyzer_batch_item_response"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(64), ForeignKey("analyzer_batches.batch_id"))
    response_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("llm_responses.id"), nullable=True
    )
    query_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("analyzer_runs.id"), nullable=True
    )
    task_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    skipped_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )


class ResponseEntity(Base):
    __tablename__ = "response_entities"
    __table_args__ = (
        UniqueConstraint("run_id", "entity_key", name="uq_response_entities_run_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("analyzer_runs.id"), nullable=False)
    response_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("llm_responses.id"), nullable=False
    )
    entity_key: Mapped[str] = mapped_column(String(128), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_name: Mapped[str] = mapped_column(String(512), nullable=False)
    canonical_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    canonical_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    canonicalization_status: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_flags_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )


class ResponseRelationFact(Base):
    __tablename__ = "response_relation_facts"
    __table_args__ = (UniqueConstraint("run_id", "relation_key", name="uq_relation_facts_run_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("analyzer_runs.id"), nullable=False)
    response_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("llm_responses.id"), nullable=False
    )
    relation_key: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_entity_key: Mapped[str] = mapped_column(String(128), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    object_entity_key: Mapped[str] = mapped_column(String(128), nullable=False)
    direction: Mapped[str | None] = mapped_column(String(16), nullable=True)
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_flags_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="current")
    kg_candidate_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )


class AnalysisFactLink(Base):
    __tablename__ = "analysis_fact_links"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "fact_type",
            "fact_key",
            "linked_fact_type",
            "linked_fact_key",
            "link_type",
            name="uq_analysis_fact_links_run_fact_link",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("analyzer_runs.id"), nullable=False)
    response_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("llm_responses.id"), nullable=False
    )
    fact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    fact_key: Mapped[str] = mapped_column(String(128), nullable=False)
    linked_fact_type: Mapped[str] = mapped_column(String(32), nullable=False)
    linked_fact_key: Mapped[str] = mapped_column(String(128), nullable=False)
    link_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="supports")
    evidence_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="current")
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )


class AnalyzerQualityFlag(Base):
    __tablename__ = "analyzer_quality_flags"
    __table_args__ = (
        UniqueConstraint("run_id", "flag_key", name="uq_analyzer_quality_flags_run_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, ForeignKey("analyzer_runs.id"), nullable=False)
    response_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("llm_responses.id"), nullable=False
    )
    flag_key: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    blocks_metric_readiness: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, server_default=expression.false()
    )
    evidence_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )


class GeoScoreDaily(Base):
    __tablename__ = "geo_score_daily"
    __table_args__ = (
        UniqueConstraint(
            "brand_id",
            "date",
            "target_llm",
            "intent",
            "language",
            name="uq_geo_daily_dims",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(Integer, ForeignKey("brands.id"), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    target_llm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    intent: Mapped[str | None] = mapped_column(String(64), nullable=True)
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    total_queries: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default="0")
    mention_count: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default="0")
    mention_rate: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    avg_position_rank: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_place_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default="0"
    )
    first_place_rate: Mapped[float | None] = mapped_column(
        Float, nullable=True, server_default="0.0"
    )
    positive_rate: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    negative_rate: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    avg_sentiment_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, server_default="0.0"
    )
    citation_rate: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    avg_sov: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    avg_visibility: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    avg_sentiment: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    avg_sov_score: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    avg_citation_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, server_default="0.0"
    )
    avg_geo_score: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    industry_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    industry_sov_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class TopicScoreDaily(Base):
    """Per-(brand, topic, date) aggregation, populated by Aggregator._aggregate_topic_daily."""

    __tablename__ = "topic_score_daily"
    __table_args__ = (UniqueConstraint("brand_id", "topic_id", "date", name="uq_topic_daily"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_id: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    mention_count: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default="0")
    total_responses: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default="0")
    mention_rate: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    avg_position_rank: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_geo_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )


class IndustryBenchmarkDaily(Base):
    __tablename__ = "industry_benchmark_daily"
    __table_args__ = (UniqueConstraint("industry", "date", "target_llm", name="uq_industry_daily"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    industry: Mapped[str] = mapped_column(String(128), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    target_llm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_brands: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default="0")
    total_queries: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default="0")
    avg_mention_rate: Mapped[float | None] = mapped_column(
        Float, nullable=True, server_default="0.0"
    )
    avg_geo_score: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    avg_sentiment: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    score_p25: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_p50: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_p75: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_brands_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class ProductScoreDaily(Base):
    __tablename__ = "product_score_daily"
    __table_args__ = (
        UniqueConstraint(
            "brand_id",
            "product_name",
            "date",
            "target_llm",
            name="uq_product_daily",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(Integer, ForeignKey("brands.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String(256), nullable=False)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    target_llm: Mapped[str | None] = mapped_column(String(64), nullable=True)
    total_queries: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default="0")
    mention_count: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default="0")
    mention_rate: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    avg_position_rank: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_place_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, server_default="0"
    )
    first_place_rate: Mapped[float | None] = mapped_column(
        Float, nullable=True, server_default="0.0"
    )
    avg_sentiment_score: Mapped[float | None] = mapped_column(
        Float, nullable=True, server_default="0.0"
    )
    avg_geo_score: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    category_sov_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    category_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comparison_wins: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default="0")
    comparison_total: Mapped[int | None] = mapped_column(Integer, nullable=True, server_default="0")
    win_rate: Mapped[float | None] = mapped_column(Float, nullable=True, server_default="0.0")
    top_features_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    top_scenarios_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    price_positioning: Mapped[str | None] = mapped_column(String(32), nullable=True)
    price_positioning_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    top_drivers_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
