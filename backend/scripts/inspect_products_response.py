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
    await session.commit()


def _can_use_metric_evidence(data: dict[str, Any], metric: str = "product") -> tuple[bool, str]:
    """Python emulation of the frontend `canUseMetricEvidence(data, 'product')`
    guard (BrandProductsPage.tsx:92).

    The frontend gate maps `metric='product'` to evidence key 'topic_product'
    and passes when:
      - `metric_formula_evidence.topic_product` exists
      - `formula_status` in {'ok', 'partial'}
      - `state` in {'ok', 'partial'}
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
    return {
        "label": label,
        "passes_gate": passes,
        "reason": reason,
        "has_topic_product": has_topic_product,
        "metric_evidence_keys": sorted(metric_evidence.keys()),
        "topic_product": metric_evidence.get("topic_product"),
        "state": body.get("state"),
        "total": body.get("total"),
        "evidence_count": body.get("evidence_count"),
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

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)
    for s in summaries:
        print(
            f"  {s['label']}: gate={'PASS' if s['passes_gate'] else 'FAIL'} "
            f"reason={s['reason']!r} "
            f"topic_product_present={s['has_topic_product']} "
            f"state={s['state']!r} total={s['total']} "
            f"evidence_count={s['evidence_count']}"
        )


if __name__ == "__main__":
    asyncio.run(main())
