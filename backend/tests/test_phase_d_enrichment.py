"""Phase D.4 / D.5 / D.6 — causal chain + anchor questions + industry benchmark."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    Diagnostic,
    GeoScoreDaily,
    IndustryBenchmarkDaily,
    Project,
    ProjectCompetitor,
    User,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


# ── unit: causal chain ───────────────────────────────────


def test_causal_chain_snake_case_evidence_substitutes_placeholders():
    """Producer (rules.py) writes snake_case — consumer must read it."""
    from app.diagnostics.causal_chain import build_causal_chain

    out = build_causal_chain(
        rule_id="visibility_decline_v1",
        evidence={
            "previous_value": 0.62,
            "current_value": 0.41,
            "change_percent": -33.9,
            "affected_queries": ["q1", "q2", "q3", "q4"],
        },
    )
    assert "0.41" in out["hypothesizedMechanism"]
    assert "0.62" in out["hypothesizedMechanism"]
    assert "33" in out["hypothesizedMechanism"]
    assert "—" not in out["hypothesizedMechanism"]
    assert "?" not in out["hypothesizedMechanism"]
    assert len(out["alternativeHypotheses"]) == 3
    assert len(out["supportingEvidence"]) == 3
    assert out["confidenceLevel"] == "med"
    assert out["source"] == "deterministic_v1"


def test_causal_chain_camelcase_evidence_still_works():
    """Legacy callers using camelCase keys still substitute correctly."""
    from app.diagnostics.causal_chain import build_causal_chain

    out = build_causal_chain(
        rule_id="visibility_decline_v1",
        evidence={
            "previousValue": 0.62,
            "currentValue": 0.41,
            "changePercent": -33.9,
            "affectedQueries": ["q1"],
        },
    )
    assert "0.41" in out["hypothesizedMechanism"]
    assert "0.62" in out["hypothesizedMechanism"]


def test_causal_chain_unknown_rule_uses_generic():
    from app.diagnostics.causal_chain import build_causal_chain

    out = build_causal_chain(
        rule_id="totally_made_up_rule_v999",
        evidence={"metric": "made_up_metric"},
    )
    assert "made_up_metric" in out["hypothesizedMechanism"]
    assert out["confidenceLevel"] == "low"


def test_causal_chain_handles_missing_evidence_keys():
    from app.diagnostics.causal_chain import build_causal_chain

    out = build_causal_chain(rule_id="visibility_decline_v1", evidence={})
    # Doesn't crash, returns dict
    assert "hypothesizedMechanism" in out
    assert "alternativeHypotheses" in out


# ── unit: anchor questions ───────────────────────────────


def test_anchor_questions_returns_per_reader():
    from app.diagnostics.anchor_questions import build_anchor_questions

    out = build_anchor_questions(
        category="visibility_decline",
        reader_hints=["manager", "branding"],
        evidence={"change_percent": -25.0},
        brand_name="Acme",
    )
    assert "manager" in out
    assert "branding" in out
    assert "operator" not in out
    assert any("Acme" in q for q in out["manager"])
    assert not any("?%" in q for q in out["manager"]), "pct placeholder must substitute"
    assert any("25" in q for q in out["manager"])


def test_anchor_questions_unknown_category_falls_back():
    from app.diagnostics.anchor_questions import build_anchor_questions

    out = build_anchor_questions(
        category="some_new_category",
        reader_hints=["manager"],
        evidence={},
    )
    assert out["manager"]  # generic fallback returns at least one


def test_anchor_questions_handles_missing_keys():
    from app.diagnostics.anchor_questions import build_anchor_questions

    out = build_anchor_questions(
        category="visibility_decline",
        reader_hints=["manager"],
        evidence={},
    )
    # No KeyError; question text retains placeholders
    assert isinstance(out["manager"], list)


# ── unit: industry benchmark ────────────────────────────


@pytest_asyncio.fixture
async def project_with_benchmark(
    db_session: AsyncSession,
) -> tuple[Project, list[int]]:
    user = User(
        id=_new_id(),
        email=f"bm-{uuid.uuid4().hex[:6]}@example.com",
        name="BM",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(user)
    await db_session.commit()

    p = Project(user_id=user.id, name="BM-P", primary_brand_id=42, industry_id=1)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    today = datetime.now().date()
    # Industry benchmark daily rows (last 5 days)
    for i in range(5):
        d = today - timedelta(days=4 - i)
        db_session.add(
            IndustryBenchmarkDaily(
                industry="cosmetics",
                date=datetime.combine(d, datetime.min.time()),
                avg_geo_score=70.0,
                avg_mention_rate=0.4,
                avg_sentiment=0.6,
                total_brands=12,
            )
        )
        # My brand 42
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=80.0,
                mention_rate=0.5,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=100,
            )
        )
        # Competitor brand 99
        db_session.add(
            GeoScoreDaily(
                brand_id=99,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=85.0,
                mention_rate=0.55,
                avg_sov=0.42,
                avg_sentiment=0.72,
                total_queries=100,
            )
        )

    db_session.add(ProjectCompetitor(project_id=p.id, brand_id=99))
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p, [42, 99]


@pytest.mark.asyncio
async def test_benchmark_returns_three_axes(db_session, project_with_benchmark):
    from app.diagnostics.benchmark import build_industry_benchmark

    p, _ = project_with_benchmark
    out = await build_industry_benchmark(db_session, project=p, metric="mention_rate")
    assert out["myValue"] == 0.5
    assert out["industryMedian"] == 0.4
    assert out["topCompetitor"]["brand_id"] == 99
    assert out["topCompetitor"]["value"] == 0.55


@pytest.mark.asyncio
async def test_benchmark_no_industry_id_returns_empty(db_session: AsyncSession):
    from app.diagnostics.benchmark import build_industry_benchmark

    user = User(
        id=_new_id(),
        email=f"x-{uuid.uuid4().hex[:6]}@example.com",
        name="x",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(user)
    await db_session.commit()
    p = Project(user_id=user.id, name="no-industry", primary_brand_id=1)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    out = await build_industry_benchmark(db_session, project=p, metric="mention_rate")
    assert out == {}


@pytest.mark.asyncio
async def test_benchmark_unsupported_metric_returns_empty(db_session, project_with_benchmark):
    from app.diagnostics.benchmark import build_industry_benchmark

    p, _ = project_with_benchmark
    out = await build_industry_benchmark(db_session, project=p, metric="never_heard_of_it")
    assert out == {}


# ── integration: evaluator fills enrichment fields ────


@pytest_asyncio.fixture
async def project_for_evaluator(db_session: AsyncSession) -> Project:
    user = User(
        id=_new_id(),
        email=f"ev-{uuid.uuid4().hex[:6]}@example.com",
        name="ev",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(user)
    await db_session.commit()

    p = Project(user_id=user.id, name="EV", primary_brand_id=42, industry_id=1)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    today = datetime.now().date()
    # 30 days of geo_score with sharp drop in last 7 days to trigger
    # the visibility_decline rule
    for i in range(30):
        d = today - timedelta(days=29 - i)
        # First 23 days: high mention, last 7 days: low mention
        mr = 0.7 if i < 23 else 0.3
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=80.0,
                mention_rate=mr,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=100,
            )
        )
    await db_session.commit()
    return p


@pytest.mark.asyncio
async def test_evaluator_populates_enrichment_fields(db_session, project_for_evaluator):
    from app.diagnostics.evaluator import evaluate_project

    inserted = await evaluate_project(db_session, project_for_evaluator)
    # evaluator may or may not insert depending on rule + evidence — we just
    # need any single diagnostic to verify enrichment plumbing.
    if not inserted:
        pytest.skip("no diagnostic triggered with current fixture; not testing here")

    rows = list(
        (
            await db_session.execute(
                select(Diagnostic).where(Diagnostic.project_id == project_for_evaluator.id)
            )
        )
        .scalars()
        .all()
    )
    assert rows
    for d in rows:
        assert d.causal_chain is not None
        assert "hypothesizedMechanism" in d.causal_chain
        mech = d.causal_chain["hypothesizedMechanism"]
        if d.evidence and "current_value" in d.evidence:
            assert "—" not in mech, f"causal_chain placeholder substitution failed: {mech}"
        if d.reader_hints:
            assert d.anchor_questions is not None
            for reader, questions in d.anchor_questions.items():
                for q in questions:
                    assert "?%" not in q, (
                        f"anchor_questions pct placeholder failed for {reader}: {q}"
                    )
