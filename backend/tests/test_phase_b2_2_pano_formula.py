"""[#1044 B2-2 / B2-3] PANO Score V/S/R/A formula + period delta.

PRD §4.7.4 mandates `PANO = 0.30*V + 0.20*S + 0.25*R + 0.25*A` with each
sub-score in [0, 100]. Before this PR the section computed an arithmetic
mean of geo_score/mention_rate/sov/sentiment — that was not PANO.

These tests assert the headline acceptance rows:
  - AC-4.7-4 pano.total = round(0.30 V + 0.20 S + 0.25 R + 0.25 A, 2)
  - AC-4.7-6 delta is None when prior window has no data, never 0
  - PRD §4.7.4.3 grade bands
  - PRD §4.7.4.4 waterfall shape on `full` variant
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import BrandMention, CitationSource, GeoScoreDaily, Project, User
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def project(db_session: AsyncSession) -> Project:
    u = User(
        id=_new_id(),
        email=f"pano-{uuid.uuid4().hex[:6]}@example.com",
        name="pano",
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
        name="PANO-Project",
        primary_brand_id=42,
        industry_id=1,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p


async def _seed_window(
    db_session: AsyncSession,
    *,
    brand_id: int,
    from_d: date,
    to_d: date,
    mention_rate: float,
    sov: float,
    first_place_rate: float,
    sentiment_score: float,
    citation_rows: int,
    authoritative_rows: int,
) -> None:
    """Seed GeoScoreDaily + BrandMention + CitationSource fixtures for one
    brand across the inclusive [from_d, to_d] window."""
    d = from_d
    while d <= to_d:
        db_session.add(
            GeoScoreDaily(
                brand_id=brand_id,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                mention_rate=mention_rate,
                avg_sov=sov,
                first_place_rate=first_place_rate,
                avg_sentiment_score=sentiment_score,
                total_queries=100,
            )
        )
        d += timedelta(days=1)
    # Seed citations under a brand mention. One BrandMention per row so
    # the FK in CitationSource has a target.
    base_response = 7000 + brand_id * 10
    for i in range(citation_rows):
        bm = BrandMention(
            response_id=base_response + i,
            brand_id=brand_id,
            brand_name="X",
            sentiment="positive",
            sentiment_score=sentiment_score,
            created_at=datetime.combine(from_d, datetime.min.time()),
        )
        db_session.add(bm)
        await db_session.flush()
        is_auth = i < authoritative_rows
        db_session.add(
            CitationSource(
                response_id=bm.response_id,
                mention_id=bm.id,
                url=f"https://d{i}.example.com/{i}",
                domain=f"d{i}.example.com",
                source_type="wiki" if is_auth else "news",
                created_at=datetime.combine(from_d, datetime.min.time()),
            )
        )
    await db_session.commit()


@pytest.mark.asyncio
async def test_pano_total_matches_weighted_formula(db_session, project):
    """High-V, high-S, high-R brand → PANO close to weighted upper-bound."""
    from app.reports.sections.base import ReportContext
    from app.reports.sections.pano_score import PanoScoreSection

    today = date.today()
    from_d = today - timedelta(days=6)
    await _seed_window(
        db_session,
        brand_id=42,
        from_d=from_d,
        to_d=today,
        mention_rate=0.8,
        sov=0.6,
        first_place_rate=0.5,
        sentiment_score=0.6,
        citation_rows=20,
        authoritative_rows=10,
    )

    ctx = ReportContext(
        session=db_session,
        project=project,
        brand_ids=[42],
        from_date=from_d,
        to_date=today,
        locale="zh-CN",
    )
    out = await PanoScoreSection().render(ctx, variant="full")
    rows = out.tables[0]["rows"]
    assert len(rows) == 1
    row = rows[0]

    # Hand-calc:
    #   V = 0.5*80 + 0.3*60 + 0.2*50 = 40 + 18 + 10 = 68
    #   S = (0.6 + 1)/2 * 100 = 80
    #   cite_norm = 20/200 * 100 = 10; unique_norm = 20/30*100 ≈ 66.67
    #   R = 0.6*10 + 0.4*66.67 = 6 + 26.67 ≈ 32.67
    #   auth_share = 10/20 = 0.5 -> 50; auth_unique 10/30*100 ≈ 33.33
    #   A = 0.5*50 + 0.5*33.33 ≈ 41.67
    #   total = 0.30*68 + 0.20*80 + 0.25*32.67 + 0.25*41.67
    #         = 20.4 + 16 + 8.17 + 10.42 ≈ 54.99
    sub = row["subdim"]
    assert abs(sub["V"] - 68.0) < 0.01
    assert abs(sub["S"] - 80.0) < 0.01
    assert 30 < sub["R"] < 35
    assert 39 < sub["A"] < 44
    expected_total = 0.30 * sub["V"] + 0.20 * sub["S"] + 0.25 * sub["R"] + 0.25 * sub["A"]
    assert abs(row["pano_total"] - round(expected_total, 2)) < 0.01
    assert row["weights"] == {"V": 0.30, "S": 0.20, "R": 0.25, "A": 0.25}


@pytest.mark.asyncio
async def test_pano_delta_is_none_when_no_prior_data(db_session, project):
    """Per AC-4.7-6: delta must be None when prior window has no rows,
    not 0 (else the FE would render '0' instead of '—')."""
    from app.reports.sections.base import ReportContext
    from app.reports.sections.pano_score import PanoScoreSection

    today = date.today()
    from_d = today - timedelta(days=6)
    # Seed current window only — no prior-week rows.
    await _seed_window(
        db_session,
        brand_id=42,
        from_d=from_d,
        to_d=today,
        mention_rate=0.5,
        sov=0.4,
        first_place_rate=0.3,
        sentiment_score=0.2,
        citation_rows=10,
        authoritative_rows=2,
    )
    ctx = ReportContext(
        session=db_session,
        project=project,
        brand_ids=[42],
        from_date=from_d,
        to_date=today,
        locale="zh-CN",
    )
    out = await PanoScoreSection().render(ctx, variant="full")
    row = out.tables[0]["rows"][0]
    assert row["delta"]["total"] is None
    assert row["delta"]["V"] is None
    assert row["delta"]["contribution"] is None


@pytest.mark.asyncio
async def test_pano_delta_computes_against_prior_period(db_session, project):
    """When prior window has data, delta reflects the diff and the
    waterfall.contribution reflects weighted contribution per subdim."""
    from app.reports.sections.base import ReportContext
    from app.reports.sections.pano_score import PanoScoreSection

    today = date.today()
    cur_from = today - timedelta(days=6)
    prior_from = cur_from - timedelta(days=7)
    prior_to = cur_from - timedelta(days=1)
    # Prior: V/S weaker
    await _seed_window(
        db_session,
        brand_id=42,
        from_d=prior_from,
        to_d=prior_to,
        mention_rate=0.4,
        sov=0.3,
        first_place_rate=0.2,
        sentiment_score=0.0,
        citation_rows=5,
        authoritative_rows=1,
    )
    # Current: V/S stronger
    await _seed_window(
        db_session,
        brand_id=42,
        from_d=cur_from,
        to_d=today,
        mention_rate=0.7,
        sov=0.5,
        first_place_rate=0.4,
        sentiment_score=0.4,
        citation_rows=10,
        authoritative_rows=3,
    )

    ctx = ReportContext(
        session=db_session,
        project=project,
        brand_ids=[42],
        from_date=cur_from,
        to_date=today,
        locale="zh-CN",
    )
    out = await PanoScoreSection().render(ctx, variant="full")
    row = out.tables[0]["rows"][0]
    delta = row["delta"]
    # Current V > prior V → delta_V > 0
    assert delta["V"] > 0
    assert delta["S"] > 0
    # delta.total ≈ 0.30*dV + 0.20*dS + 0.25*dR + 0.25*dA
    contrib = delta["contribution"]
    recomputed = contrib["V"] + contrib["S"] + contrib["R"] + contrib["A"]
    assert abs(delta["total"] - recomputed) < 0.05
    # Waterfall must be present on `full` variant
    wf = out.metrics["waterfall"]
    assert wf["delta_total"] == delta["total"]
    assert len(wf["subscores"]) == 4
    assert [s["dim"] for s in wf["subscores"]] == ["V", "S", "R", "A"]


@pytest.mark.asyncio
async def test_pano_grade_bands(db_session, project):
    """PRD §4.7.4.3: S≥90, A 80-89, B 70-79, C 60-69, D<60."""
    from app.reports.sections.pano_score import _grade

    assert _grade(95) == "S"
    assert _grade(89.99) == "A"
    assert _grade(80) == "A"
    assert _grade(70) == "B"
    assert _grade(60) == "C"
    assert _grade(59.99) == "D"
    assert _grade(0) == "D"


@pytest.mark.asyncio
async def test_pano_weights_locked_to_canonical(db_session, project):
    """AC-4.7-4: weights are 0.30/0.20/0.25/0.25 and must surface in
    payload (so consumers can audit them without re-reading code)."""
    from app.reports.sections.pano_score import W_A, W_R, W_S, W_V

    assert (W_V, W_S, W_R, W_A) == (0.30, 0.20, 0.25, 0.25)
    assert abs(W_V + W_S + W_R + W_A - 1.0) < 1e-9


@pytest.mark.asyncio
async def test_pano_no_data_brand_excluded_from_rows(db_session, project):
    """A brand with no GeoScoreDaily rows in the window must NOT be ranked
    at score 0 (cf. competitor_comparison fix B2-9)."""
    from app.reports.sections.base import ReportContext
    from app.reports.sections.pano_score import PanoScoreSection

    today = date.today()
    from_d = today - timedelta(days=6)
    # Brand 42: has data. Brand 99: no data.
    await _seed_window(
        db_session,
        brand_id=42,
        from_d=from_d,
        to_d=today,
        mention_rate=0.5,
        sov=0.4,
        first_place_rate=0.3,
        sentiment_score=0.2,
        citation_rows=5,
        authoritative_rows=1,
    )
    ctx = ReportContext(
        session=db_session,
        project=project,
        brand_ids=[42, 99],
        from_date=from_d,
        to_date=today,
        locale="zh-CN",
    )
    out = await PanoScoreSection().render(ctx, variant="full")
    rows = out.tables[0]["rows"]
    bids = [r["brand_id"] for r in rows]
    assert 42 in bids
    assert 99 not in bids
