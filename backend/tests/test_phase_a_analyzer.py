"""Phase A — analyzer extension 9 tables ORM tests."""

from __future__ import annotations

import os
import uuid
from datetime import datetime

import pytest
from genpano_models import (
    BrandGroup,
    BrandGroupMember,
    BrandGroupSharedDomain,
    BrandOfficialDomain,
    CitationWeeklyByDomain,
    CompetitorMentionDaily,
    DomainAuthority,
    GeoScoreWeekly,
    IndustryTopicDaily,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest.mark.asyncio
async def test_brand_official_domain_pair_unique(db_session: AsyncSession) -> None:
    db_session.add(BrandOfficialDomain(brand_id=42, domain="example.com", is_primary=1))
    await db_session.commit()
    db_session.add(BrandOfficialDomain(brand_id=42, domain="example.com"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_domain_authority_basic(db_session: AsyncSession) -> None:
    db_session.add(
        DomainAuthority(
            domain="nytimes.com",
            tier=1,
            confidence=1.0,
            site_type="news",
            notes="Top authority news outlet",
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_brand_group_lifecycle(db_session: AsyncSession) -> None:
    group = BrandGroup(name="Estee Lauder Companies", parent_company="Estee Lauder")
    db_session.add(group)
    await db_session.commit()
    db_session.add(BrandGroupMember(group_id=group.id, brand_id=10, role="flagship"))
    db_session.add(BrandGroupMember(group_id=group.id, brand_id=11, role="sister"))
    await db_session.commit()


@pytest.mark.asyncio
async def test_brand_group_member_role_check(db_session: AsyncSession) -> None:
    group = BrandGroup(name="Test Group")
    db_session.add(group)
    await db_session.commit()
    db_session.add(BrandGroupMember(group_id=group.id, brand_id=20, role="invalid_role"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_brand_group_shared_domain(db_session: AsyncSession) -> None:
    group = BrandGroup(name="P&G")
    db_session.add(group)
    await db_session.commit()
    db_session.add(
        BrandGroupSharedDomain(
            group_id=group.id,
            domain="pgcareers.com",
            brand_count=5,
            total_mentions=120,
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_competitor_mention_daily(db_session: AsyncSession) -> None:
    db_session.add(
        CompetitorMentionDaily(
            brand_id=42,
            competitor_id=99,
            date=datetime(2026, 5, 5),
            target_llm="chatgpt",
            co_mention_count=10,
            my_mention_count=15,
            comp_mention_count=8,
            avg_sentiment_diff=0.2,
            sov_diff=0.1,
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_geo_score_weekly(db_session: AsyncSession) -> None:
    db_session.add(
        GeoScoreWeekly(
            brand_id=42,
            week_start=datetime(2026, 5, 4),
            target_llm="chatgpt",
            avg_geo_score=82.5,
            avg_authority_tier=2.3,
            top_authority_domains_json=[
                {"domain": "nytimes.com", "tier": 1, "count": 12},
            ],
            tier1_citation_count=15,
            tier2_citation_count=20,
            tier3_citation_count=10,
            tier4_citation_count=5,
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_citation_weekly_by_domain(db_session: AsyncSession) -> None:
    db_session.add(
        CitationWeeklyByDomain(
            brand_id=42,
            domain="example.com",
            week_start=datetime(2026, 5, 4),
            citation_count=8,
            avg_position_rank=2.5,
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_industry_topic_daily(db_session: AsyncSession) -> None:
    db_session.add(
        IndustryTopicDaily(
            industry_id=1,
            category="Beauty",
            topic_id=101,
            date=datetime(2026, 5, 5),
            mention_count=42,
            unique_brand_count=12,
            hot_score=0.78,
        )
    )
    await db_session.commit()
