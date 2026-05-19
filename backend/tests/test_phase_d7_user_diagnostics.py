"""Phase D.7 — user-facing /v1/projects/:id/diagnostics endpoints."""

from __future__ import annotations

import importlib
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import Alert, BrandMention, Diagnostic, GeoScoreDaily, Project, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"d7-{uuid.uuid4().hex[:6]}@example.com",
        name="D7",
        role="paid",
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
    p = Project(
        id=_new_id(),
        user_id=user.id,
        name="D7 Project",
        primary_brand_id=850,
    )
    db_session.add(p)
    await db_session.commit()
    return p


def _make_diag(
    *,
    project: Project,
    severity: str = "P1",
    category: str = "visibility_decline",
    status: str = "open",
    title: str = "issue",
) -> Diagnostic:
    return Diagnostic(
        id=_new_id(),
        project_id=project.id,
        brand_id=project.primary_brand_id,
        category=category,
        severity=severity,
        type="brand",
        title=title,
        evidence={},
        reader_hints=["operator"],
        rule_id=f"{category}_v1",
        status=status,
    )


def _geo_score(
    *,
    brand_id: int = 850,
    avg_geo_score: float = 80.0,
    total_queries: int = 100,
    mention_rate: float = 0.8,
    avg_sov: float = 0.5,
    when: datetime | None = None,
) -> GeoScoreDaily:
    day = (when or datetime.now(UTC).replace(tzinfo=None)).date()
    return GeoScoreDaily(
        brand_id=brand_id,
        date=datetime.combine(day, datetime.min.time()),
        target_llm="chatgpt",
        mention_rate=mention_rate,
        mention_count=int(total_queries * mention_rate) if total_queries > 0 else 0,
        avg_sov=avg_sov,
        avg_position_rank=1.0,
        avg_sentiment_score=0.5,
        citation_rate=0.1,
        avg_visibility=avg_geo_score,
        avg_sentiment=0.5,
        avg_sov_score=avg_sov,
        avg_citation_score=0.1,
        avg_geo_score=avg_geo_score,
        total_queries=total_queries,
    )


def _brand_mention(
    *,
    response_id: int,
    brand_id: int | None,
    brand_name: str,
    when: datetime | None = None,
) -> BrandMention:
    return BrandMention(
        response_id=response_id,
        brand_id=brand_id,
        brand_name=brand_name,
        mention_count=1,
        position_rank=1,
        sentiment="positive",
        sentiment_score=0.5,
        created_at=when or datetime.now(UTC).replace(tzinfo=None),
    )


def _card_by_key(body: dict, metric_key: str) -> dict:
    return next(card for card in body["kpi_cards"] if card["metric_key"] == metric_key)


# ── list ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_diagnostics_default(db_session, client, user, project):
    db_session.add_all(
        [
            _make_diag(project=project, severity="P1"),
            _make_diag(project=project, severity="P2"),
        ]
    )
    await db_session.commit()
    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2


@pytest.mark.asyncio
async def test_no_slash_diagnostics_uses_table_backed_contract(db_session, client, user, project):
    diag = _make_diag(project=project, severity="P1", title="table diagnostic")
    db_session.add(diag)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics",
        headers=_bearer(user),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == diag.id
    assert body["items"][0]["project_id"] == project.id
    assert "counts_by_severity" not in body


