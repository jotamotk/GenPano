"""DB operations for the queries / stats API (Phase 9 slice 9a).

Both ``queries`` and ``llm_responses`` are admin_console-era tables not
in genpano_models (ADR-002). Defensive ``_table_exists`` probes return
empty / zero values when the tables aren't on the DB (sqlite tests).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.queries.lib import (
    is_iso_date,
    normalize_sort,
    split_pending_status,
)

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


def _analysis_summary(item: dict[str, Any]) -> dict[str, Any] | None:
    if item.get("analysis_id") is None:
        return None
    return {
        "geo_score": item.get("geo_score"),
        "visibility_score": item.get("visibility_score"),
        "sentiment_score": item.get("sentiment_score"),
        "sov_score": item.get("sov_score"),
        "citation_score": item.get("citation_score"),
        "total_brands_mentioned": item.get("total_brands_mentioned"),
        "target_brand_mentioned": item.get("target_brand_mentioned"),
        "target_brand_sentiment": item.get("target_brand_sentiment"),
        "mentions_count": item.get("mentions_count"),
        "citations_count": item.get("citations_count"),
        "features_count": item.get("features_count"),
    }


def _normalized_quality_flags(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    flags: list[dict[str, Any]] = []
    for raw in value:
        if isinstance(raw, dict):
            flags.append(raw)
    return flags


def _queue_state_from_run(status: Any) -> str | None:
    normalized = str(status or "").strip().lower()
    if normalized in {"queued", "running"}:
        return normalized
    if normalized in {"done", "partial"}:
        return "complete"
    if normalized == "failed":
        return "failed"
    return None


def _metric_readiness_status(
    *,
    quality_flag_count: Any,
    blocking_quality_flag_count: Any,
    analysis_id: Any,
) -> str | None:
    blocking_count = int(blocking_quality_flag_count or 0)
    flag_count = int(quality_flag_count or 0)
    if blocking_count > 0:
        return "blocked"
    if flag_count > 0:
        return "warning"
    if analysis_id is not None:
        return "ready"
    return None


def format_attempt_analysis_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize Attempts analyzer fields from currently available tables."""
    item = dict(row)
    raw_text = str(item.get("response") or item.get("raw_text") or "").strip()
    response_id = item.get("response_id")
    analysis_id = item.get("analysis_id")
    persisted_status = str(item.get("analysis_status") or "").strip().lower()
    latest_run_status = str(item.get("analyzer_run_status") or "").strip().lower()
    quality_flags = _normalized_quality_flags(item.get("quality_flags"))

    item.setdefault("analysis_id", None)
    item.setdefault("analyzer_model", None)
    item.setdefault("analyzed_at", None)
    item.setdefault("analysis_schema_version", None)
    item.setdefault("analyzer_run_id", None)
    item.setdefault("task_id", None)
    item.setdefault("analysis_error", None)
    item.setdefault("analysis_error_code", None)
    item.setdefault("analysis_error_message", None)
    item.setdefault("aggregation_refresh_status", None)
    item.setdefault("aggregation_refresh_task_id", None)
    item.setdefault("aggregation_refreshed_at", None)
    item.setdefault("metric_readiness_status", None)
    item.setdefault("metric_readiness_reasons", None)
    item.setdefault("analyzer_run_status", None)
    item.setdefault("quality_flag_count", 0)
    item.setdefault("blocking_quality_flag_count", 0)
    item["quality_flags"] = quality_flags
    if item.get("analyzer_model") is None and item.get("run_model") is not None:
        item["analyzer_model"] = item.get("run_model")
    if item.get("analyzed_at") is None and item.get("analyzer_run_completed_at") is not None:
        item["analyzed_at"] = _isoformat(item.get("analyzer_run_completed_at"))

    if response_id is None or not raw_text:
        item["analysis_status"] = "not_eligible"
        item["analysis_error_code"] = item.get("analysis_error_code") or "no_response_text"
        item["analysis_error_message"] = (
            item.get("analysis_error_message") or "No response text available for analyzer."
        )
    elif latest_run_status in {"queued", "running"}:
        item["analysis_status"] = latest_run_status
    elif persisted_status == "pending" and analysis_id is None:
        item["analysis_status"] = "missing"
    elif persisted_status:
        item["analysis_status"] = persisted_status
    else:
        item["analysis_status"] = "missing"

    if item.get("analysis_error") is None and item.get("analysis_error_message"):
        item["analysis_error"] = item.get("analysis_error_message")
    if item.get("metric_readiness_status") is None:
        item["metric_readiness_status"] = _metric_readiness_status(
            quality_flag_count=item.get("quality_flag_count"),
            blocking_quality_flag_count=item.get("blocking_quality_flag_count"),
            analysis_id=analysis_id,
        )
    if item.get("metric_readiness_reasons") is None:
        item["metric_readiness_reasons"] = quality_flags or None

    item["analysis_summary"] = _analysis_summary(item)
    item["analysis_task"] = {
        "latest_task_id": item.get("task_id"),
        "latest_run_id": item.get("analyzer_run_id"),
        "latest_batch_id": item.get("batch_id"),
        "queue_state": _queue_state_from_run(latest_run_status),
    }
    for ts_field in (
        "analyzed_at",
        "analyzer_run_started_at",
        "analyzer_run_completed_at",
        "aggregation_refreshed_at",
    ):
        if item.get(ts_field) is not None:
            item[ts_field] = _isoformat(item.get(ts_field))
    return item


