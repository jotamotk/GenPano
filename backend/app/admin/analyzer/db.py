"""DB operations for the analyzer API (Phase 9 slice 9c).

All upstream tables (llm_responses / response_analyses / brand_mentions /
sentiment_drivers / citation_sources / product_feature_mentions /
geo_score_daily) are admin_console-era schemas not in genpano_models
(ADR-002). Defensive ``_table_exists`` probes degrade gracefully on
sqlite test fixtures.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


async def _table_exists(session: AsyncSession, name: str) -> bool:
    try:
        row = (
            await session.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = :n LIMIT 1"
                ),
                {"n": name},
            )
        ).first()
    except Exception:
        return False
    return row is not None


async def fetch_analyzer_stats(session: AsyncSession) -> dict[str, Any]:
    """Aggregate analyzer counts + avg_geo_score + brand count.

    Defensive: if ``llm_responses`` is missing returns the empty shape
    rather than 500ing; ``response_analyses`` and ``brands`` are tried
    independently so a partial migration still surfaces what's available.
    """
    base: dict[str, Any] = {
        "total": 0,
        "done": 0,
        "pending": 0,
        "running": 0,
        "failed": 0,
        "avg_geo_score": None,
        "total_brands_tracked": 0,
    }
    if not await _table_exists(session, "llm_responses"):
        return base
    counts_row = (
        (
            await session.execute(
                text(
                    """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE analysis_status = 'done') AS done,
                    COUNT(*) FILTER (WHERE analysis_status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE analysis_status = 'running') AS running,
                    COUNT(*) FILTER (WHERE analysis_status = 'failed') AS failed
                FROM llm_responses
                """
                )
            )
        )
        .mappings()
        .first()
    )
    if counts_row:
        base.update(
            {
                "total": int(counts_row.get("total") or 0),
                "done": int(counts_row.get("done") or 0),
                "pending": int(counts_row.get("pending") or 0),
                "running": int(counts_row.get("running") or 0),
                "failed": int(counts_row.get("failed") or 0),
            }
        )

    if await _table_exists(session, "response_analyses"):
        try:
            avg_row = (
                (
                    await session.execute(
                        text(
                            "SELECT AVG(geo_score) AS avg FROM response_analyses "
                            "WHERE geo_score > 0"
                        )
                    )
                )
                .mappings()
                .first()
            )
            if avg_row and avg_row.get("avg") is not None:
                base["avg_geo_score"] = float(avg_row["avg"])
        except Exception:
            pass

    if await _table_exists(session, "brands"):
        try:
            brand_row = (
                (await session.execute(text("SELECT COUNT(*) AS count FROM brands")))
                .mappings()
                .first()
            )
            if brand_row:
                base["total_brands_tracked"] = int(brand_row.get("count") or 0)
        except Exception:
            pass
    return base


async def list_brands(session: AsyncSession) -> list[dict[str, Any]]:
    if not await _table_exists(session, "brands"):
        return []
    rows = (
        (await session.execute(text("SELECT id, name FROM brands ORDER BY name"))).mappings().all()
    )
    return [dict(r) for r in rows]


async def list_distinct_llms(session: AsyncSession) -> list[str]:
    if not await _table_exists(session, "queries"):
        return []
    rows = (
        await session.execute(
            text(
                "SELECT DISTINCT target_llm FROM queries "
                "WHERE target_llm IS NOT NULL ORDER BY target_llm"
            )
        )
    ).all()
    return [r[0] for r in rows]


async def list_responses(
    session: AsyncSession,
    *,
    status: str | None = None,
    brand_id: int | None = None,
    llm: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> list[dict[str, Any]]:
    if not await _table_exists(session, "llm_responses"):
        return []
    where: list[str] = []
    params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}
    if status:
        where.append("lr.analysis_status = :status")
        params["status"] = status
    if brand_id is not None:
        where.append("q.brand_id = :brand_id")
        params["brand_id"] = brand_id
    if llm:
        where.append("q.target_llm = :llm")
        params["llm"] = llm
    if date_from:
        where.append("lr.collected_at::date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where.append("lr.collected_at::date <= :date_to")
        params["date_to"] = date_to
    where_clause = ("WHERE " + " AND ".join(where)) if where else ""
    sql = text(
        f"""
        SELECT lr.id AS response_id, lr.analysis_status, lr.collected_at,
               q.target_llm, b.name AS brand_name,
               ra.geo_score, ra.visibility_score, ra.sentiment_score,
               ra.sov_score, ra.citation_score,
               ra.total_brands_mentioned, ra.target_brand_mentioned,
               ra.target_brand_sentiment
        FROM llm_responses lr
        JOIN queries q ON q.id = lr.query_id
        LEFT JOIN brands b ON b.id = q.brand_id
        LEFT JOIN response_analyses ra ON ra.response_id = lr.id
        {where_clause}
        ORDER BY lr.id DESC
        LIMIT :limit OFFSET :offset
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["collected_at"] = _isoformat(item.get("collected_at"))
        out.append(item)
    return out


