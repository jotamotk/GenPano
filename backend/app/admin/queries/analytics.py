"""Brand query analytics — Phase 9 slice 9e.

GET /api/admin/queries/analytics?brand_id=...&date_from=...&date_to=...&engine=...
returns aggregated metrics derived from queries JOIN llm_responses JOIN
response_analyses JOIN brand_mentions JOIN prompts JOIN topics. Designed
to feed the C-side TopicsPage QueryActivityCard.

Defensive shape: every join is gated by ``_table_exists`` because the
backend test bind (sqlite) doesn't have these tables, and production
schemas vary by deploy generation. Empty/zero values flow through to a
shape-stable response.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.queries.lib import is_iso_date

logger = logging.getLogger(__name__)


_DEFAULT_WINDOW_DAYS = 30


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


def _empty_result(
    *,
    brand_id: int | None,
    date_from: str,
    date_to: str,
    engine: str | None,
) -> dict[str, Any]:
    return {
        "filters": {
            "brand_id": brand_id,
            "date_from": date_from,
            "date_to": date_to,
            "engine": engine,
        },
        "totals": {"queries": 0, "responses": 0, "analyzed": 0, "mentions_target": 0},
        "by_status": {"done": 0, "failed": 0, "pending": 0, "running": 0},
        "by_engine": [],
        "daily_trend": [],
        "by_topic": [],
        "sentiment_distribution": {"positive": 0, "neutral": 0, "negative": 0},
        "position_distribution": [
            {"bucket": "Top1", "count": 0},
            {"bucket": "Top3", "count": 0},
            {"bucket": "Top5", "count": 0},
            {"bucket": "Top10", "count": 0},
            {"bucket": "Other", "count": 0},
        ],
    }


def _resolve_window(date_from: str | None, date_to: str | None) -> tuple[str, str]:
    """Validate or default to the last 30 days. Always returns two ISO
    date strings (date_from <= date_to)."""
    today = datetime.now(UTC).date()
    df = (
        date_from
        if date_from and is_iso_date(date_from)
        else (today - timedelta(days=_DEFAULT_WINDOW_DAYS)).isoformat()
    )
    dt = date_to if date_to and is_iso_date(date_to) else today.isoformat()
    if df > dt:
        df, dt = dt, df
    return df, dt


async def fetch_query_analytics(
    session: AsyncSession,
    *,
    brand_id: int | None,
    date_from: str | None,
    date_to: str | None,
    engine: str | None,
) -> dict[str, Any]:
    df, dt = _resolve_window(date_from, date_to)

    if not await _table_exists(session, "queries") or brand_id is None:
        return _empty_result(brand_id=brand_id, date_from=df, date_to=dt, engine=engine)

    has_llm_responses = await _table_exists(session, "llm_responses")
    has_response_analyses = await _table_exists(session, "response_analyses")
    has_brand_mentions = await _table_exists(session, "brand_mentions")
    has_prompts = await _table_exists(session, "prompts")
    has_topics = await _table_exists(session, "topics")

    base_where = "q.brand_id = :brand_id AND q.created_at::date BETWEEN :df AND :dt"
    params: dict[str, Any] = {"brand_id": int(brand_id), "df": df, "dt": dt}
    if engine:
        base_where += " AND q.target_llm = :engine"
        params["engine"] = engine

    # ── totals ──────────────────────────────────────────────────────────
    total_queries_row = (
        await session.execute(
            text(f"SELECT COUNT(*) FROM queries q WHERE {base_where}"),
            params,
        )
    ).first()
    total_queries = int((total_queries_row or [0])[0] or 0)

    total_responses = 0
    total_analyzed = 0
    if has_llm_responses:
        total_responses = int(
            (
                await session.execute(
                    text(
                        f"""
                        SELECT COUNT(*) FROM queries q
                        JOIN llm_responses r ON r.query_id = q.id
                        WHERE {base_where}
                        """
                    ),
                    params,
                )
            ).scalar()
            or 0
        )
        if has_response_analyses:
            total_analyzed = int(
                (
                    await session.execute(
                        text(
                            f"""
                            SELECT COUNT(*) FROM queries q
                            JOIN llm_responses r ON r.query_id = q.id
                            JOIN response_analyses ra ON ra.response_id = r.id
                            WHERE {base_where}
                            """
                        ),
                        params,
                    )
                ).scalar()
                or 0
            )

    total_mentions_target = 0
    if has_brand_mentions and has_llm_responses:
        total_mentions_target = int(
            (
                await session.execute(
                    text(
                        f"""
                        SELECT COUNT(*) FROM queries q
                        JOIN llm_responses r ON r.query_id = q.id
                        JOIN brand_mentions bm
                          ON bm.response_id = r.id AND bm.brand_id = q.brand_id
                        WHERE {base_where}
                        """
                    ),
                    params,
                )
            ).scalar()
            or 0
        )

    # ── by_status ───────────────────────────────────────────────────────
    by_status_rows = (
        (
            await session.execute(
                text(
                    f"""
                SELECT LOWER(q.status) AS status, COUNT(*) AS cnt
                FROM queries q WHERE {base_where}
                GROUP BY LOWER(q.status)
                """
                ),
                params,
            )
        )
        .mappings()
        .all()
    )
    by_status: dict[str, int] = {"done": 0, "failed": 0, "pending": 0, "running": 0}
    for row in by_status_rows:
        s = (row.get("status") or "").lower()
        if s in by_status:
            by_status[s] += int(row.get("cnt") or 0)

    # ── by_engine ───────────────────────────────────────────────────────
    by_engine: list[dict[str, Any]] = []
    if has_llm_responses and has_response_analyses and has_brand_mentions:
        rows = (
            (
                await session.execute(
                    text(
                        f"""
                    SELECT
                        q.target_llm AS engine,
                        COUNT(DISTINCT q.id) AS queries,
                        COUNT(DISTINCT bm.id)::float
                          / NULLIF(COUNT(DISTINCT q.id), 0) AS mention_rate,
                        AVG(ra.sentiment_score) AS avg_sentiment,
                        AVG(bm.position_rank) AS avg_position_rank,
                        AVG(ra.geo_score) AS avg_geo_score
                    FROM queries q
                    LEFT JOIN llm_responses r ON r.query_id = q.id
                    LEFT JOIN response_analyses ra ON ra.response_id = r.id
                    LEFT JOIN brand_mentions bm
                      ON bm.response_id = r.id AND bm.brand_id = q.brand_id
                    WHERE {base_where}
                    GROUP BY q.target_llm
                    ORDER BY queries DESC
                    """
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        by_engine = [
            {
                "engine": (r.get("engine") or "unknown"),
                "queries": int(r.get("queries") or 0),
                "mention_rate": _round(r.get("mention_rate"), 4),
                "avg_sentiment": _round(r.get("avg_sentiment"), 4),
                "avg_position_rank": _round(r.get("avg_position_rank"), 2),
                "avg_geo_score": _round(r.get("avg_geo_score"), 4),
            }
            for r in rows
        ]
    else:
        rows = (
            (
                await session.execute(
                    text(
                        f"""
                    SELECT q.target_llm AS engine, COUNT(*) AS queries
                    FROM queries q WHERE {base_where}
                    GROUP BY q.target_llm ORDER BY queries DESC
                    """
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        by_engine = [
            {
                "engine": (r.get("engine") or "unknown"),
                "queries": int(r.get("queries") or 0),
                "mention_rate": None,
                "avg_sentiment": None,
                "avg_position_rank": None,
                "avg_geo_score": None,
            }
            for r in rows
        ]

    # ── daily_trend ─────────────────────────────────────────────────────
    mention_select = (
        ", COUNT(DISTINCT bm.id)::float / NULLIF(COUNT(DISTINCT q.id), 0) AS mention_rate"
        if has_brand_mentions and has_llm_responses
        else ""
    )
    sentiment_select = (
        ", AVG(ra.sentiment_score) AS avg_sentiment"
        if has_response_analyses and has_llm_responses
        else ""
    )
    geo_select = (
        ", AVG(ra.geo_score) AS avg_geo_score"
        if has_response_analyses and has_llm_responses
        else ""
    )
    join_responses = "LEFT JOIN llm_responses r ON r.query_id = q.id" if has_llm_responses else ""
    join_analyses = (
        "LEFT JOIN response_analyses ra ON ra.response_id = r.id"
        if has_response_analyses and has_llm_responses
        else ""
    )
    join_mentions = (
        "LEFT JOIN brand_mentions bm ON bm.response_id = r.id AND bm.brand_id = q.brand_id"
        if has_brand_mentions and has_llm_responses
        else ""
    )
    daily_rows = (
        (
            await session.execute(
                text(
                    f"""
                SELECT
                    q.created_at::date AS day,
                    COUNT(DISTINCT q.id) AS queries
                    {mention_select}
                    {sentiment_select}
                    {geo_select}
                FROM queries q
                {join_responses}
                {join_analyses}
                {join_mentions}
                WHERE {base_where}
                GROUP BY q.created_at::date
                ORDER BY q.created_at::date
                """
                ),
                params,
            )
        )
        .mappings()
        .all()
    )
    daily_trend = [
        {
            "date": str(r["day"]),
            "queries": int(r.get("queries") or 0),
            "mention_rate": _round(r.get("mention_rate"), 4),
            "avg_sentiment": _round(r.get("avg_sentiment"), 4),
            "avg_geo_score": _round(r.get("avg_geo_score"), 4),
        }
        for r in daily_rows
    ]

    # ── by_topic (top 10) ───────────────────────────────────────────────
    by_topic: list[dict[str, Any]] = []
    if has_prompts and has_topics:
        topic_rows = (
            (
                await session.execute(
                    text(
                        f"""
                    SELECT
                        t.id AS topic_id,
                        t.text AS topic_text,
                        COUNT(DISTINCT q.id) AS queries
                        {mention_select}
                        {sentiment_select}
                        {geo_select}
                    FROM queries q
                    JOIN prompts pr ON pr.id = q.prompt_id
                    JOIN topics t ON t.id = pr.topic_id
                    {join_responses}
                    {join_analyses}
                    {join_mentions}
                    WHERE {base_where}
                    GROUP BY t.id, t.text
                    ORDER BY queries DESC
                    LIMIT 10
                    """
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        by_topic = [
            {
                "topic_id": int(r["topic_id"]),
                "topic_text": (r.get("topic_text") or ""),
                "queries": int(r.get("queries") or 0),
                "mention_rate": _round(r.get("mention_rate"), 4),
                "avg_sentiment": _round(r.get("avg_sentiment"), 4),
                "avg_geo_score": _round(r.get("avg_geo_score"), 4),
            }
            for r in topic_rows
        ]

    # ── sentiment_distribution ─────────────────────────────────────────
    sentiment_distribution = {"positive": 0, "neutral": 0, "negative": 0}
    if has_brand_mentions and has_llm_responses:
        sent_rows = (
            (
                await session.execute(
                    text(
                        f"""
                    SELECT bm.sentiment, COUNT(*) AS cnt
                    FROM queries q
                    JOIN llm_responses r ON r.query_id = q.id
                    JOIN brand_mentions bm
                      ON bm.response_id = r.id AND bm.brand_id = q.brand_id
                    WHERE {base_where}
                    GROUP BY bm.sentiment
                    """
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        for row in sent_rows:
            label = (row.get("sentiment") or "neutral").lower()
            if label in sentiment_distribution:
                sentiment_distribution[label] += int(row.get("cnt") or 0)

    # ── position_distribution ──────────────────────────────────────────
    position_buckets = {"Top1": 0, "Top3": 0, "Top5": 0, "Top10": 0, "Other": 0}
    if has_brand_mentions and has_llm_responses:
        pos_rows = (
            (
                await session.execute(
                    text(
                        f"""
                    SELECT
                        CASE
                            WHEN bm.position_rank = 1 THEN 'Top1'
                            WHEN bm.position_rank <= 3 THEN 'Top3'
                            WHEN bm.position_rank <= 5 THEN 'Top5'
                            WHEN bm.position_rank <= 10 THEN 'Top10'
                            ELSE 'Other'
                        END AS bucket,
                        COUNT(*) AS cnt
                    FROM queries q
                    JOIN llm_responses r ON r.query_id = q.id
                    JOIN brand_mentions bm
                      ON bm.response_id = r.id AND bm.brand_id = q.brand_id
                    WHERE {base_where} AND bm.position_rank IS NOT NULL
                    GROUP BY bucket
                    """
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        for row in pos_rows:
            bucket = row.get("bucket")
            if bucket in position_buckets:
                position_buckets[bucket] += int(row.get("cnt") or 0)
    position_distribution = [
        {"bucket": k, "count": position_buckets[k]}
        for k in ("Top1", "Top3", "Top5", "Top10", "Other")
    ]

    return {
        "filters": {
            "brand_id": int(brand_id),
            "date_from": df,
            "date_to": dt,
            "engine": engine,
        },
        "totals": {
            "queries": total_queries,
            "responses": total_responses,
            "analyzed": total_analyzed,
            "mentions_target": total_mentions_target,
        },
        "by_status": by_status,
        "by_engine": by_engine,
        "daily_trend": daily_trend,
        "by_topic": by_topic,
        "sentiment_distribution": sentiment_distribution,
        "position_distribution": position_distribution,
    }


def _round(value: Any, digits: int) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


__all__ = ["fetch_query_analytics"]
