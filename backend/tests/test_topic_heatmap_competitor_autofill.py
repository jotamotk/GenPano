"""Regression: /topic-heatmap auto-fills competitor rows from `brand_mentions`
when ``ProjectCompetitor`` is empty.

User-visible symptom (AI leader feedback, 2026-05-19):
    "品牌 × Topic 情感热力图 这里不应该只有 best coffer 一个品牌，
     还需要有很多 response 里提到的竞品"

Captured evidence the fix is anchored to:
- ``BESTCOFFER_BRAND_ID = 24`` — real production primary brand id, also
  used by ``test_topic_heatmap_pad_with_owned_topics.py`` and
  ``test_competitor_industry_filter.py`` (bestCoffer BEFORE readback
  https://github.com/jotamotk/trash_test/actions/runs/26013912049).
- Industry ``'数据安全'`` — bestCoffer's row in production ``brands.industry``.

Before the fix, ``get_topic_heatmap()`` derived competitors only from
``ProjectCompetitor`` (pinned, capped at 4). When that table was empty
for a project, ``compare_with`` was empty and only the primary brand
rendered. The fix expands the cap to 7 competitors and auto-fills from
brands co-mentioned in this project's responses (via
``discover_related_brand_ids``), keeping the same-industry filter
(issue #975).

Cases pinned by this module:
    (a) ProjectCompetitor empty + mentions → auto-fill produces rows
    (b) Pinned competitors come BEFORE auto-filled ones
    (c) Industry filter still drops cross-industry mentions
    (d) Explicit ``compare_with`` query param bypasses auto-fill
    (e) No pins + no mentions → primary-only response (no regression)
"""

from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    BrandMention,
    Project,
    ProjectCompetitor,
    TopicScoreDaily,
    User,
)
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)

# Real captured production values (see module docstring).
BESTCOFFER_BRAND_ID = 24
PRIMARY_INDUSTRY = "数据安全"
WINDOW_DAY = date(2026, 5, 12)
TOPIC_ID = 153  # "企业级AI数据脱敏工具选购指南", real captured topic.


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


def _new_id() -> str:
    return str(uuid.uuid4())


async def _ensure_brand_columns(db_session: AsyncSession) -> None:
    for col in ("industry", "name_en", "name_zh", "name"):
        try:
            await db_session.execute(text(f"ALTER TABLE brands ADD COLUMN {col} TEXT"))
        except Exception:
            pass


async def _ensure_topics_table(db_session: AsyncSession) -> None:
    """Create the legacy `topics` table that `get_topic_heatmap()` pads
    from when TopicScoreDaily has fewer rows than top_n. Mirrors the
    pattern in test_topic_heatmap_pad_with_owned_topics.py.
    """
    try:
        await db_session.execute(
            text(
                "CREATE TABLE IF NOT EXISTS topics ("
                "id INTEGER PRIMARY KEY, brand_id INTEGER, text TEXT, "
                "category TEXT, status TEXT, created_at DATETIME)"
            )
        )
        await db_session.commit()
    except Exception:
        pass


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"heatmap-autofill-{uuid.uuid4().hex[:6]}@example.com",
        name="Heatmap Autofill User",
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
async def brands_seeded(db_session: AsyncSession) -> None:
    """Seed bestCoffer (24) + same-industry competitors + a cross-industry
    one. The same-industry pool must be ≥ 7 so auto-fill can reach the cap.
    """
    await _ensure_brand_columns(db_session)
    await _ensure_topics_table(db_session)
    rows = [
        (24, PRIMARY_INDUSTRY, "bestCoffer"),
        (501, PRIMARY_INDUSTRY, "同盾科技"),
        (502, PRIMARY_INDUSTRY, "明朝万达"),
        (503, PRIMARY_INDUSTRY, "数据堂"),
        (504, PRIMARY_INDUSTRY, "安恒信息"),
        (505, PRIMARY_INDUSTRY, "天融信"),
        (506, PRIMARY_INDUSTRY, "绿盟科技"),
        (507, PRIMARY_INDUSTRY, "启明星辰"),
        (508, PRIMARY_INDUSTRY, "深信服"),
        (599, "人工智能", "OpenAI"),  # cross-industry, must be excluded
    ]
    for bid, industry, name in rows:
        await db_session.execute(
            text(
                "INSERT INTO brands (id, industry, name_en) "
                "VALUES (:id, :ind, :n)"
            ),
            {"id": bid, "ind": industry, "n": name},
        )
    await db_session.commit()


