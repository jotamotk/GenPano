"""Phase O admin operations ORMs (PRD §4.4)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
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
from sqlalchemy.orm import Mapped, mapped_column

from genpano_models.base import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class EngineHealthDaily(Base):
    """Per-engine daily aggregates (PRD §4.2.2)."""

    __tablename__ = "engine_health_daily"
    __table_args__ = (UniqueConstraint("engine", "date", name="uq_engine_health_engine_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    engine: Mapped[str] = mapped_column(String(64), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    success_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    p50_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    p95_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cookie_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    captcha_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    ip_blocked_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rate_limited_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_updated: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class ProxyHealthDaily(Base):
    """Per-proxy daily aggregates."""

    __tablename__ = "proxy_health_daily"
    __table_args__ = (UniqueConstraint("proxy_id", "date", name="uq_proxy_health_proxy_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proxy_id: Mapped[int] = mapped_column(Integer, nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    total_requests: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    success_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class DiscoveryLog(Base):
    """LLM discovery log (PRD §4.3.6 KG quality monitor)."""

    __tablename__ = "discovery_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    hallucination_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    hallucination_evidence: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class CostEvent(Base):
    """Cost ledger (ADR-015 — 4 scopes: pipeline / kg / mcp / reports)."""

    __tablename__ = "cost_events"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('pipeline', 'kg', 'mcp', 'reports')",
            name="ck_cost_events_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(10, 4), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_metadata: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class BudgetThreshold(Base):
    """Per-scope budget hard-stop (ADR-015)."""

    __tablename__ = "budget_thresholds"
    __table_args__ = (
        CheckConstraint(
            "scope IN ('pipeline', 'kg', 'mcp', 'reports')",
            name="ck_budget_thresholds_scope",
        ),
    )

    scope: Mapped[str] = mapped_column(String(16), primary_key=True)
    daily_limit_cny: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    weekly_limit_cny: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    monthly_limit_cny: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    alert_at_pct: Mapped[int] = mapped_column(Integer, nullable=False, server_default="80")
    hard_stop_at_pct: Mapped[int] = mapped_column(Integer, nullable=False, server_default="100")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class AdminAuditLog(Base):
    """Admin mutation audit (ADR-014)."""

    __tablename__ = "admin_audit_log"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('low', 'med', 'high')",
            name="ck_admin_audit_log_severity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    operator_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    before: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    after: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class CommsAnnouncement(Base):
    """Admin → users / operator announcements (PRD §4.4.4)."""

    __tablename__ = "comms_announcements"
    __table_args__ = (
        CheckConstraint(
            "channel IN ('inapp', 'email', 'both')",
            name="ck_comms_announcements_channel",
        ),
        CheckConstraint(
            "status IN ('draft', 'scheduled', 'sending', 'sent', 'cancelled')",
            name="ck_comms_announcements_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    title_zh: Mapped[str | None] = mapped_column(String(256), nullable=True)
    title_en: Mapped[str | None] = mapped_column(String(256), nullable=True)
    body_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    audience: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="draft")
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class McpCallLog(Base):
    """MCP call log (PRD §4.4.6 — Phase O.2.3)."""

    __tablename__ = "mcp_call_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    api_key_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    tool: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate_cny: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    request_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
