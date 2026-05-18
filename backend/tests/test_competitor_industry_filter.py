"""Regression tests for issue #1185 / #1192 — unified competitor industry filter.

Symptom (verbatim from #1185, P0, 2026-05-18):
    "竞品分析页面出现了很多不是竞品的品牌，其甚至不是一个行业的！"

Recurrence of #975 because the partial fixes in #978 / earlier rev of
``_response_entity_competitor_metrics`` only scoped competitor rows
that carried a real ``brand_id``. Name-only mention buckets
(``brand_mentions.brand_name`` set, ``brand_id IS NULL``) were
passed through unfiltered — which is the actual leak path for
bestCoffer (BEFORE readback at
https://github.com/jotamotk/trash_test/actions/runs/26013912049
shows every leaked brand as ``brand_id: null``).

This module pins the new behavior of ``_filter_competitors_by_industry``
plus the ``primary_brand_industry_missing`` short-circuit added to
``_response_entity_competitor_metrics`` and ``get_competitor_metrics``
in the same PR.

Cases covered (per #1192 STEP C):
    (a) name-only bucket, name does NOT resolve     → DROPPED
    (b) name-only bucket, name resolves same-industry → KEPT
    (c) name-only bucket, name resolves diff-industry → DROPPED
    (d) brand_id bucket, different industry          → DROPPED
    (e) brand_id bucket, same industry               → KEPT
    (f) primary_industry IS NULL                     → controlled empty,
        ``state="empty"``,
        ``state_reason="primary_brand_industry_missing"``

Fixture inputs are pinned to real captured values from the bestCoffer
BEFORE readback (``brand_id=24`` / canonical_name='bestCoffer' /
leaked names 'IBM Security', 'Microsoft', 'OpenAI') so the regression
is tied to the live symptom rather than an abstract scenario.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import BrandMention, Project, User
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._brand_dto import CompetitorBrandRow
from app.api.v1.projects._brand_service import _filter_competitors_by_industry
from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


def _row(brand_id: int | None, brand_name: str | None) -> CompetitorBrandRow:
    """Minimal CompetitorBrandRow with only id/name set (filter ignores metrics)."""
    return CompetitorBrandRow(
        brand_id=brand_id,
        brand_key=f"id:{brand_id}" if brand_id is not None else f"name:{brand_name}",
        brand_name=brand_name,
        avg_geo_score=None,
        avg_mention_rate=None,
        avg_sov=None,
        avg_sentiment=None,
    )


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"i1192-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue1192 User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


async def _ensure_brand_columns(db_session: AsyncSession) -> None:
    """Add the legacy display-name + industry columns to the bare test ``brands`` table.

    Mirrors the pattern used by ``test_issue_975_pinned_competitors.py`` — the
    test-suite schema only has the bare PK ``id`` column; we add the rest
    via ``ALTER TABLE`` so the name-resolution path in
    ``resolve_brand_industry_by_name`` has columns to scan.
    """
    for col in ("industry", "name_en", "name_zh", "name", "primary_name", "aliases"):
        try:
            await db_session.execute(text(f"ALTER TABLE brands ADD COLUMN {col} TEXT"))
        except Exception:
            pass


@pytest_asyncio.fixture
async def brands_table_with_industry(db_session: AsyncSession) -> None:
    """Seed brand rows with industry + name_en for the unit-level cases.

    Brand 24 = bestCoffer (industry: 数据安全) - the actual primary
    brand from the #1185 readback.
    Brand 50 = 同盾科技 (数据安全) - a plausible same-industry rival.
    Brand 51 = OpenAI (人工智能) - one of the leaked brands; here it has
    a row so the brand_id-resolved variant of the test can use it.
    """
    await _ensure_brand_columns(db_session)
    await db_session.execute(
        text(
            "INSERT INTO brands (id, industry, name_en) VALUES "
            "(24, '数据安全', 'bestCoffer'), "
            "(50, '数据安全', '同盾科技'), "
            "(51, '人工智能', 'OpenAI')"
        )
    )
    await db_session.commit()


# ──────────────────────────────────────────────────────────────────────
# Unit-level coverage of _filter_competitors_by_industry — cases (a)..(e)
# ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_filter_drops_name_only_unresolvable(
    db_session: AsyncSession, brands_table_with_industry: None
):
    """Case (a): name-only bucket whose name doesn't resolve → DROPPED.

    Uses 'IBM Security' from the bestCoffer BEFORE readback (see
    https://github.com/jotamotk/trash_test/issues/1192#issuecomment-4474451590)
    — this brand is not in the `brands` table at all so name resolution
    fails and the row must be dropped, not silently kept like before.
    """
    competitors = [_row(None, "IBM Security")]
    kept = await _filter_competitors_by_industry(db_session, competitors, "数据安全")
    assert kept == []


@pytest.mark.asyncio
async def test_filter_keeps_name_only_same_industry(
    db_session: AsyncSession, brands_table_with_industry: None
):
    """Case (b): name-only bucket resolves to a same-industry brand → KEPT.

    Mention says '同盾科技' as a name; lookup hits brands.name_en =
    '同盾科技' (industry '数据安全'), which matches the primary's
    '数据安全' → row is retained.
    """
    competitors = [_row(None, "同盾科技")]
    kept = await _filter_competitors_by_industry(db_session, competitors, "数据安全")
    assert len(kept) == 1
    assert kept[0].brand_name == "同盾科技"


@pytest.mark.asyncio
async def test_filter_drops_name_only_different_industry(
    db_session: AsyncSession, brands_table_with_industry: None
):
    """Case (c): name-only bucket resolves to a different-industry brand → DROPPED.

    'OpenAI' from the bestCoffer BEFORE readback resolves to brand 51
    (industry '人工智能') and bestCoffer is '数据安全', so this must
    drop. This is the exact failure mode the user reported.
    """
    competitors = [_row(None, "OpenAI")]
    kept = await _filter_competitors_by_industry(db_session, competitors, "数据安全")
    assert kept == []


@pytest.mark.asyncio
async def test_filter_drops_brand_id_different_industry(
    db_session: AsyncSession, brands_table_with_industry: None
):
    """Case (d): brand_id-resolved bucket with different industry → DROPPED."""
    competitors = [_row(51, "OpenAI")]
    kept = await _filter_competitors_by_industry(db_session, competitors, "数据安全")
    assert kept == []


@pytest.mark.asyncio
async def test_filter_keeps_brand_id_same_industry(
    db_session: AsyncSession, brands_table_with_industry: None
):
    """Case (e): brand_id-resolved bucket with same industry → KEPT."""
    competitors = [_row(50, "同盾科技")]
    kept = await _filter_competitors_by_industry(db_session, competitors, "数据安全")
    assert len(kept) == 1
    assert kept[0].brand_id == 50


@pytest.mark.asyncio
async def test_filter_drops_everything_when_primary_industry_empty(
    db_session: AsyncSession, brands_table_with_industry: None
):
    """The helper itself fails closed when primary_industry is missing.

    The endpoint-level short-circuit (test ``test_endpoint_*_returns_empty_state``
    below) handles the user-visible surface; this test pins the lower-
    level invariant so the helper never accidentally degrades to 'pass
    everything through'.
    """
    competitors = [_row(50, "同盾科技"), _row(None, "同盾科技")]
    assert await _filter_competitors_by_industry(db_session, competitors, None) == []
    assert await _filter_competitors_by_industry(db_session, competitors, "") == []


# ──────────────────────────────────────────────────────────────────────
# Endpoint-level coverage — case (f) + happy path with name-only leak
# ──────────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def bestcoffer_repro_project(
    db_session: AsyncSession, user: User, brands_table_with_industry: None
) -> Project:
    """Reproduce the bestCoffer leak: primary brand 24 + mention rows that
    include both same-industry name '同盾科技' AND cross-industry name-only
    leak 'OpenAI' AND name-only unresolvable 'IBM Security'.

    Mirrors the leaked-buckets shape from
    https://github.com/jotamotk/trash_test/actions/runs/26013912049 —
    name-only entries that previously slipped past the industry filter.
    """
    project = Project(
        user_id=user.id,
        name="bestCoffer repro",
        primary_brand_id=24,
        industry_id=1,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    now = datetime.now()
    # Primary (brand_id=24) plus the leaked-style buckets across 6 responses.
    for i in range(6):
        rid = 88000 + i
        db_session.add(
            BrandMention(
                response_id=rid,
                brand_id=24,
                brand_name="bestCoffer",
                sentiment_score=0.7,
                created_at=now - timedelta(days=i % 3),
            )
        )
        # Same-industry resolvable name-only mention — should stay.
        db_session.add(
            BrandMention(
                response_id=rid,
                brand_id=None,
                brand_name="同盾科技",
                sentiment_score=0.6,
                created_at=now - timedelta(days=i % 3),
            )
        )
        # Cross-industry name-only mention — must be dropped (was the bug).
        db_session.add(
            BrandMention(
                response_id=rid,
                brand_id=None,
                brand_name="OpenAI",
                sentiment_score=0.5,
                created_at=now - timedelta(days=i % 3),
            )
        )
        # Unresolvable name-only mention — must be dropped (was the bug).
        db_session.add(
            BrandMention(
                response_id=rid,
                brand_id=None,
                brand_name="IBM Security",
                sentiment_score=0.4,
                created_at=now - timedelta(days=i % 3),
            )
        )
    await db_session.commit()
    return project


@pytest.mark.asyncio
async def test_endpoint_drops_name_only_cross_industry_buckets(
    client, user, bestcoffer_repro_project
):
    """End-to-end: the /competitors/metrics endpoint must NOT surface
    name-only cross-industry mentions even when they have higher mention
    counts than the same-industry rival.

    This is the exact symptom from #1185: leaked names like 'OpenAI'
    and 'IBM Security' (all brand_id=null in the BEFORE readback) were
    visible on the competitor panel.
    """
    resp = await client.get(
        f"/api/v1/projects/{bestcoffer_repro_project.id}/competitors/metrics",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    names = {c.get("brand_name") for c in body["competitors"]}
    assert "OpenAI" not in names, (
        f"Cross-industry name-only leak (OpenAI) reproduced: {body['competitors']}"
    )
    assert "IBM Security" not in names, (
        f"Unresolvable name-only leak (IBM Security) reproduced: {body['competitors']}"
    )
    # Same-industry name-only mention should stay.
    assert "同盾科技" in names, (
        f"Same-industry name-only mention was dropped: {body['competitors']}"
    )


@pytest_asyncio.fixture
async def bestcoffer_industry_null_project(db_session: AsyncSession, user: User) -> Project:
    """Same primary brand (24) but with `industry` NULL — the actual
    pre-data-fix state of bestCoffer's `brands` row.

    Without the new short-circuit the endpoint would silently degrade
    to leaking everything; this fixture exists so case (f) is grounded
    in the real data shape.
    """
    await _ensure_brand_columns(db_session)
    await db_session.execute(
        text("INSERT INTO brands (id, industry, name_en) VALUES (24, NULL, 'bestCoffer')")
    )
    project = Project(
        user_id=user.id,
        name="bestCoffer industry-null",
        primary_brand_id=24,
        industry_id=1,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])

    now = datetime.now()
    for i in range(3):
        rid = 99000 + i
        db_session.add(
            BrandMention(
                response_id=rid,
                brand_id=24,
                brand_name="bestCoffer",
                sentiment_score=0.7,
                created_at=now - timedelta(days=i % 3),
            )
        )
        db_session.add(
            BrandMention(
                response_id=rid,
                brand_id=None,
                brand_name="OpenAI",
                sentiment_score=0.5,
                created_at=now - timedelta(days=i % 3),
            )
        )
    await db_session.commit()
    return project


@pytest.mark.asyncio
async def test_endpoint_primary_industry_null_returns_empty_state(
    client, user, bestcoffer_industry_null_project
):
    """Case (f): primary brand's `brands.industry` IS NULL.

    The endpoint must return ``competitors=[]``, ``state="empty"``,
    ``state_reason="primary_brand_industry_missing"`` — not silently
    pass leaked rows through. This is the controlled-empty contract
    decided with the user on 2026-05-18.
    """
    resp = await client.get(
        f"/api/v1/projects/{bestcoffer_industry_null_project.id}/competitors/metrics",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["competitors"] == [], (
        f"Industry-null primary still leaked competitors: {body['competitors']}"
    )
    assert body["state"] == "empty", body
    assert body["state_reason"] == "primary_brand_industry_missing", body
