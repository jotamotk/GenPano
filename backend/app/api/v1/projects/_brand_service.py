"""Services for Brand products / competitors metrics / diagnostics (Phase 2.3).

Phase D will replace the diagnostics derivation with the real `diagnostics`
table; until then, this service derives lightweight diagnostics from
existing tables (geo_score_daily delta + sentiment dist) so FE can
demonstrate the page interactivity end-to-end.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta
from typing import Any

from genpano_models import (
    BrandMention,
    GeoScoreDaily,
    ProductFeatureMention,
    ProductScoreDaily,
    Project,
    ProjectCompetitor,
    ResponseAnalysis,
)
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._analytics_contract import (
    MetricDefinition,
    build_contract_context,
    context_update,
    metric_definition,
    metric_definitions,
    ratio_decimal,
    score_0_100,
)
from app.api.v1.projects._brand_dto import (
    CompetitorBrandRow,
    CompetitorMetricsOut,
    CompetitorTrendPoint,
    CompetitorTrendSeries,
    CompetitorTrendsOut,
    DiagnosticEvidence,
    DiagnosticRow,
    DiagnosticsOut,
    ProductFeatureRow,
    ProductRow,
    ProductScenarioRow,
    ProductsOut,
)
from app.api.v1.projects._legacy_lookups import (
    resolve_brand_industry,
    resolve_brand_names,
)
from app.api.v1.projects._mention_rollups import (
    _industry_brand_ids,
    brand_mention_match_condition,
    brand_mention_names,
    discover_related_brand_ids,
)
from app.api.v1.projects._topic_analysis_service import (
    AnalysisFilters,
    _as_float,
    _as_int,
    _date_key,
    _fact_all_mention_count,
    _fact_rows,
    _fact_target_mention_count,
    _has_admin_chain,
)

DEFAULT_WINDOW_DAYS = 30


def _resolve_window(from_date: date | None, to_date: date | None) -> tuple[date, date]:
    today = date.today()
    to_d = to_date or today
    from_d = from_date or (to_d - timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    return from_d, to_d


def _period(from_d: date, to_d: date) -> dict[str, str]:
    return {"from": from_d.isoformat(), "to": to_d.isoformat()}


def _brand_entity_key(brand_id: int | None, brand_name: str | None) -> str:
    if brand_id is not None:
        return f"id:{brand_id}"
    name = (brand_name or "unknown").strip().casefold()
    return f"name:{name}"


def _fact_geo_score(value: object) -> float | None:
    score = _as_float(value)
    if score is None:
        return None
    return round(score * 100, 2) if 0 <= score <= 1 else round(score, 2)


def _normalize_competitor_row(row: CompetitorBrandRow | None) -> CompetitorBrandRow | None:
    if row is None:
        return None
    return row.model_copy(
        update={
            "avg_geo_score": score_0_100(row.avg_geo_score),
            "avg_mention_rate": ratio_decimal(row.avg_mention_rate),
            "avg_sov": ratio_decimal(row.avg_sov),
        }
    )


def _normalize_competitor_rows(rows: list[CompetitorBrandRow]) -> list[CompetitorBrandRow]:
    return [
        normalized for row in rows if (normalized := _normalize_competitor_row(row)) is not None
    ]


def _normalize_trend_metric(metric: str, value: float | int | None) -> float | None:
    if value is None:
        return None
    if metric in {"mention_rate", "sov", "citation"}:
        return ratio_decimal(value)
    if metric == "geo_score":
        return score_0_100(value)
    return round(float(value), 4)


def _competitor_metric_definitions() -> dict[str, MetricDefinition]:
    return metric_definitions(["avg_geo_score", "avg_mention_rate", "avg_sov", "avg_sentiment"])


async def _hydrate_competitor_rows_from_daily_scores(
    session: AsyncSession,
    rows: list[CompetitorBrandRow],
    from_d: date,
    to_d: date,
) -> list[CompetitorBrandRow]:
    brand_ids = sorted({row.brand_id for row in rows if row.brand_id is not None})
    if not brand_ids:
        return rows
    stmt = (
        select(
            GeoScoreDaily.brand_id,
            func.avg(GeoScoreDaily.avg_geo_score),
            func.avg(GeoScoreDaily.mention_rate),
            func.avg(GeoScoreDaily.avg_sov),
            func.avg(GeoScoreDaily.avg_sentiment),
        )
        .where(
            and_(
                GeoScoreDaily.brand_id.in_(brand_ids),
                GeoScoreDaily.date >= datetime.combine(from_d, datetime.min.time()),
                GeoScoreDaily.date <= datetime.combine(to_d, datetime.max.time()),
            )
        )
        .group_by(GeoScoreDaily.brand_id)
    )
    aggregates = {int(r[0]): r for r in (await session.execute(stmt)).all() if r[0] is not None}
    hydrated: list[CompetitorBrandRow] = []
    for row in rows:
        if row.brand_id is None:
            hydrated.append(row)
            continue
        aggregate = aggregates.get(row.brand_id)
        if aggregate is None:
            hydrated.append(row)
            continue
        hydrated.append(
            row.model_copy(
                update={
                    "avg_geo_score": row.avg_geo_score
                    if row.avg_geo_score is not None
                    else aggregate[1],
                    "avg_mention_rate": row.avg_mention_rate
                    if row.avg_mention_rate is not None
                    else aggregate[2],
                    "avg_sov": row.avg_sov if row.avg_sov is not None else aggregate[3],
                    "avg_sentiment": row.avg_sentiment
                    if row.avg_sentiment is not None
                    else aggregate[4],
                }
            )
        )
    return hydrated


async def _fact_primary_competitor_row(
    session: AsyncSession,
    primary_id: int,
    fact_rows: list[dict[str, Any]],
) -> CompetitorBrandRow | None:
    response_ids: set[int] = set()
    denominator_response_ids: set[int] = set()
    target_response_ids: set[int] = set()
    target_mentions = 0
    all_mentions = 0
    ranks: list[float] = []
    sentiments: list[float] = []
    geo_scores: list[float] = []

    for row in fact_rows:
        rid = _as_int(row.get("response_id"))
        if rid is None or rid in response_ids:
            continue
        response_ids.add(rid)
        is_non_branded = str(row.get("prompt_scope") or "").strip().lower() == "non_branded"
        if is_non_branded:
            denominator_response_ids.add(rid)
        mentions = _fact_target_mention_count(row)
        total = _fact_all_mention_count(row, mentions)
        all_mentions += total
        if mentions > 0:
            target_response_ids.add(rid)
            target_mentions += mentions
        rank = _as_int(row.get("min_position_rank") or row.get("target_brand_rank"))
        if rank is not None:
            ranks.append(float(rank))
        sentiment = _as_float(row.get("sentiment_score"))
        if sentiment is not None:
            sentiments.append(sentiment)
        geo = _fact_geo_score(row.get("geo_score"))
        if geo is not None:
            geo_scores.append(geo)

    if not response_ids:
        return None
    mention_denominator = len(denominator_response_ids)
    name_map = await resolve_brand_names(session, [primary_id])
    avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else None
    return CompetitorBrandRow(
        brand_id=primary_id,
        brand_key=_brand_entity_key(primary_id, None),
        brand_name=name_map.get(primary_id),
        avg_geo_score=round(sum(geo_scores) / len(geo_scores), 2) if geo_scores else None,
        avg_mention_rate=(
            round(len(target_response_ids) / mention_denominator, 4)
            if mention_denominator > 0
            else None
        ),
        avg_sov=round(target_mentions / all_mentions, 4)
        if all_mentions > target_mentions
        else None,
        avg_sentiment=round(avg_sentiment, 3) if avg_sentiment is not None else None,
        co_mention_count=0,
        delta_30d_pct=None,
    )


async def _response_entity_competitor_metrics(
    session: AsyncSession,
    project: Project,
    primary_id: int,
    from_d: date,
    to_d: date,
    filters: AnalysisFilters | None = None,
) -> tuple[CompetitorBrandRow | None, list[CompetitorBrandRow], str] | None:
    """Build SoV from response-level brand_mentions, including name-only rivals."""

    from_dt = datetime.combine(from_d, datetime.min.time())
    to_dt = datetime.combine(to_d, datetime.max.time())
    fact_brand_override = primary_id if primary_id != project.primary_brand_id else None

    fact_rows = await _fact_rows(
        session,
        project,
        filters=filters or AnalysisFilters(from_date=from_d, to_date=to_d),
        brand_id_override=fact_brand_override,
    )
    scoped_response_ids = {
        int(row["response_id"]) for row in fact_rows if row.get("response_id") is not None
    }
    if await _has_admin_chain(session) and not scoped_response_ids:
        return None, [], "empty"

    conditions = [BrandMention.created_at >= from_dt, BrandMention.created_at <= to_dt]
    if scoped_response_ids:
        conditions.append(BrandMention.response_id.in_(scoped_response_ids))

    rows = (
        await session.execute(
            select(
                BrandMention.response_id,
                BrandMention.brand_id,
                BrandMention.brand_name,
                BrandMention.mention_count,
                BrandMention.position_rank,
                BrandMention.sentiment_score,
            ).where(and_(*conditions))
        )
    ).all()
    if not rows:
        fact_primary = await _fact_primary_competitor_row(session, primary_id, fact_rows)
        if fact_primary is not None:
            return fact_primary, [], "partial"
        return None

    primary_names = await brand_mention_names(session, primary_id)
    buckets: dict[str, dict[str, Any]] = {}
    total_mentions = 0
    all_response_ids: set[int] = set()
    primary_response_ids: set[int] = set()
    for response_id, brand_id, brand_name, mention_count, position_rank, sentiment_score in rows:
        rid = int(response_id)
        bid = int(brand_id) if brand_id is not None else None
        name_key = str(brand_name or "").strip().lower()
        is_primary = bid == primary_id or (bool(name_key) and name_key in primary_names)
        bucket_brand_id = primary_id if is_primary else bid
        amount = int(mention_count) if mention_count is not None else 1
        key = _brand_entity_key(bucket_brand_id, None if is_primary else brand_name)
        bucket = buckets.setdefault(
            key,
            {
                "brand_key": key,
                "brand_id": bucket_brand_id,
                "brand_name": brand_name,
                "mention_count": 0,
                "response_ids": set(),
                "position_ranks": [],
                "sentiments": [],
            },
        )
        bucket["mention_count"] += amount
        bucket["response_ids"].add(rid)
        if position_rank is not None:
            bucket["position_ranks"].append(float(position_rank))
        if sentiment_score is not None:
            bucket["sentiments"].append(float(sentiment_score))
        total_mentions += amount
        all_response_ids.add(rid)
        if is_primary:
            primary_response_ids.add(rid)

    if total_mentions <= 0 or not buckets:
        return None

    brand_ids = [b["brand_id"] for b in buckets.values() if b["brand_id"] is not None]
    name_map = await resolve_brand_names(session, brand_ids)
    total_responses = len(scoped_response_ids)
    has_competitive_mentions = len(buckets) > 1 and total_mentions > 0

    def make_row(bucket: dict[str, Any]) -> CompetitorBrandRow:
        response_count = len(bucket["response_ids"])
        mention_count = int(bucket["mention_count"])
        avg_sentiment = (
            sum(bucket["sentiments"]) / len(bucket["sentiments"]) if bucket["sentiments"] else None
        )
        bid = bucket["brand_id"]
        co_count = 0
        if bid != primary_id:
            co_count = len(set(bucket["response_ids"]) & primary_response_ids)
        brand_name = bucket["brand_name"]
        if bid is not None:
            brand_name = name_map.get(bid) or brand_name
        return CompetitorBrandRow(
            brand_id=bid,
            brand_key=bucket["brand_key"],
            brand_name=brand_name,
            avg_geo_score=None,
            avg_mention_rate=round(response_count / total_responses, 4)
            if total_responses > 0
            else None,
            avg_sov=round(mention_count / total_mentions, 4) if has_competitive_mentions else None,
            avg_sentiment=round(float(avg_sentiment), 3) if avg_sentiment is not None else None,
            co_mention_count=co_count,
            delta_30d_pct=None,
        )

    primary = buckets.get(_brand_entity_key(primary_id, None))
    primary_row = make_row(primary) if primary is not None else None
    if primary_row is None and fact_brand_override is not None:
        fact_primary = await _fact_primary_competitor_row(session, primary_id, fact_rows)
        if fact_primary is not None:
            return fact_primary, [], "partial"
    competitors = [
        make_row(bucket)
        for key, bucket in buckets.items()
        if key != _brand_entity_key(primary_id, None)
    ]
    # Issue #975: drop competitor buckets whose brand_id falls outside the
    # primary brand's industry. Name-only buckets (brand_id=None) cannot be
    # scoped reliably and are kept as-is.
    primary_industry = await resolve_brand_industry(session, primary_id)
    industry_brand_ids = await _industry_brand_ids(session, primary_industry)
    if industry_brand_ids:
        competitors = [
            row for row in competitors if row.brand_id is None or row.brand_id in industry_brand_ids
        ]
    competitors.sort(key=lambda row: (-(row.avg_sov or 0), row.brand_name or row.brand_key or ""))
    state = "partial" if primary_row and not competitors else "ok"
    return primary_row, competitors, state


# ─── /products ─────────────────────────────────────────────────────
async def get_products(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    brand_id_override: int | None = None,
) -> ProductsOut:
    """Return SKU-level product list with feature + scenario rollups.

    Reads `product_score_daily` (per-brand, per-product, per-day metrics) and
    augments with `product_feature_mentions` for top features / scenarios.
    """
    from_d, to_d = _resolve_window(from_date, to_date)

    primary_id = brand_id_override if brand_id_override is not None else project.primary_brand_id
    if primary_id is None:
        return ProductsOut(
            project_id=project.id,
            items=[],
            total=0,
            state="empty",
            state_reason="no_primary_brand",
        )

    from_dt = datetime.combine(from_d, datetime.min.time())
    to_dt = datetime.combine(to_d, datetime.max.time())
    fact_rows = await _fact_rows(
        session,
        project,
        filters=AnalysisFilters(from_date=from_d, to_date=to_d),
        brand_id_override=primary_id,
    )
    scoped_response_ids = sorted(
        {rid for row in fact_rows if (rid := _as_int(row.get("response_id"))) is not None}
    )

    # Aggregate by product_name over the window from product_score_daily.
    stmt = (
        select(
            ProductScoreDaily.product_name,
            ProductScoreDaily.category,
            func.sum(ProductScoreDaily.mention_count).label("mentions"),
            func.avg(ProductScoreDaily.mention_rate).label("mention_rate"),
            func.avg(ProductScoreDaily.avg_position_rank).label("rank"),
            func.avg(ProductScoreDaily.avg_geo_score).label("geo"),
            func.avg(ProductScoreDaily.avg_sentiment_score).label("sent"),
            func.avg(ProductScoreDaily.category_sov_pct).label("sov"),
            func.avg(ProductScoreDaily.category_rank).label("category_rank"),
            func.avg(ProductScoreDaily.win_rate).label("win"),
        )
        .where(
            and_(
                ProductScoreDaily.brand_id == primary_id,
                ProductScoreDaily.date >= from_dt,
                ProductScoreDaily.date <= to_dt,
            )
        )
        .group_by(ProductScoreDaily.product_name, ProductScoreDaily.category)
        .order_by(desc("mentions"))
        .limit(50)
    )
    # Tuple of (name, category, mentions, mention_rate, rank, geo, sent, sov,
    # category_rank, win) — None for fields the product evidence cannot fill.
    product_rows: list[tuple[Any, ...]] = []
    try:
        product_rows = [tuple(r) for r in (await session.execute(stmt)).all()]
    except Exception:
        product_rows = []

    # ProductFeatureMention can expose product names and counts as partial
    # evidence. Rate/trend/sov/sentiment remain null without product_score_daily.
    if not product_rows:
        legacy_stmt = select(
            ProductFeatureMention.product_name,
            func.count().label("mentions"),
        ).where(ProductFeatureMention.product_name.isnot(None))
        if scoped_response_ids:
            legacy_stmt = legacy_stmt.join(
                ResponseAnalysis,
                ResponseAnalysis.id == ProductFeatureMention.analysis_id,
            ).where(ResponseAnalysis.response_id.in_(scoped_response_ids))
        legacy_stmt = (
            legacy_stmt.group_by(ProductFeatureMention.product_name)
            .order_by(desc("mentions"))
            .limit(50)
        )
        try:
            legacy_rows = (await session.execute(legacy_stmt)).all()
        except Exception:
            legacy_rows = []
        product_rows = [
            (r[0], None, int(r[1] or 0), None, None, None, None, None, None, None)
            for r in legacy_rows
        ]

    def _product_feature_scope(statement: Any) -> Any:
        if not scoped_response_ids:
            return statement
        return statement.join(
            ResponseAnalysis,
            ResponseAnalysis.id == ProductFeatureMention.analysis_id,
        ).where(ResponseAnalysis.response_id.in_(scoped_response_ids))

    # ── Batched per-product rollups (issue #1031) ──
    # Previously the loop below issued 3 queries per product (sparkline +
    # features + scenarios). With up to 50 products that's ~150 round-trips
    # and exceeds the gateway's response budget, surfacing as 502 in the
    # browser. Fetch each rollup once with a `WHERE product_name IN (...)`,
    # then bucket in Python.
    product_names: list[str] = [str(r[0]) for r in product_rows if r[0]]
    sparkline_by_product: dict[str, list[tuple[date, float | None]]] = {
        n: [] for n in product_names
    }
    features_by_product: dict[str, list[tuple[str | None, str | None, int]]] = {
        n: [] for n in product_names
    }
    scenarios_by_product: dict[str, list[tuple[str, int]]] = {n: [] for n in product_names}

    if product_names:
        # Sparkline + trend source — grouped by (product_name, date).
        spark_stmt = (
            select(
                ProductScoreDaily.product_name,
                ProductScoreDaily.date,
                func.avg(ProductScoreDaily.mention_rate),
            )
            .where(
                and_(
                    ProductScoreDaily.brand_id == primary_id,
                    ProductScoreDaily.product_name.in_(product_names),
                    ProductScoreDaily.date >= from_dt,
                    ProductScoreDaily.date <= to_dt,
                )
            )
            .group_by(ProductScoreDaily.product_name, ProductScoreDaily.date)
            .order_by(ProductScoreDaily.product_name, ProductScoreDaily.date)
        )
        try:
            for pname, sdate, mrate in (await session.execute(spark_stmt)).all():
                if pname in sparkline_by_product:
                    sparkline_by_product[pname].append((sdate, mrate))
        except Exception:
            pass

        # Features — grouped by (product_name, feature_name, feature_sentiment),
        # ordered so top-N per product can be sliced in Python without window
        # functions (portable across SQLite test fixtures + production Postgres).
        feat_stmt = _product_feature_scope(
            select(
                ProductFeatureMention.product_name,
                ProductFeatureMention.feature_name,
                ProductFeatureMention.feature_sentiment,
                func.count().label("cnt"),
            ).where(ProductFeatureMention.product_name.in_(product_names))
        )
        feat_stmt = feat_stmt.group_by(
            ProductFeatureMention.product_name,
            ProductFeatureMention.feature_name,
            ProductFeatureMention.feature_sentiment,
        ).order_by(ProductFeatureMention.product_name, desc("cnt"))
        try:
            for pname, fname, fsent, cnt in (await session.execute(feat_stmt)).all():
                feat_bucket = features_by_product.get(pname)
                if feat_bucket is not None and len(feat_bucket) < 5:
                    feat_bucket.append((fname, fsent, int(cnt or 0)))
        except Exception:
            pass

        # Scenarios — same batching pattern.
        sc_stmt = _product_feature_scope(
            select(
                ProductFeatureMention.product_name,
                ProductFeatureMention.scenario,
                func.count().label("cnt"),
            ).where(
                and_(
                    ProductFeatureMention.product_name.in_(product_names),
                    ProductFeatureMention.scenario.isnot(None),
                )
            )
        )
        sc_stmt = sc_stmt.group_by(
            ProductFeatureMention.product_name,
            ProductFeatureMention.scenario,
        ).order_by(ProductFeatureMention.product_name, desc("cnt"))
        try:
            for pname, scenario, cnt in (await session.execute(sc_stmt)).all():
                if scenario is None:
                    continue  # WHERE clause already filters, defensive for SQLite shim
                sc_bucket = scenarios_by_product.get(pname)
                if sc_bucket is not None and len(sc_bucket) < 5:
                    sc_bucket.append((str(scenario), int(cnt or 0)))
        except Exception:
            pass

    items: list[ProductRow] = []
    for row in product_rows:
        product_name = row[0]
        category = row[1]
        if not product_name:
            continue

        synth_id = int(hashlib.sha256(f"{primary_id}|{product_name}".encode()).hexdigest()[:8], 16)

        spark_points = sparkline_by_product.get(product_name, [])
        sparkline = [round(float(v or 0), 4) for _, v in spark_points]
        trend_30d: float | None = None
        if len(sparkline) >= 14:
            first = sum(sparkline[:7]) / 7
            last = sum(sparkline[-7:]) / 7
            trend_30d = round((last - first) / first, 4) if first > 0 else None

        features = [
            ProductFeatureRow(
                feature_name=fname or "(unspecified)",
                feature_sentiment=fsent,
                mention_count=cnt,
            )
            for fname, fsent, cnt in features_by_product.get(product_name, [])
        ]
        scenarios = [
            ProductScenarioRow(scenario=scenario, mention_count=cnt)
            for scenario, cnt in scenarios_by_product.get(product_name, [])
        ]

        items.append(
            ProductRow(
                product_id=synth_id,
                product_name=product_name,
                brand_id=primary_id,
                category=category,
                mention_count=int(row[2] or 0),
                mention_rate=round(float(row[3]), 4) if row[3] is not None else None,
                avg_position_rank=round(float(row[4]), 2) if row[4] is not None else None,
                avg_geo_score=round(float(row[5]), 2) if row[5] is not None else None,
                avg_sentiment=round(float(row[6]), 3) if row[6] is not None else None,
                sov=round(float(row[7]), 2) if row[7] is not None else None,
                ranking=int(row[8]) if row[8] is not None else None,
                win_rate=round(float(row[9]), 3) if row[9] is not None else None,
                trend_30d=trend_30d,
                sparkline=sparkline,
                top_features=features,
                top_scenarios=scenarios,
            )
        )

    if not items:
        evidence_count = len(scoped_response_ids)
        return ProductsOut(
            project_id=project.id,
            items=[],
            total=0,
            state="empty",
            state_reason="product_aggregates_pending" if evidence_count else "no_product_data",
            evidence_count=evidence_count,
        ).model_copy(
            update=context_update(
                await build_contract_context(
                    session,
                    project,
                    brand_id=primary_id,
                    from_date=from_d,
                    to_date=to_d,
                    has_data=False,
                    base_state="empty",
                    base_missing_inputs=["product_score_daily"],
                    source_provenance=["product_score_daily", "product_feature_mentions"],
                )
            )
        )

    out = ProductsOut(
        project_id=project.id,
        items=items,
        total=len(items),
        state="ok",
        state_reason="data_available",
        evidence_count=len(items),
    )
    context = await build_contract_context(
        session,
        project,
        brand_id=primary_id,
        from_date=from_d,
        to_date=to_d,
        has_data=True,
        base_state="ok",
        source_provenance=["product_score_daily", "product_feature_mentions"],
    )
    return out.model_copy(update=context_update(context))


# ─── /competitors/metrics ──────────────────────────────────────────
async def get_competitor_metrics(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
    brand_id_override: int | None = None,
    filters: AnalysisFilters | None = None,
) -> CompetitorMetricsOut:
    """Compare primary brand + each pinned competitor across 4 metrics."""
    from_d, to_d = _resolve_window(from_date, to_date)
    primary_id = brand_id_override if brand_id_override is not None else project.primary_brand_id
    has_effective_override = (
        brand_id_override is not None and brand_id_override != project.primary_brand_id
    )

    if primary_id is None:
        out = CompetitorMetricsOut(
            project_id=project.id,
            primary_brand_id=None,
            period=_period(from_d, to_d),
            primary=None,
            competitors=[],
            state="empty",
            metric_definitions=_competitor_metric_definitions(),
        )
        context = await build_contract_context(
            session,
            project,
            brand_id=None,
            from_date=from_d,
            to_date=to_d,
            has_data=False,
            base_state="empty",
            base_state_reason="no_primary_brand",
        )
        return out.model_copy(update=context_update(context))

    response_entities = await _response_entity_competitor_metrics(
        session,
        project,
        primary_id,
        from_d,
        to_d,
        filters or AnalysisFilters(from_date=from_d, to_date=to_d),
    )
    if response_entities is not None:
        primary_row, competitor_rows, entity_state = response_entities
        hydrated_rows = await _hydrate_competitor_rows_from_daily_scores(
            session,
            [row for row in [primary_row, *competitor_rows] if row is not None],
            from_d,
            to_d,
        )
        if hydrated_rows:
            primary_row = hydrated_rows[0] if primary_row is not None else None
            competitor_rows = hydrated_rows[1:] if primary_row is not None else hydrated_rows
        primary_row = _normalize_competitor_row(primary_row)
        competitor_rows = _normalize_competitor_rows(competitor_rows)
        has_data = primary_row is not None or bool(competitor_rows)
        out = CompetitorMetricsOut(
            project_id=project.id,
            primary_brand_id=primary_id,
            period=_period(from_d, to_d),
            primary=primary_row,
            competitors=competitor_rows,
            state=entity_state,
            metric_definitions=_competitor_metric_definitions(),
        )
        context = await build_contract_context(
            session,
            project,
            brand_id=primary_id,
            from_date=from_d,
            to_date=to_d,
            has_data=has_data,
            base_state=entity_state,
            base_state_reason="partial_competitor_data" if entity_state == "partial" else None,
        )
        return out.model_copy(update=context_update(context))

    primary_industry = await resolve_brand_industry(session, primary_id)
    if has_effective_override:
        competitor_ids = await discover_related_brand_ids(
            session, primary_id, from_d, to_d, industry_name=primary_industry
        )
    else:
        competitor_stmt = select(ProjectCompetitor.brand_id).where(
            ProjectCompetitor.project_id == project.id
        )
        competitor_ids = [r[0] for r in (await session.execute(competitor_stmt)).all()]
        # Issue #975: drop pinned competitors that fall outside the primary
        # brand's industry. Cross-industry pins (manual or auto-seeded by
        # an older worker) were leaking into the competitor panel even
        # after #978 scoped the auto-discovery path.
        industry_brand_ids = await _industry_brand_ids(session, primary_industry)
        if industry_brand_ids and competitor_ids:
            competitor_ids = [bid for bid in competitor_ids if bid in industry_brand_ids]
        if not competitor_ids:
            competitor_ids = await discover_related_brand_ids(
                session, primary_id, from_d, to_d, industry_name=primary_industry
            )
    competitor_ids = [bid for bid in competitor_ids if bid is not None and bid != primary_id]

    async def _row_for(brand_id: int) -> CompetitorBrandRow:
        stmt = select(
            func.avg(GeoScoreDaily.avg_geo_score),
            func.avg(GeoScoreDaily.mention_rate),
            func.avg(GeoScoreDaily.avg_sov),
            func.avg(GeoScoreDaily.avg_sentiment),
        ).where(
            and_(
                GeoScoreDaily.brand_id == brand_id,
                GeoScoreDaily.date >= datetime.combine(from_d, datetime.min.time()),
                GeoScoreDaily.date <= datetime.combine(to_d, datetime.max.time()),
            )
        )
        r = (await session.execute(stmt)).one_or_none()

        # Prior 30d for delta
        prior_from = from_d - timedelta(days=DEFAULT_WINDOW_DAYS)
        prior_to = from_d - timedelta(days=1)
        stmt_prior = select(func.avg(GeoScoreDaily.avg_geo_score)).where(
            and_(
                GeoScoreDaily.brand_id == brand_id,
                GeoScoreDaily.date >= datetime.combine(prior_from, datetime.min.time()),
                GeoScoreDaily.date <= datetime.combine(prior_to, datetime.max.time()),
            )
        )
        prior_geo = (await session.execute(stmt_prior)).scalar_one_or_none()

        # Co-mention count: rough heuristic — count brand_mentions with
        # both primary brand_id and this brand on the same response
        co_count = 0
        if primary_id and brand_id != primary_id:
            primary_filter = await brand_mention_match_condition(session, primary_id)
            brand_filter = await brand_mention_match_condition(session, brand_id)
            primary_resp_stmt = (
                select(BrandMention.response_id)
                .where(
                    and_(
                        primary_filter,
                        BrandMention.created_at >= datetime.combine(from_d, datetime.min.time()),
                        BrandMention.created_at <= datetime.combine(to_d, datetime.max.time()),
                    )
                )
                .scalar_subquery()
            )
            co_stmt = select(func.count()).where(
                and_(
                    brand_filter,
                    BrandMention.response_id.in_(primary_resp_stmt),
                    BrandMention.created_at >= datetime.combine(from_d, datetime.min.time()),
                    BrandMention.created_at <= datetime.combine(to_d, datetime.max.time()),
                )
            )
            co_count = int((await session.execute(co_stmt)).scalar_one() or 0)

        avg_geo = r[0] if r else None
        avg_mention = r[1] if r else None
        avg_sov = r[2] if r else None
        avg_sentiment = r[3] if r else None

        delta = None
        if avg_geo is not None and prior_geo is not None and prior_geo != 0:
            delta = round((avg_geo - prior_geo) / prior_geo * 100, 1)

        return CompetitorBrandRow(
            brand_id=brand_id,
            brand_key=_brand_entity_key(brand_id, None),
            brand_name=None,  # filled in below via bulk name lookup
            avg_geo_score=round(avg_geo, 2) if avg_geo is not None else None,
            avg_mention_rate=round(avg_mention, 4) if avg_mention is not None else None,
            avg_sov=round(avg_sov, 4) if avg_sov is not None else None,
            avg_sentiment=round(avg_sentiment, 3) if avg_sentiment is not None else None,
            co_mention_count=co_count,
            delta_30d_pct=delta,
        )

    primary_row = await _row_for(primary_id)
    comp_rows = [await _row_for(bid) for bid in competitor_ids]

    # Bulk brand-name lookup
    all_ids: list[int] = [primary_id]
    all_ids.extend(competitor_ids)
    name_map = await resolve_brand_names(session, all_ids)
    if primary_row is not None and primary_row.brand_id is not None:
        primary_row.brand_name = name_map.get(primary_row.brand_id)
    for c in comp_rows:
        if c.brand_id is not None:
            c.brand_name = name_map.get(c.brand_id)
    primary_row = _normalize_competitor_row(primary_row)
    comp_rows = _normalize_competitor_rows(comp_rows)

    state = "ok" if (primary_row or comp_rows) else "empty"
    out = CompetitorMetricsOut(
        project_id=project.id,
        primary_brand_id=primary_id,
        period=_period(from_d, to_d),
        primary=primary_row,
        competitors=comp_rows,
        state=state,
        metric_definitions=_competitor_metric_definitions(),
    )
    context = await build_contract_context(
        session,
        project,
        brand_id=primary_id,
        from_date=from_d,
        to_date=to_d,
        has_data=state != "empty",
        base_state=state,
    )
    return out.model_copy(update=context_update(context))


# ─── /diagnostics ──────────────────────────────────────────────────
async def get_diagnostics(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> DiagnosticsOut:
    """Phase 2.3 derives diagnostics from geo_score_daily delta + sentiment.

    Phase D will replace this with rule-engine-driven `diagnostics` table.
    """
    from_d, to_d = _resolve_window(from_date, to_date)
    items: list[DiagnosticRow] = []

    if project.primary_brand_id is None:
        return DiagnosticsOut(
            project_id=project.id,
            period=_period(from_d, to_d),
            items=[],
            counts_by_severity={"P0": 0, "P1": 0, "P2": 0, "P3": 0},
            state="empty",
        )

    brand_id = project.primary_brand_id

    # ── visibility decline rule ───────────────────────────────────
    cur_stmt = select(func.avg(GeoScoreDaily.mention_rate)).where(
        and_(
            GeoScoreDaily.brand_id == brand_id,
            GeoScoreDaily.date >= datetime.combine(from_d, datetime.min.time()),
            GeoScoreDaily.date <= datetime.combine(to_d, datetime.max.time()),
        )
    )
    cur_avg = (await session.execute(cur_stmt)).scalar_one_or_none()

    prior_from = from_d - timedelta(days=DEFAULT_WINDOW_DAYS)
    prior_to = from_d - timedelta(days=1)
    prior_stmt = select(func.avg(GeoScoreDaily.mention_rate)).where(
        and_(
            GeoScoreDaily.brand_id == brand_id,
            GeoScoreDaily.date >= datetime.combine(prior_from, datetime.min.time()),
            GeoScoreDaily.date <= datetime.combine(prior_to, datetime.max.time()),
        )
    )
    prior_avg = (await session.execute(prior_stmt)).scalar_one_or_none()

    if cur_avg is not None and prior_avg is not None and prior_avg != 0:
        change = (cur_avg - prior_avg) / prior_avg * 100
        if change <= -15:  # down ≥ 15%
            severity = "P1" if change <= -30 else "P2"
            items.append(
                DiagnosticRow(
                    id=f"deriv-vis-{brand_id}-{from_d.isoformat()}",
                    category="visibility_decline",
                    severity=severity,
                    type="brand",
                    title=f"mention rate dropped {abs(change):.1f}% over 30d",
                    description=(
                        "Mention rate trended down vs prior 30d window. "
                        "Inspect topic coverage / prompt quality / citation attribution."
                    ),
                    detected_at=datetime.now().isoformat(),
                    focus_area="mention_rate",
                    direction=(
                        "Check whether top topics were overtaken by competitors; "
                        "review recent PR campaigns."
                    ),
                    reader_hints=["operator", "manager"],
                    evidence=DiagnosticEvidence(
                        metric="mention_rate",
                        current_value=round(cur_avg, 4),
                        previous_value=round(prior_avg, 4),
                        change_percent=round(change, 2),
                    ),
                )
            )

    # ── negative sentiment growth rule ────────────────────────────
    neg_stmt = select(
        func.sum(func.iif(BrandMention.sentiment == "negative", 1, 0)),
        func.count(),
    ).where(
        and_(
            BrandMention.brand_id == brand_id,
            BrandMention.created_at >= datetime.combine(from_d, datetime.min.time()),
            BrandMention.created_at <= datetime.combine(to_d, datetime.max.time()),
        )
    )
    try:
        neg_row = (await session.execute(neg_stmt)).one_or_none()
    except Exception:
        neg_row = None

    if neg_row and neg_row[1] and neg_row[1] > 0:
        neg_pct = (neg_row[0] or 0) / neg_row[1] * 100
        if neg_pct >= 25:
            severity = "P1" if neg_pct >= 40 else "P2"
            items.append(
                DiagnosticRow(
                    id=f"deriv-neg-{brand_id}-{from_d.isoformat()}",
                    category="negative_keyword_growth",
                    severity=severity,
                    type="brand",
                    title=f"negative mention ratio {neg_pct:.1f}%",
                    description=(
                        "Negative mentions crossed the alert threshold. "
                        "Pull sentiment_drivers top negative for review."
                    ),
                    detected_at=datetime.now().isoformat(),
                    focus_area="sentiment_distribution",
                    direction=(
                        "Inspect sentiment_drivers top negative; "
                        "coordinate with PR to adjust messaging."
                    ),
                    reader_hints=["operator", "branding"],
                    evidence=DiagnosticEvidence(
                        metric="negative_rate",
                        current_value=round(neg_pct, 2),
                    ),
                )
            )

    counts = {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
    for d in items:
        counts[d.severity] = counts.get(d.severity, 0) + 1

    return DiagnosticsOut(
        project_id=project.id,
        period=_period(from_d, to_d),
        items=items,
        counts_by_severity=counts,
        state="ok" if items else "empty",
    )


# ─── /competitors/trends ──────────────────────────────────────────
ALLOWED_TREND_METRICS = {
    "geo_score": GeoScoreDaily.avg_geo_score,
    "mention_rate": GeoScoreDaily.mention_rate,
    "sov": GeoScoreDaily.avg_sov,
    "sentiment": GeoScoreDaily.avg_sentiment,
    "rank": GeoScoreDaily.avg_position_rank,
    "citation": GeoScoreDaily.citation_rate,
}


def _fact_trend_value(metric: str, row: dict[str, Any]) -> float | None:
    if metric == "geo_score":
        score = _fact_geo_score(row.get("geo_score"))
        if score is not None:
            return score
        return None
    if metric == "rank":
        rank = _as_int(row.get("min_position_rank") or row.get("target_brand_rank"))
        return float(rank) if rank is not None else None
    if metric == "sentiment":
        return _as_float(row.get("sentiment_score"))
    if metric in {"mention_rate", "sov"}:
        mentions = _fact_target_mention_count(row)
        total = _fact_all_mention_count(row, mentions)
        if metric == "mention_rate":
            return None
        return round(mentions / total, 4) if total > mentions else None
    if metric == "citation":
        return float(row.get("citation_count") or 0)
    return None


async def _fact_primary_trend_series(
    session: AsyncSession,
    project: Project,
    *,
    primary_id: int,
    metric: str,
    from_d: date,
    to_d: date,
    brand_id_override: int | None,
) -> CompetitorTrendSeries | None:
    rows = await _fact_rows(
        session,
        project,
        filters=AnalysisFilters(from_date=from_d, to_date=to_d),
        brand_id_override=brand_id_override,
    )
    buckets: dict[str, list[float]] = {}
    seen_response_ids: set[int] = set()
    for row in rows:
        rid = _as_int(row.get("response_id"))
        if rid is None or rid in seen_response_ids:
            continue
        seen_response_ids.add(rid)
        day = _date_key(
            row.get("response_created_at")
            or row.get("query_finished_at")
            or row.get("query_created_at")
        )
        if not day:
            continue
        value = _fact_trend_value(metric, row)
        if value is None:
            continue
        buckets.setdefault(day, []).append(value)
    if not buckets:
        return None
    name_map = await resolve_brand_names(session, [primary_id])
    return CompetitorTrendSeries(
        brand_id=primary_id,
        brand_name=name_map.get(primary_id),
        is_primary=True,
        points=[
            CompetitorTrendPoint(date=day, value=round(sum(values) / len(values), 4))
            for day, values in sorted(buckets.items())
        ],
    )


async def get_competitor_trends(
    session: AsyncSession,
    project: Project,
    *,
    metric: str = "geo_score",
    from_date: date | None = None,
    to_date: date | None = None,
    brand_id_override: int | None = None,
) -> CompetitorTrendsOut:
    """Daily 30d trend for primary brand + each pinned competitor.

    Reads geo_score_daily and groups by (brand_id, date) so the FE can
    render the per-competitor PANO trend chart with real pipeline data.
    """
    if metric not in ALLOWED_TREND_METRICS:
        metric = "geo_score"
    metric_col = ALLOWED_TREND_METRICS[metric]

    from_d, to_d = _resolve_window(from_date, to_date)

    primary_id = brand_id_override if brand_id_override is not None else project.primary_brand_id
    has_effective_override = (
        brand_id_override is not None and brand_id_override != project.primary_brand_id
    )
    if primary_id is not None and await _has_admin_chain(session):
        fact_series = await _fact_primary_trend_series(
            session,
            project,
            primary_id=primary_id,
            metric=metric,
            from_d=from_d,
            to_d=to_d,
            brand_id_override=brand_id_override,
        )
        if fact_series is not None:
            out = CompetitorTrendsOut(
                project_id=project.id,
                metric=metric,
                period=_period(from_d, to_d),
                series=[fact_series],
                state="ok",
                metric_definition=metric_definition(metric),
            )
            context = await build_contract_context(
                session,
                project,
                brand_id=primary_id,
                from_date=from_d,
                to_date=to_d,
                has_data=True,
                base_state="ok",
            )
            return out.model_copy(update=context_update(context))
    primary_industry = (
        await resolve_brand_industry(session, primary_id) if primary_id is not None else None
    )
    if has_effective_override and primary_id is not None:
        competitor_ids = await discover_related_brand_ids(
            session, primary_id, from_d, to_d, industry_name=primary_industry
        )
    else:
        competitor_stmt = select(ProjectCompetitor.brand_id).where(
            ProjectCompetitor.project_id == project.id
        )
        competitor_ids = [r[0] for r in (await session.execute(competitor_stmt)).all()]
        # Issue #975: scope pinned competitors to the primary brand's
        # industry (see get_competitor_metrics for rationale).
        industry_brand_ids = await _industry_brand_ids(session, primary_industry)
        if industry_brand_ids and competitor_ids:
            competitor_ids = [bid for bid in competitor_ids if bid in industry_brand_ids]
        if primary_id is not None and not competitor_ids:
            competitor_ids = await discover_related_brand_ids(
                session, primary_id, from_d, to_d, industry_name=primary_industry
            )

    brand_ids = list({*competitor_ids, *([primary_id] if primary_id is not None else [])})
    if not brand_ids:
        out = CompetitorTrendsOut(
            project_id=project.id,
            metric=metric,
            period=_period(from_d, to_d),
            series=[],
            state="empty",
            metric_definition=metric_definition(metric),
        )
        context = await build_contract_context(
            session,
            project,
            brand_id=primary_id,
            from_date=from_d,
            to_date=to_d,
            has_data=False,
            base_state="empty",
            base_state_reason="no_primary_brand",
        )
        return out.model_copy(update=context_update(context))

    stmt = (
        select(
            GeoScoreDaily.brand_id,
            GeoScoreDaily.date,
            func.avg(metric_col).label("value"),
        )
        .where(
            and_(
                GeoScoreDaily.brand_id.in_(brand_ids),
                GeoScoreDaily.date >= datetime.combine(from_d, datetime.min.time()),
                GeoScoreDaily.date <= datetime.combine(to_d, datetime.max.time()),
            )
        )
        .group_by(GeoScoreDaily.brand_id, GeoScoreDaily.date)
        .order_by(GeoScoreDaily.brand_id, GeoScoreDaily.date)
    )
    rows = list((await session.execute(stmt)).all())

    series_by_brand: dict[int, list[CompetitorTrendPoint]] = {bid: [] for bid in brand_ids}
    for brand_id, dt, value in rows:
        series_by_brand[brand_id].append(
            CompetitorTrendPoint(
                date=dt.date().isoformat() if hasattr(dt, "date") else str(dt),
                value=_normalize_trend_metric(metric, value),
            )
        )
    name_map = await resolve_brand_names(session, brand_ids)
    output_series = [
        CompetitorTrendSeries(
            brand_id=bid,
            brand_name=name_map.get(bid),
            is_primary=(bid == primary_id),
            points=series_by_brand[bid],
        )
        for bid in brand_ids
    ]
    state = "ok" if any(s.points for s in output_series) else "empty"
    definition_key = "avg_sentiment" if metric == "sentiment" and rows else metric
    out = CompetitorTrendsOut(
        project_id=project.id,
        metric=metric,
        period=_period(from_d, to_d),
        series=output_series,
        state=state,
        metric_definition=metric_definition(definition_key),
    )
    context = await build_contract_context(
        session,
        project,
        brand_id=primary_id,
        from_date=from_d,
        to_date=to_d,
        has_data=state != "empty",
        base_state=state,
    )
    return out.model_copy(update=context_update(context))
