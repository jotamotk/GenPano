"""[#1044 B2-5 remainder] industry_landscape + brand_performance +
branding_narrative + product_competitiveness sections.

Closes the remaining 4 of 6 missing sections from PRD §4.7.2. Each
section is exercised via the builder so SECTION_MATRIX + SECTION_ORDER
wiring is asserted alongside the per-section render.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    BrandMention,
    GeoScoreDaily,
    IndustryBenchmarkDaily,
    ProductScoreDaily,
    Project,
    SentimentDriver,
    TopicScoreDaily,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    u = User(
        id=_new_id(),
        email=f"sec4-{uuid.uuid4().hex[:6]}@example.com",
        name="sec4",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    p = Project(
        id=_new_id(),
        user_id=u.id,
        name="P-sec4",
        primary_brand_id=42,
        industry_id=1,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p


def _ctx(db_session, project, *, locale="zh-CN"):
    from app.reports.sections.base import ReportContext

    today = date.today()
    return ReportContext(
        session=db_session,
        project=project,
        brand_ids=[42],
        from_date=today - timedelta(days=6),
        to_date=today,
        locale=locale,
    )


# ── industry_landscape ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_industry_landscape_empty_when_no_industry_data(db_session, project):
    from app.reports.sections.industry_landscape import IndustryLandscapeSection

    out = await IndustryLandscapeSection().render(_ctx(db_session, project), variant="full")
    assert out.section_type == "industry_landscape"
    # Either no_brand_data (no GeoScoreDaily yet) or empty industry — both produce sparse output
    assert out.metrics.get("empty_reason") in {"no_brand_data", "no_primary_brand"}


@pytest.mark.asyncio
async def test_industry_landscape_percentile_band(db_session, project):
    from app.reports.sections.industry_landscape import IndustryLandscapeSection

    today = date.today()
    for i in range(7):
        d = today - timedelta(days=6 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=d,
                target_llm="chatgpt",
                avg_geo_score=85.0,
                industry_rank=3,
                total_queries=100,
            )
        )
        db_session.add(
            IndustryBenchmarkDaily(
                industry="cosmetics",
                date=d,
                avg_geo_score=70.0,
                score_p25=60.0,
                score_p50=70.0,
                score_p75=80.0,
                total_brands=12,
            )
        )
    await db_session.commit()

    out = await IndustryLandscapeSection().render(_ctx(db_session, project), variant="full")
    m = out.metrics
    assert m["my_geo_score"] == 85.0
    assert m["industry_median"] == 70.0
    assert m["industry_total_brands"] == 12
    assert m["distance_from_median"] == 15.0
    assert m["position_band"] == "top_quartile"


# ── brand_performance ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_brand_performance_empty_state(db_session, project):
    from app.reports.sections.base import ReportContext
    from app.reports.sections.brand_performance import BrandPerformanceSection

    today = date.today()
    empty_ctx = ReportContext(
        session=db_session,
        project=project,
        brand_ids=[],
        from_date=today - timedelta(days=6),
        to_date=today,
        locale="zh-CN",
    )
    out = await BrandPerformanceSection().render(empty_ctx, variant="full")
    assert "无可衡量品牌" in out.summary


@pytest.mark.asyncio
async def test_brand_performance_renders_per_brand(db_session, project):
    from app.reports.sections.brand_performance import BrandPerformanceSection

    today = date.today()
    for i in range(7):
        d = today - timedelta(days=6 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=d,
                target_llm="chatgpt",
                avg_geo_score=80.0,
                mention_rate=0.5,
                avg_sov=0.4,
                first_place_rate=0.2,
                avg_sentiment=0.6,
                total_queries=100,
            )
        )
    await db_session.commit()

    out = await BrandPerformanceSection().render(_ctx(db_session, project), variant="full")
    rows = out.tables[0]["rows"]
    assert len(rows) == 1
    assert rows[0]["brand_id"] == 42
    assert rows[0]["is_primary"] is True
    assert rows[0]["mention_rate"] == 0.5
    assert rows[0]["engines"] == 1
    assert out.metrics["brand_count"] == 1
    assert out.metrics["primary"]["brand_id"] == 42


# ── branding_narrative ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_branding_narrative_empty_when_no_signals(db_session, project):
    from app.reports.sections.branding_narrative import BrandingNarrativeSection

    out = await BrandingNarrativeSection().render(_ctx(db_session, project), variant="full")
    assert out.metrics.get("empty_reason") in {"no_signals_in_window", "no_primary_brand"}


@pytest.mark.asyncio
async def test_branding_narrative_aggregates_drivers_and_topics(db_session, project):
    from app.reports.sections.branding_narrative import BrandingNarrativeSection

    today = date.today()
    in_window = datetime.combine(today - timedelta(days=2), datetime.min.time())
    # Two mentions for brand 42; each carries drivers
    for i in range(3):
        bm = BrandMention(
            response_id=9000 + i,
            brand_id=42,
            brand_name="X",
            sentiment="positive",
            sentiment_score=0.6,
            created_at=in_window,
        )
        db_session.add(bm)
        await db_session.flush()
        db_session.add(
            SentimentDriver(
                mention_id=bm.id,
                response_id=bm.response_id,
                brand_name="X",
                driver_text="好口碑",
                polarity="positive",
                strength=0.7,
                created_at=in_window,
            )
        )
        if i < 2:
            db_session.add(
                SentimentDriver(
                    mention_id=bm.id,
                    response_id=bm.response_id,
                    brand_name="X",
                    driver_text="性价比争议",
                    polarity="negative",
                    strength=0.5,
                    created_at=in_window,
                )
            )
    # Topics
    for tid in (1, 2):
        db_session.add(
            TopicScoreDaily(
                brand_id=42,
                topic_id=tid,
                date=today - timedelta(days=2),
                mention_count=5 * tid,
                avg_sentiment_score=0.5,
            )
        )
    await db_session.commit()

    out = await BrandingNarrativeSection().render(_ctx(db_session, project), variant="full")
    table_names = {t["name"] for t in out.tables}
    assert "top_positive_drivers" in table_names
    assert "top_negative_drivers" in table_names
    assert "top_topics" in table_names
    assert out.metrics["positive_driver_count"] == 1
    assert out.metrics["negative_driver_count"] == 1
    assert out.metrics["topic_count"] == 2
    # Summary mentions both polarity tops
    assert "好口碑" in out.summary
    assert "性价比争议" in out.summary


# ── product_competitiveness ─────────────────────────────────────


@pytest.mark.asyncio
async def test_product_competitiveness_empty(db_session, project):
    from app.reports.sections.product_competitiveness import ProductCompetitivenessSection

    out = await ProductCompetitivenessSection().render(_ctx(db_session, project), variant="full")
    assert out.metrics.get("empty_reason") in {"no_product_data", "no_primary_brand"}


@pytest.mark.asyncio
async def test_product_competitiveness_ranks_products(db_session, project):
    from app.reports.sections.product_competitiveness import ProductCompetitivenessSection

    today = date.today()
    for i in range(7):
        d = today - timedelta(days=6 - i)
        db_session.add(
            ProductScoreDaily(
                brand_id=42,
                product_name="精华液",
                category="skincare",
                date=d,
                target_llm="chatgpt",
                mention_rate=0.6,
                first_place_rate=0.3,
                avg_sentiment_score=0.5,
                avg_geo_score=82.0,
                category_rank=2,
                comparison_wins=3,
            )
        )
        db_session.add(
            ProductScoreDaily(
                brand_id=42,
                product_name="爽肤水",
                category="skincare",
                date=d,
                target_llm="chatgpt",
                mention_rate=0.3,
                first_place_rate=0.1,
                avg_sentiment_score=0.4,
                avg_geo_score=65.0,
                category_rank=5,
                comparison_wins=1,
            )
        )
    await db_session.commit()

    out = await ProductCompetitivenessSection().render(_ctx(db_session, project), variant="full")
    rows = out.tables[0]["rows"]
    assert len(rows) == 2
    # Sorted desc by avg_geo_score
    assert rows[0]["product_name"] == "精华液"
    assert rows[1]["product_name"] == "爽肤水"
    assert out.metrics["top_product"]["product_name"] == "精华液"
    assert out.metrics["weakest_product"]["product_name"] == "爽肤水"


# ── builder e2e: monthly contains all 6 new sections + 4 legacy ──


@pytest.mark.asyncio
async def test_monthly_report_includes_all_new_sections(db_session, project):
    from app.reports import build_report

    payload = await build_report(db_session, project=project, report_type="monthly")
    types = [s["section_type"] for s in payload["sections"]]
    for required in (
        "executive_summary",
        "pano_score",
        "industry_landscape",
        "brand_performance",
        "product_competitiveness",
        "branding_narrative",
        "competitor_comparison",
        "diagnostic_summary",
    ):
        assert required in types, f"missing {required} in monthly section list"


@pytest.mark.asyncio
async def test_weekly_report_includes_industry_and_brand_perf(db_session, project):
    from app.reports import build_report

    payload = await build_report(db_session, project=project, report_type="weekly")
    types = [s["section_type"] for s in payload["sections"]]
    assert "industry_landscape" in types
    assert "brand_performance" in types
