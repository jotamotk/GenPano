"""Phase M.2 — real MCP tool implementations.

Each tool wires to a service function (Phase 2 / E / RP service layer) so
output is byte-equal to the REST endpoint counterpart.

PRD §4.5.2.2 — 9 tools:
1. genpano_get_brand_visibility
2. genpano_compare_brands
3. genpano_get_industry_trends
4. genpano_get_product_ranking
5. genpano_generate_report
6. genpano_get_optimization_insights
7. genpano_get_citations
8. genpano_list_pr_targets
9. genpano_simulate_authority_boost

Phase M.3 (later) will wire `tools/list` to return real input schemas and
`tools/call` to dispatch by name.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from genpano_models import (
    BrandMention,
    CitationSource,
    DomainAuthority,
    GeoScoreDaily,
    IndustryBenchmarkDaily,
    Project,
    User,
)
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.exports.service import simulate_authority_boost

# ────── tool 1: get_brand_visibility ─────────────────────────────


async def get_brand_visibility(
    session: AsyncSession,
    *,
    user: User,
    brand_id: int,
    project_id: str,
    engine: str | None = None,
    period: str = "30d",
) -> dict[str, Any]:
    """Visibility KPI + 30d trend (PRD §4.5.2.2 tool 1)."""
    days = int(period.rstrip("d")) if period.endswith("d") else 30
    today = date.today()
    from_d = today - timedelta(days=days - 1)

    base_filter = and_(
        GeoScoreDaily.brand_id == brand_id,
        GeoScoreDaily.date >= from_d,
        GeoScoreDaily.date <= today,
    )
    if engine:
        base_filter = and_(base_filter, GeoScoreDaily.target_llm == engine)

    # Aggregate
    stmt = select(
        func.avg(GeoScoreDaily.mention_rate),
        func.avg(GeoScoreDaily.avg_sov),
        func.avg(GeoScoreDaily.avg_position_rank),
        func.avg(GeoScoreDaily.avg_geo_score),
    ).where(base_filter)
    r = (await session.execute(stmt)).one_or_none()

    # Time series
    ts_stmt = (
        select(
            GeoScoreDaily.date,
            func.avg(GeoScoreDaily.mention_rate),
            func.avg(GeoScoreDaily.avg_sov),
            func.avg(GeoScoreDaily.avg_position_rank),
        )
        .where(base_filter)
        .group_by(GeoScoreDaily.date)
        .order_by(GeoScoreDaily.date)
    )
    ts_rows = (await session.execute(ts_stmt)).all()

    return {
        "brand_id": brand_id,
        "project_id": project_id,
        "engine": engine,
        "period": {"from": from_d.isoformat(), "to": today.isoformat()},
        "mention_rate": round(r[0] or 0, 4) if r else 0,
        "sov": round(r[1] or 0, 4) if r else 0,
        "position_rank": round(r[2] or 0, 2) if r else 0,
        "geo_score": round(r[3] or 0, 2) if r else 0,
        "time_series": [
            {
                "date": row[0].date().isoformat() if hasattr(row[0], "date") else str(row[0])[:10],
                "mention_rate": round(row[1] or 0, 4),
                "sov": round(row[2] or 0, 4),
                "rank": round(row[3] or 0, 2),
            }
            for row in ts_rows
        ],
    }


# ────── tool 2: compare_brands ──────────────────────────────────


async def compare_brands(
    session: AsyncSession,
    *,
    user: User,
    project_id: str,
    brand_ids: list[int],
    metrics: list[str] | None = None,
    period: str = "30d",
) -> dict[str, Any]:
    """Compare 2-5 brands across requested metrics."""
    if len(brand_ids) < 2 or len(brand_ids) > 5:
        return {"error": "brand_ids must be 2..5"}
    metrics = metrics or [
        "mention_rate",
        "sov",
        "sentiment",
        "geo_score",
    ]
    days = int(period.rstrip("d")) if period.endswith("d") else 30
    today = date.today()
    from_d = today - timedelta(days=days - 1)

    METRIC_COL = {
        "mention_rate": GeoScoreDaily.mention_rate,
        "sov": GeoScoreDaily.avg_sov,
        "sentiment": GeoScoreDaily.avg_sentiment,
        "citation_share": GeoScoreDaily.citation_rate,
        "geo_score": GeoScoreDaily.avg_geo_score,
    }
    brands_data = []
    for bid in brand_ids:
        row_metrics = {}
        for m in metrics:
            col = METRIC_COL.get(m)
            if col is None:
                continue
            stmt = select(func.avg(col)).where(
                and_(
                    GeoScoreDaily.brand_id == bid,
                    GeoScoreDaily.date >= from_d,
                    GeoScoreDaily.date <= today,
                )
            )
            v = (await session.execute(stmt)).scalar_one_or_none()
            row_metrics[m] = round(v or 0, 4)
        brands_data.append({"brand_id": bid, "name": None, "metrics": row_metrics})

    return {
        "project_id": project_id,
        "period": {"from": from_d.isoformat(), "to": today.isoformat()},
        "brands": brands_data,
    }


# ────── tool 3: get_industry_trends ─────────────────────────────


async def get_industry_trends(
    session: AsyncSession,
    *,
    user: User,
    industry_id: int,
    industry_name: str | None = None,
    period: str = "30d",
) -> dict[str, Any]:
    """Industry KPI + top brands + 30d trend."""
    days = int(period.rstrip("d")) if period.endswith("d") else 30
    today = date.today()
    from_d = today - timedelta(days=days - 1)

    bench_filter = and_(
        IndustryBenchmarkDaily.date >= from_d,
        IndustryBenchmarkDaily.date <= today,
    )
    if industry_name:
        bench_filter = and_(bench_filter, IndustryBenchmarkDaily.industry == industry_name)

    stmt = select(
        func.avg(IndustryBenchmarkDaily.avg_geo_score),
        func.avg(IndustryBenchmarkDaily.avg_mention_rate),
        func.avg(IndustryBenchmarkDaily.avg_sentiment),
        func.max(IndustryBenchmarkDaily.total_brands),
    ).where(bench_filter)
    r = (await session.execute(stmt)).one_or_none()

    # Top brands
    top_stmt = (
        select(
            GeoScoreDaily.brand_id,
            func.avg(GeoScoreDaily.avg_geo_score).label("g"),
        )
        .where(GeoScoreDaily.date >= from_d)
        .group_by(GeoScoreDaily.brand_id)
        .order_by(desc("g"))
        .limit(10)
    )
    top_rows = (await session.execute(top_stmt)).all()

    return {
        "industry": industry_name,
        "industry_id": industry_id,
        "total_brands": int(r[3]) if r and r[3] else 0,
        "avg_geo_score": round(r[0] or 0, 2) if r else 0,
        "avg_mention_rate": round(r[1] or 0, 4) if r else 0,
        "avg_sentiment": round(r[2] or 0, 3) if r else 0,
        "top_brands": [
            {"brand_id": row[0], "name": None, "geo_score": round(row[1], 2), "rank": i + 1}
            for i, row in enumerate(top_rows)
        ],
        "period": {"from": from_d.isoformat(), "to": today.isoformat()},
    }


# ────── tool 4: get_product_ranking ──────────────────────────────


async def get_product_ranking(
    session: AsyncSession,
    *,
    user: User,
    project_id: str,
    product_id: int | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Phase A.7 wires real product_score_daily; Phase M.2 stub."""
    return {
        "project_id": project_id,
        "products": [],
        "note": "Phase A.7 wires real product ranking",
    }


