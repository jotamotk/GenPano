"""BrandMention helper queries for App analytics endpoint identity matching."""

from __future__ import annotations

from datetime import date, datetime

from genpano_models import BrandMention
from sqlalchemy import and_, desc, func, not_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.api.v1.projects._legacy_lookups import brand_table_columns


def _bounds(from_date: date, to_date: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(from_date, datetime.min.time()),
        datetime.combine(to_date, datetime.max.time()),
    )


def _clean_brand_name(value: object) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip().lower()
    return cleaned or None


async def brand_mention_names(session: AsyncSession, brand_id: int) -> set[str]:
    """Names/aliases that should be treated as the same brand in mentions.

    Production analyzer data is not always perfectly FK-normalized:
    `brand_mentions.brand_name` can contain the display name while
    `brand_mentions.brand_id` is null. Analytics identity matching therefore
    checks either the FK or the canonical names from `brands`.
    """
    cols = await brand_table_columns(session)
    name_cols = [c for c in ("name_zh", "name_en", "name", "primary_name") if c in cols]
    names: set[str] = set()

    if name_cols:
        select_list = ", ".join(name_cols)
        try:
            row = (
                await session.execute(
                    text(f"SELECT {select_list} FROM brands WHERE id = :id"),
                    {"id": brand_id},
                )
            ).one_or_none()
            if row:
                names.update(filter(None, (_clean_brand_name(v) for v in row)))
        except Exception:
            names = set()

    if "aliases" in cols:
        try:
            alias_rows = (
                await session.execute(
                    text(
                        """
                        SELECT alias
                        FROM brands b,
                             LATERAL jsonb_array_elements_text(
                               CASE WHEN jsonb_typeof(b.aliases) = 'array'
                                    THEN b.aliases ELSE '[]'::jsonb END
                             ) AS a(alias)
                        WHERE b.id = :id
                        """
                    ),
                    {"id": brand_id},
                )
            ).all()
            names.update(filter(None, (_clean_brand_name(r[0]) for r in alias_rows)))
        except Exception:
            pass

    return names


def brand_mention_name_condition(names: set[str]) -> ColumnElement[bool] | None:
    if not names:
        return None
    return func.lower(func.trim(BrandMention.brand_name)).in_(sorted(names))


async def brand_mention_match_condition(
    session: AsyncSession, brand_id: int
) -> ColumnElement[bool]:
    names = await brand_mention_names(session, brand_id)
    name_condition = brand_mention_name_condition(names)
    if name_condition is None:
        return BrandMention.brand_id == brand_id
    return or_(BrandMention.brand_id == brand_id, name_condition)


async def _industry_brand_ids(session: AsyncSession, industry_name: str | None) -> set[int] | None:
    """Return brand_ids whose `brands.industry` matches `industry_name`.

    Returns None when no scoping should apply (no industry, table empty,
    or query unsupported) — callers treat None as "do not filter".
    """
    if not industry_name:
        return None
    try:
        rows = await session.execute(
            text("SELECT id FROM brands WHERE industry = :ind"),
            {"ind": industry_name},
        )
        ids = {int(r[0]) for r in rows.all() if r[0] is not None}
        return ids or None
    except Exception:
        return None


async def discover_related_brand_ids(
    session: AsyncSession,
    brand_id: int,
    from_date: date,
    to_date: date,
    *,
    limit: int = 3,
    industry_name: str | None = None,
) -> list[int]:
    """Discover competitor brand_ids co-mentioned with `brand_id`.

    When `industry_name` is provided, only brands listed under that
    industry in `brands.industry` are returned — prevents cross-industry
    products from leaking into the competitor comparison panel (issue
    #975). When the industry scope cannot be applied (no name, empty
    `brands` table, or no brands found for the industry), discovery
    falls back to the unscoped behavior.
    """
    from_dt, to_dt = _bounds(from_date, to_date)
    primary_names = await brand_mention_names(session, brand_id)
    primary_name_condition = brand_mention_name_condition(primary_names)
    primary_filter = (
        BrandMention.brand_id == brand_id
        if primary_name_condition is None
        else or_(BrandMention.brand_id == brand_id, primary_name_condition)
    )
    exclude_primary_filter = BrandMention.brand_id != brand_id
    if primary_name_condition is not None:
        exclude_primary_filter = and_(
            exclude_primary_filter,
            not_(primary_name_condition),
        )

    industry_brand_ids = await _industry_brand_ids(session, industry_name)
    industry_filter = (
        BrandMention.brand_id.in_(industry_brand_ids - {brand_id}) if industry_brand_ids else None
    )

    primary_responses = (
        select(BrandMention.response_id)
        .where(
            and_(
                primary_filter,
                BrandMention.created_at >= from_dt,
                BrandMention.created_at <= to_dt,
            )
        )
        .scalar_subquery()
    )
    related_where = [
        BrandMention.brand_id.isnot(None),
        exclude_primary_filter,
        BrandMention.response_id.in_(primary_responses),
        BrandMention.created_at >= from_dt,
        BrandMention.created_at <= to_dt,
    ]
    if industry_filter is not None:
        related_where.append(industry_filter)
    rows = (
        await session.execute(
            select(BrandMention.brand_id, func.count().label("cnt"))
            .where(and_(*related_where))
            .group_by(BrandMention.brand_id)
            .order_by(desc("cnt"))
            .limit(limit)
        )
    ).all()
    related = [int(row[0]) for row in rows if row[0] is not None]
    if related:
        return related

    fallback_where = [
        BrandMention.brand_id.isnot(None),
        exclude_primary_filter,
        BrandMention.created_at >= from_dt,
        BrandMention.created_at <= to_dt,
    ]
    if industry_filter is not None:
        fallback_where.append(industry_filter)
    rows = (
        await session.execute(
            select(BrandMention.brand_id, func.count().label("cnt"))
            .where(and_(*fallback_where))
            .group_by(BrandMention.brand_id)
            .order_by(desc("cnt"))
            .limit(limit)
        )
    ).all()
    return [int(row[0]) for row in rows if row[0] is not None]
