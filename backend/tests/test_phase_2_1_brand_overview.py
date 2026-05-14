"""Phase 2.1 — GET /v1/projects/:id/overview."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import BrandMention, GeoScoreDaily, Project, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects import _overview_service
from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"o-{uuid.uuid4().hex[:6]}@example.com",
        name="Overview User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def empty_project(db_session: AsyncSession, user: User) -> Project:
    p = Project(
        user_id=user.id,
        name="Empty Project",
        primary_brand_id=None,  # no brand → state='empty'
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])
    return p


@pytest_asyncio.fixture
async def project_with_data(db_session: AsyncSession, user: User) -> Project:
    p = Project(
        user_id=user.id,
        name="With Data",
        primary_brand_id=42,
        industry_id=1,
    )
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    # Insert 30d of geo_score_daily for brand 42
    today = datetime.now().date()
    for i in range(30):
        d = today - timedelta(days=29 - i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=70.0 + i * 0.5,
                mention_rate=0.5 + i * 0.005,
                avg_sov=0.3 + i * 0.005,
                avg_sentiment=0.6 + i * 0.005,
                total_queries=100,
            )
        )
    # Insert some brand_mentions for top_prompts test
    for i in range(5):
        db_session.add(
            BrandMention(
                response_id=1000 + i,
                brand_id=42,
                brand_name="Test Brand",
                position_rank=i + 1,
                sentiment_score=0.7,
                created_at=datetime.now() - timedelta(days=i),
            )
        )
    await db_session.commit()
    return p


@pytest.mark.asyncio
async def test_overview_empty_state(client, user, empty_project):
    """Project without primary_brand_id → state='empty', null KPIs."""
    resp = await client.get(f"/api/v1/projects/{empty_project.id}/overview", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "empty"
    assert body["brand_id"] is None
    assert body["geo_score_30d"] == []
    assert body["sov_30d"] == []
    assert body["sentiment_30d"] == []
    assert len(body["kpi_cards"]) == 4
    for c in body["kpi_cards"]:
        assert c["value"] is None
        assert c["delta_30d_pct"] is None


@pytest.mark.asyncio
async def test_overview_with_data(client, user, project_with_data):
    """Project with geo_score_daily rows returns populated trends + KPIs."""
    resp = await client.get(
        f"/api/v1/projects/{project_with_data.id}/overview",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "partial"
    assert body["formula_status"] in {"missing_required_inputs", "formula_pending_upstream"}
    assert body["brand_id"] == 42
    assert body["industry_id"] == 1
    # 30d window has 30 data points
    assert len(body["geo_score_30d"]) == 30
    assert len(body["sov_30d"]) == 30
    # KPI cards have non-zero values
    geo_card = next(c for c in body["kpi_cards"] if c["label_en"] == "GeoScore")
    assert geo_card["value"] > 0
    # Prompt linkage is missing in this fixture, so the API does not synthesize prompt rows.
    assert body["top_prompts"] == []


@pytest.mark.asyncio
async def test_overview_cross_tenant_returns_404(client, user, project_with_data, db_session):
    """Different user → 404."""
    other = User(
        id=_new_id(),
        email=f"x-{uuid.uuid4().hex[:6]}@example.com",
        name="Other",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(other)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project_with_data.id}/overview",
        headers=_bearer(other),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_overview_no_auth_returns_401(client, project_with_data):
    resp = await client.get(f"/api/v1/projects/{project_with_data.id}/overview")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_overview_brand_id_override_swaps_brand(client, user, project_with_data):
    """`?brand_id=X` overrides the project's primary brand. Drives the
    DashboardPage brand picker (cross-industry brand viewing). The
    project still scopes industry and ownership; only brand_id changes
    in the response and downstream queries."""
    resp = await client.get(
        f"/api/v1/projects/{project_with_data.id}/overview?brand_id=99",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    # Override took effect even though no geo_score_daily rows exist for
    # brand_id=99 in the fixture — state collapses to 'empty', brand_id
    # echoes the override.
    assert body["brand_id"] == 99
    assert body["state"] == "empty"
    assert all(c["value"] is None for c in body["kpi_cards"])


@pytest.mark.asyncio
async def test_overview_brand_id_override_falsy_keeps_default(client, user, project_with_data):
    """Omitting `brand_id` keeps the project's primary_brand_id."""
    resp = await client.get(
        f"/api/v1/projects/{project_with_data.id}/overview",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    assert resp.json()["brand_id"] == 42


@pytest_asyncio.fixture
async def project_with_primary_sources_and_competitors(
    db_session: AsyncSession, user: User
) -> Project:
    """Issue #948 fixture: all primary sources populated for target +
    competitor, but no analyzer fact packages.

    Reproduces the production scenario where /brand/overview returned `—`
    for KPI cards (`_apply_kpi_contract` nulled `card.value`) even though
    `geo_score_daily` had rows.
    """
    p = Project(user_id=user.id, name="Peripheral KPI", primary_brand_id=42, industry_id=1)
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
                avg_geo_score=70.0 + i * 0.5,
                mention_rate=0.5 + i * 0.005,
                avg_sov=0.3 + i * 0.005,
                avg_sentiment=0.6 + i * 0.005,
                total_queries=100,
            )
        )
    for i in range(6):
        db_session.add(
            BrandMention(
                response_id=8000 + i,
                brand_id=42,
                brand_name="Test Brand",
                sentiment="positive",
                sentiment_score=0.7,
                position_rank=(i % 3) + 1,
                created_at=datetime.now() - timedelta(days=i),
            )
        )
    for i in range(3):
        db_session.add(
            BrandMention(
                response_id=8100 + i,
                brand_id=99,
                brand_name="Competitor",
                sentiment="neutral",
                sentiment_score=0.0,
                position_rank=(i % 3) + 1,
                created_at=datetime.now() - timedelta(days=i),
            )
        )
    await db_session.commit()
    return p


