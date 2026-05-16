"""Local reproduction of /api/v1/projects/<id>/products response shape.

Evidence-First Debugging (AGENTS.md): the live env is not reachable from
this sandbox, so this script spins up an in-memory SQLite schema (via
`Base.metadata.create_all`), seeds a `Project` with primary_brand_id=24
(BestCoffer's brand_id per `tests/test_issue_744_bestcoffer_chart_aggregates.py:113`)
and three flavors of `ResponseAnalysis.raw_analysis_json.analyzer_fact_packages`,
then calls `get_products()` directly (skipping HTTP/auth) and pretty-prints
the JSON the endpoint would emit.

Scenarios:
  (a) packages contain `topic_product` with `product_fact_count > 0`
      → expected: `metric_formula_evidence.topic_product.formula_status == "ok"`
      → frontend `canUseMetricEvidence(data, 'product')` should pass
  (b) packages contain `topic_product` but `product_fact_count = 0`
      → expected: contract emits `topic_product.status == "empty"`,
        `formula_status == "empty"`; frontend gate FAILS
  (c) packages do NOT contain `topic_product` key at all (legacy v3 / older
      issue_602_v1 fixtures)
      → expected: PR #1043 preserves backwards-compat by OMITTING
        `topic_product` from `metric_formula_evidence`
  (d) raw_analysis_json is `{"analyzer_fact_package_v3": {...}}` carrying
      a non-empty `products[]` array (BestCoffer prod shape)
      → expected (post-issue-#1049): `_as_v3_package` derives a
        `topic_product` sub-block from `products[]`, so the rollup
        emits `topic_product.formula_status == "ok"` and the gate
        PASSES even though the v3 schema never carried that key directly.
  (e) Issue #1040 root-cause repro: same as (d) (v3 packages exist so the
      gate PASSes), PLUS multiple distinct `ProductFeatureMention.product_name`
      rows so the fallback path returns multiple items — but
      `product_score_daily` remains EMPTY (the table the daily aggregator
      Celery task would populate, except no beat schedule fires it).
      → expected: `items[*].product_name` populated for each distinct
        product, `items[*].mention_rate / sov / avg_sentiment / ranking /
        trend_30d` all NULL, `metric_formula_evidence.topic_product.
        formula_status == "ok"` (frontend gate PASSES). This is exactly
        the BestCoffer screenshot pattern — page renders, all per-product
        metric columns show "--".
  (f) Issue #1031 trend_30d evidence repro: v3 packages with non-empty
      products[] should now emit BOTH `metric_formula_evidence.topic_product`
      AND `metric_formula_evidence.trend_30d` (status="ok"). Asserts the
      bcgData-style filter (`x != null && y != null && z != null`) would
      pass for at least one product when sparkline + mention_count are
      populated. Without trend_30d evidence, the frontend
      `canUseMetricEvidence(data, 'trend_30d')` gate returns false and
      EVERY row in the BCG matrix is dropped → "暂无产品数据".
  (g) Issue #1031 BCG row-filter repro: same v3 setup as (f), PLUS seed
      20 days of `ProductScoreDaily` rows per product (mention_rate > 0)
      so the per-product sparkline crosses the 14-day threshold in
      `_brand_service.py:601` and per-product `trend_30d` is computed
      (non-null). This is the FULL happy path:
      - `metric_formula_evidence.trend_30d.formula_status == "ok"` (gate)
      - per-item `trend_30d`, `mention_rate`, `mention_count` are all
        non-null so the BCG filter (`x,y,z != null`) passes for ≥1 row
      If (f) passes but (g) drops rows: confirms the page-level gate is
      correct AND the per-product compute path works when given enough
      ProductScoreDaily history — so production "暂无产品数据" means
      BestCoffer has < 14 days of `product_score_daily` rows per product.
  (h) Issue #1031 EARLY-STAGE BRAND repro: v3 packages PLUS only 5 days of
      `ProductScoreDaily` per product (between the new
      `MIN_SPARKLINE_DAYS=3` floor and the old `>= 14` threshold). After
      lowering the threshold + switching to an adaptive half-and-half
      window, the per-product `trend_30d` MUST still compute (non-null)
      and the BCG filter MUST pass for ≥1 row. Pre-fix this scenario
      would produce `trend_30d=None` on every product and render
      "暂无产品数据" even though the brand has visible products. This is
      the BestCoffer simulation.

Usage:
  uv run python backend/scripts/inspect_products_response.py
  # or, from backend/:
  uv run python scripts/inspect_products_response.py

Idempotent: each run uses a fresh temp SQLite file that's removed on exit.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Make this script runnable either as `python backend/scripts/...` from repo
# root or as `python scripts/...` from inside `backend/`. Either way we add
# `backend/` to sys.path so the `app` / `genpano_models` packages resolve.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Set required env vars BEFORE importing the app modules that read them.
os.environ.setdefault("USER_JWT_SECRET", "x" * 64)
os.environ.setdefault("GENPANO_RATE_LIMIT_DISABLED", "1")

# Importing this side-effect registers upstream Tables (llm_responses, brands,
# competitors, prompts) so `Base.metadata.create_all` produces the same
# schema the test conftest uses.
from genpano_models import (  # noqa: E402
    Base,
    BrandMention,
    GeoScoreDaily,
    ProductFeatureMention,
    ProductScoreDaily,
    Project,
    ProjectCompetitor,
    ResponseAnalysis,
    User,
)
from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.api.v1.projects._brand_service import get_products  # noqa: E402
from app.db import _upstream_stubs  # noqa: E402, F401

# BestCoffer brand_id per `tests/test_issue_744_bestcoffer_chart_aggregates.py:113`
# and `tests/test_issue_711_analyzer_v3_fact_contract.py:38`.
BESTCOFFER_BRAND_ID = 24


def _v3_package_with_products(
    *,
    response_id: int,
    product_count: int,
) -> dict[str, Any]:
    """Minimal `analyzer_fact_package_v3` fixture mirroring BestCoffer prod
    shape, where `raw_analysis_json` carries the durable v3 contract
    (`geo_tracker/analyzer/fact_contract.py::build_response_fact_package_v3`)
    and never the legacy `analyzer_fact_packages` block.

    The v3 schema pre-dates the per-response `topic_product` sub-block;
    `_as_v3_package` (issue #1049) derives it from the `products[]` array.
    """
    products = [
        {
            "product_name": f"BestCoffer Product {i + 1}",
            "brand_id": BESTCOFFER_BRAND_ID,
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
        "source_brand_id": BESTCOFFER_BRAND_ID,
        "target_brand_id": BESTCOFFER_BRAND_ID,
        "engine": "deepseek",
        "collected_at": datetime.now().isoformat(),
        "analysis_started_at": datetime.now().isoformat(),
        "analysis_completed_at": datetime.now().isoformat(),
        "provider": "openai",
        "model": "gpt-4.1-mini",
        "prompt_version": "issue-1049-inspect",
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
                "brand_id": BESTCOFFER_BRAND_ID,
                "canonical_name": "BestCoffer",
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
            "topic_name": "BestCoffer espresso workflow",
            "dimension": "product",
            "associated_brand_id": BESTCOFFER_BRAND_ID,
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


def _topic_product_packages(
    *,
    response_id: int,
    product_fact_count: int,
    topic_chain_count: int = 1,
    include_topic_product: bool = True,
) -> dict[str, Any]:
    """Minimal `analyzer_fact_packages` payload mimicking the shape in
    `tests/test_issue_603_analyzer_evidence_contract.py:273-280` and
    `tests/test_issue_1039_topic_product_rollup.py:183-217`.

    When `include_topic_product=False` the `topic_product` key is omitted
    entirely — this mimics legacy v3 / older issue_602_v1 fixtures that
    PR #1043 must preserve unchanged.
    """
    package: dict[str, Any] = {
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
            "target_brand_id": BESTCOFFER_BRAND_ID,
            "target_brand_name": "BestCoffer",
            "facts": [],
        },
    }
    if include_topic_product:
        package["topic_product"] = {
            "status": "ok" if product_fact_count > 0 or topic_chain_count > 0 else "empty",
            "topic_chain_count": topic_chain_count,
            "product_fact_count": product_fact_count,
            "topic_chain_missing_response_ids": [],
            "product_status": "ok" if product_fact_count > 0 else "empty",
            "reason_codes": [],
        }
    return package


async def _create_schema(engine: Any) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed_user_and_project(session: AsyncSession) -> tuple[User, Project]:
    user = User(
        id=str(uuid.uuid4()),
        email=f"inspect-{uuid.uuid4().hex[:8]}@example.com",
        name="Inspect Bot",
        role="free",
        provider="email",
        email_verified=True,
        password_hash="dummy",
        locale="zh-CN",
    )
    session.add(user)
    await session.flush()

    project = Project(
        user_id=user.id,
        name="BestCoffer inspect",
        primary_brand_id=BESTCOFFER_BRAND_ID,
        industry_id=1,
    )
    session.add(project)
    await session.flush()
    # Force the selectin-loaded `competitors` relationship to be present so
    # downstream code can iterate it without lazy-load surprises.
    await session.refresh(project, ["competitors"])
    return user, project


async def _seed_common_evidence(
    session: AsyncSession,
    *,
    project: Project,
    user: User,
    response_ids: list[int],
    product_fact_count: int,
    include_topic_product: bool,
    topic_chain_count: int = 1,
    v3_payload: bool = False,
    product_score_daily_days: int = 0,
    product_score_daily_names: tuple[str, ...] = (
        "BestCoffer Filter",
        "BestCoffer Cold Brew",
        "BestCoffer Espresso",
    ),
) -> None:
    """Seed the minimum tables the contract builder & products service read.

    Per `app/api/v1/projects/contracts/builder.py:_load_in_scope_packages`
    the topic_product rollup requires:
      - `ResponseAnalysis.raw_analysis_json.analyzer_fact_packages` carrying
        a `topic_product` key (or NOT, for scenario c)
      - `BrandMention` rows so `_target_response_ids` returns the response_ids
        we care about (these get filtered through `brand_mention_match_condition`)
    `GeoScoreDaily` rows make the contract context non-empty and ensure
    `_first_class_analyzer_fact_rollup` doesn't short-circuit.
    """
    now = datetime.now()
    today = now.date()

    # Pin one competitor so `_competitor_ids` returns something realistic.
    session.add(ProjectCompetitor(project_id=project.id, brand_id=99, pinned_by=user.id))

    # 5 days of GeoScoreDaily for the BestCoffer brand.
    for i in range(5):
        d = today - timedelta(days=i)
        session.add(
            GeoScoreDaily(
                brand_id=BESTCOFFER_BRAND_ID,
                date=datetime.combine(d, datetime.min.time()),
                target_llm="chatgpt",
                avg_geo_score=70.0,
                mention_rate=0.6,
                avg_sov=0.4,
                avg_sentiment=0.7,
                total_queries=100,
            )
        )

    # Brand mentions + response analyses (one per response_id).
    for rid in response_ids:
        session.add(
            BrandMention(
                response_id=rid,
                brand_id=BESTCOFFER_BRAND_ID,
                brand_name="BestCoffer",
                sentiment="positive",
                sentiment_score=0.6,
                created_at=now - timedelta(days=1),
            )
        )
        if v3_payload:
            raw_json = {
                "analyzer_fact_package_v3": _v3_package_with_products(
                    response_id=rid,
                    product_count=product_fact_count,
                )
            }
        else:
            raw_json = {
                "analyzer_fact_packages": _topic_product_packages(
                    response_id=rid,
                    product_fact_count=product_fact_count,
                    topic_chain_count=topic_chain_count,
                    include_topic_product=include_topic_product,
                )
            }
        session.add(
            ResponseAnalysis(
                response_id=rid,
                target_brand_mentioned=True,
                sentiment_score=0.6,
                analyzed_at=now - timedelta(days=1),
                raw_analysis_json=raw_json,
                created_at=now - timedelta(days=1),
            )
        )

    # ProductFeatureMention rows so the products endpoint has something to
    # return (legacy fallback path); they don't influence the topic_product
    # rollup, but they keep the response body non-empty so we can see what
    # the production payload actually looks like.
    await session.flush()  # ensures ResponseAnalysis.id is populated
    analysis_ids = list(
        (
            await session.execute(  # type: ignore[arg-type]
                select(ResponseAnalysis.id).where(ResponseAnalysis.response_id.in_(response_ids))
            )
        ).scalars()
    )
    for i, pn in enumerate(("BestCoffer Filter", "BestCoffer Cold Brew", "BestCoffer Espresso")):
        analysis_id = analysis_ids[i % len(analysis_ids)] if analysis_ids else 1
        session.add(
            ProductFeatureMention(
                analysis_id=analysis_id,
                brand_name="BestCoffer",
                product_name=pn,
                feature_name="aroma" if i % 2 == 0 else "smoothness",
                feature_sentiment="positive",
                scenario="morning" if i % 2 == 0 else "afternoon",
                created_at=now - timedelta(days=i),
            )
        )

    # Scenario (g) — seed `product_score_daily` so the per-product sparkline
    # in `_brand_service.py:598-604` crosses the 14-day threshold required
    # for `trend_30d` to be computed (not null). Production gets these rows
    # from the daily aggregator (`geo_tracker.analyzer.aggregator.
    # Aggregator._aggregate_product_daily`); the inspect harness writes
    # them directly. Per the model's UniqueConstraint
    # (`uq_product_daily(brand_id, product_name, date, target_llm)`) we
    # write one row per (product, day) with target_llm=None to mirror
    # what `_aggregate_product_daily` produces.
    if product_score_daily_days > 0:
        for day_offset in range(product_score_daily_days):
            d = today - timedelta(days=day_offset)
            for j, pname in enumerate(product_score_daily_names):
                session.add(
                    ProductScoreDaily(
                        brand_id=BESTCOFFER_BRAND_ID,
                        product_name=pname,
                        category="coffee",
                        date=datetime.combine(d, datetime.min.time()),
                        target_llm=None,
                        total_queries=100,
                        mention_count=10 + j,
                        # Vary mention_rate by day so trend_30d resolves to
                        # a non-zero number (avg first-7 vs last-7 differ).
                        mention_rate=round(0.20 + 0.01 * day_offset + 0.05 * j, 4),
                        avg_position_rank=2.0 + j * 0.5,
                        first_place_count=2,
                        first_place_rate=0.2,
                        avg_sentiment_score=0.7,
                        avg_geo_score=72.0,
                        category_sov_pct=0.30 + 0.05 * j,
                        category_rank=j + 1,
                        comparison_wins=3,
                        comparison_total=5,
                        win_rate=0.6,
                    )
                )
    await session.commit()


def _can_use_metric_evidence(data: dict[str, Any], metric: str = "product") -> tuple[bool, str]:
    """Python emulation of the frontend `canUseMetricEvidence(data, 'product')`
    guard (BrandProductsPage.tsx:92).

    The frontend gate maps `metric='product'` to evidence key 'topic_product'
    and passes when:
      - `metric_formula_evidence.<key>` exists
      - `formula_status` in {'ok', 'partial'}
      - `state` in {'ok', 'partial'}
    For metric='trend_30d' the gate maps to evidence key 'trend_30d'.
    """
    evidence_key = "topic_product" if metric == "product" else metric
    metric_evidence = data.get("metric_formula_evidence") or {}
    evidence = metric_evidence.get(evidence_key)
    if not evidence:
        return False, f"missing metric_formula_evidence.{evidence_key}"
    formula_status = str(evidence.get("formula_status") or "")
    state = str(evidence.get("status") or "")
    if formula_status not in {"ok", "partial"}:
        return False, f"formula_status={formula_status!r} not in ok|partial"
    if state and state not in {"ok", "partial"}:
        return False, f"status={state!r} not in ok|partial"
    return True, f"formula_status={formula_status} status={state}"


def _bcg_filter_would_pass(items: list[dict[str, Any]]) -> tuple[bool, int, int]:
    """Python emulation of BrandProductsPage.tsx:134 BCG filter
    (`x != null && y != null && z != null`), where x=mention_rate,
    y=trend_30d, z=mention_count. Returns (any_row_passes, passing_count,
    total_count). Page renders "暂无产品数据" when no row passes.
    """
    total = len(items)
    passing = 0
    for item in items:
        x = item.get("mention_rate")
        y = item.get("trend_30d")
        z = item.get("mention_count")
        if x is not None and y is not None and z is not None:
            passing += 1
    return passing > 0, passing, total


def _scenario_banner(label: str, description: str) -> str:
    width = 78
    return "\n".join(
        [
            "",
            "=" * width,
            f"SCENARIO {label}: {description}",
            "=" * width,
        ]
    )


async def _run_scenario(
    label: str,
    description: str,
    *,
    response_ids: list[int],
    product_fact_count: int,
    include_topic_product: bool,
    topic_chain_count: int = 1,
    v3_payload: bool = False,
    product_score_daily_days: int = 0,
) -> dict[str, Any]:
    """Spin up a fresh SQLite DB, seed it, call get_products(), return dump."""
    with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as tmp:
        db_path = Path(tmp.name)
    url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(url, future=True)
    try:
        await _create_schema(engine)
        sessionmaker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
        async with sessionmaker() as session:
            user, project = await _seed_user_and_project(session)
            await _seed_common_evidence(
                session,
                project=project,
                user=user,
                response_ids=response_ids,
                product_fact_count=product_fact_count,
                include_topic_product=include_topic_product,
                topic_chain_count=topic_chain_count,
                v3_payload=v3_payload,
                product_score_daily_days=product_score_daily_days,
            )

        # Re-open a fresh session for the actual service call so the
        # identity_map is empty (mimicking the request flow).
        async with sessionmaker() as session:
            project_row = (
                await session.execute(  # type: ignore[arg-type]
                    select(Project)
                )
            ).scalar_one()
            out = await get_products(session, project_row)
            body = out.model_dump(mode="json")
    finally:
        await engine.dispose()
        db_path.unlink(missing_ok=True)  # noqa: ASYNC240 — script cleanup, OK to block

    banner = _scenario_banner(label, description)
    print(banner)
    print(json.dumps(body, indent=2, sort_keys=True, default=str))

    passes, reason = _can_use_metric_evidence(body, "product")
    metric_evidence = body.get("metric_formula_evidence") or {}
    has_topic_product = "topic_product" in metric_evidence
    print(
        "\n-- canUseMetricEvidence(data, 'product') emulation --\n"
        f"  result: {'PASS' if passes else 'FAIL'}\n"
        f"  reason: {reason}\n"
        f"  metric_formula_evidence keys: {sorted(metric_evidence.keys())}\n"
        f"  topic_product key present: {has_topic_product}"
    )

    # Issue #1031: separate gate for trend_30d, plus BCG filter audit.
    trend_passes, trend_reason = _can_use_metric_evidence(body, "trend_30d")
    has_trend_30d = "trend_30d" in metric_evidence
    bcg_pass, bcg_passing_count, bcg_total = _bcg_filter_would_pass(body.get("items") or [])
    print(
        "\n-- canUseMetricEvidence(data, 'trend_30d') emulation (Issue #1031) --\n"
        f"  result: {'PASS' if trend_passes else 'FAIL'}\n"
        f"  reason: {trend_reason}\n"
        f"  trend_30d key present: {has_trend_30d}\n"
        f"  BCG filter (x,y,z != null): {bcg_passing_count}/{bcg_total} rows pass "
        f"({'render' if bcg_pass else '暂无产品数据'})"
    )

    # Per-item metric audit — surfaces the BestCoffer screenshot pattern
    # (product names populated but every per-product metric column is "--").
    items_metric_audit: list[dict[str, Any]] = []
    for item in body.get("items") or []:
        items_metric_audit.append(
            {
                "product_name": item.get("product_name"),
                "mention_count": item.get("mention_count"),
                "mention_rate": item.get("mention_rate"),
                "sov": item.get("sov"),
                "avg_sentiment": item.get("avg_sentiment"),
                "ranking": item.get("ranking"),
                "trend_30d": item.get("trend_30d"),
            }
        )

    return {
        "label": label,
        "passes_gate": passes,
        "reason": reason,
        "has_topic_product": has_topic_product,
        "metric_evidence_keys": sorted(metric_evidence.keys()),
        "topic_product": metric_evidence.get("topic_product"),
        "trend_30d": metric_evidence.get("trend_30d"),
        "has_trend_30d": has_trend_30d,
        "trend_30d_passes_gate": trend_passes,
        "trend_30d_reason": trend_reason,
        "bcg_filter_pass": bcg_pass,
        "bcg_filter_passing_count": bcg_passing_count,
        "bcg_filter_total": bcg_total,
        "state": body.get("state"),
        "total": body.get("total"),
        "evidence_count": body.get("evidence_count"),
        "items_metric_audit": items_metric_audit,
    }


async def main() -> None:
    print(
        "Local reproduction of /api/v1/projects/<id>/products.\n"
        f"Brand: BestCoffer (brand_id={BESTCOFFER_BRAND_ID}).\n"
        "Each scenario spins up an isolated in-memory schema, so results are\n"
        "deterministic and independent of any prior state."
    )

    summaries: list[dict[str, Any]] = []
    summaries.append(
        await _run_scenario(
            "(a)",
            "packages CONTAIN topic_product with product_fact_count > 0 (page should render)",
            response_ids=[3000, 3001, 3002],
            product_fact_count=2,
            include_topic_product=True,
        )
    )
    # Scenario (b) — to surface `topic_product.status == "empty"` the rollup
    # requires BOTH product_fact_count == 0 AND topic_chain_count == 0
    # (rollups.py:_rollup_topic_product:345-352). Anything else returns "ok".
    summaries.append(
        await _run_scenario(
            "(b)",
            "packages CONTAIN topic_product but product_fact_count = 0 "
            "AND topic_chain_count = 0 (empty, contract emits status='empty')",
            response_ids=[4000, 4001, 4002],
            product_fact_count=0,
            include_topic_product=True,
            topic_chain_count=0,
        )
    )
    summaries.append(
        await _run_scenario(
            "(c)",
            "packages DO NOT contain topic_product key "
            "(PR #1043: contract OMITS the entry entirely)",
            response_ids=[5000, 5001, 5002],
            product_fact_count=0,
            include_topic_product=False,
        )
    )
    # Scenario (d) — Issue #1049: v3 payload (BestCoffer prod shape) with
    # non-empty products[]. Pre-fix this returned `topic_product` missing
    # because v3 schema never carried that key. Post-fix `_as_v3_package`
    # derives it from products[], so the gate PASSes.
    summaries.append(
        await _run_scenario(
            "(d)",
            "raw_analysis_json carries analyzer_fact_package_v3 with "
            "products[] (BestCoffer prod shape) — Issue #1049 derivation "
            "should make the gate PASS",
            response_ids=[6000, 6001, 6002],
            product_fact_count=2,
            include_topic_product=False,  # ignored when v3_payload=True
            v3_payload=True,
        )
    )
    # Scenario (e) — Issue #1040 root cause: v3 packages populate the
    # `topic_product` rollup (so the page renders), AND multiple distinct
    # ProductFeatureMention product_name rows populate the fallback list,
    # BUT product_score_daily is empty (the aggregate_daily_scores Celery
    # task has no beat schedule). Each item should have a populated
    # product_name + mention_count from the fallback, but mention_rate /
    # sov / avg_sentiment / ranking / trend_30d will all be NULL.
    summaries.append(
        await _run_scenario(
            "(e)",
            "Issue #1040 reproducer — v3 packages PASS the gate but "
            "product_score_daily is empty so per-product metric columns "
            "are all NULL (matches BestCoffer screenshot)",
            response_ids=[7000, 7001, 7002],
            product_fact_count=3,
            include_topic_product=False,
            v3_payload=True,
        )
    )
    # Scenario (f) — Issue #1031: v3 packages with products[] should now
    # emit `metric_formula_evidence.trend_30d.formula_status="ok"`
    # (post-fix). Asserts:
    #   - trend_30d evidence key is present
    #   - frontend canUseMetricEvidence(data, 'trend_30d') gate PASSes
    # The BCG filter still requires per-product `mention_rate`,
    # `trend_30d`, `mention_count` all non-null — which depends on
    # `product_score_daily` having data. Since this scenario seeds
    # ProductScoreDaily-equivalent data via the fallback path's
    # ProductFeatureMention rows (mention_count populated), but
    # per-product trend_30d is computed from sparkline (requires 14+
    # days of ProductScoreDaily), the BCG row filter will still drop
    # rows when sparkline is empty. The IMPORTANT result for #1031 is
    # that the `trend_30d` evidence key exists and its formula_status
    # is "ok" so the FE gate flips to true.
    summaries.append(
        await _run_scenario(
            "(f)",
            "Issue #1031 trend_30d evidence repro — v3 packages with "
            "products[] should emit metric_formula_evidence.trend_30d.formula_status='ok'",
            response_ids=[8000, 8001, 8002],
            product_fact_count=3,
            include_topic_product=False,
            v3_payload=True,
        )
    )
    # Scenario (g) — Issue #1031 FULL happy-path: v3 packages PLUS 20 days
    # of ProductScoreDaily per product so the per-product sparkline triggers
    # the legacy first-7 vs last-7 path in `_compute_trend_30d`
    # (`_brand_service.py`) and `trend_30d` is non-null per item. Verifies
    # that when production has 14+ days of `product_score_daily` history
    # for a brand, the BCG filter (`x,y,z != null`) passes for ≥1 row and
    # the page renders. Scenario (h) covers the early-stage (< 14 days) case.
    summaries.append(
        await _run_scenario(
            "(g)",
            "Issue #1031 BCG row-filter happy path — v3 packages + 20 "
            "days of ProductScoreDaily (>=14) so per-product trend_30d "
            "is non-null and the BCG filter passes for >=1 row",
            response_ids=[9000, 9001, 9002],
            product_fact_count=3,
            include_topic_product=False,
            v3_payload=True,
            product_score_daily_days=20,
        )
    )
    # Scenario (h) — Issue #1031 EARLY-STAGE BRAND: v3 packages PLUS only
    # 5 days of ProductScoreDaily per product. This sits BETWEEN the new
    # `MIN_SPARKLINE_DAYS=3` floor and the legacy `>= 14` threshold.
    # Pre-fix (`len(sparkline) >= 14`) this would render "暂无产品数据"
    # because every product's `trend_30d` was None. Post-fix the adaptive
    # window (`min(7, len // 2)` → window=2 here) computes a non-zero
    # trend and the BCG filter passes for ≥1 row. This is the BestCoffer
    # production simulation (brand barely a week old).
    summaries.append(
        await _run_scenario(
            "(h)",
            "Issue #1031 EARLY-STAGE BRAND — v3 packages + only 5 days "
            "of ProductScoreDaily (between MIN_SPARKLINE_DAYS=3 and the "
            "legacy 14-day threshold). Adaptive window should still "
            "produce a non-null trend_30d so the BCG filter passes",
            response_ids=[10000, 10001, 10002],
            product_fact_count=3,
            include_topic_product=False,
            v3_payload=True,
            product_score_daily_days=5,
        )
    )

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    for s in summaries:
        print(
            f"  {s['label']}: gate={'PASS' if s['passes_gate'] else 'FAIL'} "
            f"reason={s['reason']!r} "
            f"topic_product_present={s['has_topic_product']} "
            f"trend_30d_present={s['has_trend_30d']} "
            f"trend_gate={'PASS' if s['trend_30d_passes_gate'] else 'FAIL'} "
            f"bcg_filter={s['bcg_filter_passing_count']}/{s['bcg_filter_total']} "
            f"state={s['state']!r} total={s['total']} "
            f"evidence_count={s['evidence_count']}"
        )
        # Scenarios (e) and (g) inspect per-item metric nullity to confirm
        # the BestCoffer screenshot pattern (e: Issue #1040 — all per-item
        # metrics NULL) vs the full happy path (g: Issue #1031 — per-item
        # mention_rate / trend_30d / mention_count all non-null so the BCG
        # row filter passes).
        if s["label"] in {"(e)", "(g)", "(h)"}:
            for item in s.get("items_metric_audit") or []:
                print(
                    f"      item.product_name={item['product_name']!r} "
                    f"mention_count={item['mention_count']} "
                    f"mention_rate={item['mention_rate']} "
                    f"sov={item['sov']} avg_sentiment={item['avg_sentiment']} "
                    f"ranking={item['ranking']} trend_30d={item['trend_30d']}"
                )

    # Issue #1031 explicit assertion — scenario (f) must surface
    # `metric_formula_evidence.trend_30d.formula_status == "ok"`.
    scenario_f = next((s for s in summaries if s["label"] == "(f)"), None)
    if scenario_f is None:
        raise AssertionError("scenario (f) result missing from summaries")
    trend_evidence = scenario_f["trend_30d"]
    assert trend_evidence is not None, (
        "scenario (f): metric_formula_evidence.trend_30d MUST be present (Issue #1031); got None"
    )
    formula_status = trend_evidence.get("formula_status")
    assert formula_status == "ok", (
        f"scenario (f): metric_formula_evidence.trend_30d.formula_status "
        f"MUST be 'ok'; got {formula_status!r}"
    )
    assert scenario_f["trend_30d_passes_gate"], (
        f"scenario (f): canUseMetricEvidence(data, 'trend_30d') gate "
        f"MUST pass; got reason={scenario_f['trend_30d_reason']!r}"
    )
    print(
        "\n-- Issue #1031 assertion --\n"
        "  scenario (f) trend_30d evidence: PASS\n"
        f"  formula_status={formula_status!r} status={trend_evidence.get('status')!r}\n"
        f"  data_point_count={trend_evidence.get('data_point_count')}\n"
        f"  product_data_point_count={trend_evidence.get('product_data_point_count')}\n"
        f"  BCG filter pass: {scenario_f['bcg_filter_passing_count']}"
        f"/{scenario_f['bcg_filter_total']} rows "
        f"({'render' if scenario_f['bcg_filter_pass'] else '暂无产品数据'})\n"
        "  NOTE: BCG row filter additionally requires per-product sparkline\n"
        "        + mention_count, which depends on product_score_daily having\n"
        "        >= 14 days of data. Issue #1031 fixes the gate; per-product\n"
        "        rendering still needs ProductScoreDaily rows."
    )

    # Issue #1031 scenario (g) assertion — FULL happy path: with 20 days of
    # ProductScoreDaily seeded, per-product `trend_30d` MUST be non-null on
    # at least one item AND the BCG row filter (`x,y,z != null`) MUST pass
    # for >=1 row. If this fails, the per-product compute path in
    # `_brand_service.py:598-604` is broken (NOT the page-level rollup).
    scenario_g = next((s for s in summaries if s["label"] == "(g)"), None)
    if scenario_g is None:
        raise AssertionError("scenario (g) result missing from summaries")
    items_g = scenario_g.get("items_metric_audit") or []
    items_with_trend = [it for it in items_g if it.get("trend_30d") is not None]
    assert items_g, "scenario (g): expected >=1 product item, got 0"
    assert items_with_trend, (
        f"scenario (g): expected >=1 item with non-null trend_30d "
        f"(20 days of ProductScoreDaily seeded, threshold is 14); "
        f"got all-null. items={items_g!r}"
    )
    assert scenario_g["bcg_filter_pass"], (
        f"scenario (g): BCG filter MUST pass for >=1 row when "
        f"ProductScoreDaily has 14+ days; "
        f"got {scenario_g['bcg_filter_passing_count']}"
        f"/{scenario_g['bcg_filter_total']} rows passing. items={items_g!r}"
    )
    print(
        "\n-- Issue #1031 scenario (g) assertion --\n"
        "  scenario (g) per-product trend_30d compute path: PASS\n"
        f"  items with non-null trend_30d: {len(items_with_trend)}/{len(items_g)}\n"
        f"  BCG filter pass: {scenario_g['bcg_filter_passing_count']}"
        f"/{scenario_g['bcg_filter_total']} rows "
        f"({'render' if scenario_g['bcg_filter_pass'] else '暂无产品数据'})\n"
        "  Conclusion: when product_score_daily has 14+ days/product, the\n"
        "  BCG matrix renders. If production still shows '暂无产品数据',\n"
        "  the brand's product_score_daily history is < 14 days."
    )

    # Issue #1031 scenario (h) — EARLY-STAGE BRAND assertion. With only 5
    # days of ProductScoreDaily (below the legacy 14-day threshold but
    # above the new MIN_SPARKLINE_DAYS=3 floor), the adaptive window in
    # `_compute_trend_30d` must still resolve a non-null trend so the BCG
    # filter passes for >=1 row. Pre-fix this would fail (BCG renders
    # "暂无产品数据" for any brand under 14 days of history); post-fix it
    # renders for brands at or above 3 days.
    scenario_h = next((s for s in summaries if s["label"] == "(h)"), None)
    if scenario_h is None:
        raise AssertionError("scenario (h) result missing from summaries")
    items_h = scenario_h.get("items_metric_audit") or []
    items_h_with_trend = [it for it in items_h if it.get("trend_30d") is not None]
    assert items_h, "scenario (h): expected >=1 product item, got 0"
    assert items_h_with_trend, (
        f"scenario (h): expected >=1 item with non-null trend_30d "
        f"(5 days of ProductScoreDaily seeded, MIN_SPARKLINE_DAYS=3); "
        f"got all-null. The adaptive window in _compute_trend_30d is "
        f"broken. items={items_h!r}"
    )
    assert scenario_h["bcg_filter_pass"], (
        f"scenario (h): BCG filter MUST pass for >=1 row at 5 days of "
        f"ProductScoreDaily (post-#1031 adaptive window); got "
        f"{scenario_h['bcg_filter_passing_count']}"
        f"/{scenario_h['bcg_filter_total']} rows passing. items={items_h!r}"
    )
    print(
        "\n-- Issue #1031 scenario (h) assertion (EARLY-STAGE BRAND) --\n"
        "  scenario (h) adaptive trend_30d for short sparkline: PASS\n"
        f"  items with non-null trend_30d: {len(items_h_with_trend)}/{len(items_h)}\n"
        f"  BCG filter pass: {scenario_h['bcg_filter_passing_count']}"
        f"/{scenario_h['bcg_filter_total']} rows "
        f"({'render' if scenario_h['bcg_filter_pass'] else '暂无产品数据'})\n"
        "  Conclusion: early-stage brands with 3-13 days of product_score_daily\n"
        "  now render in the BCG matrix (was '暂无产品数据' pre-#1031). The\n"
        "  adaptive half-and-half window prevents the first/last slice overlap\n"
        "  that would otherwise zero out the trend at exactly 7 days."
    )


if __name__ == "__main__":
    asyncio.run(main())
