"""Request / response DTOs shared across the 6 admin auth endpoints.

Centralised so each endpoint module stays small and the FastAPI OpenAPI
schema names stay stable across handlers.

**Field-naming contract (Session A0' Step 7)**: every DTO inherits from
`_BaseDto`, which configures Pydantic with `alias_generator=to_camel`,
`populate_by_name=True`, and `serialize_by_alias=True`. Net effect:

  - Outbound responses serialise field names as camelCase
    (`forcePasswordChangeAt`, `accessExpiresAt`, …) so the master TS-era
    frontend reads (e.g. `user.forcePasswordChangeAt`) keep working.
  - Inbound requests accept BOTH camelCase keys (`newPassword`,
    `currentPassword`) and snake_case keys (`new_password`,
    `current_password`) — the latter so the Step 5 integration tests
    (which were written against snake_case) keep passing without churn.

Adding a new DTO? Inherit from `_BaseDto`, NOT from `BaseModel`. Per-DTO
`model_config` is forbidden (drift risk — single source on the parent).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

EmailLocale = Literal["zh-CN", "en-US"]


class _BaseDto(BaseModel):
    """Single source for the camelCase-on-the-wire field-naming policy.

    Every Request + Response DTO MUST inherit from this class. Do not
    set `model_config` on subclasses — the parent's config is the only
    authoritative copy.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class AdminUserDto(_BaseDto):
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


class AuthSuccessResponse(_BaseDto):
    """Body returned by /login and /refresh on the happy path."""

    user: AdminUserDto
    access_expires_at: int  # epoch seconds — frontend uses this to schedule silent refresh


class LoginRequest(_BaseDto):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1)


class RefreshRequest(_BaseDto):
    """No body required — the refresh cookie carries the credential."""


class ForgotPasswordRequest(_BaseDto):
    email: str = Field(min_length=3, max_length=255)
    locale: EmailLocale = "zh-CN"


class ResetPasswordRequest(_BaseDto):
    token: str = Field(min_length=8)
    new_password: str = Field(min_length=1)


class ChangePasswordRequest(_BaseDto):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class OkResponse(_BaseDto):
    ok: bool = True
