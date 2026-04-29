"""Product user auth models.

These tables back the public GENPANO registration/login flow. Admin auth keeps
its own isolated tables under `app.models.admin`; product users use bearer JWTs
and one-time hashed tokens for email verification, OAuth profile completion,
and password reset.
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
    Text,
    false,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('free', 'paid')",
            name="role_chk",
        ),
        CheckConstraint(
            "provider IN ('email', 'google')",
            name="provider_chk",
        ),
        CheckConstraint(
            "locale IN ('zh-CN', 'en-US')",
            name="locale_chk",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    company: Mapped[str | None] = mapped_column(String(160), nullable=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, server_default="free")
    provider: Mapped[str] = mapped_column(String(24), nullable=False, server_default="email")
    google_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    newsletter_subscribed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=true()
    )
    locale: Mapped[str] = mapped_column(String(8), nullable=False, server_default="zh-CN")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=False), nullable=True, onupdate=func.now()
    )

    auth_tokens: Mapped[list[UserAuthToken]] = relationship(
        "UserAuthToken",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserAuthToken(Base):
    __tablename__ = "user_auth_tokens"
    __table_args__ = (
        CheckConstraint(
            "token_type IN ('verify_email', 'password_reset', 'oauth_setup')",
            name="token_type_chk",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    token_type: Mapped[str] = mapped_column(String(24), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    email_snapshot: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), nullable=False, server_default=func.now()
    )

    user: Mapped[User] = relationship("User", back_populates="auth_tokens")
