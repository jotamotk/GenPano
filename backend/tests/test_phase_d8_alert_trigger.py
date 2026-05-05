"""Phase D.8 — diagnostic→alert trigger.

P0/P1 diagnostics auto-create an `alerts` row so the FE bell badge
surfaces them. Lower severities don't trigger.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import Alert, Diagnostic, GeoScoreDaily, Project, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.alerts.triggers import (
    create_alert_from_diagnostic,
    resolve_alert_for_diagnostic,
)
from app.diagnostics.evaluator import evaluate_project

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"d8-{uuid.uuid4().hex[:6]}@example.com",
        name="D8",
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
    p = Project(id=_new_id(), user_id=user.id, name="P", primary_brand_id=505)
    db_session.add(p)
    await db_session.commit()
    return p


# ── unit: create_alert_from_diagnostic ────────────────────────────


@pytest.mark.asyncio
async def test_create_alert_for_p0(db_session, project):
    diag = Diagnostic(
        id=_new_id(),
        project_id=project.id,
        brand_id=505,
        category="pano_score_drop",
        severity="P0",
        type="brand",
        title="GEO score crashed",
        description="dropped 50% in 30d",
        evidence={"metric": "geo_score"},
        reader_hints=["manager"],
        rule_id="geo_score_drop_v1",
        status="open",
    )
    db_session.add(diag)
    await db_session.commit()

    alert = await create_alert_from_diagnostic(db_session, diag)
    assert alert is not None
    assert alert.severity == "P0"
    assert alert.source == "diagnostic"
    assert alert.source_ref_id == diag.id
    assert alert.scope == "user"
    assert alert.title == "GEO score crashed"


@pytest.mark.asyncio
async def test_create_alert_for_p1(db_session, project):
    diag = Diagnostic(
        id=_new_id(),
        project_id=project.id,
        brand_id=505,
        category="visibility_decline",
        severity="P1",
        type="brand",
        title="visibility down",
        evidence={},
        reader_hints=["operator"],
        rule_id="visibility_decline_v1",
        status="open",
    )
    db_session.add(diag)
    await db_session.commit()
    alert = await create_alert_from_diagnostic(db_session, diag)
    assert alert is not None
    assert alert.severity == "P1"


@pytest.mark.asyncio
async def test_no_alert_for_p2(db_session, project):
    diag = Diagnostic(
        id=_new_id(),
        project_id=project.id,
        brand_id=505,
        category="visibility_decline",
        severity="P2",
        type="brand",
        title="mild dip",
        evidence={},
        reader_hints=["operator"],
        rule_id="visibility_decline_v1",
        status="open",
    )
    db_session.add(diag)
    await db_session.commit()
    alert = await create_alert_from_diagnostic(db_session, diag)
    assert alert is None


@pytest.mark.asyncio
async def test_no_alert_for_p3(db_session, project):
    diag = Diagnostic(
        id=_new_id(),
        project_id=project.id,
        brand_id=505,
        category="visibility_decline",
        severity="P3",
        type="brand",
        title="minor",
        evidence={},
        reader_hints=["operator"],
        rule_id="visibility_decline_v1",
        status="open",
    )
    db_session.add(diag)
    await db_session.commit()
    alert = await create_alert_from_diagnostic(db_session, diag)
    assert alert is None


# ── resolve_alert_for_diagnostic ──────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_alert_when_diagnostic_resolved(db_session, project):
    diag = Diagnostic(
        id=_new_id(),
        project_id=project.id,
        brand_id=505,
        category="visibility_decline",
        severity="P1",
        type="brand",
        title="x",
        evidence={},
        reader_hints=["operator"],
        rule_id="visibility_decline_v1",
        status="open",
    )
    db_session.add(diag)
    await db_session.commit()
    await create_alert_from_diagnostic(db_session, diag)

    # Move diagnostic to resolved
    diag.status = "resolved"
    await db_session.commit()
    n = await resolve_alert_for_diagnostic(db_session, diag)
    assert n == 1

    a = (await db_session.execute(select(Alert).where(Alert.source_ref_id == diag.id))).scalar_one()
    assert a.status == "resolved"
    assert a.resolved_at is not None


@pytest.mark.asyncio
async def test_resolve_noop_when_diagnostic_not_resolved(db_session, project):
    diag = Diagnostic(
        id=_new_id(),
        project_id=project.id,
        brand_id=505,
        category="visibility_decline",
        severity="P1",
        type="brand",
        title="x",
        evidence={},
        reader_hints=["operator"],
        rule_id="visibility_decline_v1",
        status="open",
    )
    db_session.add(diag)
    await db_session.commit()
    n = await resolve_alert_for_diagnostic(db_session, diag)
    assert n == 0


# ── e2e: evaluate_project auto-triggers alerts ───────────────────


@pytest.mark.asyncio
async def test_evaluate_project_creates_alert_for_p1_diagnostic(db_session, user):
    project = Project(id=_new_id(), user_id=user.id, name="P-eval", primary_brand_id=606)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    today = datetime.now().date()
    # Build a strong visibility decline: prior 0.8 -> current 0.3
    for i in range(30):
        d = today - timedelta(days=59 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=606,
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
                brand_id=606,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                mention_rate=0.3,
                avg_geo_score=40.0,
                total_queries=100,
            )
        )
    await db_session.commit()

    inserted = await evaluate_project(db_session, project)
    p1_or_p0 = [d for d in inserted if d.severity in {"P0", "P1"}]
    assert len(p1_or_p0) >= 1

    alerts = list(
        (await db_session.execute(select(Alert).where(Alert.project_id == project.id)))
        .scalars()
        .all()
    )
    # At least one alert exists for the P0/P1 diagnostics
    assert len(alerts) >= 1
    for a in alerts:
        assert a.source == "diagnostic"
        assert a.severity in {"P0", "P1"}
        assert a.scope == "user"
        # source_ref_id is one of the inserted diagnostics
        assert a.source_ref_id in {d.id for d in inserted}
