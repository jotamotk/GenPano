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

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
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
    purpose: Mapped[str] = mapped_column(String(16), nullable=False, server_default="reset")
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
