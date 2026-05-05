"""Phase A — analyzer extension ORMs.

Adds 8 new tables consumed by Phase A.3-A.10 analyzer modules:
- BrandOfficialDomain — primary domain registry per brand
- DomainAuthority — domain → tier mapping (PR target scoring)
- BrandGroup + BrandGroupMember + BrandGroupSharedDomain — corporate-group
  affiliations
- CompetitorMentionDaily — co-mention pairs for competitor matrix
- GeoScoreWeekly — weekly rollup of analyzer signals
- CitationWeeklyByDomain — per-(brand, domain) weekly aggregate
- IndustryTopicDaily — topic-level industry rollup
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from genpano_models.base import Base


class BrandOfficialDomain(Base):
    """Brand → official domain map (PR target detection)."""

    __tablename__ = "brand_official_domains"
    __table_args__ = (
        UniqueConstraint("brand_id", "domain", name="uq_brand_official_domains_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    brand_id: Mapped[int] = mapped_column(Integer, nullable=False)
    domain: Mapped[str] = mapped_column(String(256), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class DomainAuthority(Base):
    """Domain → tier mapping (PR target scoring; admin-managed)."""

    __tablename__ = "domain_authorities"

    domain: Mapped[str] = mapped_column(String(256), primary_key=True)
    tier: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, server_default="1.0")
    site_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class BrandGroup(Base):
    """Corporate group (e.g. P&G, Estee Lauder Companies)."""

    __tablename__ = "brand_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    parent_company: Mapped[str | None] = mapped_column(String(256), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class BrandGroupMember(Base):
    """Brand → group membership."""

    __tablename__ = "brand_group_members"
    __table_args__ = (
        CheckConstraint(
            "role IS NULL OR role IN ('flagship', 'sister', 'sub')",
            name="ck_brand_group_members_role",
        ),
    )

    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("brand_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    brand_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())


class BrandGroupSharedDomain(Base):
    """Domain shared across brands of the same group."""

    __tablename__ = "brand_group_shared_domains"

    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("brand_groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    domain: Mapped[str] = mapped_column(String(256), primary_key=True)
    brand_count: Mapped[int] = mapped_column(Integer, nullable=False)
    total_mentions: Mapped[int] = mapped_column(Integer, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CompetitorMentionDaily(Base):
    """Daily co-mention pair aggregate."""

    __tablename__ = "competitor_mention_daily"

    brand_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    competitor_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    target_llm: Mapped[str | None] = mapped_column(String(64), primary_key=True)
    co_mention_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    my_mention_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    comp_mention_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    avg_sentiment_diff: Mapped[float | None] = mapped_column(Float, nullable=True)
    sov_diff: Mapped[float | None] = mapped_column(Float, nullable=True)


class GeoScoreWeekly(Base):
    """Weekly aggregate of analyzer signals (per brand x week x engine)."""

    __tablename__ = "geo_score_weekly"

    brand_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_start: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    target_llm: Mapped[str | None] = mapped_column(String(64), primary_key=True)
    avg_geo_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_authority_tier: Mapped[float | None] = mapped_column(Float, nullable=True)
    top_authority_domains_json: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    tier1_citation_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tier2_citation_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tier3_citation_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    tier4_citation_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class CitationWeeklyByDomain(Base):
    """Per-(brand, domain) weekly aggregate."""

    __tablename__ = "citation_weekly_by_domain"

    brand_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    domain: Mapped[str] = mapped_column(String(256), primary_key=True)
    week_start: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    citation_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    avg_position_rank: Mapped[float | None] = mapped_column(Float, nullable=True)


class IndustryTopicDaily(Base):
    """Topic-level industry rollup (Phase A.10)."""

    __tablename__ = "industry_topic_daily"

    industry_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(128), primary_key=True, server_default="")
    topic_id: Mapped[int] = mapped_column(Integer, primary_key=True, server_default="0")
    date: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unique_brand_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    hot_score: Mapped[float | None] = mapped_column(Float, nullable=True)
