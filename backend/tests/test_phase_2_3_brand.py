"""Phase 2.3 — products / competitors metrics / diagnostics endpoints."""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    BrandMention,
    GeoScoreDaily,
    ProductFeatureMention,
    Project,
    ProjectCompetitor,
    ResponseAnalysis,
    User,
)
from sqlalchemy import text
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
        email=f"b-{uuid.uuid4().hex[:6]}@example.com",
        name="Brand User",
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
    p = Project(user_id=user.id, name="Brand 2.3", primary_brand_id=42, industry_id=1)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    # Add competitor pin
    db_session.add(ProjectCompetitor(project_id=p.id, brand_id=99, pinned_by=user.id))

    today = datetime.now().date()
    # 30d geo_score for primary + competitor
    for bid in (42, 99):
        for i in range(30):
            d = today - timedelta(days=29 - i)
            db_session.add(
                GeoScoreDaily(
                    brand_id=bid,
                    date=datetime.combine(d, datetime.min.time()),
                    target_llm="chatgpt",
                    avg_geo_score=70.0 + i * 0.5 if bid == 42 else 60.0 + i * 0.4,
                    mention_rate=0.6 + i * 0.005 if bid == 42 else 0.4 + i * 0.005,
                    avg_sov=0.4 if bid == 42 else 0.3,
                    avg_sentiment=0.7 if bid == 42 else 0.5,
                    total_queries=100,
                )
            )

    # Brand mentions for co-mention test (primary + competitor on same response_ids)
    for i in range(10):
        db_session.add(
            BrandMention(
                response_id=3000 + i,
                brand_id=42,
                brand_name="Primary",
                sentiment="positive" if i % 3 != 0 else "negative",
                sentiment_score=0.6,
                created_at=datetime.now() - timedelta(days=i),
            )
        )
    for i in range(5):  # 5 of 10 responses also include competitor → 5 co-mentions
        db_session.add(
            BrandMention(
                response_id=3000 + i,
                brand_id=99,
                brand_name="Competitor",
                sentiment="positive",
                sentiment_score=0.5,
                created_at=datetime.now() - timedelta(days=i),
            )
        )

    # ResponseAnalysis (needed for some downstream queries)
    for i in range(10):
        db_session.add(
            ResponseAnalysis(
                response_id=3000 + i,
                target_brand_mentioned=True,
                sentiment_score=0.6,
                analyzed_at=datetime.now() - timedelta(days=i),
            )
        )

    # Product features for /products endpoint
    products = [
        ("Primary", "ProductA", "taste", "morning"),
        ("Primary", "ProductA", "price", "morning"),
        ("Primary", "ProductA", "taste", "afternoon"),
        ("Primary", "ProductB", "design", None),
        ("Primary", "ProductB", "design", None),
    ]
    for i, (bn, pn, fn, sc) in enumerate(products):
        db_session.add(
            ProductFeatureMention(
                analysis_id=1,  # FK any in fresh DB
                brand_name=bn,
                product_name=pn,
                feature_name=fn,
                feature_sentiment="positive" if i % 2 == 0 else "neutral",
                scenario=sc,
                created_at=datetime.now() - timedelta(days=i),
            )
        )

    await db_session.commit()
    return p


