"""Project ORM (Phase 0 schema, Phase 1 wires real endpoint).

Project = root multi-tenant entity for App users; one user can have N projects.
Per ADR-005, `org_id` is reserved for future team-management migration.

See:
- DATA_MODEL_ADDENDUM_PHASE_P §"Phase 0 — 多租户基础"
- backend/alembic/versions/2026_05_04_0002_phase_0_app_product_tables.py
"""

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
    UniqueConstraint,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from genpano_models.base import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_projects_user_id_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    org_id: Mapped[str | None] = mapped_column(String(36), nullable=True)  # Phase M
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    industry_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    primary_brand_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    preferred_engines: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    default_profile_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preferences: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    competitors: Mapped[list[ProjectCompetitor]] = relationship(
        "ProjectCompetitor",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ProjectCompetitor(Base):
    __tablename__ = "project_competitors"

    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    brand_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pinned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    pinned_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    project: Mapped[Project] = relationship("Project", back_populates="competitors")


class ProjectTopicPin(Base):
    __tablename__ = "project_topic_pins"
    __table_args__ = (
        CheckConstraint(
            "state IN ('tracked', 'ignored')",
            name="ck_project_topic_pins_state",
        ),
    )

    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id", ondelete="CASCADE"),
        primary_key=True,
    )
    topic_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    pinned_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
