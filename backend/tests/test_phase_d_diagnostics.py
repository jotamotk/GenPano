"""Phase D — diagnostics rule engine."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import BrandMention, Diagnostic, GeoScoreDaily, Project, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.diagnostics.evaluator import evaluate_project
from app.diagnostics.rules import (
    REGISTRY,
    GeoScoreDropRule,
    NegativeSentimentGrowthRule,
    VisibilityDeclineRule,
)

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"d-{uuid.uuid4().hex[:6]}@example.com",
        name="Diag User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


def test_registry_has_3_rules():
    assert len(REGISTRY) == 25
    assert VisibilityDeclineRule in REGISTRY
    assert NegativeSentimentGrowthRule in REGISTRY
    assert GeoScoreDropRule in REGISTRY


def test_rule_ids_versioned():
    """Rule IDs are namespaced + versioned for downstream tracking."""
    for cls in REGISTRY:
        rule = cls()
        assert rule.rule_id.endswith("_v1")
        assert rule.category != ""


@pytest.mark.asyncio
async def test_visibility_decline_triggers_p1(db_session, user):
    """0.8 → 0.3 mention_rate drop → P1 visibility_decline."""
    project = Project(user_id=user.id, name="Diag Test", primary_brand_id=77)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    today = datetime.now().date()
    for i in range(30):
        d = today - timedelta(days=59 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=77,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                mention_rate=0.8,
                avg_geo_score=80.0,
                total_queries=100,
            )
        )
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=77,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                mention_rate=0.3,
                avg_geo_score=40.0,
                total_queries=100,
            )
        )
    await db_session.commit()

    inserted = await evaluate_project(db_session, project)
    assert len(inserted) >= 1
    vis = [d for d in inserted if d.category == "visibility_decline"]
    assert len(vis) == 1
    assert vis[0].severity == "P1"  # ≤-30%
    assert vis[0].rule_id == "visibility_decline_v1"


@pytest.mark.asyncio
async def test_negative_sentiment_growth_triggers(db_session, user):
    """50%+ negative mentions → P1 negative_keyword_growth."""
    project = Project(user_id=user.id, name="Neg Test", primary_brand_id=88)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    # 5 positive + 5 negative
    for i in range(5):
        db_session.add(
            BrandMention(
                response_id=5000 + i,
                brand_id=88,
                brand_name="Test",
                sentiment="positive",
                sentiment_score=0.6,
                created_at=datetime.now() - timedelta(days=i),
            )
        )
    for i in range(5):
        db_session.add(
            BrandMention(
                response_id=5100 + i,
                brand_id=88,
                brand_name="Test",
                sentiment="negative",
                sentiment_score=-0.6,
                created_at=datetime.now() - timedelta(days=i),
            )
        )
    await db_session.commit()

    inserted = await evaluate_project(db_session, project)
    neg = [d for d in inserted if d.category == "negative_keyword_growth"]
    assert len(neg) == 1
    assert neg[0].severity == "P1"  # 50% ≥ 40%


@pytest.mark.asyncio
async def test_no_data_no_diagnostic(db_session, user):
    """Project without primary_brand_id → 0 diagnostics."""
    project = Project(user_id=user.id, name="Empty", primary_brand_id=None)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    inserted = await evaluate_project(db_session, project)
    assert inserted == []


@pytest.mark.asyncio
async def test_cooldown_prevents_duplicate(db_session, user):
    """Re-running evaluator within cooldown window doesn't re-insert."""
    project = Project(user_id=user.id, name="Cooldown", primary_brand_id=99)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    today = datetime.now().date()
    for i in range(60):
        d = today - timedelta(days=59 - i)
        rate = 0.8 if i < 30 else 0.3
        db_session.add(
            GeoScoreDaily(
                brand_id=99,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                mention_rate=rate,
                avg_geo_score=80.0 if i < 30 else 30.0,
                total_queries=100,
            )
        )
    await db_session.commit()

    first = await evaluate_project(db_session, project)
    assert len(first) >= 1

    # Re-run immediately — cooldown should kick in
    second = await evaluate_project(db_session, project)
    assert len(second) == 0


@pytest.mark.asyncio
async def test_diagnostic_status_check_constraint(db_session, user):
    """Invalid status raises IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    project = Project(user_id=user.id, name="Cons", primary_brand_id=11)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    db_session.add(
        Diagnostic(
            id=_new_id(),
            project_id=project.id,
            category="x",
            severity="P9",  # invalid
            type="brand",
            title="bad severity",
            evidence={},
            rule_id="invalid_v1",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
