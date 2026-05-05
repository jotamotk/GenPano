"""ExportJob ORM (Phase E schema)."""

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


class ExportJob(Base):
    __tablename__ = "export_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')",
            name="ck_export_jobs_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    export_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    output_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
