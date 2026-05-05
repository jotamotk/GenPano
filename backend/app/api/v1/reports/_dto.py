"""DTOs for Reports (Phase RP.2)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class ReportCreateIn(BaseModel):
    report_type: str = Field(default="weekly")
    locale: str = Field(default="zh-CN")
    reader_perspective: str = Field(default="manager")
    from_date: date | None = None
    to_date: date | None = None


class ReportJobOut(BaseModel):
    id: str
    project_id: str
    type: str
    status: str
    created_at: datetime
    finished_at: datetime | None
    output_url: str | None
    error: str | None


class ReportListOut(BaseModel):
    items: list[ReportJobOut]
    total: int


class ReportDetailOut(ReportJobOut):
    payload: dict[str, Any] | None = None


class ReportShareIn(BaseModel):
    expires_in_hours: int = Field(default=72, ge=1, le=720)


class ReportShareOut(BaseModel):
    token: str
    url: str
    expires_at: datetime


class PublicReportOut(BaseModel):
    payload: dict[str, Any]
    expires_at: datetime
    view_count: int
