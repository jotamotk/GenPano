"""ORM models for the admin_console-owned tables (admin auth + pipeline runs).

These tables originally lived in `admin_console/app.py`'s `_ensure_*_tables()`
startup migrations (deleted in Phase 1). They are now Alembic-owned and
modelled here so the FastAPI backend can read/write them via SQLAlchemy.

Boundaries:
- Admin operator identity: ``AdminUser`` (separate from the user-side ``User``).
- Admin login attempt audit: ``AdminLoginAttempt``.
- User moderation (freeze/unfreeze/etc.): ``UserModerationAction``.
- Pipeline runs (Topic Plan / Prompt Matrix / Query Pool): ``TopicPlanRun``,
  ``TopicCandidate``, ``PromptGenerationRun``, ``PromptCandidate``,
  ``QueryGenerationRun``, ``QueryGenerationCandidate``.
- Audience modelling: ``Segment``, ``Profile``.
- LLM-driven brand bootstrap: ``BrandGenerationLog``.

These models intentionally use the same column names that admin_console wrote
historically — switching ORMs does not change the wire schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from genpano_models.base import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _jsonb() -> Any:
    """JSONB on Postgres (prod), JSON on SQLite (CI / dev)."""
    return JSONB().with_variant(JSON(), "sqlite")


class BrandContextSnapshot(Base):
    __tablename__ = "brand_context_snapshots"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active','expired','archived')",
            name="brand_context_snapshots_status_check",
        ),
        UniqueConstraint("version", name="uq_brand_context_snapshots_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    brand_id: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="{}")
    source_notes_json: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="[]")
    search_as_of: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    created_from_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Admin operator auth
# ---------------------------------------------------------------------------


class AdminUser(Base):
    """Admin operator account — separate identity from the product ``User``."""

    __tablename__ = "admin_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, server_default="super_admin")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    force_password_change_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_password_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AdminLoginAttempt(Base):
    """Per-attempt login audit row written on every login probe."""

    __tablename__ = "admin_login_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class UserModerationAction(Base):
    """Operator-applied moderation action against a product user."""

    __tablename__ = "user_moderation_actions"
    __table_args__ = (
        CheckConstraint(
            "action IN ('freeze','unfreeze','force_password_reset','soft_delete')",
            name="ck_user_moderation_action",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    operator_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Pipeline runs — Topic Plan
# ---------------------------------------------------------------------------


class TopicPlanRun(Base):
    __tablename__ = "topic_plan_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','completed','failed','cancelled')",
            name="topic_plan_runs_status_check",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    admin_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    industry_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    brand_ids: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="[]")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="running")
    request_config: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="{}")
    coverage_snapshot: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    llm_usage_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    llm_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidates_generated: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    metrics_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class TopicCandidate(Base):
    __tablename__ = "topic_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="topic_candidates_status_check",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("topic_plan_runs.id"), nullable=True
    )
    brand_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brand_name: Mapped[str] = mapped_column(String(256), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_gap: Mapped[str | None] = mapped_column(String(256), nullable=True)
    normalized_title: Mapped[str] = mapped_column(String(256), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_topic_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    brand_context_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context_refs_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    topic_axis: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Pipeline runs — Prompt Matrix
# ---------------------------------------------------------------------------


class PromptGenerationRun(Base):
    __tablename__ = "prompt_generation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','completed','failed','cancelled')",
            name="prompt_generation_runs_status_check",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    admin_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="running")
    request_config: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="{}")
    selected_topic_ids: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="[]")
    estimated_prompts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    candidates_generated: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    llm_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    llm_usage_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    llm_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class PromptCandidate(Base):
    __tablename__ = "prompt_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','approved','rejected')",
            name="prompt_candidates_status_check",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("prompt_generation_runs.id"), nullable=True
    )
    topic_id: Mapped[int] = mapped_column(Integer, nullable=False)
    topic_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    brand_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    dimension: Mapped[str | None] = mapped_column(String(32), nullable=True)
    intent: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    template_strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    template_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    duplicate_of: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tags: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="{}")
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_prompt_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Pipeline runs — Query Pool
# ---------------------------------------------------------------------------


class QueryGenerationRun(Base):
    __tablename__ = "query_generation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','completed','failed','cancelled')",
            name="query_generation_runs_status_check",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    admin_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")
    request_config: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="{}")
    prompt_ids: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="[]")
    segment_ids_selected: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="[]")
    profiles_per_prompt: Mapped[int] = mapped_column(Integer, nullable=False, server_default="3")
    desired_engine_policy: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default="inherit"
    )
    engine_panel_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    max_candidates: Mapped[int] = mapped_column(Integer, nullable=False, server_default="12000")
    overflow_policy: Mapped[str] = mapped_column(String(32), nullable=False, server_default="split")
    candidates_estimated: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    candidates_assembled: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    estimated_cost: Mapped[Any | None] = mapped_column(Numeric, nullable=True)
    preflight_summary: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="{}")
    llm_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    llm_usage_json: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="{}")
    llm_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class QueryGenerationCandidate(Base):
    __tablename__ = "query_generation_candidates"
    __table_args__ = (
        CheckConstraint(
            "candidate_status IN ('candidate','review','ready')",
            name="query_generation_candidates_status_check",
        ),
        UniqueConstraint("run_id", "candidate_seq", name="uq_query_candidates_run_seq"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("query_generation_runs.id"), nullable=False
    )
    candidate_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prompt_id: Mapped[str] = mapped_column(String(64), nullable=False)
    segment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    profile_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rendered_query: Mapped[str] = mapped_column(Text, nullable=False)
    render_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    generation_method: Mapped[str] = mapped_column(String(32), nullable=False, server_default="llm")
    llm_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    llm_usage_json: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="{}")
    metadata_json: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="{}")
    candidate_status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="candidate"
    )
    scheduler_intake_batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Audience modelling — Segments + Profiles
# ---------------------------------------------------------------------------


class Segment(Base):
    __tablename__ = "segments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    brand_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    brand_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    industry_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    industry: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    weight: Mapped[Any] = mapped_column(Numeric, nullable=False, server_default="0")
    age_range: Mapped[str | None] = mapped_column(Text, nullable=True)
    income: Mapped[str | None] = mapped_column(Text, nullable=True)
    regions: Mapped[str | None] = mapped_column(Text, nullable=True)
    sampling_rate: Mapped[str | None] = mapped_column(Text, nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    segment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    brand_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    brand_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    demographic: Mapped[str | None] = mapped_column(Text, nullable=True)
    need: Mapped[str | None] = mapped_column(Text, nullable=True)
    weight: Mapped[Any] = mapped_column(Numeric, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    persona_json: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# Brand generation log
# ---------------------------------------------------------------------------


class BrandGenerationLog(Base):
    __tablename__ = "brand_generation_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    seed_brands: Mapped[Any | None] = mapped_column(_jsonb(), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_params: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="{}")
    output_json: Mapped[Any] = mapped_column(_jsonb(), nullable=False, server_default="[]")
    brands_generated: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    brands_imported: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[Any | None] = mapped_column(Numeric, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