# ────── tool 5: generate_report ──────────────────────────────────


async def generate_report(
    session: AsyncSession,
    *,
    user: User,
    project_id: str,
    report_type: str = "weekly",
    format: str = "json",
    period: str | None = None,
    locale: str = "zh-CN",
) -> dict[str, Any]:
    """Phase RP.2 wires real report generation; Phase M.2 stub."""
    return {
        "report_id": "report-" + project_id[:8],
        "status": "queued",
        "report_type": report_type,
        "format": format,
        "locale": locale,
        "note": "Phase RP.2 wires real report generation",
    }


# ────── tool 6: get_optimization_insights ────────────────────────


async def get_optimization_insights(
    session: AsyncSession,
    *,
    user: User,
    project_id: str,
    brand_id: int,
    severity: str | None = None,
) -> dict[str, Any]:
    """Read diagnostics for the project's primary brand."""
    from genpano_models import Diagnostic

    stmt = (
        select(Diagnostic)
        .where(
            and_(
                Diagnostic.project_id == project_id,
                Diagnostic.brand_id == brand_id,
                Diagnostic.status == "open",
            )
        )
        .order_by(Diagnostic.detected_at.desc())
    )
    if severity:
        stmt = stmt.where(Diagnostic.severity == severity)
    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "project_id": project_id,
        "brand_id": brand_id,
        "diagnostics": [
            {
                "id": d.id,
                "category": d.category,
                "severity": d.severity,
                "title": d.title,
                "evidence": d.evidence,
                "direction": d.direction,
                "anchor_questions": d.anchor_questions,
            }
            for d in rows
        ],
    }


# ────── tool 7: get_citations ────────────────────────────────────