async def fetch_response_detail(session: AsyncSession, response_id: int) -> dict[str, Any]:
    """Detail view: analysis summary + mentions (with sentiment drivers)
    + citations + product features + raw response. Returns ``{"error":
    "Response not found"}`` when ``response_id`` is missing, matching
    admin_console parity."""
    if not await _table_exists(session, "llm_responses"):
        return {"error": "Response not found"}

    analysis: dict[str, Any] | None = None
    if await _table_exists(session, "response_analyses"):
        analysis_row = (
            (
                await session.execute(
                    text("SELECT * FROM response_analyses WHERE response_id = :id"),
                    {"id": response_id},
                )
            )
            .mappings()
            .first()
        )
        analysis = dict(analysis_row) if analysis_row else None

    raw_row = (
        (
            await session.execute(
                text(
                    """
                SELECT lr.raw_text, lr.analysis_status, lr.collected_at,
                       q.query_text, q.target_llm, b.name AS brand_name
                FROM llm_responses lr
                JOIN queries q ON q.id = lr.query_id
                LEFT JOIN brands b ON b.id = q.brand_id
                WHERE lr.id = :id
                """
                ),
                {"id": response_id},
            )
        )
        .mappings()
        .first()
    )
    raw_resp = dict(raw_row) if raw_row else None

    if analysis is None:
        if not raw_resp:
            return {"error": "Response not found"}
        result = dict(raw_resp)
        result["collected_at"] = _isoformat(result.get("collected_at"))
        raw_text = result.get("raw_text")
        if raw_text and len(raw_text) > 3000:
            result["raw_text"] = raw_text[:3000]
        result["no_analysis"] = True
        result["mentions"] = []
        result["citations"] = []
        result["features"] = []
        return result

    mentions: list[dict[str, Any]] = []
    if await _table_exists(session, "brand_mentions"):
        mention_rows = (
            (
                await session.execute(
                    text(
                        "SELECT * FROM brand_mentions WHERE response_id = :id "
                        "ORDER BY is_target DESC, mention_count DESC"
                    ),
                    {"id": response_id},
                )
            )
            .mappings()
            .all()
        )
        drivers_table_exists = await _table_exists(session, "sentiment_drivers")
        for m in mention_rows:
            mention = dict(m)
            if drivers_table_exists:
                drivers_rows = (
                    (
                        await session.execute(
                            text(
                                "SELECT driver_text, polarity, category, strength, source_quote "
                                "FROM sentiment_drivers WHERE mention_id = :id "
                                "ORDER BY strength DESC"
                            ),
                            {"id": mention["id"]},
                        )
                    )
                    .mappings()
                    .all()
                )
                mention["drivers"] = [dict(d) for d in drivers_rows]
            else:
                mention["drivers"] = []
            mention["created_at"] = _isoformat(mention.get("created_at"))
            mentions.append(mention)

    citations: list[dict[str, Any]] = []
    if await _table_exists(session, "citation_sources"):
        citation_rows = (
            (
                await session.execute(
                    text(
                        "SELECT url, domain, title, citation_index, source_type "
                        "FROM citation_sources WHERE response_id = :id ORDER BY citation_index"
                    ),
                    {"id": response_id},
                )
            )
            .mappings()
            .all()
        )
        citations = [dict(r) for r in citation_rows]

    features: list[dict[str, Any]] = []
    if await _table_exists(session, "product_feature_mentions"):
        feature_rows = (
            (
                await session.execute(
                    text(
                        "SELECT brand_name, product_name, feature_name, feature_sentiment, "
                        "context_snippet, scenario, price_positioning "
                        "FROM product_feature_mentions WHERE analysis_id = :id"
                    ),
                    {"id": analysis["id"]},
                )
            )
            .mappings()
            .all()
        )
        features = [dict(r) for r in feature_rows]

    result = dict(analysis)
    result["analyzed_at"] = _isoformat(result.get("analyzed_at"))
    result["created_at"] = _isoformat(result.get("created_at"))
    result["mentions"] = mentions
    result["citations"] = citations
    result["features"] = features
    if raw_resp:
        result["query_text"] = raw_resp.get("query_text")
        raw_text = raw_resp.get("raw_text")
        result["raw_text"] = raw_text[:3000] if raw_text and len(raw_text) > 3000 else raw_text
    return result


