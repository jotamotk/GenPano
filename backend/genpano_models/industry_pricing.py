"""IndustryPricingParams ORM (Phase E schema; Simulator §4.7.6)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from genpano_models.base import Base


class IndustryPricingParams(Base):
    """Per-industry tier unit prices for Simulator base_price_equivalent calc."""

    __tablename__ = "industry_pricing_params"

    industry_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tier1_unit_price_cny: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    tier2_unit_price_cny: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    tier3_unit_price_cny: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    tier4_unit_price_cny: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
