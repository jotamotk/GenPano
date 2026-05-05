"""BaseSection contract for Phase RP.2 report engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from genpano_models import Project
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ReportContext:
    """Inputs to every section.render() call.

    Attributes:
      project: target project ORM row (multi-tenant scope already enforced)
      brand_ids: brand IDs to include (project.primary_brand + competitors)
      from_date / to_date: date window inclusive
      locale: 'zh-CN' | 'en-US'
      reader_perspective: 'operator' | 'manager' | 'branding'
    """

    session: AsyncSession
    project: Project
    brand_ids: list[int]
    from_date: date
    to_date: date
    locale: str = "zh-CN"
    reader_perspective: str = "manager"


@dataclass
class SectionData:
    """Output of a single section render."""

    section_type: str
    title: str
    summary: str
    metrics: dict[str, Any] = field(default_factory=dict)
    tables: list[dict[str, Any]] = field(default_factory=list)
    charts: list[dict[str, Any]] = field(default_factory=list)
    chosen_variant: str = "full"


class BaseSection:
    """Subclass per section_type. Override async ``render``."""

    section_type: str

    async def render(self, ctx: ReportContext, *, variant: str) -> SectionData:
        raise NotImplementedError