async def fetch_daily_scores(
    session: AsyncSession,
    *,
    brand_id: int | None = None,
    llm: str | None = None,
    days: int = 30,
) -> list[dict[str, Any]]:
    if not await _table_exists(session, "geo_score_daily"):
        return []
    where = ["gd.intent IS NULL", "gd.language IS NULL"]
    params: dict[str, Any] = {}
    if brand_id is not None:
        where.append("gd.brand_id = :brand_id")
        params["brand_id"] = brand_id
    if llm:
        where.append("gd.target_llm = :llm")
        params["llm"] = llm
    else:
        where.append("gd.target_llm IS NULL")
    where.append("gd.date >= NOW() - (CAST(:days AS text) || ' days')::interval")
    params["days"] = int(days)
    where_clause = "WHERE " + " AND ".join(where)
    sql = text(
        f"""
        SELECT gd.*, b.name AS brand_name
        FROM geo_score_daily gd
        JOIN brands b ON b.id = gd.brand_id
        {where_clause}
        ORDER BY gd.date DESC, gd.avg_geo_score DESC
        LIMIT 200
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["date"] = _isoformat(item.get("date"))
        item["created_at"] = _isoformat(item.get("created_at"))
        item["updated_at"] = _isoformat(item.get("updated_at"))
        out.append(item)
    return out


async def reset_responses_for_date(session: AsyncSession, *, date_str: str) -> int:
    """Flip llm_responses status to pending for a given collection date.
    Used by the ``reanalyze`` action of /api/analyzer/trigger."""
    if not await _table_exists(session, "llm_responses"):
        return 0
    result = await session.execute(
        text(
            "UPDATE llm_responses SET analysis_status = 'pending' "
            "WHERE collected_at::date = :date "
            "AND analysis_status IN ('done', 'failed')"
        ),
        {"date": date_str},
    )
    n = int(getattr(result, "rowcount", 0) or 0)
    await session.commit()
    return n


async def reset_response_for_rerun(session: AsyncSession, response_id: int) -> bool:
    """Flip a single llm_responses row back to pending. Returns False
    when the row doesn't exist."""
    if not await _table_exists(session, "llm_responses"):
        return False
    result = await session.execute(
        text("UPDATE llm_responses SET analysis_status = 'pending' WHERE id = :id"),
        {"id": response_id},
    )
    if (getattr(result, "rowcount", 0) or 0) == 0:
        await session.rollback()
        return False
    await session.commit()
    return True


__all__ = [
    "fetch_analyzer_stats",
    "fetch_daily_scores",
    "fetch_response_detail",
    "list_brands",
    "list_distinct_llms",
    "list_responses",
    "reset_response_for_rerun",
    "reset_responses_for_date",
]
