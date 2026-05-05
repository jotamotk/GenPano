"""Services for Brand products / competitors metrics / diagnostics (Phase 2.3).

Phase D will replace the diagnostics derivation with the real `diagnostics`
table; until then, this service derives lightweight diagnostics from
existing tables (geo_score_daily delta + sentiment dist) so FE can
demonstrate the page interactivity end-to-end.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta

from genpano_models import (
    BrandMention,
    GeoScoreDaily,
    ProductFeatureMention,
    Project,
    ProjectCompetitor,
)
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._brand_dto import (
    CompetitorBrandRow,
    CompetitorMetricsOut,
    DiagnosticEvidence,
    DiagnosticRow,
    DiagnosticsOut,
    ProductFeatureRow,
    ProductRow,
    ProductScenarioRow,
    ProductsOut,
)

DEFAULT_WINDOW_DAYS = 30


def _resolve_window(from_date: date | None, to_date: date | None) -> tuple[date, date]:
    today = date.today()
    to_d = to_date or today
    from_d = from_date or (to_d - timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    return from_d, to_d


def _period(from_d: date, to_d: date) -> dict[str, str]:
    return {"from": from_d.isoformat(), "to": to_d.isoformat()}


# ─── /products ─────────────────────────────────────────────────────
async def get_products(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> ProductsOut:
    """Return SKU-level product list with feature + scenario rollups.

    Reads `product_feature_mentions` aggregated by `(brand_name, product_name)`.
    Until Phase A.7 wires the real `products` ORM, returns synthesized
    product_ids (hash of name) so FE can navigate.
    """
    from_d, to_d = _resolve_window(from_date, to_date)

    if project.primary_brand_id is None:
        return ProductsOut(project_id=project.id, items=[], total=0, state="empty")

    # Aggregate features by (brand_name, product_name) over the window
    stmt = (
        select(
            ProductFeatureMention.brand_name,
            ProductFeatureMention.product_name,
            func.count().label("cnt"),
            func.sum(func.iif(ProductFeatureMention.feature_sentiment == "positive", 1, 0)).label(
                "pos"
            ),
        )
        .where(
            and_(
                ProductFeatureMention.created_at >= datetime.combine(from_d, datetime.min.time()),
                ProductFeatureMention.created_at <= datetime.combine(to_d, datetime.max.time()),
            )
        )
        .group_by(
            ProductFeatureMention.brand_name,
            ProductFeatureMention.product_name,
        )
        .order_by(desc("cnt"))
        .limit(50)
    )
    try:
        product_rows = (await session.execute(stmt)).all()
    except Exception:
        # SQLite may not support func.iif via this path; retry without
        product_rows = []
        stmt2 = (
            select(
                ProductFeatureMention.brand_name,
                ProductFeatureMention.product_name,
                func.count().label("cnt"),
            )
            .where(
                and_(
                    ProductFeatureMention.created_at
                    >= datetime.combine(from_d, datetime.min.time()),
                    ProductFeatureMention.created_at <= datetime.combine(to_d, datetime.max.time()),
                )
            )
            .group_by(
                ProductFeatureMention.brand_name,
                ProductFeatureMention.product_name,
            )
            .order_by(desc("cnt"))
            .limit(50)
        )
        product_rows = (await session.execute(stmt2)).all()

    items: list[ProductRow] = []
    for row in product_rows:
        brand_name = row[0]
        product_name = row[1]
        cnt = int(row[2] or 0)
        if not product_name:
            continue
        # Synthetic product_id = first 8 hex chars of hash
        synth_id = int(hashlib.sha256(f"{brand_name}|{product_name}".encode()).hexdigest()[:8], 16)

        # Top features for this product
        feat_stmt = (
            select(
                ProductFeatureMention.feature_name,
                ProductFeatureMention.feature_sentiment,
                func.count().label("cnt"),
            )
            .where(
                and_(
                    ProductFeatureMention.brand_name == brand_name,
                    ProductFeatureMention.product_name == product_name,
                )
            )
            .group_by(
                ProductFeatureMention.feature_name,
                ProductFeatureMention.feature_sentiment,
            )
            .order_by(desc("cnt"))
            .limit(5)
        )
        feat_rows = (await session.execute(feat_stmt)).all()
        features = [
            ProductFeatureRow(
                feature_name=fr[0] or "(unspecified)",
                feature_sentiment=fr[1],
                mention_count=int(fr[2] or 0),
            )
            for fr in feat_rows
        ]

        # Scenarios
        sc_stmt = (
            select(
                ProductFeatureMention.scenario,
                func.count().label("cnt"),
            )
            .where(
                and_(
                    ProductFeatureMention.brand_name == brand_name,
                    ProductFeatureMention.product_name == product_name,
                    ProductFeatureMention.scenario.isnot(None),
                )
            )
            .group_by(ProductFeatureMention.scenario)
            .order_by(desc("cnt"))
            .limit(5)
        )
        sc_rows = (await session.execute(sc_stmt)).all()
        scenarios = [
            ProductScenarioRow(scenario=sr[0], mention_count=int(sr[1] or 0)) for sr in sc_rows
        ]

        items.append(
            ProductRow(
                product_id=synth_id,
                product_name=product_name,
                brand_id=project.primary_brand_id,
                mention_count=cnt,
                top_features=features,
                top_scenarios=scenarios,
            )
        )

    return ProductsOut(
        project_id=project.id,
        items=items,
        total=len(items),
        state="ok" if items else "empty",
    )


# ─── /competitors/metrics ──────────────────────────────────────────
async def get_competitor_metrics(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date | None = None,
    to_date: date | None = None,
) -> CompetitorMetricsOut:
    """Compare primary brand + each pinned competitor across 4 metrics."""
    from_d, to_d = _resolve_window(from_date, to_date)

    competitor_stmt = select(ProjectCompetitor.brand_id).where(
        ProjectCompetitor.project_id == project.id
    )
    competitor_ids = [r[0] for r in (await session.execute(competitor_stmt)).all()]

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
        if project.primary_brand_id and brand_id != project.primary_brand_id:
            primary_resp_stmt = (
                select(BrandMention.response_id)
                .where(BrandMention.brand_id == project.primary_brand_id)
                .scalar_subquery()
            )
            co_stmt = select(func.count()).where(
                and_(
                    BrandMention.brand_id == brand_id,
                    BrandMention.response_id.in_(primary_resp_stmt),
                )
            )
            co_count = int((await session.execute(co_stmt)).scalar_one() or 0)

        avg_geo = r[0] if r else None
        delta = None
        if avg_geo is not None and prior_geo is not None and prior_geo != 0:
            delta = round((avg_geo - prior_geo) / prior_geo * 100, 1)

        return CompetitorBrandRow(
            brand_id=brand_id,
            brand_name=None,  # Phase A.7 JOIN brands.name
            avg_geo_score=round(r[0], 2) if r and r[0] else None,
            avg_mention_rate=round(r[1], 4) if r and r[1] else None,
            avg_sov=round(r[2], 4) if r and r[2] else None,
            avg_sentiment=round(r[3], 3) if r and r[3] else None,
            co_mention_count=co_count,
            delta_30d_pct=delta,
        )

    primary_row = (
        await _row_for(project.primary_brand_id) if project.primary_brand_id is not None else None
    )
    comp_rows = [await _row_for(bid) for bid in competitor_ids]

    state = "ok" if (primary_row or comp_rows) else "empty"
    return CompetitorMetricsOut(
        project_id=project.id,
        primary_brand_id=project.primary_brand_id,
        period=_period(from_d, to_d),
        primary=primary_row,
        competitors=comp_rows,
        state=state,
    )


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
