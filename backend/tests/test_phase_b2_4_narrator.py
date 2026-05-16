"""[#1044 B2-4] LLM narrator pipeline + deterministic fallback (PRD §4.7.3).

Acceptance:
  - every section in the payload now has a non-null `narrative` field
    (modulo cta, which uses summary as its prose)
  - narrative text is meaningfully distinct from `summary` (signals
    real prose layer, not duplication)
  - fallback runs when no LLM_NARRATIVE_PROVIDER is configured
  - LLM hook stub returns None today; fallback covers the gap so
    payload never ships with empty narratives
  - dominant-subdim attribution lands when one V/S/R/A delta exceeds
    the noise floor (≥ 0.05 contribution)
"""

from __future__ import annotations

import os
import uuid
from datetime import date, timedelta

import pytest
import pytest_asyncio
from genpano_models import GeoScoreDaily, Project, User
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def project_with_data(db_session: AsyncSession) -> Project:
    u = User(
        id=_new_id(),
        email=f"narr-{uuid.uuid4().hex[:6]}@example.com",
        name="narr",
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
        name="P-narr",
        primary_brand_id=42,
        industry_id=1,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    today = date.today()
    for i in range(14):
        d = today - timedelta(days=13 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=d,
                target_llm="chatgpt",
                avg_geo_score=80.0,
                mention_rate=0.5,
                avg_sov=0.4,
                avg_sentiment=0.6,
                total_queries=100,
            )
        )
    await db_session.commit()
    return p


# ── narrator unit tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_fallback_executive_summary_zh_with_delta():
    from app.reports.narrator import _fallback_narrative
    from app.reports.sections.base import ReportContext, SectionData

    sec = SectionData(
        section_type="executive_summary",
        title="执行摘要",
        summary="...",
        metrics={
            "geo_score": 75,
            "delta": {"geo_score": 3.0},
            "samples": 7,
        },
    )
    ctx = ReportContext(
        session=None,  # narrator only reads section, not session
        project=None,
        brand_ids=[42],
        from_date=date.today() - timedelta(days=6),
        to_date=date.today(),
        locale="zh-CN",
    )
    out = _fallback_narrative(sec, ctx)
    assert out is not None
    assert "回升" in out
    assert "75" in out
    assert sec.summary not in out  # actually different prose surface


@pytest.mark.asyncio
async def test_fallback_executive_summary_no_prior_data():
    from app.reports.narrator import _fallback_narrative
    from app.reports.sections.base import ReportContext, SectionData

    sec = SectionData(
        section_type="executive_summary",
        title="...",
        summary="...",
        metrics={
            "geo_score": 75,
            "delta": {"geo_score": None},
            "samples": 7,
        },
    )
    ctx = ReportContext(
        session=None,
        project=None,
        brand_ids=[42],
        from_date=date.today() - timedelta(days=6),
        to_date=date.today(),
        locale="zh-CN",
    )
    out = _fallback_narrative(sec, ctx)
    assert out is not None
    assert "上一周期无对照" in out


@pytest.mark.asyncio
async def test_fallback_pano_attributes_dominant_subdim():
    from app.reports.narrator import _fallback_narrative
    from app.reports.sections.base import ReportContext, SectionData

    sec = SectionData(
        section_type="pano_score",
        title="...",
        summary="...",
        metrics={
            "primary": {
                "pano_total": 82.5,
                "grade": "A",
                "subdim": {"V": 85, "S": 78, "R": 80, "A": 88},
                "delta": {
                    "total": 4.0,
                    "V": 2.0,
                    "S": 0.5,
                    "R": 1.0,
                    "A": 8.0,
                    "contribution": {
                        "V": 0.6,
                        "S": 0.1,
                        "R": 0.25,
                        "A": 2.0,
                    },
                },
            }
        },
    )
    ctx = ReportContext(
        session=None,
        project=None,
        brand_ids=[],
        from_date=date.today() - timedelta(days=6),
        to_date=date.today(),
        locale="zh-CN",
    )
    out = _fallback_narrative(sec, ctx)
    assert out is not None
    # A has the largest absolute contribution (2.0); narrative should
    # highlight it.
    assert "A" in out
    assert "拉升" in out or "拖累" in out


