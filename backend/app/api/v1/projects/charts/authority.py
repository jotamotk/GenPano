"""Authority-domain chart helpers.

Phase 4 of splitting `_charts_service.py` (Epic #885, design #886). Hosts the
authority-trend contract wrapper and the per-response-day authority rollup.
The public-API builders (`get_authority_trend`, `get_authority_radar`) remain
in `_charts_service.py` for now; they will move in the final phase once the
shared fact-rollup helpers they depend on are extracted.
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from datetime import date

from genpano_models import BrandMention, CitationSource, DomainAuthority, Project
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._charts_dto import AuthorityTrendOut, AuthorityTrendPoint
from app.api.v1.projects._mention_rollups import brand_mention_match_condition
from app.api.v1.projects.charts._contracts import (
    _chart_contract_update,
    _contract_metric_blocked,
)


async def _with_authority_trend_contract(
    out: AuthorityTrendOut,
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    *,
    source_provenance: list[str],
    brand_id: int | None = None,
) -> AuthorityTrendOut:
    update = await _chart_contract_update(
        session,
        project,
        from_d,
        to_d,
        out,
        metric_keys=["citation"],
        source_provenance=source_provenance,
        brand_id=brand_id,
        require_analyzer_package=True,
    )
    if not update:
        return out
    if _contract_metric_blocked(update, "citation"):
        update["points"] = []
    return out.model_copy(update=update)


async def _target_authority_points_from_facts(
    session: AsyncSession,
    *,
    brand_id: int,
    response_days: dict[int, str],
) -> tuple[list[AuthorityTrendPoint], int]:
    if not response_days:
        return [], 0
    brand_filter = await brand_mention_match_condition(session, brand_id)
    rows = (
        await session.execute(
            select(
                CitationSource.response_id,
                DomainAuthority.tier,
                func.count().label("cnt"),
            )
            .select_from(CitationSource)
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .outerjoin(DomainAuthority, DomainAuthority.domain == CitationSource.domain)
            .where(
                and_(
                    CitationSource.response_id.in_(sorted(response_days)),
                    CitationSource.domain.isnot(None),
                    brand_filter,
                )
            )
            .group_by(CitationSource.response_id, DomainAuthority.tier)
        )
    ).all()
    by_day: dict[str, dict[int | None, int]] = OrderedDict()
    total_count = 0
    for response_id, tier, count in rows:
        day = response_days.get(int(response_id))
        if day is None:
            continue
        value = int(count or 0)
        by_day.setdefault(day, defaultdict(int))[tier] += value
        total_count += value
    points: list[AuthorityTrendPoint] = []
    for day, tier_map in by_day.items():
        total = sum(tier_map.values())
        if total <= 0:
            continue
        points.append(
            AuthorityTrendPoint(
                date=day,
                tier1_pct=round(tier_map.get(1, 0) / total * 100, 1),
                tier2_pct=round(tier_map.get(2, 0) / total * 100, 1),
                tier3_pct=round(tier_map.get(3, 0) / total * 100, 1),
                tier4_pct=round(tier_map.get(4, 0) / total * 100, 1),
                untiered_pct=round(tier_map.get(None, 0) / total * 100, 1),
            )
        )
    return points, total_count