@pytest.mark.asyncio
async def test_empty_diagnostics_report_partial_analytics_state(
    db_session,
    client,
    user,
    project,
):
    db_session.add(
        _geo_score(
            brand_id=project.primary_brand_id,
            avg_geo_score=0.0,
            total_queries=0,
            mention_rate=1.0,
            avg_sov=1.0,
        )
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/",
        headers=_bearer(user),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["open_p0_p1_count"] == 0
    assert body["state"] == "partial"
    assert body["state_reason"] == "missing_formula_inputs"
    assert body["formula_status"] == "missing_required_inputs"
    assert "eligible_response_denominator" in body["missing_inputs"]
    assert body["evidence_counts"]["geo_score_daily_rows"] == 1


@pytest.mark.asyncio
async def test_active_p0_p1_wins_when_analytics_summary_fails(
    db_session,
    client,
    user,
    project,
    monkeypatch: pytest.MonkeyPatch,
):
    db_session.add(_make_diag(project=project, severity="P1", status="open"))
    await db_session.commit()

    async def broken_summary(*args, **kwargs):
        raise AssertionError("analytics summary must not run for active P0/P1")

    diagnostics_router_module = importlib.import_module("app.api.v1.diagnostics.router")
    monkeypatch.setattr(diagnostics_router_module, "_analytics_contract_summary", broken_summary)

    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/",
        headers=_bearer(user),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["open_p0_p1_count"] == 1
    assert body["state"] == "active"
    assert body["state_reason"] == "open_p0_p1_diagnostics"


@pytest.mark.asyncio
async def test_low_geo_kpi_is_explicit_attention_without_p0_p1_diagnostic(
    db_session,
    client,
    user,
    project,
):
    now = datetime.now(UTC).replace(tzinfo=None)
    db_session.add(
        _geo_score(
            brand_id=project.primary_brand_id,
            avg_geo_score=0.0,
            total_queries=10,
            mention_rate=0.1,
            avg_sov=0.1,
            when=now,
        )
    )
    db_session.add_all(
        [
            _brand_mention(
                response_id=127001,
                brand_id=project.primary_brand_id,
                brand_name="Primary",
                when=now,
            ),
            _brand_mention(
                response_id=127001,
                brand_id=999,
                brand_name="Competitor",
                when=now,
            ),
        ]
    )
    await db_session.commit()

    overview = await client.get(
        f"/api/v1/projects/{project.id}/overview",
        headers=_bearer(user),
    )
    assert overview.status_code == 200, overview.text
    geo_card = _card_by_key(overview.json(), "geo_score")
    assert geo_card["value"] == 0.0
    assert geo_card["formula_status"] == "ok"
    assert geo_card["state"] == "attention"
    assert geo_card["state_reason"] == "low_kpi_value"

    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/",
        headers=_bearer(user),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["items"] == []
    assert body["open_p0_p1_count"] == 0
    assert body["state"] == "attention"
    assert body["state_reason"] == "low_kpi_value"
    assert body["analytics_signals"]["low_kpis"][0]["metric_key"] == "geo_score"
    assert body["analytics_signals"]["freshness"]["latest_geo_score_daily_date"] is not None


@pytest.mark.asyncio
async def test_complete_data_without_p0_p1_is_neutral_no_diagnostics(
    db_session,
    client,
    user,
    project,
):
    now = datetime.now(UTC).replace(tzinfo=None)
    db_session.add(_geo_score(brand_id=project.primary_brand_id, when=now))
    db_session.add_all(
        [
            _brand_mention(
                response_id=127101,
                brand_id=project.primary_brand_id,
                brand_name="Primary",
                when=now,
            ),
            _brand_mention(
                response_id=127101,
                brand_id=999,
                brand_name="Competitor",
                when=now,
            ),
            _make_diag(project=project, severity="P2", status="open"),
        ]
    )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/",
        headers=_bearer(user),
    )
    counts = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/counts",
        headers=_bearer(user),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["open_p0_p1_count"] == 0
    assert body["state"] == "no_diagnostics"
    assert body["state_reason"] == "no_open_p0_p1_diagnostics"
    assert body["formula_status"] == "ok"

    assert counts.status_code == 200, counts.text
    counts_body = counts.json()
    assert counts_body["by_severity_open"]["P2"] == 1
    assert counts_body["open_p0_p1_count"] == 0
    assert counts_body["state"] == "no_diagnostics"


@pytest.mark.asyncio
async def test_diagnostics_reject_unscoped_brand_id(client, user, project):
    invalid_brand_id = 127099
    urls = [
        f"/api/v1/projects/{project.id}/diagnostics/?brand_id={invalid_brand_id}",
        f"/api/v1/projects/{project.id}/diagnostics?brand_id={invalid_brand_id}",
        f"/api/v1/projects/{project.id}/diagnostics/counts?brand_id={invalid_brand_id}",
    ]

    for url in urls:
        resp = await client.get(url, headers=_bearer(user))
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "validation_error"
        assert detail["field"] == "brand_id"
        assert detail["reason"] == "must match project primary brand or pinned competitor"