async def get_citations(
    session: AsyncSession,
    *,
    user: User,
    brand_id: int,
    range_from: date | None = None,
    range_to: date | None = None,
    tier: list[int] | None = None,
    method: list[str] | None = None,
    page_size: int = 100,
) -> dict[str, Any]:
    """Citation list + filters (tier when authority_tier wired)."""
    today = date.today()
    to_d = range_to or today
    from_d = range_from or (to_d - timedelta(days=29))

    stmt = (
        select(CitationSource)
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .where(
            and_(
                BrandMention.brand_id == brand_id,
                CitationSource.created_at >= from_d,
                CitationSource.created_at <= to_d,
            )
        )
        .order_by(CitationSource.created_at.desc())
        .limit(min(page_size, 500))
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return {
        "brand_id": brand_id,
        "items": [
            {
                "citation_id": c.id,
                "url": c.url,
                "domain": c.domain,
                "title": c.title,
                "source_type": c.source_type,
                "occurred_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in rows
        ],
        "total": len(rows),
    }


# ────── tool 8: list_pr_targets ──────────────────────────────────


async def list_pr_targets(
    session: AsyncSession,
    *,
    user: User,
    brand_id: int,
    top: int = 50,
    exclude_covered: bool = True,
) -> dict[str, Any]:
    """Top tier-1/2 domains the brand has NOT yet been cited on."""
    top = min(top, 200)

    # Domains where the brand IS already cited
    if exclude_covered:
        covered_stmt = (
            select(CitationSource.domain)
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .where(
                and_(
                    BrandMention.brand_id == brand_id,
                    CitationSource.domain.isnot(None),
                )
            )
            .distinct()
        )
        covered = {r[0] for r in (await session.execute(covered_stmt)).all()}
    else:
        covered = set()

    # All domain authorities sorted by tier
    auth_stmt = select(DomainAuthority).order_by(DomainAuthority.tier).limit(top * 2)
    auths = list((await session.execute(auth_stmt)).scalars().all())

    targets = []
    for a in auths:
        if a.domain in covered:
            continue
        targets.append(
            {
                "domain": a.domain,
                "tier": a.tier,
                "confidence": a.confidence,
                "site_type": a.site_type,
                "competitors_count": 0,
                "attributed_to_me_count": 0,
                "trending_30d_pct": None,
                "same_group_shared": False,
                "pr_score": (5 - a.tier) * a.confidence,
            }
        )
        if len(targets) >= top:
            break

    return {
        "brand_id": brand_id,
        "targets": targets,
        "total": len(targets),
    }


# ────── tool 9: simulate_authority_boost (REUSE Phase E service) ─


async def simulate_authority_boost_tool(
    session: AsyncSession,
    *,
    user: User,
    brand_id: int,
    delta_by_tier: dict[str, int],
    confidence_override: float | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Reuse Phase E simulator service — byte-equal output contract."""
    industry_id: int | None = None
    if project_id:
        stmt = select(Project).where(and_(Project.id == project_id, Project.user_id == user.id))
        p = (await session.execute(stmt)).scalar_one_or_none()
        if p:
            industry_id = p.industry_id
    return await simulate_authority_boost(
        session,
        brand_id=brand_id,
        delta_by_tier=delta_by_tier,
        industry_id=industry_id,
        confidence_override=confidence_override,
    )


# ────── tool registry: name → function ──────────────────────────

TOOLS: dict[str, Any] = {
    "genpano_get_brand_visibility": get_brand_visibility,
    "genpano_compare_brands": compare_brands,
    "genpano_get_industry_trends": get_industry_trends,
    "genpano_get_product_ranking": get_product_ranking,
    "genpano_generate_report": generate_report,
    "genpano_get_optimization_insights": get_optimization_insights,
    "genpano_get_citations": get_citations,
    "genpano_list_pr_targets": list_pr_targets,
    "genpano_simulate_authority_boost": simulate_authority_boost_tool,
}


async def dispatch_tool_call(
    session: AsyncSession,
    *,
    user: User,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Dispatch MCP `tools/call` invocation by name."""
    fn = TOOLS.get(tool_name)
    if fn is None:
        return {
            "content": [{"type": "text", "text": f"unknown tool: {tool_name}"}],
            "isError": True,
        }
    try:
        result = await fn(session, user=user, **arguments)
        return {
            "content": [
                {
                    "type": "text",
                    "text": str(result) if not isinstance(result, dict) else "ok",
                }
            ],
            "structuredContent": result,
            "isError": False,
        }
    except TypeError as exc:
        return {
            "content": [{"type": "text", "text": f"invalid arguments: {exc}"}],
            "isError": True,
        }
    except Exception as exc:  # pragma: no cover — broad catch by design
        return {
            "content": [{"type": "text", "text": f"tool error: {exc}"}],
            "isError": True,
        }
