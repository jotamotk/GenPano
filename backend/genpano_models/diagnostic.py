"""Diagnostic ORM (Phase D)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
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


class Diagnostic(Base):
    """User-facing diagnostic with insight stack (PRD §4.7.1)."""

    __tablename__ = "diagnostics"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('P0', 'P1', 'P2', 'P3')",
            name="ck_diagnostics_severity",
        ),
        CheckConstraint(
            "type IN ('brand', 'product', 'industry')",
            name="ck_diagnostics_type",
        ),
        CheckConstraint(
            "status IN ('open', 'acknowledged', 'ignored', 'resolved')",
            name="ck_diagnostics_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    brand_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    industry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(4), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    engine: Mapped[str | None] = mapped_column(String(32), nullable=True)
    focus_area: Mapped[str | None] = mapped_column(String(256), nullable=True)
    direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    reader_hints: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    decision_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[Any] = mapped_column(JSON, nullable=False)
    causal_chain: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    industry_benchmark: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    time_series: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    anchor_questions: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    if_untreated: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="open")
    detected_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    alert_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
