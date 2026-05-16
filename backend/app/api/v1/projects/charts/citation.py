"""Citation-domain chart helpers.

Phase 4 of splitting `_charts_service.py` (Epic #885, design #886). Hosts the
citation composition contract wrapper and the targeted citation-rows query.
The public-API `get_citation_composition` builder remains in
`_charts_service.py` for now; it will move in the final phase once the
shared fact-rollup helpers it depends on are extracted.
"""

from __future__ import annotations

from datetime import date

from genpano_models import BrandMention, CitationSource, DomainAuthority, Project
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._charts_dto import CitationCompositionOut, CitationCompositionRow
from app.api.v1.projects._mention_rollups import brand_mention_match_condition, brand_mention_names
from app.api.v1.projects.charts._contracts import (
    _chart_contract_update,
    _contract_metric_blocked,
    _metric_evidence_allows_partial_data,
)
from app.api.v1.projects.charts._domain_tier_heuristic import _classify_untiered_domain


async def _with_citation_composition_contract(
    out: CitationCompositionOut,
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    *,
    source_provenance: list[str],
    brand_id: int | None = None,
) -> CitationCompositionOut:
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
    if _contract_metric_blocked(update, "citation") and not _metric_evidence_allows_partial_data(
        update, "citation"
    ):
        update["segments"] = []
        update["total"] = 0
    return out.model_copy(update=update)


async def _target_citation_composition_rows(
    session: AsyncSession,
    *,
    brand_id: int,
    response_ids: list[int],
) -> tuple[list[CitationCompositionRow], int]:
    if not response_ids:
        return [], 0
    brand_filter = await brand_mention_match_condition(session, brand_id)
    # Issue #1020: group by ``DomainAuthority.tier`` directly bucketed every
    # citation whose domain lacked an admin-curated tier row as ``tier=null``.
    # We now group by domain so untiered rows can still be classified via
    # the heuristic fallback (Tier 1 alias, .gov/.edu Tier 2, KOL Tier 3,
    # else Tier 4). Genuinely-empty domains still return ``tier=null``.
    rows = (
        await session.execute(
            select(
                CitationSource.domain,
                DomainAuthority.tier,
                func.count().label("cnt"),
            )
            .select_from(CitationSource)
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .outerjoin(DomainAuthority, DomainAuthority.domain == CitationSource.domain)
            .where(
                and_(
                    CitationSource.response_id.in_(response_ids),
                    CitationSource.domain.isnot(None),
                    brand_filter,
                )
            )
            .group_by(CitationSource.domain, DomainAuthority.tier)
        )
    ).all()
    aliases = sorted(await brand_mention_names(session, brand_id))
    by_tier: dict[int | None, int] = {}
    total = 0
    for domain, db_tier, cnt in rows:
        count = int(cnt or 0)
        if count <= 0:
            continue
        if db_tier is None:
            tier: int | None = _classify_untiered_domain(domain, aliases)
        else:
            tier = int(db_tier)
        by_tier[tier] = by_tier.get(tier, 0) + count
        total += count
    label_for = {
        1: "Tier 1",
        2: "Tier 2",
        3: "Tier 3",
        4: "Tier 4",
        None: "Untiered",
    }
    return (
        [
            CitationCompositionRow(
                label=label_for[tier],
                tier=tier,
                count=count,
                pct=round(count / total * 100, 1) if total else 0.0,
            )
            for tier in (1, 2, 3, 4, None)
            if (count := by_tier.get(tier, 0)) or tier is not None
        ],
        total,
    )
