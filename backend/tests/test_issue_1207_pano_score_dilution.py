"""Regression: brand-overview GeoScore must not be diluted by zero-default
rows from non-target-mention responses.

Captured production symptom (bestCoffer, brand_id=24, project
7380c0e0-8798-4a5f-998f-42010a7d9caa, window 2026-04-18 → 2026-05-18):

  GET /api/v1/projects/7380c0e0-.../brand-overview?brand_id=24
    kpi_cards[?label_en=='GeoScore'].value = 8.7   (rendered as "9", trips
                                                    the <35 "需关注" badge)
    formula_status = "partial"

Per `_evidence/pano-bestcoffer-20260518T060355Z/db.txt` the underlying
distribution for that window was:

  - geo_score_daily:       0 rows for brand 24 (table empty in window;
                           endpoint falls through to admin-facts path)
  - brand_mentions:        92 responses where brand 24 was mentioned
  - total analyzed:       ~213 response_analyses rows in window

`response_analyses.geo_score` has `server_default="0.0"` (see
`backend/genpano_models/analyzer.py:145`). Responses where the target was
not mentioned therefore arrive at the admin-facts path with `geo_score=0.0`
instead of NULL. The pre-fix `_overview_from_admin_facts` body appended
every non-None `_fact_geo_display(row.geo_score)` to the per-day bucket,
including those zero-default rows, and then took an unweighted mean. With
~92 mentioned + ~121 non-mentioned rows the math reproduces the observed
8.7: a small per-mention mean (~20, the GEOScorer.calc_overall floor) is
dragged down by 121 zero contributions:

  92 * 20 / 213 ≈ 8.6  ≈ the observed 8.7

This test pins the post-fix behaviour: only mention-bearing rows
contribute to the GeoScore bucket.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from genpano_models import ResponseAnalysis, User
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._overview_service import get_brand_overview

from tests.test_issue_562_app_analytics_endpoint_consistency import (  # type: ignore[import-untyped]
    REPAIR_DAY,
    WINDOW_DAY,
    _seed_live_shaped_admin_facts,
    _v3_package,
)


@pytest_asyncio.fixture
async def dilution_user(db_session: AsyncSession) -> User:
    u = User(
        id=str(uuid.uuid4()),
        email=f"issue1207-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue 1207 User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest.mark.asyncio
async def test_geoscore_card_excludes_zero_default_non_mention_rows(
    db_session: AsyncSession,
    dilution_user: User,
) -> None:
    """Reproduce the bestCoffer dilution scenario in miniature.

    Response 401 mentions the target brand and has a real per-response
    geo_score of 0.76 (which _fact_geo_display scales to 76.0). Response 402
    is the dilution row: same window, same brand context, but the target
    is NOT mentioned and geo_score arrives as 0.0 (the SQLAlchemy
    server_default for `response_analyses.geo_score`).

    Pre-fix the card would be `_avg([76.0, 0.0]) = 38.0`. Post-fix only
    mention-bearing rows enter the bucket, so the card is `_avg([76.0]) =
    76.0`. The post-fix value is what aligns with the displayed Mention
    Rate / SoV cards on the same response set.
    """
    project = await _seed_live_shaped_admin_facts(db_session, dilution_user)

    fact_package_402 = _v3_package()
    fact_package_402["response_id"] = 402
    fact_package_402["query_id"] = 302
    fact_package_402["entities"]["target"]["mentioned"] = False
    fact_package_402["entities"]["target"]["mention_count"] = 0
    db_session.add(
        ResponseAnalysis(
            response_id=402,
            target_brand_mentioned=False,
            target_brand_rank=None,
            sentiment_score=0.0,
            geo_score=0.0,
            raw_analysis_json={"analyzer_fact_package_v3": fact_package_402},
        )
    )
    await db_session.commit()

    overview = await get_brand_overview(
        db_session,
        project,
        from_date=WINDOW_DAY.date(),
        to_date=REPAIR_DAY.date(),
        brand_id_override=12,
    )

    body = overview.model_dump(mode="json")
    geo_card = next(card for card in body["kpi_cards"] if card["label_en"] == "GeoScore")

    # Without the fix the bucket would receive [76.0, 0.0] and average to
    # 38.0 (the bestCoffer dilution in miniature). With the fix only the
    # mention-bearing row contributes.
    assert geo_card["value"] == pytest.approx(76.0), (
        f"GeoScore card should reflect mentioned-only mean (76.0), "
        f"not the diluted [76.0, 0.0] mean (38.0). Got: {geo_card['value']}"
    )
