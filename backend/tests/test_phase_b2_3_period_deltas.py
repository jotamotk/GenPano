"""[#1044 B2-3] Period-over-period delta for executive_summary +
competitor_comparison sections.

PRD §4.7.4.6: prior-period diff per metric. When prior window has zero
samples, delta MUST be None (frontend renders '—'), never 0 — emitting 0
would mislead the reader into "no change" when reality is "no comparison
data".

PRD AC-4.7-6 binds this for every metric in every section. This test
file covers the executive_summary + competitor_comparison sections;
pano_score is covered separately in test_phase_b2_2_pano_formula.py.
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import GeoScoreDaily, Project, ProjectCompetitor, User
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    u = User(
        id=_new_id(),
        email=f"b23-{uuid.uuid4().hex[:6]}@example.com",
        name="b23",
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
        name="B23-Project",
        primary_brand_id=42,
        industry_id=1,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p


async def _seed(
    db_session: AsyncSession,
    *,
    brand_id: int,
    from_d: date,
    to_d: date,
    geo_score: float,
    mention_rate: float,
    sov: float,
) -> None:
    d = from_d
    while d <= to_d:
        db_session.add(
            GeoScoreDaily(
                brand_id=brand_id,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=geo_score,
                mention_rate=mention_rate,
                avg_sov=sov,
                total_queries=100,
            )
        )
        d += timedelta(days=1)
    await db_session.commit()


# ── executive_summary ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exec_summary_delta_none_when_no_prior(db_session, project):
    """Current window has data, prior window does not → delta keys are None."""
    from app.reports.sections.base import ReportContext
    from app.reports.sections.executive_summary import ExecutiveSummarySection

    today = date.today()
    from_d = today - timedelta(days=6)
    await _seed(
        db_session,
        brand_id=42,
        from_d=from_d,
        to_d=today,
        geo_score=80,
        mention_rate=0.5,
        sov=0.3,
    )
    ctx = ReportContext(
        session=db_session,
        project=project,
        brand_ids=[42],
        from_date=from_d,
        to_date=today,
        locale="zh-CN",
    )
    out = await ExecutiveSummarySection().render(ctx, variant="full")
    delta = out.metrics["delta"]
    assert delta["geo_score"] is None
    assert delta["mention_rate"] is None
    assert delta["sov"] is None
    # Summary must indicate "no comparison" — not 0
    assert "0" not in out.summary or "无对照" in out.summary


@pytest.mark.asyncio
async def test_exec_summary_delta_against_prior_period(db_session, project):
    """Prior window seeded with weaker numbers → delta > 0 for all metrics."""
    from app.reports.sections.base import ReportContext
    from app.reports.sections.executive_summary import ExecutiveSummarySection

    today = date.today()
    cur_from = today - timedelta(days=6)
    prior_from = cur_from - timedelta(days=7)
    prior_to = cur_from - timedelta(days=1)
    await _seed(
        db_session,
        brand_id=42,
        from_d=prior_from,
        to_d=prior_to,
        geo_score=60,
        mention_rate=0.3,
        sov=0.2,
    )
    await _seed(
        db_session,
        brand_id=42,
        from_d=cur_from,
        to_d=today,
        geo_score=80,
        mention_rate=0.5,
        sov=0.3,
    )
    ctx = ReportContext(
        session=db_session,
        project=project,
        brand_ids=[42],
        from_date=cur_from,
        to_date=today,
        locale="zh-CN",
    )
    out = await ExecutiveSummarySection().render(ctx, variant="full")
    delta = out.metrics["delta"]
    assert delta["geo_score"] == pytest.approx(20.0, abs=0.05)
    assert delta["mention_rate"] == pytest.approx(0.2, abs=0.005)
    assert delta["sov"] == pytest.approx(0.1, abs=0.005)
    # Prior window meta surfaced for auditability
    assert out.metrics["prior_period"]["from"] == prior_from.isoformat()
    assert out.metrics["prior_period"]["to"] == prior_to.isoformat()


@pytest.mark.asyncio
async def test_exec_summary_empty_state_unchanged(db_session, project):
    """No brand_ids → existing empty-state behavior preserved."""
    from app.reports.sections.base import ReportContext
    from app.reports.sections.executive_summary import ExecutiveSummarySection

    today = date.today()
    ctx = ReportContext(
        session=db_session,
        project=project,
        brand_ids=[],
        from_date=today - timedelta(days=6),
        to_date=today,
        locale="zh-CN",
    )
    out = await ExecutiveSummarySection().render(ctx, variant="full")
    assert "暂无品牌数据" in out.summary


# ── competitor_comparison ────────────────────────────────────────


@pytest.mark.asyncio
async def test_competitor_rows_carry_delta(db_session, project):
    """Each ranked row exposes per-metric delta; primary brand's delta
    reflects its own prior-window change."""
    from app.reports.sections.base import ReportContext
    from app.reports.sections.competitor_comparison import CompetitorComparisonSection

    today = date.today()
    cur_from = today - timedelta(days=6)
    prior_from = cur_from - timedelta(days=7)
    prior_to = cur_from - timedelta(days=1)

    # Pin a competitor
    db_session.add(ProjectCompetitor(project_id=project.id, brand_id=43))
    await db_session.commit()

    # Primary (42): prior weak, current strong
    await _seed(
        db_session,
        brand_id=42,
        from_d=prior_from,
        to_d=prior_to,
        geo_score=50,
        mention_rate=0.3,
        sov=0.2,
    )
    await _seed(
        db_session,
        brand_id=42,
        from_d=cur_from,
        to_d=today,
        geo_score=75,
        mention_rate=0.5,
        sov=0.3,
    )
    # Competitor (43): prior strong, current weak
    await _seed(
        db_session,
        brand_id=43,
        from_d=prior_from,
        to_d=prior_to,
        geo_score=80,
        mention_rate=0.6,
        sov=0.5,
    )
    await _seed(
        db_session,
        brand_id=43,
        from_d=cur_from,
        to_d=today,
        geo_score=70,
        mention_rate=0.5,
        sov=0.4,
    )

    ctx = ReportContext(
        session=db_session,
        project=project,
        brand_ids=[42, 43],
        from_date=cur_from,
        to_date=today,
        locale="zh-CN",
    )
    out = await CompetitorComparisonSection().render(ctx, variant="full")
    rows = out.tables[0]["rows"]
    by_id = {r["brand_id"]: r for r in rows}
    assert by_id[42]["delta"]["geo_score"] == pytest.approx(25.0, abs=0.05)
    assert by_id[42]["delta"]["sov"] == pytest.approx(0.1, abs=0.005)
    assert by_id[43]["delta"]["geo_score"] == pytest.approx(-10.0, abs=0.05)
    assert by_id[43]["delta"]["sov"] == pytest.approx(-0.1, abs=0.005)


@pytest.mark.asyncio
async def test_competitor_delta_none_when_prior_empty(db_session, project):
    """Newly-added competitor with no prior-window data → delta=None,
    not 0 — defends against "newcomer falsely flagged as flat"."""
    from app.reports.sections.base import ReportContext
    from app.reports.sections.competitor_comparison import CompetitorComparisonSection

    today = date.today()
    cur_from = today - timedelta(days=6)

    db_session.add(ProjectCompetitor(project_id=project.id, brand_id=43))
    await db_session.commit()

    # Primary has current window data
    await _seed(
        db_session,
        brand_id=42,
        from_d=cur_from,
        to_d=today,
        geo_score=75,
        mention_rate=0.5,
        sov=0.3,
    )
    # Competitor has ONLY current window data (no prior)
    await _seed(
        db_session,
        brand_id=43,
        from_d=cur_from,
        to_d=today,
        geo_score=70,
        mention_rate=0.5,
        sov=0.4,
    )

    ctx = ReportContext(
        session=db_session,
        project=project,
        brand_ids=[42, 43],
        from_date=cur_from,
        to_date=today,
        locale="zh-CN",
    )
    out = await CompetitorComparisonSection().render(ctx, variant="full")
    rows = out.tables[0]["rows"]
    by_id = {r["brand_id"]: r for r in rows}
    assert by_id[42]["delta"]["geo_score"] is None
    assert by_id[43]["delta"]["geo_score"] is None
    assert by_id[42]["delta"]["sov"] is None
    assert by_id[43]["delta"]["sov"] is None
