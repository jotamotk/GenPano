"""Request / response DTOs shared across the 6 admin auth endpoints.

Centralised so each endpoint module stays small and the FastAPI OpenAPI
schema names stay stable across handlers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EmailLocale = Literal["zh-CN", "en-US"]


class AdminUserDto(BaseModel):
    """Public projection of `admin_users` returned to the frontend.

    `password_hash` and `totp_secret` are intentionally omitted — every
    endpoint must shape its response through this DTO so a stray `dict()`
    of an ORM row cannot leak the hash.
    """

    id: str
    email: str
    role: str
    status: str
    force_password_change_at: datetime | None
    last_password_at: datetime | None
    last_login_at: datetime | None


class AuthSuccessResponse(BaseModel):
    """Body returned by /login and /refresh on the happy path."""

    user: AdminUserDto
    access_expires_at: int  # epoch seconds — frontend uses this to schedule silent refresh


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    """No body required — the refresh cookie carries the credential."""


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    locale: EmailLocale = "zh-CN"


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=8)
    new_password: str = Field(min_length=1)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class OkResponse(BaseModel):
    ok: bool = True
