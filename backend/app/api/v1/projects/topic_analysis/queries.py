"""Query-side SQL builders for the topic-analysis subsystem.

Phase 5 of splitting `_topic_analysis_service.py` (Epic #885). Hosts the
big `_fact_rows` query builder (282 LOC) plus the per-query-column
helpers, scope conditions, and admin-chain probe used by it.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from genpano_models import Project
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects.topic_analysis.filters import (
    AnalysisFilters,
    _resolve_window,
    _row_matches_analysis_filters,
    _target_mention_condition,
    _text_scope_conditions,
)
from app.api.v1.projects.topic_analysis.legacy_schema import (
    _prompt_scope_expr,
    _prompt_tags_expr,
    _prompt_text_expr,
    _select_col,
    _topic_name_expr,
    legacy_table_columns,
    legacy_table_exists,
)
from app.api.v1.projects.topic_analysis.profiles import _brand_fact_terms

_PROJECT_BRAND = object()


def _dt_range(from_d: date, to_d: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(from_d, datetime.min.time()),
        datetime.combine(to_d, datetime.max.time()),
    )


def _success_status_condition(cols: set[str], alias: str = "q") -> str | None:
    if "status" not in cols:
        return None
    return f"LOWER(COALESCE({alias}.status, '')) IN ('done', 'success', 'completed')"


def _query_text_expr(cols: set[str]) -> str:
    if "query_text" in cols:
        return "q.query_text"
    if "text" in cols:
        return "q.text"
    return "NULL"


def _response_text_expr(cols: set[str]) -> str:
    if "raw_text" in cols:
        return "r.raw_text"
    if "response_text" in cols:
        return "r.response_text"
    if "text" in cols:
        return "r.text"
    return "NULL"


def _response_latest_order_sql(cols: set[str]) -> str:
    order = []
    if "created_at" in cols:
        order.extend(["r2.created_at IS NULL ASC", "r2.created_at DESC"])
    order.append("r2.id DESC")
    return ", ".join(order)


def _false_condition() -> str:
    return "1 = 0"


def _engine_conditions(
    filters: AnalysisFilters,
    query_cols: set[str],
    params: dict[str, Any],
) -> list[str]:
    if not filters.engines:
        return []
    if "target_llm" not in query_cols:
        return [_false_condition()]
    placeholders: list[str] = []
    for i, engine in enumerate(filters.engines):
        key = f"engine_{i}"
        placeholders.append(f":{key}")
        params[key] = engine
    return [f"q.target_llm IN ({', '.join(placeholders)})"]


async def _query_scope_conditions(
    session: AsyncSession,
    *,
    project: Project,
    filters: AnalysisFilters,
    query_cols: set[str],
    prefix: str = "q",
    brand_id: int | None | object = _PROJECT_BRAND,
) -> tuple[list[str], dict[str, Any]]:
    params: dict[str, Any] = {}
    conditions: list[str] = []

    scoped_brand_id: int | None
    if brand_id is _PROJECT_BRAND:
        scoped_brand_id = project.primary_brand_id
    elif isinstance(brand_id, int):
        scoped_brand_id = brand_id
    else:
        scoped_brand_id = None
    if scoped_brand_id is not None and "brand_id" in query_cols:
        conditions.append(f"{prefix}.brand_id = :primary_brand_id")
        params["primary_brand_id"] = int(scoped_brand_id)

    if filters.from_date is not None or filters.to_date is not None:
        if "created_at" not in query_cols:
            conditions.append(_false_condition())
        else:
            from_d, to_d = _resolve_window(filters)
            from_dt, to_dt = _dt_range(from_d, to_d)
            conditions.append(f"{prefix}.created_at >= :from_dt")
            conditions.append(f"{prefix}.created_at <= :to_dt")
            params["from_dt"] = from_dt
            params["to_dt"] = to_dt

    for cond in _engine_conditions(filters, query_cols, params):
        conditions.append(cond.replace("q.", f"{prefix}."))

    if filters.profile_id:
        if "profile_id" not in query_cols:
            conditions.append(_false_condition())
        else:
            conditions.append(
                f"({prefix}.profile_id IS NULL OR CAST({prefix}.profile_id AS TEXT) = :profile_id)"
            )
            params["profile_id"] = str(filters.profile_id)

    if filters.segment_id:
        profile_cols = await legacy_table_columns(session, "profiles")
        if not (
            "profile_id" in query_cols
            and await legacy_table_exists(session, "profiles")
            and {"id", "segment_id"}.issubset(profile_cols)
        ):
            conditions.append(_false_condition())
        else:
            conditions.append(
                "EXISTS ("
                "SELECT 1 FROM profiles pf "
                f"WHERE CAST(pf.id AS TEXT) = CAST({prefix}.profile_id AS TEXT) "
                "AND CAST(pf.segment_id AS TEXT) = :segment_id"
                ")"
            )
            params["segment_id"] = str(filters.segment_id)

    return conditions, params


async def _has_admin_chain(session: AsyncSession) -> bool:
    return all(
        [
            await legacy_table_exists(session, "topics"),
            await legacy_table_exists(session, "prompts"),
            await legacy_table_exists(session, "queries"),
        ]
    )


async def _fact_rows(
    session: AsyncSession,
    project: Project,
    *,
    filters: AnalysisFilters,
    topic_id: int | None = None,
    prompt_id: int | None = None,
    brand_id_override: int | None = None,
    successful_responses_only: bool = True,
) -> list[dict[str, Any]]:
    if not await _has_admin_chain(session):
        return []

    topic_cols = await legacy_table_columns(session, "topics")
    prompt_cols = await legacy_table_columns(session, "prompts")
    query_cols = await legacy_table_columns(session, "queries")
    response_cols = await legacy_table_columns(session, "llm_responses")
    if "id" not in topic_cols or "id" not in prompt_cols or "id" not in query_cols:
        return []
    if "topic_id" not in prompt_cols or "prompt_id" not in query_cols:
        return []

    has_responses = await legacy_table_exists(session, "llm_responses")
    has_analysis = await legacy_table_exists(session, "response_analyses")
    has_mentions = await legacy_table_exists(session, "brand_mentions")
    has_citations = await legacy_table_exists(session, "citation_sources")
    mention_cols = await legacy_table_columns(session, "brand_mentions") if has_mentions else set()
    if successful_responses_only and (not has_responses or "id" not in response_cols):
        return []

    scope_brand_id = (
        int(brand_id_override)
        if brand_id_override is not None
        else (int(project.primary_brand_id) if project.primary_brand_id is not None else None)
    )
    scope_terms = (
        await _brand_fact_terms(session, scope_brand_id) if scope_brand_id is not None else []
    )

    params: dict[str, Any] = {}
    target_mention_condition = _target_mention_condition(
        mention_cols,
        scope_brand_id,
        scope_terms,
        params,
    )
    topic_where: list[str] = []
    if topic_id is not None:
        topic_where.append("t.id = :topic_id")
        params["topic_id"] = int(topic_id)
    if "status" in topic_cols:
        topic_where.append("COALESCE(t.status, 'active') <> 'archived'")
    if prompt_id is not None:
        topic_where.append("p.id = :prompt_id")
        params["prompt_id"] = int(prompt_id)

    prompt_join_conditions = ["p.topic_id = t.id"]
    if "status" in prompt_cols:
        prompt_join_conditions.append("COALESCE(p.status, 'active') <> 'archived'")

    query_join_conditions = ["q.prompt_id = p.id"]
    scoped_conditions, scoped_params = await _query_scope_conditions(
        session,
        project=project,
        filters=filters,
        query_cols=query_cols,
        brand_id=None,
    )
    query_join_conditions.extend(scoped_conditions)
    params.update(scoped_params)
    success_condition = _success_status_condition(query_cols)
    if successful_responses_only and success_condition:
        query_join_conditions.append(success_condition)

    response_join = ""
    response_selects = [
        "NULL AS response_id",
        "NULL AS response_raw_text",
        "NULL AS response_target_llm",
        "NULL AS response_intent",
        "NULL AS response_llm_version",
        "NULL AS response_created_at",
    ]
    response_match_condition = ""
    if has_responses and "id" in response_cols:
        response_order_sql = _response_latest_order_sql(response_cols)
        if "query_id" in response_cols:
            response_match_condition = (
                "r.id = ("
                "SELECT r2.id FROM llm_responses r2 "
                "WHERE r2.query_id = q.id "
                f"ORDER BY {response_order_sql} "
                "LIMIT 1"
                ")"
            )
        elif "prompt_id" in response_cols:
            response_match_condition = (
                "r.id = ("
                "SELECT r2.id FROM llm_responses r2 "
                "WHERE r2.prompt_id = p.id "
                f"ORDER BY {response_order_sql} "
                "LIMIT 1"
                ")"
            )
    if response_match_condition:
        response_join_type = "JOIN" if successful_responses_only else "LEFT JOIN"
        response_join = f"{response_join_type} llm_responses r ON {response_match_condition}"
        response_selects = [
            "r.id AS response_id",
            f"{_response_text_expr(response_cols)} AS response_raw_text",
            _select_col(response_cols, "r", "target_llm", "response_target_llm"),
            _select_col(response_cols, "r", "intent", "response_intent"),
            _select_col(response_cols, "r", "llm_version", "response_llm_version"),
            _select_col(response_cols, "r", "created_at", "response_created_at"),
        ]
    elif successful_responses_only:
        return []

    brand_scope_match_select = "0 AS brand_scope_matched"
    if scope_brand_id is not None:
        params["topic_brand_id"] = scope_brand_id
        brand_scope_conditions: list[str] = []
        if "brand_id" in topic_cols:
            brand_scope_conditions.append("t.brand_id = :topic_brand_id")
        if "brand_id" in query_cols:
            brand_scope_conditions.append("q.brand_id = :topic_brand_id")
        if has_mentions and response_join and target_mention_condition:
            brand_scope_conditions.append(
                "EXISTS ("
                "SELECT 1 FROM brand_mentions bm "
                "WHERE bm.response_id = r.id "
                f"AND {target_mention_condition}"
                ")"
            )

        text_exprs: list[str] = []
        for column in ("text", "name", "title"):
            if column in topic_cols:
                text_exprs.append(f"t.{column}")
                break
        prompt_expr = _prompt_text_expr(prompt_cols)
        if prompt_expr != "NULL":
            text_exprs.append(prompt_expr)
        query_expr = _query_text_expr(query_cols)
        if query_expr != "NULL":
            text_exprs.append(query_expr)
        if response_join:
            response_expr = _response_text_expr(response_cols)
            if response_expr != "NULL":
                text_exprs.append(response_expr)
        text_scope_conditions = _text_scope_conditions(
            text_exprs,
            scope_terms,
            params,
            prefix="brand_scope_term",
        )
        brand_scope_conditions.extend(text_scope_conditions)
        if brand_scope_conditions:
            brand_scope_expr = f"({' OR '.join(brand_scope_conditions)})"
            topic_where.append(brand_scope_expr)
            if text_scope_conditions:
                text_scope_expr = f"({' OR '.join(text_scope_conditions)})"
                brand_scope_match_select = (
                    f"CASE WHEN {text_scope_expr} THEN 1 ELSE 0 END AS brand_scope_matched"
                )

    analysis_join = ""
    analysis_selects = [
        "NULL AS analysis_id",
        "NULL AS geo_score",
        "NULL AS sentiment_score",
        "NULL AS target_brand_rank",
        "NULL AS target_brand_mentioned",
    ]
    if has_analysis and response_join:
        analysis_join = "LEFT JOIN response_analyses ra ON ra.response_id = r.id"
        analysis_selects = [
            "ra.id AS analysis_id",
            "ra.geo_score AS geo_score",
            "ra.sentiment_score AS sentiment_score",
            "ra.target_brand_rank AS target_brand_rank",
            "ra.target_brand_mentioned AS target_brand_mentioned",
        ]

    primary = scope_brand_id
    target_mention_condition = target_mention_condition or "1 = 0"
    mention_selects = [
        "0 AS target_mention_count",
        "0 AS all_mention_count",
        "NULL AS min_position_rank",
        "0 AS positive_mentions",
        "0 AS neutral_mentions",
        "0 AS negative_mentions",
        "NULL AS target_sentiment_score",
        "NULL AS negative_sample_snippet",
    ]
    if has_mentions and response_join and primary is not None:
        mention_amount = "COALESCE(bm.mention_count, 1)" if "mention_count" in mention_cols else "1"
        mention_selects = [
            f"(SELECT COALESCE(SUM({mention_amount}), 0) FROM brand_mentions bm "
            f"WHERE bm.response_id = r.id AND {target_mention_condition}) "
            "AS target_mention_count",
            f"(SELECT COALESCE(SUM({mention_amount}), 0) FROM brand_mentions bm "
            "WHERE bm.response_id = r.id) "
            "AS all_mention_count",
            "(SELECT MIN(bm.position_rank) FROM brand_mentions bm "
            f"WHERE bm.response_id = r.id AND {target_mention_condition}) "
            "AS min_position_rank",
            "(SELECT COUNT(*) FROM brand_mentions bm WHERE bm.response_id = r.id "
            f"AND {target_mention_condition} "
            "AND LOWER(COALESCE(bm.sentiment, 'neutral')) = 'positive') "
            "AS positive_mentions",
            "(SELECT COUNT(*) FROM brand_mentions bm WHERE bm.response_id = r.id "
            f"AND {target_mention_condition} "
            "AND LOWER(bm.sentiment) = 'neutral') "
            "AS neutral_mentions",
            "(SELECT COUNT(*) FROM brand_mentions bm WHERE bm.response_id = r.id "
            f"AND {target_mention_condition} "
            "AND LOWER(COALESCE(bm.sentiment, 'neutral')) = 'negative') "
            "AS negative_mentions",
            "(SELECT AVG(bm.sentiment_score) FROM brand_mentions bm "
            "WHERE bm.response_id = r.id "
            f"AND {target_mention_condition} "
            "AND bm.sentiment_score IS NOT NULL) AS target_sentiment_score",
            "(SELECT bm.context_snippet FROM brand_mentions bm WHERE bm.response_id = r.id "
            f"AND {target_mention_condition} "
            "AND LOWER(COALESCE(bm.sentiment, 'neutral')) = 'negative' "
            "AND bm.context_snippet IS NOT NULL "
            "ORDER BY bm.id LIMIT 1) AS negative_sample_snippet",
        ]

    citation_select = "NULL AS citation_count"
    if has_citations and response_join:
        citation_select = (
            "(SELECT COUNT(*) FROM citation_sources cs WHERE cs.response_id = r.id) "
            "AS citation_count"
        )

    where_clause = f"WHERE {' AND '.join(topic_where)}" if topic_where else ""
    sql = text(
        f"""
        SELECT
            t.id AS topic_id,
            {_topic_name_expr(topic_cols)} AS topic_name,
            {_select_col(topic_cols, "t", "category", "topic_dimension")},
            {_select_col(topic_cols, "t", "status", "topic_status")},
            p.id AS prompt_id,
            {_prompt_text_expr(prompt_cols)} AS prompt_text,
            {_select_col(prompt_cols, "p", "intent", "prompt_intent")},
            {_prompt_scope_expr(prompt_cols)} AS prompt_scope,
            {_prompt_tags_expr(prompt_cols)} AS prompt_tags,
            {_select_col(prompt_cols, "p", "language", "prompt_language")},
            {_select_col(prompt_cols, "p", "status", "prompt_status")},
            q.id AS query_id,
            {_query_text_expr(query_cols)} AS query_text,
            {_select_col(query_cols, "q", "target_llm", "target_llm")},
            {_select_col(query_cols, "q", "status", "query_status")},
            {_select_col(query_cols, "q", "profile_id", "profile_id")},
            {_select_col(query_cols, "q", "created_at", "query_created_at")},
            {_select_col(query_cols, "q", "executed_at", "query_executed_at")},
            {_select_col(query_cols, "q", "finished_at", "query_finished_at")},
            {_select_col(query_cols, "q", "latency_ms", "latency_ms")},
            {", ".join(response_selects)},
            {brand_scope_match_select},
            {", ".join(analysis_selects)},
            {", ".join(mention_selects)},
            {citation_select}
        FROM topics t
        LEFT JOIN prompts p ON {" AND ".join(prompt_join_conditions)}
        LEFT JOIN queries q ON {" AND ".join(query_join_conditions)}
        {response_join}
        {analysis_join}
        {where_clause}
        ORDER BY t.id, p.id, q.created_at DESC, q.id DESC
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    out = [dict(r) for r in rows]
    if filters.dimensions or filters.intents or filters.prompt_scope:
        out = [row for row in out if _row_matches_analysis_filters(row, filters)]
    return out