async def _seed_co_mentions(
    db_session: AsyncSession,
    competitor_brand_ids: list[int],
    *,
    base_response_id: int = 70000,
    n_responses: int = 6,
) -> None:
    """Insert brand_mention rows where primary + each competitor co-occur
    in the same response_id (so ``discover_related_brand_ids`` matches).
    Mention count per competitor is the *order* in the list so the
    auto-fill ordering is deterministic.
    """
    now = datetime.combine(WINDOW_DAY, datetime.min.time())
    for i in range(n_responses):
        rid = base_response_id + i
        db_session.add(
            BrandMention(
                response_id=rid,
                brand_id=BESTCOFFER_BRAND_ID,
                brand_name="bestCoffer",
                sentiment_score=0.8,
                mention_count=1,
                created_at=now - timedelta(hours=i),
            )
        )
        for idx, bid in enumerate(competitor_brand_ids):
            # Higher-ranked competitors appear in more responses → higher count.
            if i >= len(competitor_brand_ids) - idx:
                continue
            db_session.add(
                BrandMention(
                    response_id=rid,
                    brand_id=bid,
                    brand_name=f"brand-{bid}",
                    sentiment_score=0.5,
                    mention_count=1,
                    created_at=now - timedelta(hours=i),
                )
            )
    await db_session.commit()


async def _seed_topic_score_daily(
    db_session: AsyncSession, brand_ids: list[int]
) -> None:
    """Give the requested brand_ids a TopicScoreDaily row for TOPIC_ID so
    the live cell-population path emits non-null cells for them.
    """
    for bid in brand_ids:
        db_session.add(
            TopicScoreDaily(
                brand_id=bid,
                topic_id=TOPIC_ID,
                date=WINDOW_DAY,
                total_responses=10,
                mention_count=5,
                mention_rate=0.5,
                avg_sentiment_score=0.6,
            )
        )
    await db_session.commit()