@pytest.mark.asyncio
async def test_fallback_pano_flat_when_all_contributions_below_noise():
    from app.reports.narrator import _fallback_narrative
    from app.reports.sections.base import ReportContext, SectionData

    sec = SectionData(
        section_type="pano_score",
        title="...",
        summary="...",
        metrics={
            "primary": {
                "pano_total": 70,
                "grade": "B",
                "subdim": {"V": 70, "S": 70, "R": 70, "A": 70},
                "delta": {
                    "total": 0.02,
                    "V": 0.01,
                    "S": 0.01,
                    "R": 0.01,
                    "A": 0.0,
                    "contribution": {
                        "V": 0.003,
                        "S": 0.002,
                        "R": 0.0025,
                        "A": 0.0,
                    },
                },
            }
        },
    )
    ctx = ReportContext(
        session=None,
        project=None,
        brand_ids=[],
        from_date=date.today() - timedelta(days=6),
        to_date=date.today(),
        locale="zh-CN",
    )
    out = _fallback_narrative(sec, ctx)
    assert out is not None
    assert "平稳" in out


@pytest.mark.asyncio
async def test_narrate_passes_through_existing_narrative():
    """Idempotency: section already has narrative → narrator no-op."""
    from app.reports.narrator import narrate
    from app.reports.sections.base import ReportContext, SectionData

    sec = SectionData(
        section_type="executive_summary",
        title="...",
        summary="...",
        narrative="hand-authored prose",
    )
    ctx = ReportContext(
        session=None,
        project=None,
        brand_ids=[],
        from_date=date.today() - timedelta(days=6),
        to_date=date.today(),
        locale="zh-CN",
    )
    out = await narrate(sec, ctx)
    assert out == "hand-authored prose"


@pytest.mark.asyncio
async def test_narrate_falls_back_when_provider_unset(monkeypatch):
    monkeypatch.delenv("LLM_NARRATIVE_PROVIDER", raising=False)
    from app.reports.narrator import narrate
    from app.reports.sections.base import ReportContext, SectionData

    sec = SectionData(
        section_type="executive_summary",
        title="...",
        summary="...",
        metrics={
            "geo_score": 80,
            "delta": {"geo_score": None},
            "samples": 7,
        },
    )
    ctx = ReportContext(
        session=None,
        project=None,
        brand_ids=[42],
        from_date=date.today() - timedelta(days=6),
        to_date=date.today(),
        locale="zh-CN",
    )
    out = await narrate(sec, ctx)
    assert out is not None
    assert len(out) > 0


@pytest.mark.asyncio
async def test_narrate_llm_failure_falls_back(monkeypatch):
    """A configured LLM provider that raises must fall through to the
    deterministic fallback — never let an empty narrative ship."""
    monkeypatch.setenv("LLM_NARRATIVE_PROVIDER", "doubao")
    from app.reports.narrator import narrate
    from app.reports.sections.base import ReportContext, SectionData

    async def boom(*args, **kwargs):
        raise RuntimeError("LLM 5xx")

    monkeypatch.setattr("app.reports.narrator._call_llm", boom)

    sec = SectionData(
        section_type="executive_summary",
        title="...",
        summary="...",
        metrics={
            "geo_score": 80,
            "delta": {"geo_score": 2.0},
            "samples": 7,
        },
    )
    ctx = ReportContext(
        session=None,
        project=None,
        brand_ids=[42],
        from_date=date.today() - timedelta(days=6),
        to_date=date.today(),
        locale="zh-CN",
    )
    out = await narrate(sec, ctx)
    assert out is not None
    assert "2" in out


@pytest.mark.asyncio
async def test_cta_section_has_no_separate_narrative():
    """cta's `summary` IS the prose — narrator returns None so renderers
    don't duplicate."""
    from app.reports.narrator import narrate
    from app.reports.sections.base import ReportContext, SectionData

    sec = SectionData(section_type="cta", title="咨询", summary="...")
    ctx = ReportContext(
        session=None,
        project=None,
        brand_ids=[],
        from_date=date.today() - timedelta(days=6),
        to_date=date.today(),
        locale="zh-CN",
    )
    out = await narrate(sec, ctx)
    assert out is None


# ── builder e2e: narrative shows up on every section ────────────


@pytest.mark.asyncio
async def test_weekly_report_includes_narrative_per_section(db_session, project_with_data):
    from app.reports import build_report

    payload = await build_report(db_session, project=project_with_data, report_type="weekly")
    for section in payload["sections"]:
        # Every section dict carries the new field (even if None for cta)
        assert "narrative" in section
        if section["section_type"] != "cta":
            assert section["narrative"], f"{section['section_type']} narrative empty"
            # Narrative is meaningfully distinct from summary text.
            assert section["narrative"] != section["summary"]