@pytest.mark.asyncio
async def test_products_returns_aggregated(client, user, project_with_data):
    resp = await client.get(
        f"/api/v1/projects/{project_with_data.id}/products",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "ok"
    assert body["formula_status"] == "ok"
    # 2 distinct (brand, product) pairs: (Primary, ProductA) + (Primary, ProductB)
    assert body["total"] >= 2
    names = {p["product_name"] for p in body["items"]}
    assert "ProductA" in names
    assert "ProductB" in names


@pytest.mark.asyncio
async def test_products_batches_per_product_rollups(client, user, project_with_data):
    """Issue #1031: top_features / top_scenarios used to be fetched in a loop
    (3 queries per product → 502 timeouts on 50-product brands). They are now
    batched. Guard the output so a regression to per-row fetch is visible.
    """
    resp = await client.get(
        f"/api/v1/projects/{project_with_data.id}/products",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    items_by_name = {p["product_name"]: p for p in resp.json()["items"]}

    # ProductA: features "taste" (2x) > "price" (1x); scenarios "morning" (2x).
    a = items_by_name["ProductA"]
    feat_names_a = [f["feature_name"] for f in a["top_features"]]
    assert "taste" in feat_names_a
    assert "morning" in [s["scenario"] for s in a["top_scenarios"]]

    # ProductB: feature "design" (2x), no scenarios (all NULL).
    b = items_by_name["ProductB"]
    assert "design" in [f["feature_name"] for f in b["top_features"]]
    assert b["top_scenarios"] == []


@pytest.mark.asyncio
async def test_products_empty_for_no_brand(client, user, db_session):
    p = Project(user_id=user.id, name="No Primary", primary_brand_id=None)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    resp = await client.get(f"/api/v1/projects/{p.id}/products", headers=_bearer(user))
    assert resp.status_code == 200
    assert resp.json()["state"] == "empty"


def _v3_package_with_products(*, response_id: int, products: list[dict]) -> dict:
    """Minimal v3 fixture exercising the issue #1049 derivation path.

    Mirrors `tests/test_issue_687_bestcoffer_app_api_contract.py::_bestcoffer_package_v3`
    but uses brand_id=42 to match this file's `project_with_data` fixture.
    """
    return {
        "analyzer_version": "v3",
        "response_id": response_id,
        "query_id": response_id + 1,
        "prompt_id": response_id + 2,
        "topic_id": response_id + 3,
        "project_ids": [],
        "source_brand_id": 42,
        "target_brand_id": 42,
        "engine": "deepseek",
        "collected_at": datetime.now().isoformat(),
        "analysis_started_at": datetime.now().isoformat(),
        "analysis_completed_at": datetime.now().isoformat(),
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "prompt_version": "issue-1049-test",
        "raw_output_sha256": f"sha{response_id}",
        "idempotency_key": f"{response_id}:v3:sha{response_id}",
        "eligibility": {
            "eligible": True,
            "success_response": True,
            "invalid_reason": None,
            "missing_reason_codes": [],
        },
        "coverage": {
            "eligible_response_count_basis": 1,
            "analyzed": True,
            "parse_status": "ok",
            "validation_errors": [],
        },
        "entities": {
            "target": {
                "brand_id": 42,
                "canonical_name": "Primary",
                "mentioned": True,
                "mention_count": 1,
            },
            "configured_competitors": [],
            "response_named_brands": [],
        },
        "visibility": {
            "is_visible": True,
            "rank": 1,
            "position_type": "ranked_list",
            "visibility_score": 1.0,
            "formula_status": "ok",
            "reason_codes": [],
        },
        "sov": {
            "numerator_target_mentions": 1,
            "denominator_competitive_mentions": 1,
            "denominator_brand_ids": [],
            "denominator_raw_names": [],
            "formula_status": "ok",
            "reason_codes": [],
            "sample_response_ids": [response_id],
        },
        "sentiment": {
            "label": "positive",
            "score": 0.8,
            "drivers": [],
            "source_quotes": [],
            "formula_status": "ok",
            "reason_codes": [],
        },
        "citations": {
            "total_citations": 0,
            "attributed_citations": [],
            "unresolved_citations": [],
            "domains": [],
            "source_types": [],
            "formula_status": "ok",
            "reason_codes": [],
        },
        "rank": {
            "best_rank": 1,
            "rank_bucket": "top_3",
            "rank_basis": "position_rank",
            "formula_status": "ok",
            "reason_codes": [],
        },
        "topic": {
            "topic_id": response_id + 3,
            "topic_name": "Primary topic",
            "dimension": "product",
            "associated_brand_id": 42,
            "prompt_id": response_id + 2,
            "query_id": response_id + 1,
        },
        "products": products,
        "topic_metrics": {
            "visible": True,
            "visibility_rate_basis": 1,
            "sentiment_basis": 1,
            "citation_basis": 0,
            "rank_basis": 1,
            "formula_status": "ok",
            "reason_codes": [],
        },
        "geo_pano": {
            "visibility_component": "ok",
            "sentiment_component": "ok",
            "sov_component": "ok",
            "citation_component": "ok",
            "geo_score": None,
            "pano_score": None,
            "formula_status": "ok",
            "reason_codes": [],
        },
    }


@pytest.mark.asyncio
async def test_products_v3_payload_with_products_passes_contract(
    client, user, db_session: AsyncSession
):
    """Issue #1049: `/api/v1/projects/<id>/products` must emit
    `metric_formula_evidence.topic_product` with `formula_status='ok'` when
    the analyzer payload is the durable v3 contract (BestCoffer prod shape).

    The v3 schema pre-dates the `topic_product` sub-block; `_as_v3_package`
    now derives it from the v3 `products[]` array so `_rollup_topic_product`
    can aggregate v3 packages just like v1 ones. Without this, the frontend
    `canUseMetricEvidence(data, 'product')` gate fails and BestCoffer's
    products page renders empty (issue #1031).
    """
    p = Project(user_id=user.id, name="Issue 1049 v3", primary_brand_id=42, industry_id=1)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    today = datetime.now().date()
    for i in range(5):
        d = today - timedelta(days=i)
        db_session.add(
            GeoScoreDaily(
                brand_id=42,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=70.0,
                mention_rate=0.6,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=100,
            )
        )

    response_ids = [9000, 9001, 9002]
    for rid in response_ids:
        db_session.add(
            BrandMention(
                response_id=rid,
                brand_id=42,
                brand_name="Primary",
                sentiment="positive",
                sentiment_score=0.6,
                created_at=datetime.now() - timedelta(days=1),
            )
        )
        db_session.add(
            ResponseAnalysis(
                response_id=rid,
                target_brand_mentioned=True,
                sentiment_score=0.6,
                analyzed_at=datetime.now() - timedelta(days=1),
                raw_analysis_json={
                    "analyzer_fact_package_v3": _v3_package_with_products(
                        response_id=rid,
                        products=[
                            {
                                "product_name": "ProductA",
                                "brand_id": 42,
                                "feature_name": None,
                                "sentiment": None,
                                "snippets": [],
                                "formula_status": "ok",
                            },
                            {
                                "product_name": "ProductB",
                                "brand_id": 42,
                                "feature_name": None,
                                "sentiment": None,
                                "snippets": [],
                                "formula_status": "ok",
                            },
                        ],
                    )
                },
                created_at=datetime.now() - timedelta(days=1),
            )
        )

    # Seed legacy ProductFeatureMention so the products endpoint payload has
    # items to surface (the rollup is independent — driven by the v3
    # raw_analysis_json — but we keep the body non-empty for realism).
    for i, pn in enumerate(("ProductA", "ProductB")):
        db_session.add(
            ProductFeatureMention(
                analysis_id=1,
                brand_name="Primary",
                product_name=pn,
                feature_name="taste",
                feature_sentiment="positive",
                scenario="morning",
                created_at=datetime.now() - timedelta(days=i),
            )
        )
    await db_session.commit()

    resp = await client.get(f"/api/v1/projects/{p.id}/products", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    metric_evidence = body.get("metric_formula_evidence") or {}
    topic_product = metric_evidence.get("topic_product")
    assert topic_product is not None, (
        "topic_product must be derived from v3 packages so the frontend "
        "canUseMetricEvidence(data, 'product') gate passes."
    )
    assert topic_product["formula_status"] == "ok"
    assert topic_product["status"] == "ok"
    # 3 v3 packages * 2 products each = 6
    assert topic_product["product_fact_count"] >= 6
    # Each v3 package contributes 1 topic chain (topic/prompt/query all set).
    assert topic_product["topic_chain_count"] >= 3


@pytest.mark.asyncio
async def test_competitor_metrics_includes_primary_and_competitors(client, user, project_with_data):
    resp = await client.get(
        f"/api/v1/projects/{project_with_data.id}/competitors/metrics",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "ok"
    assert body["formula_status"] == "ok"
    assert body["primary_brand_id"] == 42
    assert body["primary"] is not None
    assert body["primary"]["brand_id"] == 42
    assert body["primary"]["avg_geo_score"] is not None
    assert len(body["competitors"]) == 1
    comp = body["competitors"][0]
    assert comp["brand_id"] == 99
    # Co-mention should be 5 (5 responses had both brands)
    assert comp["co_mention_count"] == 5


@pytest.mark.asyncio
async def test_competitor_metrics_brand_override_keeps_missing_rollup_values_partial(
    client, user, db_session
):
    p = Project(user_id=user.id, name="Override Mentions", primary_brand_id=42, industry_id=1)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    now = datetime.now()
    for i in range(6):
        response_id = 6100 + i
        db_session.add(
            BrandMention(
                response_id=response_id,
                brand_id=12,
                brand_name="Estée Lauder",
                position_rank=1 + (i % 2),
                sentiment_score=0.8,
                created_at=now - timedelta(days=i % 4),
            )
        )
        if i < 4:
            db_session.add(
                BrandMention(
                    response_id=response_id,
                    brand_id=99,
                    brand_name="Clinique",
                    position_rank=2,
                    sentiment_score=0.5,
                    created_at=now - timedelta(days=i % 4),
                )
            )
    await db_session.commit()

    metrics_resp = await client.get(
        f"/api/v1/projects/{p.id}/competitors/metrics",
        headers=_bearer(user),
        params={"brand_id": 12},
    )
    assert metrics_resp.status_code == 200
    metrics_body = metrics_resp.json()
    assert metrics_body["state"] == "partial"
    assert metrics_body["primary_brand_id"] == 12
    assert metrics_body["primary"]["avg_geo_score"] is None
    assert metrics_body["primary"]["avg_mention_rate"] is None
    assert metrics_body["primary"]["avg_sov"] > 0
    assert [c["brand_id"] for c in metrics_body["competitors"]] == [99]
    assert metrics_body["competitors"][0]["co_mention_count"] == 4

    trends_resp = await client.get(
        f"/api/v1/projects/{p.id}/competitors/trends",
        headers=_bearer(user),
        params={"metric": "geo_score", "brand_id": 12},
    )
    assert trends_resp.status_code == 200
    trends_body = trends_resp.json()
    assert trends_body["state"] == "partial"
    primary_series = next(s for s in trends_body["series"] if s["is_primary"])
    assert primary_series["brand_id"] == 12
    assert primary_series["points"] == []


@pytest.mark.asyncio
async def test_brand_override_uses_brand_name_when_mentions_lack_fk(client, user, db_session):
    for col in ("name_zh TEXT", "name_en TEXT", "name TEXT"):
        await db_session.execute(text(f"ALTER TABLE brands ADD COLUMN {col}"))
    await db_session.execute(
        text(
            "INSERT INTO brands (id, name_zh, name_en, name) "
            "VALUES (12, '雅诗兰黛', 'Estee Lauder', 'Estee Lauder')"
        )
    )

    p = Project(user_id=user.id, name="Name Matched Brand", primary_brand_id=42, industry_id=1)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    now = datetime.now()
    for i in range(6):
        response_id = 7100 + i
        db_session.add(
            BrandMention(
                response_id=response_id,
                brand_id=None,
                brand_name="雅诗兰黛",
                position_rank=1,
                sentiment="positive",
                sentiment_score=0.85,
                created_at=now - timedelta(days=i % 5),
            )
        )
        if i < 3:
            db_session.add(
                BrandMention(
                    response_id=response_id,
                    brand_id=99,
                    brand_name="Clinique",
                    position_rank=3,
                    sentiment="neutral",
                    sentiment_score=0.55,
                    created_at=now - timedelta(days=i % 5),
                )
            )
    await db_session.commit()

    overview_resp = await client.get(
        f"/api/v1/projects/{p.id}/overview",
        headers=_bearer(user),
        params={"brand_id": 12},
    )
    assert overview_resp.status_code == 200
    overview_body = overview_resp.json()
    assert overview_body["brand_id"] == 12
    assert overview_body["brand_name"] == "雅诗兰黛"
    assert overview_body["state"] == "partial"
    assert all(card["value"] is None for card in overview_body["kpi_cards"])

    metrics_resp = await client.get(
        f"/api/v1/projects/{p.id}/metrics",
        headers=_bearer(user),
        params={"brand_id": 12, "series": "mention_rate,sov,sentiment"},
    )
    assert metrics_resp.status_code == 200
    metrics_body = metrics_resp.json()
    assert metrics_body["state"] == "partial"
    assert all(series["points"] == [] for series in metrics_body["series"])

    competitors_resp = await client.get(
        f"/api/v1/projects/{p.id}/competitors/metrics",
        headers=_bearer(user),
        params={"brand_id": 12},
    )
    assert competitors_resp.status_code == 200
    competitors_body = competitors_resp.json()
    assert competitors_body["state"] == "partial"
    assert competitors_body["primary_brand_id"] == 12
    assert competitors_body["primary"]["avg_sov"] > 0
    assert [c["brand_id"] for c in competitors_body["competitors"]] == [99]
    assert competitors_body["competitors"][0]["co_mention_count"] == 3

    trends_resp = await client.get(
        f"/api/v1/projects/{p.id}/competitors/trends",
        headers=_bearer(user),
        params={"brand_id": 12, "metric": "geo_score"},
    )
    assert trends_resp.status_code == 200
    trends_body = trends_resp.json()
    primary_series = next(s for s in trends_body["series"] if s["is_primary"])
    assert primary_series["points"] == []


@pytest.mark.asyncio
async def test_competitor_metrics_uses_response_extracted_brand_entities(client, user, db_session):
    p = Project(user_id=user.id, name="Response Entity SoV", primary_brand_id=42, industry_id=1)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    now = datetime.now()
    rows = [
        (7101, 42, "Primary", 0.8),
        (7101, 99, "Clinique", 0.5),
        (7101, None, "Null Rival", 0.2),
        (7102, 42, "Primary", 0.7),
        (7102, 99, "Clinique", 0.4),
        (7103, None, "Null Rival", 0.1),
    ]
    for response_id, brand_id, brand_name, sentiment in rows:
        db_session.add(
            BrandMention(
                response_id=response_id,
                brand_id=brand_id,
                brand_name=brand_name,
                sentiment_score=sentiment,
                created_at=now,
            )
        )
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{p.id}/competitors/metrics",
        headers=_bearer(user),
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "partial"
    assert body["formula_status"] in {"missing_required_inputs", "formula_pending_upstream"}
    assert body["primary"]["brand_id"] == 42
    assert body["primary"]["avg_sov"] == pytest.approx(2 / 6, rel=0.01)
    names = {row["brand_name"]: row for row in body["competitors"]}
    assert names["Clinique"]["avg_sov"] == pytest.approx(2 / 6, rel=0.01)
    assert names["Null Rival"]["brand_id"] is None
    assert names["Null Rival"]["avg_sov"] == pytest.approx(2 / 6, rel=0.01)


@pytest.mark.asyncio
async def test_diagnostics_derives_from_data(client, user, db_session):
    """Insert sharp drop in mention_rate → expect visibility_decline diagnostic."""
    p = Project(user_id=user.id, name="Diag", primary_brand_id=77)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    today = datetime.now().date()
    # Prior 30d: high mention_rate (0.8)
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
    # Current 30d: low mention_rate (0.3) → -62.5%
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

    resp = await client.get(f"/api/v1/projects/{p.id}/diagnostics", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "ok"
    assert len(body["items"]) >= 1
    diag = body["items"][0]
    assert diag["category"] == "visibility_decline"
    assert diag["severity"] == "P1"  # ≤ -30%
    assert diag["evidence"]["change_percent"] is not None


@pytest.mark.asyncio
async def test_diagnostics_empty_for_no_brand(client, user, db_session):
    p = Project(user_id=user.id, name="Diag Empty", primary_brand_id=None)
    db_session.add(p)
    await db_session.commit()
    await db_session.refresh(p, ["competitors"])

    resp = await client.get(f"/api/v1/projects/{p.id}/diagnostics", headers=_bearer(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["state"] == "empty"
    assert body["counts_by_severity"] == {"P0": 0, "P1": 0, "P2": 0, "P3": 0}


@pytest.mark.asyncio
async def test_phase_2_3_cross_tenant_returns_404(client, db_session, project_with_data):
    other = User(
        id=_new_id(),
        email=f"o-{uuid.uuid4().hex[:6]}@example.com",
        name="Other",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(other)
    await db_session.commit()

    for path in ["products", "competitors/metrics", "diagnostics"]:
        resp = await client.get(
            f"/api/v1/projects/{project_with_data.id}/{path}",
            headers=_bearer(other),
        )
        assert resp.status_code == 404, f"path {path}"
        assert resp.json()["detail"]["code"] == "not_found"
