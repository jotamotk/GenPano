"""ReportSchedule + ReportShareToken ORMs (Phase RP)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from genpano_models.base import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class ReportSchedule(Base):
    """Cron-driven recurring report generation (PRD §4.7.2.7)."""

    __tablename__ = "report_schedules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_type: Mapped[str] = mapped_column(String(32), nullable=False)
    cron: Mapped[str] = mapped_column(String(64), nullable=False)
    recipients: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    locale: Mapped[str] = mapped_column(String(8), nullable=False, server_default="zh-CN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class ReportShareToken(Base):
    """Public share link for a report (PRD §4.7.2.6)."""

    __tablename__ = "report_share_tokens"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    report_id: Mapped[str] = mapped_column(String(36), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
