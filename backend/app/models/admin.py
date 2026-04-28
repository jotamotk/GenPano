"""Admin auth ORM models — Session A0' truth source ADMIN_PRD §5.6.8.

Four tables: admin_users / admin_sessions / admin_password_resets /
admin_login_attempts. Six CHECK constraints (role / status / purpose /
failure_code + 2 admin_sessions temporal invariants).

Compatibility notes (per Session 0' baseline conventions):
- UUID stored as String(36); SQLite has no native UUID type and Postgres
  accepts a 36-char hex string in a uuid column when cast on insert. We
  generate the value in Python so the migration runs identically against
  sqlite (dev / preview-fallback) and postgres (Supabase prod).
- DateTime is naive (timezone=False), matching analyzer.py. UTC is the
  application convention; tz handling is deferred to a later migration if
  required.
- failure_code CHECK accepts NULL (success=true rows omit the code).

Decision references:
- CLAUDE.md #24.A (4-table master spec, algorithm semantics preserved)
- CLAUDE.md #24.C1.2 (force_password_change_at name + DateTime? type LOCKED)
- CLAUDE.md #24.C2 (role CHECK = super_admin only at MVP, A1' widens)
- CLAUDE.md #24.C4 (purpose column gap — closed in this Session)
- ADMIN_PRD §5.6.8 (truth source for field list + initial CHECKs)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class AdminUser(Base):
    __tablename__ = "admin_users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('super_admin')",
            name="role_chk",
        ),
        CheckConstraint(
            "status IN ('active', 'suspended')",
            name="status_chk",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="active")
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    force_password_change_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    last_password_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, onupdate=func.now()
    )


class AdminSession(Base):
    __tablename__ = "admin_sessions"
    __table_args__ = (
        CheckConstraint(
            "access_expires_at > issued_at",
            name="access_after_issued_chk",
        ),
        CheckConstraint(
            "refresh_expires_at > access_expires_at",
            name="refresh_after_access_chk",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    admin_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("admin_users.id"), nullable=False
    )
    access_token_jti: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    refresh_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class AdminPasswordReset(Base):
    __tablename__ = "admin_password_resets"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('reset', 'invitation')",
            name="purpose_chk",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    admin_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("admin_users.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )


class AdminLoginAttempt(Base):
    __tablename__ = "admin_login_attempts"
    __table_args__ = (
        CheckConstraint(
            "failure_code IS NULL OR failure_code IN "
            "('WRONG_PASSWORD', 'USER_SUSPENDED', 'RATE_LIMITED', 'UNKNOWN_EMAIL')",
            name="failure_code_chk",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# A1' Step 1 (round 8) — 8 new admin tables per ADMIN_PRD §4.1.4 / §4.3.7 / §4.4.8.
# Migration: alembic 15500b81322a (chains off A0' baseline 55a628f2bb7d).
# FK policy: only admin_users.id FKs are materialized; references to App users /
# kg_* tables are stored as plain String(36) UUID until Sessions 4a' / 1.5'.
# ---------------------------------------------------------------------------


class AdminUserModerationAction(Base):
    __tablename__ = "user_moderation_actions"
    __table_args__ = (
        CheckConstraint(
            "action IN ('freeze', 'unfreeze', 'force_password_reset', 'soft_delete')",
            name="action_chk",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    operator_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("admin_users.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )


class AdminUserActivityStat(Base):
    __tablename__ = "user_activity_stats"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    login_count_30d: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    query_count_30d: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)


class KgReviewQueue(Base):
    __tablename__ = "kg_review_queue"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('brand', 'product', 'category')",
            name="target_type_chk",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'merged')",
            name="status_chk",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    submitted_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("admin_users.id"), nullable=False
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
    reviewer_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("admin_users.id"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class AliasConflict(Base):
    __tablename__ = "alias_conflicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    alias_value: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    candidate_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    resolved_to_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolved_admin_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("admin_users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class BrandSubmission(Base):
    __tablename__ = "brand_submissions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="status_chk",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    submitter_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    brand_name_zh: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_name_en: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aliases: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    trust_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    sla_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    resolved_admin_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("admin_users.id"), nullable=True
    )


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('P0', 'P1', 'P2')",
            name="severity_chk",
        ),
        CheckConstraint(
            "state IN ('open', 'acknowledged', 'resolved')",
            name="state_chk",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    module: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    ack_admin_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("admin_users.id"), nullable=True
    )
    ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    resolved_admin_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("admin_users.id"), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class CostDaily(Base):
    __tablename__ = "cost_daily"
    __table_args__ = (
        UniqueConstraint(
            "date",
            "engine_id",
            "industry_id",
            "brand_id",
            "category",
            name="uq_cost_daily_composite",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    date: Mapped[datetime] = mapped_column(Date, nullable=False)
    engine_id: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    industry_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    brand_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    amount_cny: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, server_default="0")
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, server_default="0")
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    query_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    aggregated_from: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    aggregated_to: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)


class BudgetConfig(Base):
    __tablename__ = "budget_config"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('global', 'engine', 'industry', 'brand')",
            name="scope_chk",
        ),
        CheckConstraint(
            "warning_threshold_pct >= 0 AND warning_threshold_pct <= 100",
            name="warning_threshold_pct_chk",
        ),
        CheckConstraint(
            "hard_threshold_pct >= 0 AND hard_threshold_pct <= 200",
            name="hard_threshold_pct_chk",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    monthly_budget_usd: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    warning_threshold_pct: Mapped[int] = mapped_column(Integer, nullable=False, server_default="80")
    hard_threshold_pct: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    updated_admin_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("admin_users.id"), nullable=False
    )
