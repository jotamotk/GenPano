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
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._charts_dto import (
    CitationCompositionOut,
    CitationCompositionRow,
    TopCitedPageRow,
    TopCitedPagesOut,
)
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


async def _with_top_cited_pages_contract(
    out: TopCitedPagesOut,
    session: AsyncSession,
    project: Project,
    from_d: date,
    to_d: date,
    *,
    source_provenance: list[str],
    brand_id: int | None = None,
) -> TopCitedPagesOut:
    """Issue #1019: mirror `_with_citation_composition_contract` so the
    top-cited-pages endpoint surfaces the standard analytics contract
    (state / formula_status / metric_formula_evidence / missing_inputs /
    evidence_counts / source_provenance). Reuses
    `_metric_evidence_allows_partial_data` (PR #1007) so chart items
    survive `formula_status: partial` backed by real analyzer evidence
    and are only cleared in the legacy-only synthetic-partial case.
    """
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
        update["items"] = []
        update["total"] = 0
    return out.model_copy(update=update)


async def _target_top_cited_pages_rows(
    session: AsyncSession,
    *,
    brand_id: int,
    response_ids: list[int] | None = None,
    from_dt: object | None = None,
    to_dt: object | None = None,
    limit: int = 10,
) -> tuple[list[TopCitedPageRow], int]:
    """Aggregate citation sources by (url, title) ordered by count desc.

    Issue #1019: filters by `brand_mention_match_condition(brand_id)` —
    the lenient match used by `/citations` list (FK OR canonical alias)
    so production rows with `brand_id=NULL` but matching `brand_name`
    still surface. Either `response_ids` (admin-chain path) or
    `from_dt`/`to_dt` (direct CitationSource window) scopes the query.

    Returns `(items, total_distinct_pages)`. `total` is the count of
    distinct (url, title) pages so the FE can show a "showing N of M"
    summary if needed.
    """
    brand_filter = await brand_mention_match_condition(session, brand_id)
    predicates = [
        CitationSource.url.isnot(None),
        brand_filter,
    ]
    if response_ids is not None:
        if not response_ids:
            return [], 0
        predicates.append(CitationSource.response_id.in_(response_ids))
    else:
        if from_dt is not None:
            predicates.append(CitationSource.created_at >= from_dt)
        if to_dt is not None:
            predicates.append(CitationSource.created_at <= to_dt)

    # Issue #1019 / PR #1026 Codex review: group ONLY by (url, title) per the
    # endpoint contract. Including ``CitationSource.domain`` in the GROUP BY
    # would split the same cited page into duplicate rows whenever the same
    # URL was stored with inconsistent domain values (``example.com`` vs.
    # ``www.example.com`` vs. ``NULL`` from a parser miss), each row carrying
    # a lower count. The aggregated count would also no longer match the
    # frontend's "showing N of M" summary. Use ``MAX(domain)`` as a stable
    # representative (NULLs lose to non-NULL strings under SQL MAX, so a
    # populated value wins when present).
    base = (
        select(
            CitationSource.url.label("url"),
            CitationSource.title.label("title"),
            func.max(CitationSource.domain).label("domain"),
            func.count().label("cnt"),
            func.min(CitationSource.created_at).label("first_seen"),
            func.max(CitationSource.created_at).label("last_seen"),
            func.max(DomainAuthority.tier).label("tier"),
        )
        .select_from(CitationSource)
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .outerjoin(DomainAuthority, DomainAuthority.domain == CitationSource.domain)
        .where(and_(*predicates))
        .group_by(CitationSource.url, CitationSource.title)
    )

    total_distinct = int(
        (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one() or 0
    )
    rows = (await session.execute(base.order_by(desc("cnt"), desc("last_seen")).limit(limit))).all()
    # Issue #1002 follow-up to #1019/#1020: apply the heuristic tier fallback
    # to top-pages too. The original PR #1026 only joined to ``DomainAuthority``,
    # which returns NULL for every cited domain on live envs where the
    # ``domain_authorities`` table is unseeded — so the page rendered
    # ``Tier ?`` for every row even though composition + authority_trend
    # already classified the same domains (Tier 1 via brand alias for
    # ``bestcoffer.com``, Tier 4 for unclassified UGC like ``spc.org.cn``).
    # Mirror the heuristic application from ``_target_citation_composition_rows``.
    aliases = sorted(await brand_mention_names(session, brand_id))
    items = [
        TopCitedPageRow(
            url=row.url,
            title=row.title,
            domain=row.domain,
            tier=int(row.tier)
            if row.tier is not None
            else _classify_untiered_domain(row.domain, aliases),
            count=int(row.cnt or 0),
            first_seen_at=row.first_seen.isoformat() if row.first_seen else None,
            last_seen_at=row.last_seen.isoformat() if row.last_seen else None,
        )
        for row in rows
    ]
    return items, total_distinct


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