# ── (a) auto-fill from mentions when ProjectCompetitor is empty ────────
@pytest.mark.asyncio
async def test_autofill_produces_competitor_rows_when_pins_empty(
    client: AsyncClient,
    user: User,
    db_session: AsyncSession,
    brands_seeded: None,
) -> None:
    project = Project(
        id=_new_id(),
        user_id=user.id,
        name="bestCoffer autofill — no pins",
        primary_brand_id=BESTCOFFER_BRAND_ID,
        industry_id=1,
    )
    db_session.add(project)
    await db_session.commit()

    competitors = [501, 502, 503, 504, 505]
    await _seed_co_mentions(db_session, competitors)
    await _seed_topic_score_daily(
        db_session, [BESTCOFFER_BRAND_ID, *competitors]
    )

    resp = await client.get(
        f"/api/v1/projects/{project.id}/topic-heatmap",
        headers=_bearer(user),
        params={
            "brand_id": BESTCOFFER_BRAND_ID,
            "metric": "sentiment",
            "top_n": 8,
            "from": WINDOW_DAY.isoformat(),
            "to": WINDOW_DAY.isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    brand_ids_in_response = [row["brand_id"] for row in body["rows"]]
    assert brand_ids_in_response[0] == BESTCOFFER_BRAND_ID, (
        f"primary must be first row, got {brand_ids_in_response}"
    )
    competitor_rows = brand_ids_in_response[1:]
    assert set(competitor_rows) == set(competitors), (
        "every co-mentioned same-industry competitor should appear as a row; "
        f"got {competitor_rows}, expected {competitors}"
    )


# ── (b) pinned brands come before auto-filled ones ────────────────────
@pytest.mark.asyncio
async def test_pinned_competitors_appear_before_autofilled(
    client: AsyncClient,
    user: User,
    db_session: AsyncSession,
    brands_seeded: None,
) -> None:
    project = Project(
        id=_new_id(),
        user_id=user.id,
        name="bestCoffer autofill — pins first",
        primary_brand_id=BESTCOFFER_BRAND_ID,
        industry_id=1,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])
    # Pin 506 and 507 — both same-industry. The mentions will offer
    # 501..505, but the heatmap must keep the two pins ahead of them.
    db_session.add(
        ProjectCompetitor(project_id=project.id, brand_id=506, pinned_by=user.id)
    )
    db_session.add(
        ProjectCompetitor(project_id=project.id, brand_id=507, pinned_by=user.id)
    )
    await db_session.commit()

    autofill = [501, 502, 503, 504, 505]
    await _seed_co_mentions(db_session, autofill)
    await _seed_topic_score_daily(
        db_session, [BESTCOFFER_BRAND_ID, 506, 507, *autofill]
    )

    resp = await client.get(
        f"/api/v1/projects/{project.id}/topic-heatmap",
        headers=_bearer(user),
        params={
            "brand_id": BESTCOFFER_BRAND_ID,
            "metric": "sentiment",
            "top_n": 8,
            "from": WINDOW_DAY.isoformat(),
            "to": WINDOW_DAY.isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text
    rows = [r["brand_id"] for r in resp.json()["rows"]]
    assert rows[0] == BESTCOFFER_BRAND_ID
    assert rows[1] in {506, 507}, f"first competitor must be a pin, got {rows[1]}"
    assert rows[2] in {506, 507}, f"second competitor must be a pin, got {rows[2]}"
    assert {506, 507}.issubset(set(rows[1:3])), rows
    autofilled_seen = [b for b in rows[3:] if b in set(autofill)]
    assert autofilled_seen, "auto-fill should still contribute rows after pins"


# ── (c) industry filter still excludes cross-industry mentions ─────────
@pytest.mark.asyncio
async def test_autofill_respects_industry_filter(
    client: AsyncClient,
    user: User,
    db_session: AsyncSession,
    brands_seeded: None,
) -> None:
    project = Project(
        id=_new_id(),
        user_id=user.id,
        name="bestCoffer autofill — industry guard",
        primary_brand_id=BESTCOFFER_BRAND_ID,
        industry_id=1,
    )
    db_session.add(project)
    await db_session.commit()

    # Include the cross-industry brand 599 alongside same-industry ones.
    await _seed_co_mentions(db_session, [501, 502, 599])
    await _seed_topic_score_daily(
        db_session, [BESTCOFFER_BRAND_ID, 501, 502, 599]
    )

    resp = await client.get(
        f"/api/v1/projects/{project.id}/topic-heatmap",
        headers=_bearer(user),
        params={
            "brand_id": BESTCOFFER_BRAND_ID,
            "metric": "sentiment",
            "top_n": 8,
            "from": WINDOW_DAY.isoformat(),
            "to": WINDOW_DAY.isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text
    rows = {r["brand_id"] for r in resp.json()["rows"]}
    assert 599 not in rows, (
        f"cross-industry mention (599, 人工智能) leaked into 数据安全 "
        f"heatmap: {rows}"
    )
    assert {501, 502}.issubset(rows), rows


# ── (d) explicit compare_with bypasses auto-fill ──────────────────────
@pytest.mark.asyncio
async def test_explicit_compare_with_bypasses_autofill(
    client: AsyncClient,
    user: User,
    db_session: AsyncSession,
    brands_seeded: None,
) -> None:
    project = Project(
        id=_new_id(),
        user_id=user.id,
        name="bestCoffer autofill — explicit compare_with",
        primary_brand_id=BESTCOFFER_BRAND_ID,
        industry_id=1,
    )
    db_session.add(project)
    await db_session.commit()

    await _seed_co_mentions(db_session, [501, 502, 503, 504, 505])
    await _seed_topic_score_daily(
        db_session, [BESTCOFFER_BRAND_ID, 501, 502, 503, 504, 505, 508]
    )

    resp = await client.get(
        f"/api/v1/projects/{project.id}/topic-heatmap",
        headers=_bearer(user),
        params={
            "brand_id": BESTCOFFER_BRAND_ID,
            "metric": "sentiment",
            "top_n": 8,
            "compare_with": "508",
            "from": WINDOW_DAY.isoformat(),
            "to": WINDOW_DAY.isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text
    rows = [r["brand_id"] for r in resp.json()["rows"]]
    assert rows == [BESTCOFFER_BRAND_ID, 508], (
        f"explicit compare_with should be respected verbatim, got {rows}"
    )


# ── (e) regression guard: no pins + no mentions → primary-only ────────
@pytest.mark.asyncio
async def test_primary_only_when_no_pins_and_no_mentions(
    client: AsyncClient,
    user: User,
    db_session: AsyncSession,
    brands_seeded: None,
) -> None:
    project = Project(
        id=_new_id(),
        user_id=user.id,
        name="bestCoffer autofill — empty everything",
        primary_brand_id=BESTCOFFER_BRAND_ID,
        industry_id=1,
    )
    db_session.add(project)
    await db_session.commit()
    await _seed_topic_score_daily(db_session, [BESTCOFFER_BRAND_ID])

    resp = await client.get(
        f"/api/v1/projects/{project.id}/topic-heatmap",
        headers=_bearer(user),
        params={
            "brand_id": BESTCOFFER_BRAND_ID,
            "metric": "sentiment",
            "top_n": 8,
            "from": WINDOW_DAY.isoformat(),
            "to": WINDOW_DAY.isoformat(),
        },
    )
    assert resp.status_code == 200, resp.text
    rows = [r["brand_id"] for r in resp.json()["rows"]]
    assert rows == [BESTCOFFER_BRAND_ID], (
        f"with no pins and no mentions, only primary row should render; got {rows}"
    )
