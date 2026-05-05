"""Phase E services: exports + brand submissions + simulator.

The simulator function is also exposed via Phase M MCP tool
`genpano_simulate_authority_boost` — same implementation, byte-equal output
contract (ADR re Reports/Simulator shared service).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from genpano_models import (
    BrandSubmission,
    CitationSource,
    ExportJob,
    IndustryPricingParams,
    Project,
    User,
)
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import not_found, rate_limit_exceeded

EXPORT_DAILY_QUOTA = 20  # PRD §4.7.4.2
PANO_A_WEIGHTS = {
    "visibility": 0.4,
    "sov": 0.2,
    "sentiment": 0.2,
    "citation_authority": 0.2,
}
TIER_WEIGHTS = {0: 0.0, 1: 1.0, 2: 0.7, 3: 0.4, 4: 0.1}


def _new_id() -> str:
    return str(uuid.uuid4())


# ── Exports ──────────────────────────────────────────────────────


async def create_export_job(
    session: AsyncSession,
    *,
    project: Project,
    user: User,
    export_type: str,
    scope: dict[str, Any] | None,
) -> ExportJob:
    """Enqueue export job; enforce 20/day quota per user (PRD §4.7.4.2)."""
    today_start = (
        datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).replace(tzinfo=None)
    )
    today_end = today_start + timedelta(days=1)
    quota_stmt = select(func.count()).where(
        and_(
            ExportJob.user_id == user.id,
            ExportJob.created_at >= today_start,
            ExportJob.created_at < today_end,
        )
    )
    today_count = int((await session.execute(quota_stmt)).scalar_one() or 0)
    if today_count >= EXPORT_DAILY_QUOTA:
        raise rate_limit_exceeded(retry_after_seconds=86400)

    job = ExportJob(
        id=_new_id(),
        project_id=project.id,
        user_id=user.id,
        export_type=export_type,
        scope=scope,
        status="queued",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    # TODO Phase E.celery: dispatch celery task to materialize CSV → S3 + set output_url
    return job


async def get_export_job(session: AsyncSession, *, project: Project, export_id: str) -> ExportJob:
    stmt = select(ExportJob).where(
        and_(
            ExportJob.id == export_id,
            ExportJob.project_id == project.id,
        )
    )
    job = (await session.execute(stmt)).scalar_one_or_none()
    if job is None:
        raise not_found("export job not found")
    return job


async def materialize_export_csv(
    session: AsyncSession, *, project: Project, job: ExportJob
) -> tuple[str, int]:
    """Synchronously materialize the export rows as CSV text + row count.

    Returns (csv_text, row_count). Marks the job done with row_count
    populated. Raises NotImplementedError for export types we haven't
    wired yet.

    The 4 wired types pull only data the project owner can see — the
    project ownership check has already been done by the caller (router).
    """
    import csv
    import io

    from genpano_models import (
        BrandMention,
        GeoScoreDaily,
        ProjectCompetitor,
        SentimentDriver,
    )

    buf = io.StringIO()
    writer = csv.writer(buf)
    row_count = 0

    if job.export_type == "mention_list":
        writer.writerow(["created_at", "brand_id", "brand_name", "sentiment", "sentiment_score"])
        scope = job.scope or {}
        brand_filter = scope.get("brand_ids")
        stmt = select(BrandMention).order_by(BrandMention.created_at.desc()).limit(50000)
        if brand_filter:
            stmt = stmt.where(BrandMention.brand_id.in_(brand_filter))
        elif project.primary_brand_id is not None:
            stmt = stmt.where(BrandMention.brand_id == project.primary_brand_id)
        for m in (await session.execute(stmt)).scalars().all():
            writer.writerow(
                [
                    m.created_at.isoformat() if m.created_at else "",
                    m.brand_id,
                    m.brand_name or "",
                    m.sentiment or "",
                    m.sentiment_score if m.sentiment_score is not None else "",
                ]
            )
            row_count += 1

    elif job.export_type == "sentiment_list":
        writer.writerow(
            ["created_at", "brand_name", "polarity", "category", "strength", "driver_text"]
        )
        if project.primary_brand_id is not None:
            # SentimentDriver has no brand_id column — join via mention.
            sd_stmt = (
                select(SentimentDriver)
                .join(BrandMention, BrandMention.id == SentimentDriver.mention_id)
                .where(BrandMention.brand_id == project.primary_brand_id)
                .order_by(SentimentDriver.created_at.desc())
                .limit(50000)
            )
            for d in (await session.execute(sd_stmt)).scalars().all():
                writer.writerow(
                    [
                        d.created_at.isoformat() if d.created_at else "",
                        d.brand_name or "",
                        d.polarity or "",
                        d.category or "",
                        d.strength if d.strength is not None else "",
                        (d.driver_text or "").replace("\n", " ")[:500],
                    ]
                )
                row_count += 1

    elif job.export_type == "industry_ranking":
        from datetime import date as _date
        from datetime import timedelta as _td

        writer.writerow(["brand_id", "avg_geo_score_30d", "rank"])
        today = _date.today()
        from_d = today - _td(days=29)
        rank_stmt = (
            select(
                GeoScoreDaily.brand_id,
                func.avg(GeoScoreDaily.avg_geo_score).label("g"),
            )
            .where(GeoScoreDaily.date >= datetime.combine(from_d, datetime.min.time()))
            .group_by(GeoScoreDaily.brand_id)
            .order_by(func.avg(GeoScoreDaily.avg_geo_score).desc())
            .limit(500)
        )
        for i, r in enumerate((await session.execute(rank_stmt)).all()):
            writer.writerow([r[0], round(r[1] or 0, 2), i + 1])
            row_count += 1

    elif job.export_type == "competitor_matrix":
        writer.writerow(
            ["my_brand_id", "competitor_brand_id", "my_geo_30d", "comp_geo_30d", "delta"]
        )
        from datetime import date as _date
        from datetime import timedelta as _td

        comp_stmt = select(ProjectCompetitor.brand_id).where(
            ProjectCompetitor.project_id == project.id
        )
        comp_ids = [r[0] for r in (await session.execute(comp_stmt)).all()]
        if project.primary_brand_id is None or not comp_ids:
            row_count = 0
        else:
            today = _date.today()
            from_d = today - _td(days=29)

            async def _avg(bid: int) -> float | None:
                s = select(func.avg(GeoScoreDaily.avg_geo_score)).where(
                    and_(
                        GeoScoreDaily.brand_id == bid,
                        GeoScoreDaily.date >= datetime.combine(from_d, datetime.min.time()),
                    )
                )
                return (await session.execute(s)).scalar_one_or_none()

            my = await _avg(project.primary_brand_id)
            for cid in comp_ids:
                comp = await _avg(cid)
                writer.writerow(
                    [
                        project.primary_brand_id,
                        cid,
                        round(my, 2) if my is not None else "",
                        round(comp, 2) if comp is not None else "",
                        round((comp or 0) - (my or 0), 2),
                    ]
                )
                row_count += 1

    else:
        # Other types (citation_list / topic_coverage / products_list /
        # report_data) are scaffolded for future PRs.
        raise NotImplementedError(f"export_type '{job.export_type}' not yet implemented")

    job.status = "done"
    job.row_count = row_count
    job.finished_at = datetime.now(UTC).replace(tzinfo=None)
    await session.commit()
    return buf.getvalue(), row_count


# ── Brand Submission ─────────────────────────────────────────────


async def submit_brand(
    session: AsyncSession,
    *,
    user: User,
    proposed_name: str,
    proposed_industry_id: int | None,
    proposed_aliases: list[str] | None,
    proposed_official_domains: list[str] | None,
    notes: str | None,
    source_url: str | None,
) -> BrandSubmission:
    sub = BrandSubmission(
        id=_new_id(),
        user_id=user.id,
        proposed_name=proposed_name,
        proposed_industry_id=proposed_industry_id,
        proposed_aliases=proposed_aliases,
        proposed_official_domains=proposed_official_domains,
        notes=notes,
        source_url=source_url,
        status="pending",
    )
    session.add(sub)
    await session.commit()
    await session.refresh(sub)
    return sub


async def list_user_submissions(session: AsyncSession, *, user: User) -> list[BrandSubmission]:
    stmt = (
        select(BrandSubmission)
        .where(BrandSubmission.user_id == user.id)
        .order_by(BrandSubmission.created_at.desc())
    )
    return list((await session.execute(stmt)).scalars().all())


# ── Simulator ────────────────────────────────────────────────────


async def simulate_authority_boost(
    session: AsyncSession,
    *,
    brand_id: int,
    delta_by_tier: dict[str, int],
    industry_id: int | None,
    confidence_override: float | None = None,
) -> dict[str, Any]:
    """Recompute PANO_A under simulated tier additions.

    Per PRD §4.7.6:
      PANO_A = 0.4*visibility + 0.2*sov + 0.2*sentiment + 0.2*citation_authority
      citation_authority = Σ tier_weight[t] * tier_count[t] / total_citations
    """
    # Pull current tier counts for this brand from citation_sources joined via
    # brand_mentions (Phase A.4 will add `authority_tier` column; for now
    # tier_count derives from a synthetic distribution)
    from genpano_models import BrandMention  # avoid circular at module load

    stmt = (
        select(func.count())
        .select_from(CitationSource)
        .join(BrandMention, BrandMention.id == CitationSource.mention_id)
        .where(BrandMention.brand_id == brand_id)
    )
    total_citations = int((await session.execute(stmt)).scalar_one() or 0)

    # Phase A.4 stub: synthetic distribution if no `authority_tier` column yet
    # Assume balanced distribution: tier1=10%, tier2=30%, tier3=40%, tier4=20%
    cur_counts = {
        1: int(total_citations * 0.10),
        2: int(total_citations * 0.30),
        3: int(total_citations * 0.40),
        4: int(total_citations * 0.20),
    }
    if total_citations == 0:
        # Provide a baseline so the formula is exercisable in dev / fresh env
        cur_counts = {1: 10, 2: 30, 3: 40, 4: 20}
        total_citations = sum(cur_counts.values())

    sim_counts = dict(cur_counts)
    for tier_str, delta in delta_by_tier.items():
        try:
            tier = int(tier_str)
        except ValueError:
            continue
        if tier in sim_counts:
            sim_counts[tier] = max(0, sim_counts[tier] + delta)
    sim_total = sum(sim_counts.values())

    def _authority(counts: dict[int, int], total: int) -> float:
        if not total:
            return 0.0
        return sum(TIER_WEIGHTS[t] * c for t, c in counts.items()) / total

    cur_authority = _authority(cur_counts, total_citations)
    sim_authority = _authority(sim_counts, sim_total)

    # For Phase E, hold visibility/sov/sentiment constant (pulled from Phase 2.1
    # service when integrated). Here we use synthetic baseline.
    base_visibility = 0.5
    base_sov = 0.4
    base_sentiment = 0.7

    def _pano_a(authority: float) -> float:
        return (
            PANO_A_WEIGHTS["visibility"] * base_visibility * 100
            + PANO_A_WEIGHTS["sov"] * base_sov * 100
            + PANO_A_WEIGHTS["sentiment"] * base_sentiment * 100
            + PANO_A_WEIGHTS["citation_authority"] * authority * 100
        )

    cur_pano = _pano_a(cur_authority)
    sim_pano = _pano_a(sim_authority)
    delta_pano = sim_pano - cur_pano

    # base_price_equivalent_cny = Σ delta_by_tier[t] * industry_pricing_params.tierN
    pricing_stmt = select(IndustryPricingParams).where(
        IndustryPricingParams.industry_id == (industry_id or -1)
    )
    pricing = (await session.execute(pricing_stmt)).scalar_one_or_none()
    base_price = 0.0
    if pricing:
        for tier_str, delta in delta_by_tier.items():
            if delta <= 0:
                continue
            try:
                tier = int(tier_str)
            except ValueError:
                continue
            unit_price = {
                1: pricing.tier1_unit_price_cny,
                2: pricing.tier2_unit_price_cny,
                3: pricing.tier3_unit_price_cny,
                4: pricing.tier4_unit_price_cny,
            }.get(tier)
            if unit_price is not None:
                base_price += float(unit_price) * delta

    confidence = confidence_override if confidence_override is not None else 0.85

    return {
        "current_pano_a": round(cur_pano, 2),
        "simulated_pano_a": round(sim_pano, 2),
        "delta": round(delta_pano, 2),
        "delta_breakdown": {
            "visibility": 0.0,
            "sov": 0.0,
            "sentiment": 0.0,
            "citation_authority": round(delta_pano, 2),
        },
        "base_price_equivalent_cny": round(base_price, 2),
        "confidence": round(confidence, 3),
    }
