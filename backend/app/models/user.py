"""App-side User ORM model — DATA_MODEL §1.1 truth source.

Eleven columns + email UNIQUE + 2 indexes (idx_users_email,
idx_users_deletion partial WHERE deletion_requested_at IS NOT NULL).

Decision references:
- CLAUDE.md #30.H (Path B Variant 2: real users table promoted from
  upstream-stub idiom; soft-delete is the ONLY admin-writable column,
  freeze status derived from user_moderation_actions per §4.1.2)
- DATA_MODEL §1.1 (canonical column list)
- ADMIN_PRD §4.1.2 is_frozen formula (EXISTS subquery on
  user_moderation_actions; no `status` column on users)

Compatibility notes:
- UUID stored as String(36), matching A0' / Step 1 baseline pattern.
- DateTime is naive (timezone=False) per analyzer.py / admin.py
  convention; UTC is application-level invariant.
- Email regex CHECK from DATA_MODEL §1.1 is enforced at the API layer
  (Pydantic v2 EmailStr) rather than at the DB level — Postgres `~*`
  has no SQLite analogue, so the cross-DB migration ships UNIQUE only
  and validation lives one layer up.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name_zh: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name_en: Mapped[str | None] = mapped_column(String(100), nullable=True)
    preferences: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    deletion_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now(), onupdate=func.now()
    )
