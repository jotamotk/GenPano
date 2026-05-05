"""Phase M.5 — MCP resource implementations.

Three resources (PRD §4.5.2; ADR-006):

  - genpano://projects/{id}/dashboard
        Pano view for the user's project (KPI cards + recent
        diagnostics + active competitors). Multi-tenant — only
        readable by the API key's owning user.

  - genpano://brands/{id}/report
        Brand profile + 30d summary metrics + last 5 diagnostics.

  - genpano://industry/{name}/benchmark
        30d aggregate from `industry_benchmark_daily` for one industry.

The MCP `resources/read` JSON-RPC method invokes `read_resource`. The
returned shape follows the MCP spec:

    {
        "contents": [
            {"uri": "...", "mimeType": "application/json", "text": "..."}
        ]
    }

`text` is a JSON string so MCP-compliant clients can re-parse it.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from genpano_models import (
    Diagnostic,
    GeoScoreDaily,
    IndustryBenchmarkDaily,
    Project,
    ProjectCompetitor,
    User,
)
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

PROJECT_DASHBOARD_RE = re.compile(r"^genpano://projects/(?P<id>[^/]+)/dashboard$")
BRAND_REPORT_RE = re.compile(r"^genpano://brands/(?P<id>[^/]+)/report$")
INDUSTRY_BENCHMARK_RE = re.compile(r"^genpano://industry/(?P<name>[^/]+)/benchmark$")


def _content_envelope(uri: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "contents": [
            {
                "uri": uri,
                "mimeType": "application/json",
                "text": json.dumps(payload, ensure_ascii=False, default=str),
            }
        ]
    }


def _error_envelope(uri: str, code: str, message: str) -> dict[str, Any]:
    return {
        "contents": [
            {
                "uri": uri,
                "mimeType": "application/json",
                "text": json.dumps({"error": {"code": code, "message": message}}),
            }
        ],
        "isError": True,
    }


async def _read_project_dashboard(
    session: AsyncSession, *, user: User, project_id: str, uri: str
) -> dict[str, Any]:
    project = (
        await session.execute(
            select(Project).where(and_(Project.id == project_id, Project.user_id == user.id))
        )
    ).scalar_one_or_none()
    if project is None:
        return _error_envelope(uri, "not_found", "project not found or not owned by caller")

    competitor_ids = [
        r[0]
        for r in (
            await session.execute(
                select(ProjectCompetitor.brand_id).where(ProjectCompetitor.project_id == project_id)
            )
        ).all()
    ]

    today = datetime.now(UTC).date()
    cutoff = datetime.combine(today - timedelta(days=29), datetime.min.time())
    primary_metrics: dict[str, float | int | None] = {}
    if project.primary_brand_id:
        kpi_row = (
            await session.execute(
                select(
                    func.avg(GeoScoreDaily.avg_geo_score),
                    func.avg(GeoScoreDaily.mention_rate),
                    func.avg(GeoScoreDaily.avg_sentiment),
                    func.count(),
                ).where(
                    and_(
                        GeoScoreDaily.brand_id == project.primary_brand_id,
                        GeoScoreDaily.date >= cutoff,
                    )
                )
            )
        ).one_or_none()
        if kpi_row:
            primary_metrics = {
                "avg_geo_score_30d": (round(kpi_row[0], 2) if kpi_row[0] is not None else None),
                "avg_mention_rate_30d": (round(kpi_row[1], 4) if kpi_row[1] is not None else None),
                "avg_sentiment_30d": (round(kpi_row[2], 3) if kpi_row[2] is not None else None),
                "row_count_30d": int(kpi_row[3] or 0),
            }

    diag_rows = list(
        (
            await session.execute(
                select(Diagnostic)
                .where(
                    and_(
                        Diagnostic.project_id == project_id,
                        Diagnostic.status == "open",
                    )
                )
                .order_by(desc(Diagnostic.detected_at))
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    diagnostics = [
        {
            "id": d.id,
            "rule_id": d.rule_id,
            "severity": d.severity,
            "title": d.title,
            "detected_at": d.detected_at.isoformat() if d.detected_at else None,
        }
        for d in diag_rows
    ]

    return _content_envelope(
        uri,
        {
            "project_id": project.id,
            "name": project.name,
            "industry_id": project.industry_id,
            "primary_brand_id": project.primary_brand_id,
            "competitor_brand_ids": competitor_ids,
            "primary_brand_metrics_30d": primary_metrics,
            "open_diagnostics": diagnostics,
        },
    )


async def _read_brand_report(
    session: AsyncSession, *, user: User, brand_id_raw: str, uri: str
) -> dict[str, Any]:
    try:
        brand_id = int(brand_id_raw)
    except ValueError:
        return _error_envelope(uri, "validation_error", "brand id must be an integer")

    # Verify caller has at least one project that monitors this brand
    # (primary_brand_id or pinned competitor). Single tenancy guard.
    own_stmt = select(func.count(Project.id)).where(
        and_(
            Project.user_id == user.id,
            Project.primary_brand_id == brand_id,
        )
    )
    primary_count = (await session.execute(own_stmt)).scalar_one()
    competitor_stmt = (
        select(func.count(ProjectCompetitor.brand_id))
        .select_from(ProjectCompetitor)
        .join(Project, Project.id == ProjectCompetitor.project_id)
        .where(
            and_(
                Project.user_id == user.id,
                ProjectCompetitor.brand_id == brand_id,
            )
        )
    )
    competitor_count = (await session.execute(competitor_stmt)).scalar_one()
    if (primary_count or 0) + (competitor_count or 0) == 0:
        return _error_envelope(uri, "not_found", "brand not in any project owned by caller")

    today = datetime.now(UTC).date()
    cutoff = datetime.combine(today - timedelta(days=29), datetime.min.time())
    metrics_row = (
        await session.execute(
            select(
                func.avg(GeoScoreDaily.avg_geo_score),
                func.avg(GeoScoreDaily.mention_rate),
                func.avg(GeoScoreDaily.avg_sov),
                func.avg(GeoScoreDaily.avg_sentiment),
            ).where(
                and_(
                    GeoScoreDaily.brand_id == brand_id,
                    GeoScoreDaily.date >= cutoff,
                )
            )
        )
    ).one_or_none()

    diag_rows = list(
        (
            await session.execute(
                select(Diagnostic)
                .where(Diagnostic.brand_id == brand_id)
                .order_by(desc(Diagnostic.detected_at))
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    diagnostics = [
        {
            "id": d.id,
            "rule_id": d.rule_id,
            "severity": d.severity,
            "status": d.status,
            "title": d.title,
            "detected_at": d.detected_at.isoformat() if d.detected_at else None,
        }
        for d in diag_rows
    ]

    return _content_envelope(
        uri,
        {
            "brand_id": brand_id,
            "metrics_30d": {
                "avg_geo_score": (
                    round(metrics_row[0], 2) if metrics_row and metrics_row[0] is not None else None
                ),
                "avg_mention_rate": (
                    round(metrics_row[1], 4) if metrics_row and metrics_row[1] is not None else None
                ),
                "avg_sov": (
                    round(metrics_row[2], 4) if metrics_row and metrics_row[2] is not None else None
                ),
                "avg_sentiment": (
                    round(metrics_row[3], 3) if metrics_row and metrics_row[3] is not None else None
                ),
            },
            "recent_diagnostics": diagnostics,
        },
    )


async def _read_industry_benchmark(session: AsyncSession, *, name: str, uri: str) -> dict[str, Any]:
    today = datetime.now(UTC).date()
    cutoff = datetime.combine(today - timedelta(days=29), datetime.min.time())
    rows = list(
        (
            await session.execute(
                select(IndustryBenchmarkDaily)
                .where(
                    and_(
                        IndustryBenchmarkDaily.industry == name,
                        IndustryBenchmarkDaily.date >= cutoff,
                    )
                )
                .order_by(IndustryBenchmarkDaily.date.asc())
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return _error_envelope(uri, "empty", f"no benchmark data for industry={name}")

    avg = (
        await session.execute(
            select(
                func.avg(IndustryBenchmarkDaily.avg_geo_score),
                func.avg(IndustryBenchmarkDaily.avg_mention_rate),
                func.avg(IndustryBenchmarkDaily.avg_sentiment),
                func.max(IndustryBenchmarkDaily.total_brands),
            ).where(
                and_(
                    IndustryBenchmarkDaily.industry == name,
                    IndustryBenchmarkDaily.date >= cutoff,
                )
            )
        )
    ).one()
    return _content_envelope(
        uri,
        {
            "industry": name,
            "window_days": 30,
            "avg_geo_score_30d": round(avg[0], 2) if avg[0] is not None else None,
            "avg_mention_rate_30d": round(avg[1], 4) if avg[1] is not None else None,
            "avg_sentiment_30d": round(avg[2], 3) if avg[2] is not None else None,
            "max_total_brands": int(avg[3] or 0),
            "series": [
                {
                    "date": (r.date.date().isoformat() if hasattr(r.date, "date") else str(r.date)),
                    "target_llm": r.target_llm,
                    "avg_geo_score": r.avg_geo_score,
                    "avg_mention_rate": r.avg_mention_rate,
                    "avg_sentiment": r.avg_sentiment,
                    "total_brands": r.total_brands,
                }
                for r in rows
            ],
        },
    )


async def read_resource(session: AsyncSession, *, user: User | None, uri: str) -> dict[str, Any]:
    """Dispatch a `resources/read` request by URI.

    Multi-tenant: project / brand resources require an authenticated
    user; industry benchmark is public to any authenticated API key
    (no per-row ownership). `user` may be None only on the public
    industry path — guarded below.
    """
    m = PROJECT_DASHBOARD_RE.match(uri)
    if m:
        if user is None:
            return _error_envelope(uri, "unauthorized", "project resource requires user")
        return await _read_project_dashboard(session, user=user, project_id=m.group("id"), uri=uri)

    m = BRAND_REPORT_RE.match(uri)
    if m:
        if user is None:
            return _error_envelope(uri, "unauthorized", "brand resource requires user")
        return await _read_brand_report(session, user=user, brand_id_raw=m.group("id"), uri=uri)

    m = INDUSTRY_BENCHMARK_RE.match(uri)
    if m:
        return await _read_industry_benchmark(session, name=m.group("name"), uri=uri)

    return _error_envelope(uri, "unknown_resource", f"resource URI not registered: {uri}")