@pytest.mark.asyncio
async def test_list_filter_by_severity(db_session, client, user, project):
    db_session.add_all(
        [
            _make_diag(project=project, severity="P1"),
            _make_diag(project=project, severity="P2"),
        ]
    )
    await db_session.commit()
    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/?severity=P1",
        headers=_bearer(user),
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["severity"] == "P1"


@pytest.mark.asyncio
async def test_list_filter_by_status(db_session, client, user, project):
    db_session.add_all(
        [
            _make_diag(project=project, status="open"),
            _make_diag(project=project, status="resolved"),
        ]
    )
    await db_session.commit()
    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/?status=resolved",
        headers=_bearer(user),
    )
    assert resp.json()["total"] == 1


# ── counts ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_counts_aggregates(db_session, client, user, project):
    db_session.add_all(
        [
            _make_diag(project=project, severity="P0", status="open"),
            _make_diag(project=project, severity="P1", status="open"),
            _make_diag(project=project, severity="P1", status="resolved"),
        ]
    )
    await db_session.commit()
    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/counts",
        headers=_bearer(user),
    )
    body = resp.json()
    assert body["total"] == 3
    assert body["by_status"]["open"] == 2
    assert body["by_status"]["resolved"] == 1
    assert body["by_severity_open"]["P0"] == 1
    assert body["by_severity_open"]["P1"] == 1


# ── detail ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_detail(db_session, client, user, project):
    diag = _make_diag(project=project, title="My P0", severity="P0")
    db_session.add(diag)
    await db_session.commit()
    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/{diag.id}",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    assert resp.json()["title"] == "My P0"


@pytest.mark.asyncio
async def test_get_unknown_returns_404(client, user, project):
    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/no-such",
        headers=_bearer(user),
    )
    assert resp.status_code == 404


# ── PATCH ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_patch_to_acknowledged(db_session, client, user, project):
    diag = _make_diag(project=project)
    db_session.add(diag)
    await db_session.commit()
    resp = await client.patch(
        f"/api/v1/projects/{project.id}/diagnostics/{diag.id}",
        headers=_bearer(user),
        json={"status": "acknowledged"},
    )
    body = resp.json()
    assert body["status"] == "acknowledged"
    assert body["acknowledged_at"] is not None


@pytest.mark.asyncio
async def test_patch_to_resolved_resolves_linked_alert(db_session, client, user, project):
    """When diagnostic transitions to resolved, linked alerts also resolve (D.8)."""
    diag = _make_diag(project=project, severity="P1")
    db_session.add(diag)
    await db_session.commit()
    # Seed a linked alert
    alert = Alert(
        id=_new_id(),
        project_id=project.id,
        brand_id=850,
        source="diagnostic",
        source_ref_id=diag.id,
        severity="P1",
        scope="user",
        title="x",
        status="unread",
    )
    db_session.add(alert)
    await db_session.commit()

    resp = await client.patch(
        f"/api/v1/projects/{project.id}/diagnostics/{diag.id}",
        headers=_bearer(user),
        json={"status": "resolved"},
    )
    assert resp.json()["status"] == "resolved"

    # Refresh the alert object so the test session re-reads the route's
    # committed state from DB.
    await db_session.refresh(alert)
    assert alert.status == "resolved"
    assert alert.resolved_at is not None


# ── refresh ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_runs_evaluator(db_session, client, user, project):
    """Strong visibility decline → P1 inserted on refresh."""
    today = datetime.now(UTC).replace(tzinfo=None).date()
    for i in range(30):
        d = today - timedelta(days=59 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=850,
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
                brand_id=850,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                mention_rate=0.3,
                avg_geo_score=40.0,
                total_queries=100,
            )
        )
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project.id}/diagnostics/refresh",
        headers=_bearer(user),
    )
    body = resp.json()
    assert body["inserted"] >= 1
    assert body["project_id"] == project.id


# ── multi-tenancy ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_other_user_cannot_read_diagnostics(db_session, client, user, project):
    diag = _make_diag(project=project)
    db_session.add(diag)

    other = User(
        id=_new_id(),
        email=f"o-{uuid.uuid4().hex[:6]}@example.com",
        name="O",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(other)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project.id}/diagnostics/",
        headers=_bearer(other),
    )
    # get_project_for_user returns 404 on multi-tenant violation
    assert resp.status_code == 404
