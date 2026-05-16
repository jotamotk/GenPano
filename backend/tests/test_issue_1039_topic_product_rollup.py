"""Issue #1039: `metric_formula_evidence.topic_product` rollup.

Backend `/api/v1/projects/<id>/products` must emit
`metric_formula_evidence.topic_product` so the frontend
`canUseMetricEvidence(data, 'product')` gate
(BrandProductsPage.tsx:92) renders the products list when product fact
data exists in any in-scope analyzer package.
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

from app.api.v1.projects.contracts.rollups import _rollup_topic_product
from app.user_auth.jwt import sign_user_access_token

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _bearer(user: User) -> dict[str, str]:
    token, _ = sign_user_access_token(user_id=user.id, email=user.email)
    return {"Authorization": f"Bearer {token}"}


def _topic_product_only_package(
    *,
    response_id: int,
    topic_chain_count: int,
    product_fact_count: int,
    missing_chain_ids: list[int] | None = None,
    reason_codes: list[str] | None = None,
    omit: bool = False,
) -> dict[str, Any]:
    """Minimal package shape that exercises `_rollup_topic_product`."""
    package: dict[str, Any] = {
        "_package_source": "response_analyses.raw_analysis_json.analyzer_fact_packages",
        "_package_version": "issue_602_v1",
        "_response_ids": [response_id],
        "response_id": response_id,
    }
    if not omit:
        package["topic_product"] = {
            "status": "ok" if product_fact_count > 0 or topic_chain_count > 0 else "empty",
            "topic_chain_count": topic_chain_count,
            "product_fact_count": product_fact_count,
            "topic_chain_missing_response_ids": missing_chain_ids or [],
            "product_status": "ok" if product_fact_count > 0 else "empty",
            "reason_codes": reason_codes or [],
        }
    return package


def test_rollup_topic_product_with_product_facts_returns_ok() -> None:
    packages = [
        _topic_product_only_package(response_id=5001, topic_chain_count=1, product_fact_count=3),
        _topic_product_only_package(response_id=5002, topic_chain_count=1, product_fact_count=2),
    ]
    out = _rollup_topic_product(packages)
    assert out is not None
    assert out["metric_key"] == "topic_product"
    assert out["status"] == "ok"
    assert out["formula_status"] == "ok"
    assert out["topic_chain_count"] == 2
    assert out["product_fact_count"] == 5
    assert out["topic_chain_missing_response_ids"] == []
    assert out["reason_codes"] == []
    assert set(out["sample_response_ids"]) == {5001, 5002}
    assert "topic_product" in out["fact_classes"]


def test_rollup_topic_product_with_no_packages_having_key_returns_none() -> None:
    """Packages without a `topic_product` key (legacy / v3 fixtures) should
    return `None` so the contract builder can omit the entry and preserve
    backwards compatibility for callers that never consumed product
    evidence (issue #1039)."""
    packages = [
        _topic_product_only_package(
            response_id=5001, topic_chain_count=0, product_fact_count=0, omit=True
        ),
        _topic_product_only_package(
            response_id=5002, topic_chain_count=0, product_fact_count=0, omit=True
        ),
    ]
    assert _rollup_topic_product(packages) is None


def test_rollup_topic_product_with_all_zero_counts_is_empty() -> None:
    packages = [
        _topic_product_only_package(response_id=5001, topic_chain_count=0, product_fact_count=0),
    ]
    out = _rollup_topic_product(packages)
    assert out is not None
    assert out["status"] == "empty"
    assert out["formula_status"] == "empty"
    assert out["product_fact_count"] == 0


def test_rollup_topic_product_aggregates_reason_codes_and_missing_chain_ids() -> None:
    packages = [
        _topic_product_only_package(
            response_id=5001,
            topic_chain_count=0,
            product_fact_count=1,
            missing_chain_ids=[5001],
            reason_codes=["missing_topic_prompt_query_chain"],
        ),
        _topic_product_only_package(
            response_id=5002,
            topic_chain_count=1,
            product_fact_count=1,
            missing_chain_ids=[],
            reason_codes=["missing_topic_prompt_query_chain"],
        ),
    ]
    out = _rollup_topic_product(packages)
    assert out is not None
    assert out["status"] == "ok"
    assert out["formula_status"] == "ok"
    assert out["topic_chain_count"] == 1
    assert out["product_fact_count"] == 2
    assert out["topic_chain_missing_response_ids"] == [5001]
    # Reason codes deduplicated.
    assert out["reason_codes"] == ["missing_topic_prompt_query_chain"]


def test_rollup_topic_product_sample_response_ids_capped() -> None:
    packages = [
        _topic_product_only_package(response_id=5000 + i, topic_chain_count=1, product_fact_count=1)
        for i in range(10)
    ]
    out = _rollup_topic_product(packages)
    assert out is not None
    assert out["status"] == "ok"
    assert len(out["sample_response_ids"]) <= 5


def test_rollup_topic_product_with_no_packages_returns_none() -> None:
    """Empty package list (no analyzer evidence at all) returns `None` so
    the builder can skip emitting a `topic_product` entry."""
    assert _rollup_topic_product([]) is None


# ─── Integration regression ────────────────────────────────────────────


@pytest_asyncio.fixture
async def user(db_session: AsyncSession) -> User:
    u = User(
        id=_new_id(),
        email=f"i1039-{uuid.uuid4().hex[:6]}@example.com",
        name="Issue 1039 User",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    db_session.add(u)
    await db_session.commit()
    return u


def _topic_product_packages(*, response_id: int, product_fact_count: int) -> dict[str, Any]:
    """Minimal `analyzer_fact_packages` payload — only the fields the
    contract builder needs to scope the package and surface
    `topic_product` evidence."""
    return {
        "version": "issue_602_v1",
        "coverage": {
            "status": "ok",
            "formula_status": "ok",
            "eligible_response_ids": [response_id],
            "analyzed_response_ids": [response_id],
            "failed_response_ids": [],
            "missing_analyzer_response_ids": [],
            "eligible_count": 1,
            "analyzed_count": 1,
            "failed_count": 0,
            "missing_analyzer_count": 0,
            "reason_codes": [],
            "chains": [],
        },
        "entities": {
            "status": "ok",
            "target_brand_id": 42,
            "target_brand_name": "Primary",
            "facts": [],
        },
        "topic_product": {
            "status": "ok",
            "topic_chain_count": 1,
            "product_fact_count": product_fact_count,
            "topic_chain_missing_response_ids": [],
            "product_status": "ok" if product_fact_count > 0 else "empty",
            "reason_codes": [],
        },
    }


@pytest.mark.asyncio
async def test_products_emits_topic_product_evidence(
    client, user: User, db_session: AsyncSession
) -> None:
    """Issue #1039: `/api/v1/projects/<id>/products` must emit
    `metric_formula_evidence.topic_product` with `formula_status='ok'`
    when product fact data exists in any in-scope analyzer package.
    Without this, the frontend `canUseMetricEvidence(data, 'product')`
    returns false and the page renders empty.
    """
    project = Project(user_id=user.id, name="Issue 1039", primary_brand_id=42, industry_id=1)
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

    response_ids = [3000, 3001, 3002]
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
                    "analyzer_fact_packages": _topic_product_packages(
                        response_id=rid, product_fact_count=2
                    )
                },
                created_at=datetime.now() - timedelta(days=1),
            )
        )

    # Seed product mentions so the products endpoint has something to
    # return (the rollup must still emit `topic_product` evidence).
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
    topic_product = metric_evidence.get("topic_product")
    assert topic_product is not None, (
        "topic_product key missing from metric_formula_evidence; "
        "frontend canUseMetricEvidence(data, 'product') will return false."
    )
    # Frontend `canUseMetricEvidence` requires `formula_status` in
    # {'ok', 'partial'} to render the products list.
    assert topic_product["formula_status"] == "ok"
    assert topic_product["status"] == "ok"
    # 3 response packages * product_fact_count=2 each = 6
    assert topic_product["product_fact_count"] >= 6
    assert topic_product["topic_chain_count"] >= 3
