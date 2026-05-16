"""DTOs for Phase N alerts + notifications."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

AlertStatus = Literal["unread", "read", "ignored", "resolved", "snoozed"]
AlertSeverity = Literal["P0", "P1", "P2", "P3"]

# PRD §4.8.7 — explicit snooze presets. Frontend should offer these as
# quick options; clients may pass any positive integer hours but the
# spec-locked presets are listed for documentation + tests.
SNOOZE_PRESET_HOURS: tuple[int, ...] = (1, 4, 24, 24 * 7)
DEFAULT_SNOOZE_HOURS = 24


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    brand_id: int | None
    source: str
    source_ref_id: str | None
    severity: AlertSeverity
    scope: str
    title: str
    body: str | None
    status: AlertStatus
    triggered_at: datetime
    read_at: datetime | None
    resolved_at: datetime | None
    snoozed_until: datetime | None = None


class AlertListOut(BaseModel):
    items: list[AlertOut]
    next_cursor: str | None = None
    total: int


class AlertPatchIn(BaseModel):
    status: AlertStatus


class AlertSnoozeIn(BaseModel):
    """Body for POST /v1/alerts/:id/snooze.

    `hours` is clamped to [1, 24*30] server-side; default = 24h per
    PRD §4.8.7.
    """

    hours: int = Field(default=DEFAULT_SNOOZE_HOURS, ge=1, le=24 * 30)


class UnreadCountOut(BaseModel):
    unread_count: int
    by_severity: dict[str, int]


class NotificationPrefsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    p0p1_alerts: bool
    weekly_report: bool
    competitor_alert: bool
    email_locale: str
    quiet_hours: dict[str, Any] | None
    channels: list[str] | None


class NotificationPrefsPatch(BaseModel):
    p0p1_alerts: bool | None = None
    weekly_report: bool | None = None
    competitor_alert: bool | None = None
    email_locale: Literal["zh-CN", "en-US"] | None = None
    quiet_hours: dict[str, Any] | None = None
    channels: list[str] | None = None


class AlertRuleIn(BaseModel):
    rule_type: str = Field(..., min_length=1, max_length=32)
    project_id: str | None = None
    conditions: dict[str, Any] | None = None
    channels: list[str] | None = None
    enabled: bool = True


class AlertRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    project_id: str | None
    rule_type: str
    conditions: dict[str, Any] | None
    channels: list[str] | None
    enabled: bool
    created_at: datetime
