"""Issue #1031: `metric_formula_evidence.trend_30d` rollup.

Backend `/api/v1/projects/<id>/products` must emit
`metric_formula_evidence.trend_30d` so the frontend
`canUseMetricEvidence(data, 'trend_30d')` gate
(BrandProductsPage.tsx:99) returns true. Without this, every
`p.trend = null`, the BCG matrix filter
(`x != null && y != null && z != null` at BrandProductsPage.tsx:134)
drops every row, and the page renders "暂无产品数据".

Design note: the analyzer does NOT produce a per-response `trend_30d`
package directly — `trend_30d` is a page-level signal derived from
per-product `ProductScoreDaily` sparkline samples
(`_brand_service.py:597-604`). The per-package `trend_30d` sub-block is
derived in `_as_v3_package` (`package.py`) from the v3 package's
`collected_at` + `products[]` array (mirrors PR #1050's `topic_product`
derivation), and `_rollup_trend_30d` aggregates these into a page-level
evidence record.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import Any

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
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects.contracts.package import _as_v3_package
from app.api.v1.projects.contracts.rollups import _rollup_trend_30d
from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


def _trend_30d_only_package(
    *,
    response_id: int,
    data_point_count: int,
    product_data_point_count: int = 0,
    reason_codes: list[str] | None = None,
    omit: bool = False,
) -> dict[str, Any]:
    """Minimal package shape that exercises `_rollup_trend_30d`."""
    package: dict[str, Any] = {
        "_package_source": "response_analyses.raw_analysis_json.analyzer_fact_packages",
        "_package_version": "issue_602_v1",
        "_response_ids": [response_id],
        "response_id": response_id,
    }
    if not omit:
        package["trend_30d"] = {
            "status": "ok" if data_point_count > 0 else "empty",
            "data_point_count": data_point_count,
            "product_data_point_count": product_data_point_count,
            "reason_codes": reason_codes or [],
        }
    return package


# ─── Unit tests ────────────────────────────────────────────────────────


def test_rollup_trend_30d_with_packages_having_trend_signal_returns_ok() -> None:
    packages = [
        _trend_30d_only_package(response_id=8001, data_point_count=1, product_data_point_count=2),
        _trend_30d_only_package(response_id=8002, data_point_count=1, product_data_point_count=3),
    ]
    out = _rollup_trend_30d(packages)
    assert out is not None
    assert out["metric_key"] == "trend_30d"
    assert out["status"] == "ok"
    assert out["formula_status"] == "ok"
    assert out["data_point_count"] == 2
    assert out["product_data_point_count"] == 5
    assert out["reason_codes"] == []
    assert set(out["sample_response_ids"]) == {8001, 8002}
    assert "trend_30d" in out["fact_classes"]


def test_rollup_trend_30d_with_no_packages_having_key_returns_none() -> None:
    """Packages without a `trend_30d` key (legacy / non-trend fixtures)
    must return `None` so the contract builder omits the entry and
    preserves backwards compatibility — without this, endpoints that
    have never produced trend data would suddenly cascade
    `formula_status='partial'` (issue #687 regression that bit PR #1043
    for `topic_product`)."""
    packages = [
        _trend_30d_only_package(response_id=8001, data_point_count=0, omit=True),
        _trend_30d_only_package(response_id=8002, data_point_count=0, omit=True),
    ]
    assert _rollup_trend_30d(packages) is None


def test_rollup_trend_30d_with_no_packages_returns_none() -> None:
    """Empty package list (no analyzer evidence at all) returns `None`
    so the builder can skip emitting the entry."""
    assert _rollup_trend_30d([]) is None


def test_rollup_trend_30d_with_all_zero_data_points_is_empty() -> None:
    """Packages carrying the key but with no data points are reported as
    `empty` (not blocking)."""
    packages = [
        _trend_30d_only_package(response_id=8001, data_point_count=0),
    ]
    out = _rollup_trend_30d(packages)
    assert out is not None
    assert out["status"] == "empty"
    assert out["formula_status"] == "empty"
    assert out["data_point_count"] == 0


def test_rollup_trend_30d_aggregates_reason_codes() -> None:
    packages = [
        _trend_30d_only_package(
            response_id=8001,
            data_point_count=1,
            product_data_point_count=1,
            reason_codes=["missing_recent_samples"],
        ),
        _trend_30d_only_package(
            response_id=8002,
            data_point_count=1,
            product_data_point_count=2,
            reason_codes=["missing_recent_samples"],
        ),
    ]
    out = _rollup_trend_30d(packages)
    assert out is not None
    assert out["status"] == "ok"
    assert out["reason_codes"] == ["missing_recent_samples"]


def test_rollup_trend_30d_sample_response_ids_capped() -> None:
    packages = [
        _trend_30d_only_package(
            response_id=8000 + i, data_point_count=1, product_data_point_count=1
        )
        for i in range(10)
    ]
    out = _rollup_trend_30d(packages)
    assert out is not None
    assert out["status"] == "ok"
    assert len(out["sample_response_ids"]) <= 5


# ─── v3 derivation tests ───────────────────────────────────────────────


def _v3_package_payload(
    *,
    response_id: int,
    products: list[dict[str, Any]] | None,
    collected_at: str | None = "2025-05-15T00:00:00",
) -> dict[str, Any]:
    payload = {
        "analyzer_version": "v3",
        "response_id": response_id,
        "query_id": response_id + 1,
        "prompt_id": response_id + 2,
        "topic_id": response_id + 3,
        "source_brand_id": 42,
        "target_brand_id": 42,
        "engine": "deepseek",
        "coverage": {
            "eligible_response_count_basis": 1,
            "analyzed": True,
            "parse_status": "ok",
            "validation_errors": [],
        },
        "entities": {"target": {"brand_id": 42, "canonical_name": "Primary"}},
    }
    if collected_at is not None:
        payload["collected_at"] = collected_at
    if products is not None:
        payload["products"] = products
    return {"analyzer_fact_package_v3": payload}


def test_as_v3_package_derives_trend_30d_when_products_and_collected_at_present() -> None:
    """v3 packages with `collected_at` + `products[]` get a derived
    `trend_30d` sub-block so `_rollup_trend_30d` aggregates them."""
    payload = _v3_package_payload(
        response_id=9001,
        products=[
            {"product_name": "P1", "brand_id": 42},
            {"product_name": "P2", "brand_id": 42},
        ],
    )
    pkg = _as_v3_package(payload)
    assert pkg is not None
    trend = pkg.get("trend_30d")
    assert trend is not None
    assert trend["status"] == "ok"
    assert trend["data_point_count"] == 1
    assert trend["product_data_point_count"] == 2


def test_as_v3_package_omits_trend_30d_when_products_empty() -> None:
    """v3 packages without trend signal (empty `products[]`) must NOT
    receive a `trend_30d` sub-block so `_rollup_trend_30d` returns
    `None` and the contract builder omits the entry. Without this,
    non-products endpoints (sentiment, citations) would emit
    `trend_30d.formula_status='empty'` and cascade into
    `formula_status='partial'` — exact regression
    `test_issue_687_bestcoffer_app_api_contract` guards against."""
    payload = _v3_package_payload(response_id=9002, products=[])
    pkg = _as_v3_package(payload)
    assert pkg is not None
    assert "trend_30d" not in pkg


def test_as_v3_package_omits_trend_30d_when_collected_at_missing() -> None:
    """No `collected_at` means the package can't contribute to a time
    series, so no trend evidence is derived."""
    payload = _v3_package_payload(
        response_id=9003,
        products=[{"product_name": "P1", "brand_id": 42}],
        collected_at=None,
    )
    pkg = _as_v3_package(payload)
    assert pkg is not None
    assert "trend_30d" not in pkg


# ─── Integration regression ────────────────────────────────────────────


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"i1031-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue 1031 User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


def _v3_package_with_products(*, response_id: int, product_count: int = 2) -> dict[str, Any]:
    products = [
        {
            "product_name": f"Product {i + 1}",
            "brand_id": 42,
            "feature_name": None,
            "sentiment": None,
            "snippets": [],
            "formula_status": "ok",
        }
        for i in range(product_count)
    ]
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
        "prompt_version": "issue-1031-test",
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
            "topic_name": "Primary product workflow",
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
async def test_products_emits_trend_30d_evidence(
    client, user: User, db_session: AsyncSession
) -> None:
    """Issue #1031: `/api/v1/projects/<id>/products` must emit
    `metric_formula_evidence.trend_30d` with `formula_status='ok'`
    when in-scope analyzer packages carry trend signal (products[] +
    collected_at). Without this, the frontend
    `canUseMetricEvidence(data, 'trend_30d')` gate returns false and
    the BCG matrix drops every row."""
    project = Project(user_id=user.id, name="Issue 1031", primary_brand_id=42, industry_id=1)
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project, ["competitors"])
    db_session.add(ProjectCompetitor(project_id=project.id, brand_id=99, pinned_by=user.id))

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

    response_ids = [3500, 3501, 3502]
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
                        response_id=rid, product_count=2
                    )
                },
                created_at=datetime.now() - timedelta(days=1),
            )
        )

    # Seed ProductFeatureMention so the products endpoint has items.
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

    resp = await client.get(
        f"/api/v1/projects/{project.id}/products",
        headers=_bearer(user),
    )
    assert resp.status_code == 200
    body = resp.json()
    metric_evidence = body.get("metric_formula_evidence") or {}
    trend = metric_evidence.get("trend_30d")
    assert trend is not None, (
        "trend_30d key missing from metric_formula_evidence; "
        "frontend canUseMetricEvidence(data, 'trend_30d') will return false."
    )
    # Frontend `canUseMetricEvidence` requires `formula_status` in
    # {'ok', 'partial'} to render trend values.
    assert trend["formula_status"] == "ok"
    assert trend["status"] == "ok"
    # 3 v3 packages, each contributes 1 data point.
    assert trend["data_point_count"] >= 3
    # 3 v3 packages * 2 products each = 6 product data points.
    assert trend["product_data_point_count"] >= 6
