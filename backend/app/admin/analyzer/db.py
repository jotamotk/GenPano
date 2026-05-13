"""DB operations for the analyzer API (Phase 9 slice 9c).

All upstream tables (llm_responses / response_analyses / brand_mentions /
sentiment_drivers / citation_sources / product_feature_mentions /
geo_score_daily) are admin_console-era schemas not in genpano_models
(ADR-002). Defensive ``_table_exists`` probes degrade gracefully on
sqlite test fixtures.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from genpano_models import AnalyzerBatch, AnalyzerBatchItem, AnalyzerRun
from sqlalchemy import bindparam, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.analyzer.lib import BatchPreviewRows
from app.admin.queries.lib import split_pending_status
from app.db import _upstream_stubs

logger = logging.getLogger(__name__)
# Keep analyzer ORM ForeignKey metadata resolvable in production imports, matching tests.
_UPSTREAM_STUBS_REGISTERED = _upstream_stubs.UPSTREAM_STUB_NAMES
BATCH_DRY_RUN_QUERY_LIMIT = 5000
ACTIVE_ANALYZER_RUN_STATUSES = {"queued", "running"}
ACTIVE_ANALYZER_BATCH_STATUSES = {"queued", "running"}
ANALYZER_RUN_DISPATCH_CLAIM_TIMEOUT_SECONDS = 300
REQUIRED_ANALYZER_RUN_SUBMIT_INDEXES = {
    "uq_analyzer_runs_response_idempotency",
    "uq_analyzer_runs_active_response",
}
REQUIRED_ANALYZER_BATCH_SUBMIT_INDEXES = {"uq_analyzer_batches_idempotency"}
REQUIRED_ANALYZER_RUN_SUBMIT_COLUMNS = {
    "id",
    "response_id",
    "schema_version",
    "status",
    "trigger_source",
    "idempotency_key",
    "task_id",
    "batch_id",
    "batch_item_id",
    "validator_summary_json",
    "started_at",
    "completed_at",
    "failure_code",
    "failure_message",
    "dispatch_claim_token",
    "dispatch_claimed_at",
}
REQUIRED_ANALYZER_BATCH_COLUMNS = {
    "batch_id",
    "mode",
    "status",
    "trigger_source",
    "idempotency_key",
    "dry_run_id",
    "request_json",
    "preview_json",
    "submitted_response_ids_json",
    "skipped_counts_json",
    "skipped_reasons_json",
    "submitted_count",
    "skipped_count",
    "created_by",
    "reason",
    "created_at",
    "updated_at",
    "completed_at",
}
REQUIRED_ANALYZER_BATCH_ITEM_COLUMNS = {
    "id",
    "batch_id",
    "response_id",
    "query_id",
    "run_id",
    "task_id",
    "status",
    "skipped_reason",
    "detail_json",
    "created_at",
    "updated_at",
}


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def analyzer_single_submit_ready(session: AsyncSession) -> bool:
    if not await _table_exists(session, "analyzer_runs"):
        return False
    columns = await _table_columns(session, "analyzer_runs")
    if not REQUIRED_ANALYZER_RUN_SUBMIT_COLUMNS.issubset(columns):
        return False
    return await _submit_unique_indexes_ready(session, REQUIRED_ANALYZER_RUN_SUBMIT_INDEXES)


async def analyzer_batch_submit_ready(session: AsyncSession) -> bool:
    if not await analyzer_single_submit_ready(session):
        return False
    if not await _table_exists(session, "analyzer_batches"):
        return False
    if not await _table_exists(session, "analyzer_batch_items"):
        return False
    batch_columns = await _table_columns(session, "analyzer_batches")
    item_columns = await _table_columns(session, "analyzer_batch_items")
    if not REQUIRED_ANALYZER_BATCH_COLUMNS.issubset(
        batch_columns
    ) or not REQUIRED_ANALYZER_BATCH_ITEM_COLUMNS.issubset(item_columns):
        return False
    return await _submit_unique_indexes_ready(session, REQUIRED_ANALYZER_BATCH_SUBMIT_INDEXES)


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
        if row is not None:
            return True
    except Exception:
        pass
    try:
        row = (
            await session.execute(
                text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:n LIMIT 1"),
                {"n": name},
            )
        ).first()
    except Exception:
        return False
    return row is not None


async def _table_columns(session: AsyncSession, name: str) -> set[str]:
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
        if rows:
            return {str(r[0]) for r in rows}
    except Exception:
        pass
    if not name.replace("_", "").isalnum():
        return set()
    try:
        rows = (await session.execute(text(f"PRAGMA table_info({name})"))).all()
    except Exception:
        return set()
    return {str(r[1]) for r in rows}


async def _submit_unique_indexes_ready(
    session: AsyncSession,
    required_indexes: set[str],
) -> bool:
    if not required_indexes:
        return True
    try:
        dialect_name = session.get_bind().dialect.name
    except Exception:
        return False
    if dialect_name != "postgresql":
        return True
    sql = text(
        "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND indexname IN :index_names"
    ).bindparams(bindparam("index_names", expanding=True))
    try:
        rows = (await session.execute(sql, {"index_names": sorted(required_indexes)})).all()
    except Exception:
        return False
    present = {str(row[0]) for row in rows}
    return required_indexes.issubset(present)


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


async def fetch_response_analyzer_status(
    session: AsyncSession, response_id: int
) -> dict[str, Any] | None:
    if not await _table_exists(session, "llm_responses"):
        return None
    has_response_analyses = await _table_exists(session, "response_analyses")
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
        "ra.id AS analysis_id, ra.analyzer_model, ra.analyzed_at AS analysis_analyzed_at"
        if has_response_analyses
        else "NULL AS analysis_id, NULL AS analyzer_model, NULL AS analysis_analyzed_at"
    )
    analysis_join = (
        "LEFT JOIN response_analyses ra ON ra.response_id = lr.id" if has_response_analyses else ""
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
            NULL AS analyzer_run_id,
            NULL AS analysis_schema_version,
            NULL AS analyzer_run_status,
            NULL AS run_model,
            NULL AS analyzer_run_started_at,
            NULL AS analyzer_run_completed_at,
            NULL AS analysis_error_code,
            NULL AS analysis_error_message,
            NULL AS task_id,
            NULL AS batch_id,
            NULL AS validator_summary_json,
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
                        WHERE ar.response_id = lr.id
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
            aqf.quality_flags
        """
        if has_analyzer_runs and has_analyzer_quality_flags
        else """
            0 AS quality_flag_count,
            0 AS blocking_quality_flag_count,
            NULL AS quality_flags
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
                                        'blocks_metric_readiness',
                                            aqf.blocks_metric_readiness
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
    row = (
        (
            await session.execute(
                text(
                    f"""
                    SELECT
                        lr.id AS response_id,
                        lr.query_id,
                        lr.raw_text,
                        lr.analysis_status,
                        lr.analyzed_at,
                        q.status AS attempt_status,
                        {analysis_select},
                        {latest_run_select}
                        {quality_flags_select}
                    FROM llm_responses lr
                    LEFT JOIN queries q ON q.id = lr.query_id
                    {analysis_join}
                    {latest_run_join}
                    {quality_flags_join}
                    WHERE lr.id = :response_id
                    """
                ),
                {"response_id": int(response_id)},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        return None
    item = dict(row)
    item["analyzed_at"] = _isoformat(item.get("analysis_analyzed_at") or item.get("analyzed_at"))
    item.pop("analysis_analyzed_at", None)
    return item


async def preview_batch_analyzer_candidates(
    session: AsyncSession,
    *,
    scope: dict[str, Any],
) -> BatchPreviewRows:
    if not await _table_exists(session, "queries"):
        return BatchPreviewRows([])

    has_responses = await _table_exists(session, "llm_responses")
    if not has_responses:
        return BatchPreviewRows([])

    response_cols = await _table_columns(session, "llm_responses")
    has_response_analyses = await _table_exists(session, "response_analyses")
    has_analyzer_runs = await _table_exists(session, "analyzer_runs")

    scope_conditions: list[str] = []
    filter_conditions: list[str] = []
    params: dict[str, Any] = {}
    bindparams: list[Any] = []

    response_ids = [int(v) for v in scope.get("response_ids") or []]
    if response_ids:
        scope_conditions.append("lr.id IN :response_ids")
        params["response_ids"] = tuple(set(response_ids))
        bindparams.append(bindparam("response_ids", expanding=True))

    query_ids = [int(v) for v in scope.get("query_ids") or []]
    if query_ids:
        scope_conditions.append("q.id IN :query_ids")
        params["query_ids"] = tuple(set(query_ids))
        bindparams.append(bindparam("query_ids", expanding=True))

    filters = dict(scope.get("filters") or {})
    if filters.get("brand_id") is not None:
        filter_conditions.append("q.brand_id = :brand_id")
        params["brand_id"] = int(filters["brand_id"])
    if filters.get("topic_id") is not None:
        filter_conditions.append(
            "q.prompt_id IN (SELECT id FROM prompts WHERE topic_id = :topic_id)"
        )
        params["topic_id"] = int(filters["topic_id"])
    if filters.get("prompt_id") is not None:
        filter_conditions.append("q.prompt_id = :prompt_id")
        params["prompt_id"] = int(filters["prompt_id"])
    if filters.get("llm"):
        filter_conditions.append("q.target_llm = :llm")
        params["llm"] = filters["llm"]
    if filters.get("attempt_status"):
        special = split_pending_status(filters["attempt_status"])
        if special == "unqueued":
            filter_conditions.append("LOWER(q.status) = 'pending' AND q.queued_at IS NULL")
        elif special == "queued":
            filter_conditions.append("LOWER(q.status) = 'pending' AND q.queued_at IS NOT NULL")
        else:
            filter_conditions.append("LOWER(q.status) = :attempt_status")
            params["attempt_status"] = filters["attempt_status"]
    if filters.get("analysis_status"):
        if filters["analysis_status"] == "missing":
            if has_response_analyses:
                filter_conditions.append("(lr.id IS NULL OR ra.id IS NULL)")
            else:
                filter_conditions.append("1=1")
        else:
            filter_conditions.append(
                "LOWER(COALESCE(lr.analysis_status, 'missing')) = :analysis_status"
            )
            params["analysis_status"] = filters["analysis_status"]
    if filters.get("date"):
        filter_conditions.append("q.created_at::date = :date_filter")
        params["date_filter"] = filters["date"]
    if filters.get("date_from"):
        filter_conditions.append("q.created_at::date >= :date_from")
        params["date_from"] = filters["date_from"]
    if filters.get("date_to"):
        filter_conditions.append("q.created_at::date <= :date_to")
        params["date_to"] = filters["date_to"]
    if filters.get("q"):
        filter_conditions.append("q.query_text ILIKE :prompt_q")
        params["prompt_q"] = f"%{filters['q']}%"

    if filter_conditions:
        scope_conditions.append("(" + " AND ".join(filter_conditions) + ")")
    where_clause = " OR ".join(f"({condition})" for condition in scope_conditions) or "1=0"
    analyzed_at_select = "lr.analyzed_at" if "analyzed_at" in response_cols else "NULL"
    analysis_select = (
        "ra.id AS analysis_id, ra.analyzer_model, ra.analyzed_at AS analysis_analyzed_at"
        if has_response_analyses
        else "NULL AS analysis_id, NULL AS analyzer_model, NULL AS analysis_analyzed_at"
    )
    analysis_join = (
        "LEFT JOIN response_analyses ra ON ra.response_id = lr.id" if has_response_analyses else ""
    )
    latest_run_select = (
        "ar.analyzer_run_status," if has_analyzer_runs else "NULL AS analyzer_run_status,"
    )
    latest_run_join = (
        """
        LEFT JOIN LATERAL (
            SELECT ar.status AS analyzer_run_status
            FROM analyzer_runs ar
            WHERE ar.response_id = lr.id
            ORDER BY ar.started_at DESC NULLS LAST, ar.id DESC
            LIMIT 1
        ) ar ON TRUE
        """
        if has_analyzer_runs
        else ""
    )
    sentinel_limit = BATCH_DRY_RUN_QUERY_LIMIT + 1
    sql = text(
        f"""
        SELECT
            q.id AS query_id,
            q.status AS attempt_status,
            q.target_llm,
            q.brand_id,
            lr.id AS response_id,
            lr.raw_text,
            lr.analysis_status,
            {analyzed_at_select} AS analyzed_at,
            {latest_run_select}
            {analysis_select}
        FROM queries q
        LEFT JOIN llm_responses lr ON lr.query_id = q.id
        {analysis_join}
        {latest_run_join}
        WHERE {where_clause}
        ORDER BY q.id DESC, lr.id DESC
        LIMIT {sentinel_limit}
        """
    )
    if bindparams:
        sql = sql.bindparams(*bindparams)
    rows = (await session.execute(sql, params)).mappings().all()
    query_truncated = len(rows) > BATCH_DRY_RUN_QUERY_LIMIT
    out: list[dict[str, Any]] = []
    for row in rows[:BATCH_DRY_RUN_QUERY_LIMIT]:
        item = dict(row)
        item["analyzed_at"] = _isoformat(
            item.get("analysis_analyzed_at") or item.get("analyzed_at")
        )
        item.pop("analysis_analyzed_at", None)
        out.append(item)
    return BatchPreviewRows(
        out,
        query_truncated=query_truncated,
        query_limit=BATCH_DRY_RUN_QUERY_LIMIT,
    )


def _run_payload(run: AnalyzerRun, *, idempotent: bool) -> dict[str, Any]:
    return {
        "run_id": int(run.id),
        "response_id": int(run.response_id),
        "status": run.status,
        "task_id": run.task_id,
        "idempotent": idempotent,
        "previous_analysis_status": None,
        "batch_id": run.batch_id,
        "batch_item_id": run.batch_item_id,
        "failure_code": run.failure_code,
        "failure_message": run.failure_message,
    }


async def _find_existing_analyzer_run(
    session: AsyncSession,
    *,
    response_id: int,
    idempotency_key: str | None = None,
) -> tuple[AnalyzerRun | None, bool]:
    if idempotency_key:
        existing = (
            await session.execute(
                select(AnalyzerRun)
                .where(
                    AnalyzerRun.response_id == int(response_id),
                    AnalyzerRun.idempotency_key == idempotency_key,
                )
                .order_by(AnalyzerRun.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing, True

    active = (
        await session.execute(
            select(AnalyzerRun)
            .where(
                AnalyzerRun.response_id == int(response_id),
                AnalyzerRun.status.in_(ACTIVE_ANALYZER_RUN_STATUSES),
            )
            .order_by(AnalyzerRun.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return active, active is not None


async def _set_response_analysis_status(
    session: AsyncSession,
    response_id: int,
    status: str,
) -> None:
    columns = await _table_columns(session, "llm_responses")
    if "analysis_status" not in columns:
        return
    await session.execute(
        text("UPDATE llm_responses SET analysis_status = :status WHERE id = :response_id"),
        {"status": status, "response_id": int(response_id)},
    )


async def create_or_get_queued_analyzer_run(
    session: AsyncSession,
    *,
    response_id: int,
    mode: str,
    trigger_source: str,
    previous_analysis_status: str | None,
    idempotency_key: str | None = None,
    batch_id: str | None = None,
    batch_item_id: int | None = None,
) -> dict[str, Any]:
    for attempt in range(2):
        existing, is_idempotent = await _find_existing_analyzer_run(
            session,
            response_id=response_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            payload = _run_payload(existing, idempotent=is_idempotent)
            payload["previous_analysis_status"] = previous_analysis_status
            return payload

        run = AnalyzerRun(
            response_id=int(response_id),
            schema_version="analyzer_v4",
            status="queued",
            trigger_source=trigger_source,
            idempotency_key=idempotency_key,
            batch_id=batch_id,
            batch_item_id=batch_item_id,
            started_at=_utcnow_naive(),
            validator_summary_json={"mode": mode, "queued_by": trigger_source},
        )
        session.add(run)
        try:
            await session.flush()
            if str(previous_analysis_status or "").lower() != "done":
                await _set_response_analysis_status(session, response_id, "queued")
            await session.commit()
        except IntegrityError:
            await session.rollback()
            if attempt == 0:
                continue
            raise
        await session.refresh(run)
        payload = _run_payload(run, idempotent=False)
        payload["previous_analysis_status"] = previous_analysis_status
        return payload

    raise RuntimeError("failed to create or retrieve analyzer run")


async def claim_analyzer_run_for_dispatch(
    session: AsyncSession,
    *,
    run_id: int,
) -> dict[str, Any]:
    now = _utcnow_naive()
    cutoff = now - timedelta(seconds=ANALYZER_RUN_DISPATCH_CLAIM_TIMEOUT_SECONDS)
    claim_token = f"claim_{uuid.uuid4().hex[:24]}"
    result = await session.execute(
        update(AnalyzerRun)
        .where(
            AnalyzerRun.id == int(run_id),
            AnalyzerRun.status == "queued",
            AnalyzerRun.task_id.is_(None),
            or_(
                AnalyzerRun.dispatch_claim_token.is_(None),
                AnalyzerRun.dispatch_claimed_at.is_(None),
                AnalyzerRun.dispatch_claimed_at < cutoff,
            ),
        )
        .values(dispatch_claim_token=claim_token, dispatch_claimed_at=now)
    )
    await session.commit()
    if int(getattr(result, "rowcount", 0) or 0) == 1:
        return {"claimed": True, "claim_token": claim_token, "reason": "claimed"}

    run = await session.get(AnalyzerRun, int(run_id))
    if run is None:
        return {"claimed": False, "reason": "missing_run"}
    if run.status == "queued" and run.task_id is None and run.dispatch_claim_token:
        return {
            "claimed": False,
            "reason": "already_claimed",
            "status": run.status,
            "task_id": None,
        }
    return {
        "claimed": False,
        "reason": "not_claimable",
        "status": run.status,
        "task_id": run.task_id,
    }


async def mark_analyzer_run_enqueued(
    session: AsyncSession,
    *,
    run_id: int,
    task_id: str,
) -> None:
    await session.execute(
        update(AnalyzerRun)
        .where(AnalyzerRun.id == int(run_id))
        .values(
            task_id=task_id,
            status="queued",
            dispatch_claim_token=None,
            dispatch_claimed_at=None,
        )
    )
    await session.commit()


async def mark_analyzer_run_enqueue_failed(
    session: AsyncSession,
    *,
    run_id: int,
    previous_analysis_status: str | None,
    failure_message: str = "Analyzer task enqueue failed.",
) -> None:
    run = await session.get(AnalyzerRun, int(run_id))
    if run is None:
        return
    run.status = "failed"
    run.completed_at = _utcnow_naive()
    run.failure_code = "enqueue_failed"
    run.failure_message = failure_message
    run.dispatch_claim_token = None
    run.dispatch_claimed_at = None
    restore_status = "done" if str(previous_analysis_status or "").lower() == "done" else "failed"
    await _set_response_analysis_status(session, int(run.response_id), restore_status)
    await session.commit()


def _sum_skipped_counts(preview: dict[str, Any]) -> int:
    return sum(int(v or 0) for v in (preview.get("skipped_counts") or {}).values())


def _batch_payload(batch: AnalyzerBatch, items: list[AnalyzerBatchItem]) -> dict[str, Any]:
    item_payloads = [_batch_item_payload(item) for item in items]
    submitted_response_ids = [
        int(item.response_id)
        for item in items
        if item.response_id is not None and item.status != "skipped"
    ]
    accepted_response_ids = [
        int(item.response_id)
        for item in items
        if item.response_id is not None and item.status != "skipped" and item.task_id is not None
    ]
    failed_response_ids = [
        int(item.response_id)
        for item in items
        if item.response_id is not None and str(item.status or "").lower() == "failed"
    ]
    return {
        "success": True,
        "batch_id": batch.batch_id,
        "dry_run_id": batch.dry_run_id,
        "status": batch.status,
        "mode": batch.mode,
        "submitted_count": int(batch.submitted_count or 0),
        "accepted_count": len(accepted_response_ids),
        "skipped_count": int(batch.skipped_count or 0),
        "submitted_response_ids": submitted_response_ids,
        "accepted_response_ids": accepted_response_ids,
        "failed_response_ids": failed_response_ids,
        "items": item_payloads,
        "preview": batch.preview_json,
        "idempotent": False,
    }


def _batch_item_payload(item: AnalyzerBatchItem) -> dict[str, Any]:
    detail = item.detail_json if isinstance(item.detail_json, dict) else {}
    return {
        "item_id": int(item.id),
        "batch_id": item.batch_id,
        "response_id": item.response_id,
        "query_id": item.query_id,
        "run_id": item.run_id,
        "task_id": item.task_id,
        "status": item.status,
        "skipped_reason": item.skipped_reason,
        "previous_analysis_status": detail.get("previous_analysis_status"),
        "dispatch_required": bool(detail.get("dispatch_required", False)),
        "reused_active_run": bool(detail.get("reused_active_run", False)),
    }


async def _find_existing_batch(
    session: AsyncSession,
    *,
    idempotency_key: str | None,
    dry_run_id: str,
) -> AnalyzerBatch | None:
    if idempotency_key:
        conditions: list[Any] = [AnalyzerBatch.idempotency_key == idempotency_key]
    else:
        conditions = [
            AnalyzerBatch.status.in_(ACTIVE_ANALYZER_BATCH_STATUSES),
            AnalyzerBatch.dry_run_id == dry_run_id,
        ]
    return (
        await session.execute(
            select(AnalyzerBatch)
            .where(*conditions)
            .order_by(AnalyzerBatch.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def create_analyzer_batch_submission(
    session: AsyncSession,
    *,
    normalized: dict[str, Any],
    preview: dict[str, Any],
    operator_id: str | None,
) -> dict[str, Any]:
    dry_run_id = str(preview["dry_run_id"])
    for attempt in range(2):
        existing = await _find_existing_batch(
            session,
            idempotency_key=normalized.get("idempotency_key"),
            dry_run_id=dry_run_id,
        )
        if existing is not None:
            status = await fetch_analyzer_batch_status(session, existing.batch_id)
            if status is not None:
                status["idempotent"] = True
                return status
        try:
            return await _insert_analyzer_batch_submission(
                session,
                normalized=normalized,
                preview=preview,
                operator_id=operator_id,
                dry_run_id=dry_run_id,
            )
        except IntegrityError:
            await session.rollback()
            if attempt == 0:
                continue
            raise

    raise RuntimeError("failed to create or retrieve analyzer batch")


async def _insert_analyzer_batch_submission(
    session: AsyncSession,
    *,
    normalized: dict[str, Any],
    preview: dict[str, Any],
    operator_id: str | None,
    dry_run_id: str,
) -> dict[str, Any]:

    submitted_response_ids = [int(v) for v in preview.get("eligible_response_ids") or []]
    candidate_rows = list(preview.get("_candidate_rows") or [])
    stored_preview = {k: v for k, v in preview.items() if k != "_candidate_rows"}
    now = _utcnow_naive()
    batch = AnalyzerBatch(
        batch_id=f"anb_{uuid.uuid4().hex[:24]}",
        mode=str(normalized["mode"]),
        status="queued" if submitted_response_ids else "complete",
        trigger_source="admin_batch",
        idempotency_key=normalized.get("idempotency_key"),
        dry_run_id=dry_run_id,
        request_json=normalized,
        preview_json=stored_preview,
        submitted_response_ids_json=submitted_response_ids,
        skipped_counts_json=preview.get("skipped_counts") or {},
        skipped_reasons_json=preview.get("skipped_samples") or {},
        submitted_count=len(submitted_response_ids),
        skipped_count=_sum_skipped_counts(preview),
        created_by=operator_id,
        reason=normalized.get("reason"),
        created_at=now,
        updated_at=now,
        completed_at=None if submitted_response_ids else now,
    )
    session.add(batch)
    await session.flush()

    items: list[AnalyzerBatchItem] = []
    row_by_response_id = {
        int(row["response_id"]): row for row in candidate_rows if row.get("response_id") is not None
    }
    for response_id in submitted_response_ids:
        row = row_by_response_id.get(response_id, {})
        run, _ = await _find_existing_analyzer_run(session, response_id=response_id)
        created_run = False
        previous_analysis_status = row.get("analysis_status")
        if run is None:
            created_run = True
            run = AnalyzerRun(
                response_id=response_id,
                schema_version="analyzer_v4",
                status="queued",
                trigger_source="admin_batch",
                idempotency_key=f"{batch.batch_id}:{response_id}",
                batch_id=batch.batch_id,
                started_at=now,
                validator_summary_json={"mode": batch.mode, "queued_by": "admin_batch"},
            )
            session.add(run)
            await session.flush()
        reused_active_run = not created_run
        dispatch_required = created_run or (
            str(run.status or "").lower() == "queued" and not run.task_id
        )
        item = AnalyzerBatchItem(
            batch_id=batch.batch_id,
            response_id=response_id,
            query_id=row.get("query_id"),
            run_id=int(run.id),
            task_id=run.task_id,
            status=run.status or "queued",
            detail_json={
                "mode": batch.mode,
                "previous_analysis_status": previous_analysis_status,
                "dispatch_required": dispatch_required,
                "reused_active_run": reused_active_run,
            },
            created_at=now,
            updated_at=now,
        )
        session.add(item)
        await session.flush()
        if created_run:
            run.batch_id = batch.batch_id
            run.batch_item_id = int(item.id)
        items.append(item)

    skipped_seen: set[tuple[str, int | None]] = set()
    for reason, samples in (preview.get("skipped_samples") or {}).items():
        for sample in samples:
            raw_response_id = sample.get("response_id")
            skipped_response_id = (
                int(raw_response_id)
                if raw_response_id is not None and reason != "invalid_response_id"
                else None
            )
            key = (str(reason), skipped_response_id)
            if key in skipped_seen:
                continue
            skipped_seen.add(key)
            item = AnalyzerBatchItem(
                batch_id=batch.batch_id,
                response_id=skipped_response_id,
                query_id=sample.get("query_id"),
                status="skipped",
                skipped_reason=str(reason),
                detail_json=sample,
                created_at=now,
                updated_at=now,
            )
            session.add(item)
            items.append(item)

    await session.commit()
    for item in items:
        await session.refresh(item)
    await session.refresh(batch)
    return _batch_payload(batch, items)


async def mark_analyzer_batch_item_enqueued(
    session: AsyncSession,
    *,
    item_id: int,
    run_id: int,
    task_id: str,
) -> None:
    now = _utcnow_naive()
    await session.execute(
        update(AnalyzerBatchItem)
        .where(AnalyzerBatchItem.id == int(item_id))
        .values(task_id=task_id, status="queued", updated_at=now)
    )
    await session.execute(
        update(AnalyzerRun)
        .where(AnalyzerRun.id == int(run_id))
        .values(
            task_id=task_id,
            status="queued",
            dispatch_claim_token=None,
            dispatch_claimed_at=None,
        )
    )
    await session.commit()


async def mark_analyzer_batch_item_enqueue_failed(
    session: AsyncSession,
    *,
    item_id: int,
    run_id: int,
    previous_analysis_status: str | None = None,
    failure_message: str = "Analyzer task enqueue failed.",
) -> None:
    now = _utcnow_naive()
    await session.execute(
        update(AnalyzerBatchItem)
        .where(AnalyzerBatchItem.id == int(item_id))
        .values(status="failed", skipped_reason="enqueue_failed", updated_at=now)
    )
    await mark_analyzer_run_enqueue_failed(
        session,
        run_id=run_id,
        previous_analysis_status=previous_analysis_status,
        failure_message=failure_message,
    )


async def refresh_analyzer_batch_status(
    session: AsyncSession,
    batch_id: str,
) -> dict[str, Any] | None:
    batch = await session.get(AnalyzerBatch, batch_id)
    if batch is None:
        return None
    items = (
        (
            await session.execute(
                select(AnalyzerBatchItem)
                .where(AnalyzerBatchItem.batch_id == batch_id)
                .order_by(AnalyzerBatchItem.id)
            )
        )
        .scalars()
        .all()
    )
    run_ids = [int(item.run_id) for item in items if item.run_id is not None]
    runs: dict[int, AnalyzerRun] = {}
    if run_ids:
        run_rows = (
            (await session.execute(select(AnalyzerRun).where(AnalyzerRun.id.in_(run_ids))))
            .scalars()
            .all()
        )
        runs = {int(run.id): run for run in run_rows}

    submitted_items = [item for item in items if item.status != "skipped"]
    now = _utcnow_naive()
    running_count = 0
    queued_count = 0
    completed_count = 0
    failed_count = 0
    for item in submitted_items:
        run = runs.get(int(item.run_id or 0))
        status = str((run.status if run is not None else item.status) or "").lower()
        if run is not None:
            next_item_status = status or item.status
            if item.status != next_item_status or item.task_id != run.task_id:
                item.status = next_item_status
                item.task_id = run.task_id
                item.updated_at = now
        if status == "running":
            running_count += 1
        elif status == "queued":
            queued_count += 1
        elif status in {"done", "partial"}:
            completed_count += 1
        elif status == "failed":
            failed_count += 1

    if running_count:
        next_status = "running"
    elif queued_count:
        next_status = "queued"
    elif submitted_items and failed_count == len(submitted_items):
        next_status = "failed"
    elif submitted_items and failed_count:
        next_status = "partial"
    else:
        next_status = "complete"

    batch.status = next_status
    batch.updated_at = now
    if next_status in {"complete", "partial", "failed"} and batch.completed_at is None:
        batch.completed_at = now
    await session.commit()
    await session.refresh(batch)

    payload = _batch_payload(batch, list(items))
    payload.update(
        {
            "running_count": running_count,
            "queued_count": queued_count,
            "completed_count": completed_count,
            "failed_count": failed_count,
        }
    )
    return payload


async def fetch_analyzer_batch_status(
    session: AsyncSession,
    batch_id: str,
) -> dict[str, Any] | None:
    if not await analyzer_batch_submit_ready(session):
        return {
            "success": False,
            "error": "analyzer_batch_persistence_required",
            "batch_id": batch_id,
        }
    return await refresh_analyzer_batch_status(session, batch_id)


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
    "analyzer_batch_submit_ready",
    "analyzer_single_submit_ready",
    "claim_analyzer_run_for_dispatch",
    "create_analyzer_batch_submission",
    "create_or_get_queued_analyzer_run",
    "fetch_analyzer_batch_status",
    "fetch_analyzer_stats",
    "fetch_daily_scores",
    "fetch_response_analyzer_status",
    "fetch_response_detail",
    "list_brands",
    "list_distinct_llms",
    "list_responses",
    "mark_analyzer_batch_item_enqueue_failed",
    "mark_analyzer_batch_item_enqueued",
    "mark_analyzer_run_enqueue_failed",
    "mark_analyzer_run_enqueued",
    "preview_batch_analyzer_candidates",
    "refresh_analyzer_batch_status",
    "reset_response_for_rerun",
    "reset_responses_for_date",
]
