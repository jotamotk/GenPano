"""Alert + AlertRule + UserNotificationPreferences ORMs (Phase N)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from genpano_models.base import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('P0', 'P1', 'P2', 'P3')",
            name="ck_alerts_severity",
        ),
        CheckConstraint(
            "scope IN ('user', 'operator')",
            name="ck_alerts_scope",
        ),
        # PRD §4.8.7: 'snoozed' is a deferred-not-terminal state distinct
        # from 'ignored'. When `snoozed_until > now()` the alert is hidden
        # from unread counts; on expiry it auto-returns to 'unread'.
        CheckConstraint(
            "status IN ('unread', 'read', 'ignored', 'resolved', 'snoozed')",
            name="ck_alerts_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    brand_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_ref_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    severity: Mapped[str] = mapped_column(String(4), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, server_default="user")
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="unread")
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    read_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(36), nullable=True)
    runbook_url: Mapped[str | None] = mapped_column(Text, nullable=True)


class AlertRule(Base):
    __tablename__ = "alert_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
    )
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    conditions: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    channels: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class UserNotificationPreferences(Base):
    """Per-user notification preferences (PRD §4.7.3 + SettingsPage 3 toggles)."""

    __tablename__ = "user_notification_preferences"

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    p0p1_alerts: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    weekly_report: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    competitor_alert: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    email_locale: Mapped[str] = mapped_column(String(8), nullable=False, server_default="zh-CN")
    quiet_hours: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    channels: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
