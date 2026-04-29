from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

EmailLocale = Literal["zh-CN", "en-US"]


class _BaseDto(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class UserDto(_BaseDto):
    id: str
    email: str
    name: str | None
    company: str | None
    role: str = "free"
    provider: str
    email_verified: bool
    locale: EmailLocale
    created_at: datetime


class LoginResponse(_BaseDto):
    token: str
    user: UserDto


class RegisterRequest(_BaseDto):
    email: str = Field(min_length=3, max_length=255)
    locale: EmailLocale = "zh-CN"


class RegisterResponse(_BaseDto):
    message: str
    email: str


class LookupRequest(_BaseDto):
    email: str = Field(min_length=3, max_length=255)


class LookupResponse(_BaseDto):
    next: Literal["register", "login"]
    exists: bool
    has_password: bool
    provider: Literal["email", "google"] | None = None
    locale_hint: EmailLocale | None = None


class LoginRequest(_BaseDto):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1)


class ForgotPasswordRequest(_BaseDto):
    email: str = Field(min_length=3, max_length=255)
    locale: EmailLocale = "zh-CN"


class OkResponse(_BaseDto):
    message: str = "ok"


class SetupTokenResponse(_BaseDto):
    email: str
    provider: Literal["email", "google"]
    name: str | None
    company: str | None
    requires_password: bool
    token_type: Literal["verify_email", "oauth_setup"]


class SetupRequest(_BaseDto):
    token: str = Field(min_length=8)
    email: str | None = Field(default=None, min_length=3, max_length=255)
    password: str | None = Field(default=None, min_length=1)
    name: str = Field(min_length=1, max_length=120)
    company: str = Field(min_length=1, max_length=160)
    newsletter: bool = True
    locale: EmailLocale = "zh-CN"


class ResetPasswordRequest(_BaseDto):
    token: str = Field(min_length=8)
    password: str = Field(min_length=1)


class ResendVerificationRequest(_BaseDto):
    email: str = Field(min_length=3, max_length=255)
    locale: EmailLocale = "zh-CN"