@pytest.mark.asyncio
async def test_overview_kpi_cards_with_evidence_survive_peripheral_missing_inputs(
    client, user, project_with_primary_sources_and_competitors
):
    """Issue #948: 提及率 / 引用份额 / 行业排名 / Sentiment cards rendered
    `—` on /brand/overview because `_apply_kpi_contract` nulled out
    `card.value` when peripheral analyzer inputs were missing — even when
    `geo_score_daily` rows actually backed the value and all per-metric
    primary sources (brand_mentions for target + competitor) were
    populated.

    The fix keeps `card.value` populated and downgrades `formula_status`
    to `partial` so the frontend's `canUseContractMetricValue` gate still
    surfaces the number. Critical missing inputs (denominator missing,
    primary source missing) still null the value per the no-fallback
    contract — see
    `test_overview_marks_brand_mentions_partial_when_daily_rollups_missing`.
    """
    resp = await client.get(
        f"/api/v1/projects/{project_with_primary_sources_and_competitors.id}/overview",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["evidence_counts"]["geo_score_daily_rows"] == 30
    for card in body["kpi_cards"]:
        assert card["value"] is not None, (
            f"{card['label_en']} value should survive peripheral missing "
            f"inputs when geo_score_daily evidence + primary sources back it"
        )
        assert card["formula_status"] != "missing_required_inputs", (
            f"{card['label_en']} formula_status should not be "
            f"missing_required_inputs when value is real (got "
            f"{card['formula_status']})"
        )


@pytest.mark.asyncio
async def test_overview_marks_brand_mentions_partial_when_daily_rollups_missing(
    client, user, db_session
):
    p = Project(user_id=user.id, name="Mention Only", primary_brand_id=12, industry_id=1)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    now = datetime.now()
    for i in range(4):
        db_session.add(
            BrandMention(
                response_id=4100 + i,
                brand_id=12,
                brand_name="Estée Lauder",
                position_rank=(i % 3) + 1,
                sentiment_score=0.75,
                created_at=now - timedelta(days=i),
            )
        )
    for i in range(2):
        db_session.add(
            BrandMention(
                response_id=4200 + i,
                brand_id=99,
                brand_name="Other Brand",
                position_rank=2,
                sentiment_score=0.2,
                created_at=now - timedelta(days=i),
            )
        )
    await db_session.commit()

    resp = await client.get(f"/api/v1/projects/{p.id}/overview", headers=_bearer(user))

    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "partial"
    assert body["formula_status"] == "missing_required_inputs"
    assert "eligible_response_denominator" in body["missing_inputs"]
    geo_card = next(c for c in body["kpi_cards"] if c["label_en"] == "GeoScore")
    mention_card = next(c for c in body["kpi_cards"] if c["label_en"] == "Mention Rate")
    assert geo_card["value"] is None
    assert mention_card["value"] is None
    assert body["geo_score_30d"] == []
    assert body["sov_30d"] == []
    assert body["evidence_counts"]["brand_mention_count"] == 4


class _FakeNestedTransaction:
    def __init__(self, session: _FakeTopPromptsSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeNestedTransaction:
        self._session.savepoints += 1
        self._session.in_savepoint = True
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self._session.savepoint_rollbacks += 1
        self._session.in_savepoint = False
        return False


class _FakeRows:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeTopPromptsSession:
    def __init__(self) -> None:
        self.calls = 0
        self.in_savepoint = False
        self.aborted = False
        self.savepoints = 0
        self.savepoint_rollbacks = 0

    def begin_nested(self) -> _FakeNestedTransaction:
        return _FakeNestedTransaction(self)

    async def execute(self, statement, params=None):
        self.calls += 1
        if self.calls == 1:
            if not self.in_savepoint:
                self.aborted = True
            raise RuntimeError("legacy prompt join failed")
        if self.aborted:
            raise RuntimeError("current transaction is aborted")
        if self.calls in (2, 3):
            return _FakeRows([])
        return _FakeRows([(5, 2.4, 0.7)])


@pytest.mark.asyncio
async def test_top_prompts_raw_join_failure_returns_empty_without_aggregate_substitution():
    session = _FakeTopPromptsSession()
    today = datetime.now().date()

    rows = await _overview_service._top_prompts(
        session,
        42,
        today - timedelta(days=29),
        today,
    )

    assert rows == []
    assert session.savepoints == 1
    assert session.savepoint_rollbacks == 1
