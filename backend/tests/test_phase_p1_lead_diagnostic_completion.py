"""[#1044 P1] B2-7 (lead_diagnostic industry comparison) + B2-8
(lead_diagnostic respects from_date/to_date).

PRD §4.7.2.8 lead_diagnostic Layer 1 advertises a "Current State"
metric block. Pre-fix it only carried the project's own GEO score etc.
With B2-7, when the project has an industry_id and benchmark rows exist
in window, we also surface industry_avg + percentile band so the BD
team can frame the conversation.

PRD §4.7.4 says report APIs accept from_date/to_date. Pre-fix the
lead_diagnostic builder hardcoded a rolling 30-day window. B2-8
plumbs explicit from/to through every caller in service.py.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    GeoScoreDaily,
    IndustryBenchmarkDaily,
    Project,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"ld-{uuid.uuid4().hex[:6]}@example.com",
        name="ld",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def project(db_session: AsyncSession, user: User) -> Project:
    # _resolve_industry_name in industries/service.py maps numeric
    # industry_id to industry name by 1-indexed position in the
    # IndustryBenchmarkDaily table (sorted by row count desc). To make
    # the lookup deterministic for tests, we use industry_id=1 — the
    # most-frequent industry name. Tests below insert benchmark rows
    # for "luxury_beauty" so that name lands at position 1.
    p = Project(
        id=_new_id(),
        user_id=user.id,
        name="LeadDiag P",
        primary_brand_id=42,
        industry_id=1,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p


# ── B2-7 industry comparison ────────────────────────────────


@pytest.mark.asyncio
async def test_b2_7_layer1_includes_industry_avg_when_benchmark_exists(db_session, project):
    """When the project's industry has IndustryBenchmarkDaily rows in
    window, layer 1 metrics surface industry_avg + position band."""
    from app.reports.lead_diagnostic_builder import build_lead_diagnostic

    today = date.today()
    # Brand has its own GEO data
    for i in range(15):
        d = today - timedelta(days=i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=82.0,  # high — should land top_quartile vs 60
                mention_rate=0.5,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=100,
            )
        )
    # Industry benchmark rows — distributed so my 82 lands top_quartile
    for i in range(15):
        d = today - timedelta(days=i)
        db_session.add(
            IndustryBenchmarkDaily(
                industry="luxury_beauty",
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=60.0,
                score_p25=50.0,
                score_p50=60.0,
                score_p75=70.0,
                total_brands=20,
            )
        )
    await db_session.commit()

    payload = await build_lead_diagnostic(db_session, project=project)
    layer1 = payload["layers"][0]
    m = layer1["metrics"]
    assert m["industry_name"] == "luxury_beauty"
    assert m["industry_avg"] == 60.0
    assert m["industry_position"] == "top_quartile"
    # Summary mentions industry baseline
    assert "行业基线" in layer1["summary"] or "Industry baseline" in layer1["summary"]


@pytest.mark.asyncio
async def test_b2_7_layer1_omits_industry_avg_when_no_benchmark_in_window(db_session, project):
    """Industry exists in the DB (resolver returns a name) but the
    benchmark rows for that industry are all outside the report window
    → samples=0, no industry_avg in metrics. Guards against the BD
    deck fabricating a baseline from stale data."""
    from app.reports.lead_diagnostic_builder import build_lead_diagnostic

    today = date.today()
    # Brand data in-window
    for i in range(15):
        d = today - timedelta(days=i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=82.0,
                mention_rate=0.5,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=100,
            )
        )
    # Benchmark exists for the industry but ALL rows are 100+ days old
    # (outside the rolling 30-day window).
    for i in range(5):
        d = today - timedelta(days=100 + i)
        db_session.add(
            IndustryBenchmarkDaily(
                industry="luxury_beauty",
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=60.0,
                score_p50=60.0,
                total_brands=20,
            )
        )
    await db_session.commit()

    payload = await build_lead_diagnostic(db_session, project=project)
    m = payload["layers"][0]["metrics"]
    assert m.get("industry_name") == "luxury_beauty"
    assert m.get("industry_samples") == 0
    assert "industry_avg" not in m


@pytest.mark.asyncio
async def test_b2_7_layer1_skips_industry_when_project_has_no_industry_id(db_session, user):
    """Project without industry_id → no industry block at all (no
    resolver call, no benchmark query)."""
    from app.reports.lead_diagnostic_builder import build_lead_diagnostic

    p = Project(
        id=_new_id(),
        user_id=user.id,
        name="NoInd P",
        primary_brand_id=42,
        industry_id=None,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    today = date.today()
    db_session.add(
        GeoScoreDaily(
            brand_id=42,
            date=datetime.combine(today, datetime.min.time()),
            target_llm="chatgpt",
            avg_geo_score=70.0,
            mention_rate=0.5,
            avg_sov=0.4,
            avg_sentiment=0.7,
            total_queries=100,
        )
    )
    await db_session.commit()

    payload = await build_lead_diagnostic(db_session, project=p)
    m = payload["layers"][0]["metrics"]
    assert "industry_name" not in m


# ── B2-8 from_date / to_date plumbed through ─────────────────


@pytest.mark.asyncio
async def test_b2_8_explicit_from_to_overrides_rolling_window(db_session, project):
    """Pre-fix, build_lead_diagnostic always used the last 30 days. With
    B2-8 the explicit from/to win, so reports for an arbitrary window
    pick up only rows in that window."""
    from app.reports.lead_diagnostic_builder import build_lead_diagnostic

    today = date.today()
    # In-window data: GEO score 90
    for i in range(5):
        d = today - timedelta(days=60 + i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=90.0,
                mention_rate=0.5,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=100,
            )
        )
    # Out-of-window (recent) data: GEO score 10 (very different)
    for i in range(5):
        d = today - timedelta(days=i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=10.0,
                mention_rate=0.5,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=100,
            )
        )
    await db_session.commit()

    # Pin the window to 60-65 days ago — should only see GEO 90.
    explicit_from = today - timedelta(days=65)
    explicit_to = today - timedelta(days=60)
    payload = await build_lead_diagnostic(
        db_session, project=project, from_date=explicit_from, to_date=explicit_to
    )
    layer1 = payload["layers"][0]
    assert layer1["metrics"]["geo_score"] == 90.0
    assert payload["period"]["from"] == explicit_from.isoformat()
    assert payload["period"]["to"] == explicit_to.isoformat()


@pytest.mark.asyncio
async def test_b2_8_default_window_still_30_days_when_no_explicit_dates(db_session, project):
    """Backward compat: callers that don't pass from_date/to_date
    (the lead auto-create path) still get the rolling 30-day window."""
    from app.reports.lead_diagnostic_builder import build_lead_diagnostic

    payload = await build_lead_diagnostic(db_session, project=project)
    from_d = date.fromisoformat(payload["period"]["from"])
    to_d = date.fromisoformat(payload["period"]["to"])
    assert (to_d - from_d).days == 29
    assert to_d == date.today()


@pytest.mark.asyncio
async def test_b2_8_period_label_in_summary_uses_actual_days(db_session, project):
    """Pre-fix, the summary string always said '近 30 天'. With B2-8,
    when the window is e.g. 7 days, the label should match."""
    from app.reports.lead_diagnostic_builder import build_lead_diagnostic

    today = date.today()
    explicit_from = today - timedelta(days=6)
    explicit_to = today
    for i in range(7):
        d = today - timedelta(days=i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=70.0,
                mention_rate=0.5,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=100,
            )
        )
    await db_session.commit()

    payload = await build_lead_diagnostic(
        db_session, project=project, from_date=explicit_from, to_date=explicit_to
    )
    summary = payload["layers"][0]["summary"]
    assert "近 7 天" in summary  # zh default locale
