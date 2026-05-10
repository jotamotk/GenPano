"""BrandMention-based metric fallbacks for live dashboard endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from genpano_models import BrandMention, CitationSource
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class MentionRollup:
    mention_count: int
    response_count: int
    total_response_count: int
    total_mention_count: int
    avg_position_rank: float | None
    avg_sentiment_score: float | None
    citation_response_count: int = 0

    @property
    def has_data(self) -> bool:
        return self.mention_count > 0 or self.response_count > 0


def _bounds(from_date: date, to_date: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(from_date, datetime.min.time()),
        datetime.combine(to_date, datetime.max.time()),
    )


def _day_key(value: object) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _ratio(numerator: int | float | None, denominator: int | float | None) -> float:
    if numerator is None or denominator is None or denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


def _sentiment_unit(value: float | None) -> float:
    if value is None:
        return 0.5
    if value < 0:
        return max(0.0, min(1.0, (value + 1.0) / 2.0))
    if value > 1:
        return max(0.0, min(1.0, value / 100.0))
    return max(0.0, min(1.0, value))


def _rank_unit(value: float | None) -> float:
    if value is None:
        return 0.5
    return max(0.0, min(1.0, (6.0 - min(float(value), 6.0)) / 5.0))


def mention_rate(rollup: MentionRollup) -> float:
    return _ratio(rollup.response_count, rollup.total_response_count)


def share_of_voice(rollup: MentionRollup) -> float:
    return _ratio(rollup.mention_count, rollup.total_mention_count)


def citation_rate(rollup: MentionRollup) -> float:
    return _ratio(rollup.citation_response_count, rollup.response_count)


def geo_score(rollup: MentionRollup) -> float:
    score = (
        mention_rate(rollup) * 0.35
        + share_of_voice(rollup) * 0.25
        + _rank_unit(rollup.avg_position_rank) * 0.25
        + _sentiment_unit(rollup.avg_sentiment_score) * 0.15
    )
    return round(max(0.0, min(100.0, score * 100.0)), 2)


def metric_value(rollup: MentionRollup, metric: str) -> float:
    if metric == "mention_rate":
        return round(mention_rate(rollup), 4)
    if metric == "sov":
        return round(share_of_voice(rollup), 4)
    if metric == "sentiment":
        return round(float(rollup.avg_sentiment_score or 0), 4)
    if metric == "rank":
        return round(float(rollup.avg_position_rank or 0), 4)
    if metric == "citation":
        return round(citation_rate(rollup), 4)
    if metric == "geo_score":
        return geo_score(rollup)
    return 0.0


async def brand_mention_window_rollup(
    session: AsyncSession,
    brand_id: int,
    from_date: date,
    to_date: date,
) -> MentionRollup:
    from_dt, to_dt = _bounds(from_date, to_date)
    window_filter = and_(BrandMention.created_at >= from_dt, BrandMention.created_at <= to_dt)

    total_row = (
        await session.execute(
            select(
                func.count(func.distinct(BrandMention.response_id)),
                func.sum(func.coalesce(BrandMention.mention_count, 1)),
            ).where(window_filter)
        )
    ).one()
    brand_row = (
        await session.execute(
            select(
                func.count(BrandMention.id),
                func.count(func.distinct(BrandMention.response_id)),
                func.sum(func.coalesce(BrandMention.mention_count, 1)),
                func.avg(BrandMention.position_rank),
                func.avg(BrandMention.sentiment_score),
            ).where(and_(window_filter, BrandMention.brand_id == brand_id))
        )
    ).one()
    citation_count = int(
        (
            await session.execute(
                select(func.count(func.distinct(CitationSource.response_id)))
                .join(BrandMention, BrandMention.id == CitationSource.mention_id)
                .where(
                    and_(
                        BrandMention.brand_id == brand_id,
                        CitationSource.created_at >= from_dt,
                        CitationSource.created_at <= to_dt,
                    )
                )
            )
        ).scalar_one()
        or 0
    )

    mention_count = int(brand_row[2] or brand_row[0] or 0)
    return MentionRollup(
        mention_count=mention_count,
        response_count=int(brand_row[1] or 0),
        total_response_count=int(total_row[0] or 0),
        total_mention_count=int(total_row[1] or total_row[0] or 0),
        avg_position_rank=float(brand_row[3]) if brand_row[3] is not None else None,
        avg_sentiment_score=float(brand_row[4]) if brand_row[4] is not None else None,
        citation_response_count=citation_count,
    )


async def brand_mention_daily_rollups(
    session: AsyncSession,
    brand_id: int,
    from_date: date,
    to_date: date,
) -> dict[str, MentionRollup]:
    from_dt, to_dt = _bounds(from_date, to_date)
    bucket = func.date(BrandMention.created_at)
    window_filter = and_(BrandMention.created_at >= from_dt, BrandMention.created_at <= to_dt)

    total_rows = (
        await session.execute(
            select(
                bucket,
                func.count(func.distinct(BrandMention.response_id)),
                func.sum(func.coalesce(BrandMention.mention_count, 1)),
            )
            .where(window_filter)
            .group_by(bucket)
        )
    ).all()
    totals = {
        _day_key(row[0]): (int(row[1] or 0), int(row[2] or row[1] or 0)) for row in total_rows
    }

    brand_rows = (
        await session.execute(
            select(
                bucket,
                func.count(BrandMention.id),
                func.count(func.distinct(BrandMention.response_id)),
                func.sum(func.coalesce(BrandMention.mention_count, 1)),
                func.avg(BrandMention.position_rank),
                func.avg(BrandMention.sentiment_score),
            )
            .where(and_(window_filter, BrandMention.brand_id == brand_id))
            .group_by(bucket)
            .order_by(bucket)
        )
    ).all()

    citation_bucket = func.date(CitationSource.created_at)
    citation_rows = (
        await session.execute(
            select(citation_bucket, func.count(func.distinct(CitationSource.response_id)))
            .join(BrandMention, BrandMention.id == CitationSource.mention_id)
            .where(
                and_(
                    BrandMention.brand_id == brand_id,
                    CitationSource.created_at >= from_dt,
                    CitationSource.created_at <= to_dt,
                )
            )
            .group_by(citation_bucket)
        )
    ).all()
    citation_counts = {_day_key(row[0]): int(row[1] or 0) for row in citation_rows}

    out: dict[str, MentionRollup] = {}
    for row in brand_rows:
        key = _day_key(row[0])
        total_responses, total_mentions = totals.get(key, (0, 0))
        mention_count = int(row[3] or row[1] or 0)
        out[key] = MentionRollup(
            mention_count=mention_count,
            response_count=int(row[2] or 0),
            total_response_count=total_responses,
            total_mention_count=total_mentions,
            avg_position_rank=float(row[4]) if row[4] is not None else None,
            avg_sentiment_score=float(row[5]) if row[5] is not None else None,
            citation_response_count=citation_counts.get(key, 0),
        )
    return out


async def discover_related_brand_ids(
    session: AsyncSession,
    brand_id: int,
    from_date: date,
    to_date: date,
    *,
    limit: int = 3,
) -> list[int]:
    from_dt, to_dt = _bounds(from_date, to_date)
    primary_responses = (
        select(BrandMention.response_id)
        .where(
            and_(
                BrandMention.brand_id == brand_id,
                BrandMention.created_at >= from_dt,
                BrandMention.created_at <= to_dt,
            )
        )
        .scalar_subquery()
    )
    rows = (
        await session.execute(
            select(BrandMention.brand_id, func.count().label("cnt"))
            .where(
                and_(
                    BrandMention.brand_id.isnot(None),
                    BrandMention.brand_id != brand_id,
                    BrandMention.response_id.in_(primary_responses),
                    BrandMention.created_at >= from_dt,
                    BrandMention.created_at <= to_dt,
                )
            )
            .group_by(BrandMention.brand_id)
            .order_by(desc("cnt"))
            .limit(limit)
        )
    ).all()
    related = [int(row[0]) for row in rows if row[0] is not None]
    if related:
        return related

    rows = (
        await session.execute(
            select(BrandMention.brand_id, func.count().label("cnt"))
            .where(
                and_(
                    BrandMention.brand_id.isnot(None),
                    BrandMention.brand_id != brand_id,
                    BrandMention.created_at >= from_dt,
                    BrandMention.created_at <= to_dt,
                )
            )
            .group_by(BrandMention.brand_id)
            .order_by(desc("cnt"))
            .limit(limit)
        )
    ).all()
    return [int(row[0]) for row in rows if row[0] is not None]
