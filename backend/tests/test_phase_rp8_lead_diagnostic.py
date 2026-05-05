"""Phase RP.8 — lead_diagnostic 4-layer report builder + lead auto-creation."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import Diagnostic, GeoScoreDaily, Project, ReportJob, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"rp8-{uuid.uuid4().hex[:6]}@example.com",
        name="RP8",
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
async def project_with_data(db_session: AsyncSession, user: User) -> Project:
    p = Project(user_id=user.id, name="Lead P", primary_brand_id=42, industry_id=1)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    today = datetime.now().date()
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=70.0 + i * 0.3,
                mention_rate=0.5,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=100,
            )
        )
    await db_session.commit()
    return p


@pytest_asyncio.fixture
async def empty_project(db_session: AsyncSession, user: User) -> Project:
    p = Project(user_id=user.id, name="Empty Lead P", primary_brand_id=99)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p


# ── builder unit ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_lead_diagnostic_returns_4_layers(db_session, project_with_data):
    from app.reports.lead_diagnostic_builder import build_lead_diagnostic

    payload = await build_lead_diagnostic(db_session, project=project_with_data)
    assert payload["report_type"] == "lead_diagnostic"
    assert len(payload["layers"]) == 4
    assert len(payload["sections"]) == 4
    # Layer 1 has metric cards
    assert payload["layers"][0]["metrics"]["geo_score"] > 0
    # Layer 4 has CTA
    assert "cta_link" in payload["layers"][3]["metrics"]


@pytest.mark.asyncio
async def test_build_lead_diagnostic_empty_project(db_session, empty_project):
    from app.reports.lead_diagnostic_builder import build_lead_diagnostic

    payload = await build_lead_diagnostic(db_session, project=empty_project)
    # Layer 3 directional summary suggests starting collection
    layer3 = payload["layers"][2]
    assert "采集" in layer3["summary"] or "collection" in layer3["summary"].lower()


@pytest.mark.asyncio
async def test_build_lead_diagnostic_top_diagnostics(db_session, project_with_data):
    from app.reports.lead_diagnostic_builder import build_lead_diagnostic

    db_session.add_all(
        [
            Diagnostic(
                id=_new_id(),
                project_id=project_with_data.id,
                category="visibility_decline",
                severity="P0",
                type="brand",
                title="提及率断崖式下跌",
                rule_id="visibility_decline_v1",
                evidence={},
                reader_hints=["manager"],
                status="open",
                detected_at=_now(),
            ),
            Diagnostic(
                id=_new_id(),
                project_id=project_with_data.id,
                category="sentiment_drop",
                severity="P1",
                type="brand",
                title="情感分跌破阈值",
                rule_id="sentiment_drop_v1",
                evidence={},
                reader_hints=["manager"],
                status="open",
                detected_at=_now(),
            ),
            Diagnostic(
                id=_new_id(),
                project_id=project_with_data.id,
                category="topic_loss",
                severity="P3",  # excluded — only P0/P1
                type="brand",
                title="低优先级",
                rule_id="topic_loss_v1",
                evidence={},
                reader_hints=["manager"],
                status="open",
                detected_at=_now(),
            ),
        ]
    )
    await db_session.commit()

    payload = await build_lead_diagnostic(db_session, project=project_with_data)
    layer2 = payload["layers"][1]
    assert layer2["tables"]
    rows = layer2["tables"][0]["rows"]
    assert len(rows) == 2  # P0 + P1 only
    severities = {r["severity"] for r in rows}
    assert severities == {"P0", "P1"}


@pytest.mark.asyncio
async def test_build_lead_diagnostic_en_locale(db_session, project_with_data):
    from app.reports.lead_diagnostic_builder import build_lead_diagnostic

    payload = await build_lead_diagnostic(db_session, project=project_with_data, locale="en-US")
    # Headings in English
    titles = [layer["title"] for layer in payload["layers"]]
    assert "Current State" in titles
    assert "Direction" in titles
    assert "Next Step" in titles


# ── endpoint integration ────────────────────────────────────


@pytest.mark.asyncio
async def test_create_lead_diagnostic_via_endpoint(client, user, project_with_data):
    resp = await client.post(
        f"/api/v1/projects/{project_with_data.id}/reports",
        headers=_bearer(user),
        json={"report_type": "lead_diagnostic", "locale": "zh-CN"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "done"
    assert body["payload"]["report_type"] == "lead_diagnostic"
    assert len(body["payload"]["layers"]) == 4


@pytest.mark.asyncio
async def test_download_lead_diagnostic_markdown(client, user, project_with_data):
    rid = (
        await client.post(
            f"/api/v1/projects/{project_with_data.id}/reports",
            headers=_bearer(user),
            json={"report_type": "lead_diagnostic"},
        )
    ).json()["id"]

    resp = await client.get(
        f"/api/v1/projects/{project_with_data.id}/reports/{rid}/download?format=markdown",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.text
    assert "LEAD_DIAGNOSTIC" in body
    # 4 layer headings present
    assert body.count("##") >= 4


# ── lead submission auto-creates report ──────────────────────


@pytest.mark.asyncio
async def test_submit_lead_with_project_creates_lead_diagnostic_job(
    client, user, project_with_data, db_session: AsyncSession
):
    resp = await client.post(
        "/api/v1/leads/",
        headers=_bearer(user),
        json={
            "source": "contact_form",
            "project_id": project_with_data.id,
            "context": {"phone": "+86 13800000000"},
        },
    )
    assert resp.status_code == 201

    # ReportJob row created automatically
    rows = list(
        (
            await db_session.execute(
                select(ReportJob).where(
                    ReportJob.project_id == project_with_data.id,
                    ReportJob.scope.like("%lead_diagnostic%"),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].status == "done"
    assert rows[0].created_by == user.id


@pytest.mark.asyncio
async def test_submit_lead_no_project_skips_report(client, user, db_session: AsyncSession):
    """Anonymous lead without project — no auto-report."""
    resp = await client.post(
        "/api/v1/leads/",
        headers=_bearer(user),
        json={"source": "contact_form"},
    )
    assert resp.status_code == 201

    rows = list(
        (
            await db_session.execute(
                select(ReportJob).where(
                    ReportJob.scope.like("%lead_diagnostic%"),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_submit_lead_unknown_project_skips_report(client, user, db_session: AsyncSession):
    """Lead with non-existent project_id — submit OK but no auto-report."""
    resp = await client.post(
        "/api/v1/leads/",
        headers=_bearer(user),
        json={
            "source": "contact_form",
            "project_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert resp.status_code == 201

    rows = list(
        (
            await db_session.execute(
                select(ReportJob).where(
                    ReportJob.scope.like("%lead_diagnostic%"),
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 0