async def fetch_status_stats(session: AsyncSession) -> dict[str, Any]:
    """Return ``{total, done, pending, running, failed}`` aggregated from
    ``queries.status``. Empty / zeroed when the table doesn't exist."""
    empty = {"total": 0, "done": 0, "pending": 0, "running": 0, "failed": 0}
    if not await _table_exists(session, "queries"):
        return empty
    sql = text(
        "SELECT UPPER(status) AS status, COUNT(*) AS count FROM queries GROUP BY UPPER(status)"
    )
    rows = (await session.execute(sql)).mappings().all()
    counts = {str(r.get("status") or ""): int(r.get("count") or 0) for r in rows}
    total = sum(counts.values())
    return {
        "total": total,
        "done": counts.get("DONE", 0),
        "pending": counts.get("PENDING", 0),
        "running": counts.get("RUNNING", 0),
        "failed": counts.get("FAILED", 0),
    }


async def list_queries(
    session: AsyncSession,
    *,
    llm: str | None = None,
    status: str | None = None,
    brand_id: int | None = None,
    topic_id: int | None = None,
    prompt_id: int | None = None,
    query_id: int | None = None,
    prompt_q: str | None = None,
    date_filter: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
    offset: int = 0,
    sort: str = "id_desc",
    include_count: bool = False,
) -> tuple[list[dict[str, Any]], int | None, dict[str, int] | None]:
    """Filtered list of queries with the joined wire shape admin.html
    expects. Returns ``(rows, total, by_status)`` where total/by_status
    are ``None`` when ``include_count`` is False (admin_console parity).

    Empty when ``queries`` table doesn't exist (sqlite test fixture).
    """
    if not await _table_exists(session, "queries"):
        return [], (0 if include_count else None), ({} if include_count else None)

    where: list[str] = []
    params: dict[str, Any] = {"limit": int(limit), "offset": int(offset)}

    if query_id is not None:
        where.append("q.id = :query_id")
        params["query_id"] = query_id
    if llm:
        where.append("q.target_llm = :llm")
        params["llm"] = llm
    if status:
        special = split_pending_status(status)
        if special == "unqueued":
            where.append("LOWER(q.status) = 'pending' AND q.queued_at IS NULL")
        elif special == "queued":
            where.append("LOWER(q.status) = 'pending' AND q.queued_at IS NOT NULL")
        else:
            where.append("UPPER(q.status) = UPPER(:status_filter)")
            params["status_filter"] = status
    if date_filter and is_iso_date(date_filter):
        where.append("q.created_at::date = :date_filter")
        params["date_filter"] = date_filter
    if date_from and is_iso_date(date_from):
        where.append("q.created_at::date >= :date_from")
        params["date_from"] = date_from
    if date_to and is_iso_date(date_to):
        where.append("q.created_at::date <= :date_to")
        params["date_to"] = date_to
    if brand_id is not None:
        where.append("q.brand_id = :brand_id")
        params["brand_id"] = brand_id
    if topic_id is not None:
        where.append("q.prompt_id IN (SELECT id FROM prompts WHERE topic_id = :topic_id)")
        params["topic_id"] = topic_id
    if prompt_id is not None:
        where.append("q.prompt_id = :prompt_id")
        params["prompt_id"] = prompt_id
    if prompt_q:
        where.append("q.query_text ILIKE :prompt_q")
        params["prompt_q"] = f"%{prompt_q}%"
    where_clause = " AND ".join(where) if where else "1=1"

    total: int | None = None
    by_status: dict[str, int] | None = None
    if include_count:
        cnt_row = (
            (
                await session.execute(
                    text(f"SELECT COUNT(*) AS cnt FROM queries q WHERE {where_clause}"),
                    params,
                )
            )
            .mappings()
            .first()
        )
        total = int((dict(cnt_row) if cnt_row else {}).get("cnt") or 0)

        status_rows = (
            (
                await session.execute(
                    text(
                        f"""
                    SELECT
                        CASE
                            WHEN LOWER(q.status) = 'pending' AND q.queued_at IS NULL
                                THEN 'unqueued'
                            WHEN LOWER(q.status) = 'pending' AND q.queued_at IS NOT NULL
                                THEN 'queued'
                            ELSE LOWER(q.status)
                        END AS st,
                        COUNT(*) AS cnt
                    FROM queries q WHERE {where_clause}
                    GROUP BY 1
                    """
                    ),
                    params,
                )
            )
            .mappings()
            .all()
        )
        by_status = {(r.get("st") or "unknown"): int(r.get("cnt") or 0) for r in status_rows}
        pending_legacy = by_status.get("unqueued", 0) + by_status.get("queued", 0)
        if pending_legacy:
            by_status["pending"] = pending_legacy

    has_response_analyses = await _table_exists(session, "response_analyses")
    has_brand_mentions = await _table_exists(session, "brand_mentions")
    has_citation_sources = await _table_exists(session, "citation_sources")
    has_product_feature_mentions = await _table_exists(session, "product_feature_mentions")
    has_analyzer_runs = await _table_exists(session, "analyzer_runs")
    analyzer_run_cols = (
        await _table_columns(session, "analyzer_runs") if has_analyzer_runs else set()
    )
    has_run_task_fields = {"task_id", "batch_id"}.issubset(analyzer_run_cols)
    has_analyzer_quality_flags = await _table_exists(session, "analyzer_quality_flags")
    latest_run_task_select = (
        """
            ar.task_id,
            ar.batch_id,
        """
        if has_run_task_fields
        else """
            NULL AS task_id,
            NULL AS batch_id,
        """
    )

    analysis_select = (
        """
            ra.id as analysis_id,
            ra.analyzer_model,
            ra.geo_score,
            ra.visibility_score,
            ra.sentiment_score,
            ra.sov_score,
            ra.citation_score,
            ra.total_brands_mentioned,
            ra.target_brand_mentioned,
            ra.target_brand_sentiment,
        """
        if has_response_analyses
        else """
            NULL as analysis_id,
            NULL as analyzer_model,
            NULL as geo_score,
            NULL as visibility_score,
            NULL as sentiment_score,
            NULL as sov_score,
            NULL as citation_score,
            NULL as total_brands_mentioned,
            NULL as target_brand_mentioned,
            NULL as target_brand_sentiment,
        """
    )
    analysis_join = (
        "LEFT JOIN response_analyses ra ON ra.response_id = r.id" if has_response_analyses else ""
    )
    mentions_count_select = (
        "(SELECT COUNT(*) FROM brand_mentions bm WHERE bm.response_id = r.id) as mentions_count,"
        if has_brand_mentions
        else "NULL as mentions_count,"
    )
    citations_count_select = (
        "(SELECT COUNT(*) FROM citation_sources cs WHERE cs.response_id = r.id) as citations_count,"
        if has_citation_sources
        else "NULL as citations_count,"
    )
    features_count_select = (
        """
            (SELECT COUNT(*)
             FROM product_feature_mentions pfm
             WHERE pfm.analysis_id = ra.id) as features_count,
        """
        if has_product_feature_mentions and has_response_analyses
        else "NULL as features_count,"
    )
    latest_run_select = (
        f"""
            ar.analyzer_run_id,
            ar.analysis_schema_version,
            ar.analyzer_run_status,
            ar.run_model,
            ar.analyzer_run_started_at,
            ar.analyzer_run_completed_at,
            ar.analysis_error_code,
            ar.analysis_error_message,
            {latest_run_task_select}
            ar.validator_summary_json,
        """
        if has_analyzer_runs
        else """
            NULL as analyzer_run_id,
            NULL as analysis_schema_version,
            NULL as analyzer_run_status,
            NULL as run_model,
            NULL as analyzer_run_started_at,
            NULL as analyzer_run_completed_at,
            NULL as analysis_error_code,
            NULL as analysis_error_message,
            NULL as task_id,
            NULL as batch_id,
            NULL as validator_summary_json,
        """
    )
    latest_run_join = (
        f"""
        LEFT JOIN LATERAL (
            SELECT
                ar.id AS analyzer_run_id,
                ar.schema_version AS analysis_schema_version,
                ar.status AS analyzer_run_status,
                ar.model AS run_model,
                ar.started_at AS analyzer_run_started_at,
                ar.completed_at AS analyzer_run_completed_at,
                ar.failure_code AS analysis_error_code,
                ar.failure_message AS analysis_error_message,
                {latest_run_task_select}
                ar.validator_summary_json
            FROM analyzer_runs ar
            WHERE ar.response_id = r.id
            ORDER BY ar.started_at DESC NULLS LAST, ar.id DESC
            LIMIT 1
        ) ar ON TRUE
        """
        if has_analyzer_runs
        else ""
    )
    quality_flags_select = (
        """
            aqf.quality_flag_count,
            aqf.blocking_quality_flag_count,
            aqf.quality_flags,
        """
        if has_analyzer_runs and has_analyzer_quality_flags
        else """
            0 as quality_flag_count,
            0 as blocking_quality_flag_count,
            NULL as quality_flags,
        """
    )
    quality_flags_join = (
        """
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*)::int AS quality_flag_count,
                COUNT(*) FILTER (
                    WHERE COALESCE(aqf.blocks_metric_readiness, FALSE)
                )::int AS blocking_quality_flag_count,
                COALESCE(
                    jsonb_agg(
                        jsonb_build_object(
                            'code', aqf.code,
                            'severity', aqf.severity,
                            'message', aqf.message,
                            'target_type', aqf.target_type,
                            'target_key', aqf.target_key,
                            'blocks_metric_readiness', aqf.blocks_metric_readiness
                        )
                        ORDER BY aqf.id
                    ) FILTER (WHERE aqf.id IS NOT NULL),
                    '[]'::jsonb
                ) AS quality_flags
            FROM analyzer_quality_flags aqf
            WHERE aqf.run_id = ar.analyzer_run_id
        ) aqf ON TRUE
        """
        if has_analyzer_runs and has_analyzer_quality_flags
        else ""
    )

    sql = text(
        f"""
        SELECT
            q.id,
            q.target_llm,
            q.status,
            q.query_text,
            q.brand_id,
            q.profile_id,
            q.account_id,
            q.created_at,
            q.executed_at,
            q.retry_count,
            q.queued_at,
            q.started_at,
            q.finished_at,
            q.latency_ms,
            q.retry_reason,
            q.prompt_id,
            pr.text as prompt_text,
            t.id as topic_id,
            t.text as topic_text,
            r.id as response_id,
            r.raw_text as response,
            r.analysis_status,
            r.analyzed_at,
            r.llm_version,
            r.citations_json as citations,
            {analysis_select}
            {mentions_count_select}
            {citations_count_select}
            {features_count_select}
            {latest_run_select}
            {quality_flags_select}
            p.name as profile_name,
            p.location as profile_location,
            p.country_code as profile_country,
            a.phone_number as account_label,
            a.llm_name as account_llm
        FROM queries q
        LEFT JOIN llm_responses r ON q.id = r.query_id
        {analysis_join}
        {latest_run_join}
        {quality_flags_join}
        LEFT JOIN profiles p ON q.profile_id::text = p.id::text
        LEFT JOIN llm_accounts a ON q.account_id = a.id
        LEFT JOIN prompts pr ON q.prompt_id = pr.id
        LEFT JOIN topics t ON pr.topic_id = t.id
        WHERE {where_clause}
        ORDER BY {normalize_sort(sort)}
        LIMIT :limit OFFSET :offset
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        for ts_field in (
            "created_at",
            "executed_at",
            "queued_at",
            "started_at",
            "finished_at",
            "analyzed_at",
        ):
            item[ts_field] = _isoformat(item.get(ts_field))
        item = format_attempt_analysis_fields(item)
        out.append(item)
    return out, total, by_status


# ── write paths (slice 9b) ──────────────────────────────────


async def _table_columns(session: AsyncSession, name: str) -> set[str]:
    """Return the set of column names for ``name``, or empty if missing.

    Mirrors the picker router helper. Used by ensure_default_prompt() to
    decide which optional columns (status / generated_by / created_at) to
    include in the INSERT — production tables have them, sqlite stubs may
    not, and we never assume.
    """
    try:
        rows = (
            await session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = :n"
                ),
                {"n": name},
            )
        ).all()
    except Exception:
        return set()
    return {r[0] for r in rows}


async def ensure_default_prompt(
    session: AsyncSession,
    *,
    brand_id: int | None,
    query_text: str,
) -> int | None:
    """Find or create a prompt row for the given (brand, query_text), so
    queries.prompt_id can be set non-NULL.

    Idempotent — re-runs return the same prompt id. Returns ``None`` when
    the upstream tables are unavailable (sqlite CI), brand_id is None, or
    schema doesn't have the columns we need (defensive — admin_console
    legacy schemas vary per deploy).

    Mirrors the Alembic backfill logic (Step 1 + Step 2): one
    ``category='legacy-import'`` topic per brand, one prompt per
    distinct (brand, query_text) under that topic.
    """
    if brand_id is None:
        return None
    if not (
        await _table_exists(session, "queries")
        and await _table_exists(session, "topics")
        and await _table_exists(session, "prompts")
    ):
        return None

    topic_cols = await _table_columns(session, "topics")
    prompt_cols = await _table_columns(session, "prompts")
    if not (
        {"brand_id", "text", "category"}.issubset(topic_cols)
        and {"topic_id", "text"}.issubset(prompt_cols)
    ):
        return None

    existing = (
        await session.execute(
            text(
                """
                SELECT pr.id FROM prompts pr
                JOIN topics t ON t.id = pr.topic_id
                WHERE t.brand_id = :brand_id
                  AND t.category = 'legacy-import'
                  AND pr.text = :query_text
                LIMIT 1
                """
            ),
            {"brand_id": brand_id, "query_text": query_text},
        )
    ).first()
    if existing is not None:
        return int(existing[0])

    topic_row = (
        await session.execute(
            text(
                "SELECT id FROM topics WHERE brand_id = :brand_id "
                "AND category = 'legacy-import' LIMIT 1"
            ),
            {"brand_id": brand_id},
        )
    ).first()
    if topic_row is None:
        topic_columns = ["brand_id", "text", "category"]
        topic_value_exprs = [":brand_id", "'未分类查询'", "'legacy-import'"]
        if "generated_by" in topic_cols:
            topic_columns.append("generated_by")
            topic_value_exprs.append("'backfill'")
        if "status" in topic_cols:
            topic_columns.append("status")
            topic_value_exprs.append("'active'")
        if "created_at" in topic_cols:
            topic_columns.append("created_at")
            topic_value_exprs.append("NOW()")
        topic_row = (
            await session.execute(
                text(
                    f"INSERT INTO topics ({', '.join(topic_columns)}) "
                    f"VALUES ({', '.join(topic_value_exprs)}) RETURNING id"
                ),
                {"brand_id": brand_id},
            )
        ).first()
        if topic_row is None:
            return None
    topic_id = int(topic_row[0])

    prompt_columns = ["topic_id", "text"]
    prompt_value_exprs = [":topic_id", ":query_text"]
    if "intent" in prompt_cols:
        prompt_columns.append("intent")
        prompt_value_exprs.append("'informational'")
    if "language" in prompt_cols:
        prompt_columns.append("language")
        prompt_value_exprs.append("'zh'")
    if "status" in prompt_cols:
        prompt_columns.append("status")
        prompt_value_exprs.append("'active'")
    if "generated_by" in prompt_cols:
        prompt_columns.append("generated_by")
        prompt_value_exprs.append("'backfill'")
    if "created_at" in prompt_cols:
        prompt_columns.append("created_at")
        prompt_value_exprs.append("NOW()")
    inserted = (
        await session.execute(
            text(
                f"INSERT INTO prompts ({', '.join(prompt_columns)}) "
                f"VALUES ({', '.join(prompt_value_exprs)}) RETURNING id"
            ),
            {"topic_id": topic_id, "query_text": query_text},
        )
    ).first()
    if inserted is None:
        return None
    return int(inserted[0])


async def create_query(
    session: AsyncSession,
    *,
    target_llm: str,
    query_text: str,
    brand_id: int | None,
    prompt_id: int | None = None,
) -> int | None:
    """INSERT a new pending query. Returns the new id; ``None`` when the
    queries table is missing (sqlite test path).

    When ``prompt_id`` is not supplied, calls ``ensure_default_prompt`` so
    the new row is linked to a real prompts/topics chain — keeps the admin
    "Query Attempts" filter dropdowns populated for queries created via
    the ad-hoc POST /api/queries path.
    """
    if not await _table_exists(session, "queries"):
        return None

    if prompt_id is None:
        prompt_id = await ensure_default_prompt(session, brand_id=brand_id, query_text=query_text)

    row = (
        (
            await session.execute(
                text(
                    """
                INSERT INTO queries
                    (target_llm, query_text, brand_id, prompt_id, status,
                     created_at, queued_at)
                VALUES (:target_llm, :query_text, :brand_id, :prompt_id,
                        'pending', NOW(), NOW())
                RETURNING id
                """
                ),
                {
                    "target_llm": target_llm,
                    "query_text": query_text,
                    "brand_id": brand_id,
                    "prompt_id": prompt_id,
                },
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    await session.commit()
    return int(dict(row)["id"])


async def retry_query(
    session: AsyncSession,
    *,
    query_id: int,
    retry_reason: str | None,
) -> dict[str, Any] | None:
    """Reset a single query to pending + bump retry_count + clear timing
    fields. Returns the (pre-update) target_llm so the caller can
    dispatch the new attempt to celery; ``None`` when the row is missing.
    """
    if not await _table_exists(session, "queries"):
        return None
    detail_row = (
        (
            await session.execute(
                text("SELECT id, target_llm, query_text, brand_id FROM queries WHERE id = :id"),
                {"id": query_id},
            )
        )
        .mappings()
        .first()
    )
    if not detail_row:
        return None
    await session.execute(
        text(
            """
            UPDATE queries
            SET status = 'pending',
                retry_count = COALESCE(retry_count, 0) + 1,
                queued_at = NOW(),
                started_at = NULL,
                finished_at = NULL,
                latency_ms = NULL,
                retry_reason = :retry_reason
            WHERE id = :id
            """
        ),
        {"retry_reason": retry_reason, "id": query_id},
    )
    await session.commit()
    return dict(detail_row)


async def batch_trigger_queries(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
) -> tuple[int, list[dict[str, Any]], bool]:
    """Bulk reset matching queries to pending and return dispatch items for
    celery dispatch. Returns ``(matched_total, dispatch_items, refused)``
    where ``refused`` is True when the matched count exceeds the
    operator-specified ``max`` cap (caller surfaces 400)."""
    if not await _table_exists(session, "queries"):
        return 0, [], False

    where: list[str] = []
    params: dict[str, Any] = {}
    if payload.get("ids"):
        where.append("id = ANY(:ids)")
        params["ids"] = payload["ids"]
    else:
        if "query_id" in payload:
            where.append("id = :query_id")
            params["query_id"] = payload["query_id"]
        if "llm" in payload:
            where.append("target_llm = :llm")
            params["llm"] = payload["llm"]
        if "status" in payload:
            where.append("UPPER(status) = UPPER(:status)")
            params["status"] = payload["status"]
        else:
            where.append("LOWER(status) IN ('pending','failed')")
        if "brand_id" in payload:
            where.append("brand_id = :brand_id")
            params["brand_id"] = payload["brand_id"]
        if "topic_id" in payload:
            where.append("prompt_id IN (SELECT id FROM prompts WHERE topic_id = :topic_id)")
            params["topic_id"] = payload["topic_id"]
        if "prompt_id" in payload:
            where.append("prompt_id = :prompt_id")
            params["prompt_id"] = payload["prompt_id"]
        if "prompt_q" in payload:
            where.append("query_text ILIKE :prompt_q")
            params["prompt_q"] = f"%{payload['prompt_q']}%"
    where_clause = " AND ".join(where) if where else "1=1"

    cnt_row = (
        (
            await session.execute(
                text(f"SELECT COUNT(*) AS n FROM queries WHERE {where_clause}"),
                params,
            )
        )
        .mappings()
        .first()
    )
    total = int((dict(cnt_row) if cnt_row else {}).get("n") or 0)

    if payload.get("dry_run"):
        return total, [], False
    if total == 0:
        return 0, [], False
    max_count = int(payload.get("max_count") or 2000)
    if total > max_count:
        return total, [], True

    update_params = {"reason": payload.get("reason") or "batch_trigger", **params}
    rows = (
        (
            await session.execute(
                text(
                    f"""
                UPDATE queries
                SET status = 'pending',
                    retry_count = COALESCE(retry_count, 0) + 1,
                    queued_at = NOW(),
                    started_at = NULL,
                    finished_at = NULL,
                    latency_ms = NULL,
                    retry_reason = :reason
                WHERE {where_clause}
                RETURNING id, target_llm
                """
                ),
                update_params,
            )
        )
        .mappings()
        .all()
    )
    dispatch_items = [{"id": int(r["id"]), "target_llm": r.get("target_llm")} for r in rows]
    await session.commit()
    return total, dispatch_items, False


async def cleanup_queries(
    session: AsyncSession,
    *,
    cleanup_type: str,
    days: int = 30,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Delete orphan queries by type. Returns ``(matched, deleted)``;
    when ``dry_run`` is True ``deleted`` is 0."""
    if not await _table_exists(session, "queries"):
        return 0, 0
    if cleanup_type == "unqueued":
        where_clause = "LOWER(status) = 'pending' AND queued_at IS NULL"
        params: dict[str, Any] = {}
    elif cleanup_type == "all_pending":
        where_clause = "LOWER(status) = 'pending'"
        params = {}
    elif cleanup_type == "failed_old":
        where_clause = (
            "LOWER(status) = 'failed' AND "
            "created_at < NOW() - (CAST(:days AS text) || ' days')::interval"
        )
        params = {"days": int(days)}
    else:
        return 0, 0

    cnt_row = (
        (
            await session.execute(
                text(f"SELECT COUNT(*) AS n FROM queries WHERE {where_clause}"), params
            )
        )
        .mappings()
        .first()
    )
    matched = int((dict(cnt_row) if cnt_row else {}).get("n") or 0)
    if dry_run:
        return matched, 0
    result = await session.execute(text(f"DELETE FROM queries WHERE {where_clause}"), params)
    deleted = int(getattr(result, "rowcount", 0) or 0)
    await session.commit()
    return matched, deleted


async def mark_query_failed(session: AsyncSession, query_id: int) -> bool:
    """Flip a done query to failed (used for retroactive QA flagging).
    Only changes rows currently in ``done`` status — admin_console parity."""
    if not await _table_exists(session, "queries"):
        return False
    result = await session.execute(
        text("UPDATE queries SET status = 'failed' WHERE id = :id AND status = 'done'"),
        {"id": query_id},
    )
    if (getattr(result, "rowcount", 0) or 0) == 0:
        await session.rollback()
        return False
    await session.commit()
    return True


__all__ = [
    "batch_trigger_queries",
    "cleanup_queries",
    "create_query",
    "ensure_default_prompt",
    "fetch_status_stats",
    "format_attempt_analysis_fields",
    "list_queries",
    "mark_query_failed",
    "retry_query",
]
