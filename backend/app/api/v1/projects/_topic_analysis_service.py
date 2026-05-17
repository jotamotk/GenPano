"""Project-scoped analytics over Admin Topic -> Prompt -> Query -> Response data."""

from __future__ import annotations

from collections import Counter, OrderedDict, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from genpano_models import Project
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._legacy_lookups import (
    resolve_brand_names,
)
from app.api.v1.projects._topic_analysis_dto import (
    AnalyzerFacts,
    BrandMentionDetail,
    CitationDetail,
    ProductFeatureAttributeDetail,
    ProjectProfileRow,
    ProjectSegmentRow,
    ProjectSegmentsOut,
    PromptQueriesOut,
    PromptQueryDailyRow,
    PromptQueryRow,
    QueryActivityDailyRow,
    QueryActivityEngineRow,
    QueryActivityOut,
    QueryActivityTopicRow,
    QueryDetail,
    QueryResponseDetailOut,
    ResponseAnalysisDetail,
    ResponseAttemptDetail,
    ResponseDetail,
    ResponseRelationDetail,
    SentimentDriverDetail,
    TopicIntentMatrixRow,
    TopicMonitoringOut,
    TopicMonitoringRow,
    TopicMonitoringSummary,
    TopicPromptRow,
    TopicPromptsOut,
)
from app.api.v1.projects.topic_analysis.fact_rollup import (
    _bucket_position as _bucket_position,
)
from app.api.v1.projects.topic_analysis.fact_rollup import (
    _fact_all_mention_count as _fact_all_mention_count,
)
from app.api.v1.projects.topic_analysis.fact_rollup import (
    _fact_brand_scope_matched as _fact_brand_scope_matched,
)
from app.api.v1.projects.topic_analysis.fact_rollup import (
    _fact_target_mention_count as _fact_target_mention_count,
)
from app.api.v1.projects.topic_analysis.fact_rollup import (
    _logical_query_key as _logical_query_key,
)
from app.api.v1.projects.topic_analysis.fact_rollup import (
    _row_attempt_sort_key as _row_attempt_sort_key,
)
from app.api.v1.projects.topic_analysis.fact_rollup import (
    _row_attempt_time as _row_attempt_time,
)
from app.api.v1.projects.topic_analysis.filters import (
    DEFAULT_WINDOW_DAYS as DEFAULT_WINDOW_DAYS,
)
from app.api.v1.projects.topic_analysis.filters import (
    AnalysisFilters as AnalysisFilters,
)
from app.api.v1.projects.topic_analysis.filters import (
    _is_non_branded_row as _is_non_branded_row,
)
from app.api.v1.projects.topic_analysis.filters import (
    _mention_name_condition as _mention_name_condition,
)
from app.api.v1.projects.topic_analysis.filters import (
    _prompt_scope_from_row as _prompt_scope_from_row,
)
from app.api.v1.projects.topic_analysis.filters import (
    _resolve_window as _resolve_window,
)
from app.api.v1.projects.topic_analysis.filters import (
    _row_matches_analysis_filters as _row_matches_analysis_filters,
)
from app.api.v1.projects.topic_analysis.filters import (
    _target_mention_condition as _target_mention_condition,
)
from app.api.v1.projects.topic_analysis.filters import (
    _text_scope_conditions as _text_scope_conditions,
)
from app.api.v1.projects.topic_analysis.legacy_schema import (
    _not_deleted_condition as _not_deleted_condition,
)
from app.api.v1.projects.topic_analysis.legacy_schema import (
    _prompt_scope_expr as _prompt_scope_expr,
)
from app.api.v1.projects.topic_analysis.legacy_schema import (
    _prompt_tags_expr as _prompt_tags_expr,
)
from app.api.v1.projects.topic_analysis.legacy_schema import (
    _prompt_text_expr as _prompt_text_expr,
)
from app.api.v1.projects.topic_analysis.legacy_schema import (
    _safe_ident as _safe_ident,
)
from app.api.v1.projects.topic_analysis.legacy_schema import (
    _select_col as _select_col,
)
from app.api.v1.projects.topic_analysis.legacy_schema import (
    _topic_name_expr as _topic_name_expr,
)
from app.api.v1.projects.topic_analysis.legacy_schema import (
    legacy_table_columns as legacy_table_columns,
)
from app.api.v1.projects.topic_analysis.legacy_schema import (
    legacy_table_exists as legacy_table_exists,
)
from app.api.v1.projects.topic_analysis.normalize import (
    _as_float as _as_float,
)
from app.api.v1.projects.topic_analysis.normalize import (
    _as_int as _as_int,
)
from app.api.v1.projects.topic_analysis.normalize import (
    _coerce_json as _coerce_json,
)
from app.api.v1.projects.topic_analysis.normalize import (
    _date_key as _date_key,
)
from app.api.v1.projects.topic_analysis.normalize import (
    _iso as _iso,
)
from app.api.v1.projects.topic_analysis.normalize import (
    _mean as _mean,
)
from app.api.v1.projects.topic_analysis.normalize import (
    _normalize_key as _normalize_key,
)
from app.api.v1.projects.topic_analysis.normalize import (
    _pct as _pct,
)
from app.api.v1.projects.topic_analysis.normalize import (
    _response_preview as _response_preview,
)
from app.api.v1.projects.topic_analysis.normalize import (
    _round as _round,
)
from app.api.v1.projects.topic_analysis.normalize import (
    _timestamp_key as _timestamp_key,
)
from app.api.v1.projects.topic_analysis.profiles import (
    _brand_fact_terms as _brand_fact_terms,
)
from app.api.v1.projects.topic_analysis.profiles import (
    _clean_fact_term as _clean_fact_term,
)
from app.api.v1.projects.topic_analysis.profiles import (
    _expand_brand_fact_terms as _expand_brand_fact_terms,
)
from app.api.v1.projects.topic_analysis.profiles import (
    _profile_name as _profile_name,
)
from app.api.v1.projects.topic_analysis.profiles import (
    _profile_names_for_ids as _profile_names_for_ids,
)
from app.api.v1.projects.topic_analysis.profiles import (
    _profile_names_for_rows as _profile_names_for_rows,
)
from app.api.v1.projects.topic_analysis.queries import (
    _PROJECT_BRAND as _PROJECT_BRAND,
)
from app.api.v1.projects.topic_analysis.queries import (
    _dt_range as _dt_range,
)
from app.api.v1.projects.topic_analysis.queries import (
    _engine_conditions as _engine_conditions,
)
from app.api.v1.projects.topic_analysis.queries import (
    _fact_rows as _fact_rows,
)
from app.api.v1.projects.topic_analysis.queries import (
    _false_condition as _false_condition,
)
from app.api.v1.projects.topic_analysis.queries import (
    _has_admin_chain as _has_admin_chain,
)
from app.api.v1.projects.topic_analysis.queries import (
    _query_scope_conditions as _query_scope_conditions,
)
from app.api.v1.projects.topic_analysis.queries import (
    _query_text_expr as _query_text_expr,
)
from app.api.v1.projects.topic_analysis.queries import (
    _response_latest_order_sql as _response_latest_order_sql,
)
from app.api.v1.projects.topic_analysis.queries import (
    _response_text_expr as _response_text_expr,
)
from app.api.v1.projects.topic_analysis.queries import (
    _success_status_condition as _success_status_condition,
)
from app.core.errors import not_found


def _period(from_d: date, to_d: date) -> dict[str, str]:
    return {"from": from_d.isoformat(), "to": to_d.isoformat()}


def _effective_brand_id(project: Project, brand_id_override: int | None = None) -> int | None:
    return (
        int(brand_id_override)
        if brand_id_override is not None
        else (_as_int(project.primary_brand_id) if project.primary_brand_id is not None else None)
    )


def _empty_monitoring(
    project: Project,
    state: str = "empty",
    *,
    brand_id: int | None = None,
) -> TopicMonitoringOut:
    return TopicMonitoringOut(
        project_id=project.id,
        brand_id=brand_id if brand_id is not None else project.primary_brand_id,
        summary=TopicMonitoringSummary(),
        topics=[],
        intent_matrix=[],
        state=state,
    )


async def _count_brand_topics_total(session: AsyncSession, brand_id: int) -> int:
    """Active topic count for a brand (user-facing analytics scope).

    Scope mirrors `topic_analysis/queries.py:_fact_rows` line 226 — same
    `COALESCE(t.status, 'active') <> 'archived'` predicate — so the count,
    the merged listing, and downstream evidence rows reference the same
    population. Archived topics never produce fact rows, so including them
    would cause ghost zero-everything rows in the user-facing list (#1029).
    """
    try:
        cols = await legacy_table_columns(session, "topics")
    except Exception:
        return 0
    if not cols or "id" not in cols or "brand_id" not in cols:
        return 0
    where_clauses = ["brand_id = :brand_id"]
    if "status" in cols:
        where_clauses.append("COALESCE(status, 'active') <> 'archived'")
    sql = text(f"SELECT COUNT(*) AS topic_count FROM topics WHERE {' AND '.join(where_clauses)}")
    try:
        result = await session.execute(sql, {"brand_id": int(brand_id)})
        row = result.mappings().first()
    except Exception:
        return 0
    if row is None:
        return 0
    return int(row.get("topic_count") or 0)


async def _fetch_brand_topics_listing(session: AsyncSession, brand_id: int) -> list[dict[str, Any]]:
    """Active topic rows for a brand (id, text, category, status).

    Scope mirrors `topic_analysis/queries.py:_fact_rows` line 226
    (`COALESCE(t.status, 'active') <> 'archived'`) so the listing aligns with
    the population that `_fact_rows` evaluates. Used by
    `_merge_missing_brand_topics` to surface active-but-evidence-less topics
    in the user-facing list (#1029, re-implementation of reverted #1034).
    Returns ``[]`` when the legacy ``topics`` table is missing or the query
    fails — caller must handle that gracefully.
    """
    try:
        cols = await legacy_table_columns(session, "topics")
    except Exception:
        return []
    if not cols or "id" not in cols or "brand_id" not in cols:
        return []
    text_expr = _topic_name_expr(cols)
    category_expr = "t.category" if "category" in cols else "NULL"
    status_expr = "t.status" if "status" in cols else "NULL"
    created_expr = "t.created_at" if "created_at" in cols else "NULL"
    order_clause = (
        "ORDER BY t.created_at DESC NULLS LAST, t.id DESC"
        if "created_at" in cols
        else "ORDER BY t.id DESC"
    )
    where_clauses = ["t.brand_id = :brand_id"]
    if "status" in cols:
        where_clauses.append("COALESCE(t.status, 'active') <> 'archived'")
    sql = text(
        f"""
        SELECT
            t.id AS topic_id,
            {text_expr} AS topic_name,
            {category_expr} AS topic_dimension,
            {status_expr} AS topic_status,
            {created_expr} AS topic_created_at
        FROM topics t
        WHERE {" AND ".join(where_clauses)}
        {order_clause}
        """
    )
    try:
        rows = (await session.execute(sql, {"brand_id": int(brand_id)})).mappings().all()
    except Exception:
        return []
    return [dict(r) for r in rows]


def _merge_missing_brand_topics(
    topics: list[TopicMonitoringRow],
    listing: list[dict[str, Any]],
    *,
    associated_brand: str | None,
) -> list[TopicMonitoringRow]:
    """Append active brand topics that have no fact rows yet, with zero/null
    metrics, so the user-facing list matches the population of active topics
    (#1029, re-implementation of reverted #1034).

    Topics already present (with evidence) keep their position and metrics;
    missing topics appear after them with all metric fields at the renderer-
    safe default values (frontend `TopicsPage.tsx` renders ``null`` rates and
    zero counts as ``--`` / ``-`` so no extra null-handling work is needed).

    Caller MUST invoke this AFTER ``build_contract_context`` has been run on
    the with-evidence ``topics`` list. ``build_contract_context`` reads
    ``has_data = bool(summary.response_count or topics)``; if the merge runs
    earlier, evidence-less topics would flip ``has_data`` to ``True`` and
    cascade into ``metric_formula_evidence`` evaluation, producing the
    "Limited proof" regression that reverted PR #1052 caused.
    """
    if not listing:
        return topics
    present = {item.topic_id for item in topics}
    merged: list[TopicMonitoringRow] = list(topics)
    for row in listing:
        tid = _as_int(row.get("topic_id"))
        if tid is None or tid in present:
            continue
        present.add(tid)
        merged.append(
            TopicMonitoringRow(
                topic_id=tid,
                topic_name=row.get("topic_name") or f"topic-{tid}",
                dimension=row.get("topic_dimension"),
                associated_brand=associated_brand,
                status=row.get("topic_status"),
                prompt_count=0,
                query_count=0,
                response_count=0,
                success_rate=None,
                engine_coverage=[],
                mention_rate=None,
                visibility_rate=None,
                sov=None,
                avg_rank=None,
                avg_geo_score=None,
                sentiment_distribution={"positive": 0, "neutral": 0, "negative": 0},
                citation_count=0,
                citation_rate=None,
                last_collected=None,
            )
        )
    return merged


def _topic_aggregates(
    rows: list[dict[str, Any]],
    *,
    project: Project,
    filters: AnalysisFilters,
    associated_brand: str | None = None,
) -> tuple[list[TopicMonitoringRow], TopicMonitoringSummary, list[TopicIntentMatrixRow]]:
    topic_order: list[int] = []
    topics: dict[int, dict[str, Any]] = {}
    matrix: dict[tuple[int, str], dict[str, Any]] = {}

    for row in rows:
        tid = _as_int(row.get("topic_id"))
        if tid is None:
            continue
        if tid not in topics:
            topic_order.append(tid)
            topics[tid] = {
                "topic_id": tid,
                "topic_name": row.get("topic_name") or f"topic-{tid}",
                "dimension": row.get("topic_dimension"),
                "associated_brand": associated_brand,
                "status": row.get("topic_status"),
                "prompt_ids": set(),
                "query_ids": set(),
                "response_ids": set(),
                "analysis_ids": set(),
                "success_count": 0,
                "engines": set(),
                "target_mentions": 0,
                "all_mentions": 0,
                "mention_denominator_response_ids": set(),
                "target_mention_response_ids": set(),
                "citation_count": 0,
                "cited_response_ids": set(),
                "ranks": [],
                "geo_scores": [],
                "sentiment": {"positive": 0, "neutral": 0, "negative": 0},
                "last_collected": None,
            }
        bucket = topics[tid]

        pid = _as_int(row.get("prompt_id"))
        if pid is not None:
            bucket["prompt_ids"].add(pid)
        qid = _as_int(row.get("query_id"))
        if qid is not None:
            bucket["query_ids"].add(qid)
            status = str(row.get("query_status") or "").lower()
            if status in {"done", "success", "completed"}:
                bucket["success_count"] += 1
            engine = row.get("target_llm") or row.get("response_target_llm")
            if engine:
                bucket["engines"].add(str(engine))
            last = (
                row.get("query_finished_at")
                or row.get("response_created_at")
                or row.get("query_created_at")
            )
            if last is not None and (
                bucket["last_collected"] is None or str(last) > str(bucket["last_collected"])
            ):
                bucket["last_collected"] = last

        rid = _as_int(row.get("response_id"))
        if rid is not None and rid not in bucket["response_ids"]:
            bucket["response_ids"].add(rid)
            aid = _as_int(row.get("analysis_id"))
            if aid is not None:
                bucket["analysis_ids"].add(aid)
            target_mentions = _fact_target_mention_count(row)
            all_mentions = _fact_all_mention_count(row, target_mentions)
            bucket["target_mentions"] += target_mentions
            bucket["all_mentions"] += all_mentions
            if _is_non_branded_row(row):
                bucket["mention_denominator_response_ids"].add(rid)
                if target_mentions > 0:
                    bucket["target_mention_response_ids"].add(rid)
            bucket["citation_count"] += int(row.get("citation_count") or 0)
            if int(row.get("citation_count") or 0) > 0:
                bucket["cited_response_ids"].add(rid)
            rank = _as_int(row.get("min_position_rank") or row.get("target_brand_rank"))
            if rank is not None:
                bucket["ranks"].append(float(rank))
            geo = _as_float(row.get("geo_score"))
            if geo is not None:
                bucket["geo_scores"].append(geo)
            bucket["sentiment"]["positive"] += int(row.get("positive_mentions") or 0)
            bucket["sentiment"]["neutral"] += int(row.get("neutral_mentions") or 0)
            bucket["sentiment"]["negative"] += int(row.get("negative_mentions") or 0)

        intent = row.get("prompt_intent") or "unknown"
        matrix_key = (tid, str(intent))
        if matrix_key not in matrix:
            matrix[matrix_key] = {
                "topic_id": tid,
                "topic_name": bucket["topic_name"],
                "intent": str(intent),
                "prompt_ids": set(),
                "query_ids": set(),
                "response_ids": set(),
            }
        if pid is not None:
            matrix[matrix_key]["prompt_ids"].add(pid)
        if qid is not None:
            matrix[matrix_key]["query_ids"].add(qid)
        if rid is not None:
            matrix[matrix_key]["response_ids"].add(rid)

    if filters.explicit:
        topic_order = [tid for tid in topic_order if len(topics[tid]["query_ids"]) > 0]

    items: list[TopicMonitoringRow] = []
    summary_sets: dict[str, set[int]] = {
        "topics": set(),
        "prompts": set(),
        "queries": set(),
        "responses": set(),
        "analyses": set(),
    }
    total_target_mentions = 0
    total_citations = 0
    last_collected: Any = None

    for tid in topic_order:
        bucket = topics[tid]
        prompt_count = len(bucket["prompt_ids"])
        query_count = len(bucket["query_ids"])
        response_count = len(bucket["response_ids"])
        target_mentions = int(bucket["target_mentions"])
        all_mentions = int(bucket["all_mentions"])
        citations = int(bucket["citation_count"])
        mention_denominator = len(bucket["mention_denominator_response_ids"])
        target_mention_responses = len(bucket["target_mention_response_ids"])
        visibility_rate = _pct(target_mention_responses, mention_denominator)
        items.append(
            TopicMonitoringRow(
                topic_id=tid,
                topic_name=bucket["topic_name"],
                dimension=bucket["dimension"],
                associated_brand=bucket["associated_brand"],
                status=bucket["status"],
                prompt_count=prompt_count,
                query_count=query_count,
                response_count=response_count,
                success_rate=_pct(bucket["success_count"], query_count),
                engine_coverage=sorted(bucket["engines"]),
                mention_rate=visibility_rate,
                visibility_rate=visibility_rate,
                sov=_pct(target_mentions, all_mentions),
                avg_rank=_mean(bucket["ranks"]),
                avg_geo_score=_mean(bucket["geo_scores"]),
                sentiment_distribution=bucket["sentiment"],
                citation_count=citations,
                citation_rate=_pct(len(bucket["cited_response_ids"]), response_count),
                last_collected=_iso(bucket["last_collected"]),
            )
        )
        summary_sets["topics"].add(tid)
        summary_sets["prompts"].update(bucket["prompt_ids"])
        summary_sets["queries"].update(bucket["query_ids"])
        summary_sets["responses"].update(bucket["response_ids"])
        summary_sets["analyses"].update(bucket["analysis_ids"])
        total_target_mentions += target_mentions
        total_citations += citations
        if bucket["last_collected"] is not None and (
            last_collected is None or str(bucket["last_collected"]) > str(last_collected)
        ):
            last_collected = bucket["last_collected"]

    allowed_topics = {item.topic_id for item in items}
    intent_rows = [
        TopicIntentMatrixRow(
            topic_id=v["topic_id"],
            topic_name=v["topic_name"],
            intent=v["intent"],
            prompt_count=len(v["prompt_ids"]),
            query_count=len(v["query_ids"]),
            response_count=len(v["response_ids"]),
        )
        for v in matrix.values()
        if v["topic_id"] in allowed_topics and (not filters.explicit or len(v["query_ids"]) > 0)
    ]
    intent_rows.sort(key=lambda r: (r.topic_id or 0, r.intent))

    summary = TopicMonitoringSummary(
        topic_count=len(summary_sets["topics"]),
        prompt_count=len(summary_sets["prompts"]),
        query_count=len(summary_sets["queries"]),
        response_count=len(summary_sets["responses"]),
        analyzed_count=len(summary_sets["analyses"]),
        target_mention_count=total_target_mentions,
        citation_count=total_citations,
        last_collected=_iso(last_collected),
    )
    return items, summary, intent_rows


async def get_topic_monitoring(
    session: AsyncSession,
    project: Project,
    *,
    filters: AnalysisFilters,
    brand_id_override: int | None = None,
) -> TopicMonitoringOut:
    from app.api.v1.projects._analytics_contract import (
        FORMULA_OK_STATUS,
        build_contract_context,
        context_update,
        formula_diagnostics_for,
    )

    brand_id = _effective_brand_id(project, brand_id_override)
    if brand_id is None:
        return _empty_monitoring(project, brand_id=brand_id)
    rows = await _fact_rows(session, project, filters=filters, brand_id_override=brand_id)
    brand_names = await resolve_brand_names(session, [brand_id])
    topics, summary, intent_matrix = _topic_aggregates(
        rows,
        project=project,
        filters=filters,
        associated_brand=brand_names.get(brand_id),
    )
    summary.topic_count_total = await _count_brand_topics_total(session, brand_id)
    state = "ok" if summary.query_count or (topics and not filters.explicit) else "empty"
    out = TopicMonitoringOut(
        project_id=project.id,
        brand_id=brand_id,
        summary=summary,
        topics=topics,
        intent_matrix=intent_matrix,
        state=state,
        state_reason="data_available" if state == "ok" else "no_topic_monitoring_data",
        evidence_count=summary.response_count,
    )
    to_date = filters.to_date or date.today()
    from_date = filters.from_date or (to_date - timedelta(days=29))
    context = await build_contract_context(
        session,
        project,
        brand_id=brand_id,
        from_date=from_date,
        to_date=to_date,
        has_data=bool(summary.response_count or topics),
        base_state=state,
        selected_filters={
            "engine": list(filters.engines) if filters.engines else None,
            "segment_id": filters.segment_id,
            "profile_id": filters.profile_id,
            "dimension": list(filters.dimensions) if filters.dimensions else None,
            "intent": list(filters.intents) if filters.intents else None,
            "prompt_scope": filters.prompt_scope,
        },
        source_provenance=["admin_facts", "response_analyses.raw_analysis_json"],
    )
    update = context_update(context)
    coverage_evidence = context.metric_formula_evidence.get("coverage")
    coverage_status = (
        str(coverage_evidence.get("formula_status") or "")
        if isinstance(coverage_evidence, dict)
        else "ok"
    )
    coverage_sources = (
        [str(source) for source in coverage_evidence.get("source_tables", [])]
        if isinstance(coverage_evidence, dict)
        else []
    )
    analyzer_package_sources = {
        "response_analyses.raw_analysis_json.analyzer_fact_package_v3",
        "response_analyses.raw_analysis_json.analyzer_fact_packages",
    }
    if coverage_status in {"", "ok"} or not analyzer_package_sources.intersection(coverage_sources):
        update.update(
            {
                "state": out.state,
                "state_reason": out.state_reason,
                "missing_inputs": out.missing_inputs,
                "missing_sources": out.missing_sources,
                "missing_reasons": out.missing_reasons,
            }
        )
    if (
        update.get("state") == "ok"
        and not update.get("missing_inputs")
        and not update.get("missing_sources")
        and out.evidence_count > 0
    ):
        update["formula_status"] = FORMULA_OK_STATUS
        update["formula_diagnostics"] = formula_diagnostics_for(FORMULA_OK_STATUS)
    # #1029: merge active-but-evidence-less topics into the list so the
    # user-facing /topics view matches the brand's actual active topic
    # population, not just the subset that already has llm_response rows.
    #
    # ORDER MATTERS — this merge MUST run AFTER `build_contract_context`
    # (above) has consumed `has_data = bool(summary.response_count or topics)`.
    # If the merge ran earlier, the additional zero-metric topics would flip
    # `has_data` to True for evidence-empty brands and cascade into
    # `metric_formula_evidence` evaluation, producing the "Limited proof"
    # regression that triggered the revert of PR #1052.
    #
    # The gate is NOT `filters.explicit` (that tripped on the default
    # frontend state of date + engine preselect, which caused PR #1041 to
    # silently never merge). Instead we gate only on filters that narrow the
    # *topic set itself*: dimensions, intents, prompt_scope. Date / engine /
    # segment / profile filters are query-scope and a topic with no
    # responses in the window is still a valid "no evidence yet" entry.
    filters_narrow_topic_set = bool(filters.dimensions or filters.intents or filters.prompt_scope)
    if not filters_narrow_topic_set:
        listing = await _fetch_brand_topics_listing(session, brand_id)
        merged_topics = _merge_missing_brand_topics(
            out.topics,
            listing,
            associated_brand=brand_names.get(brand_id),
        )
        if len(merged_topics) != len(out.topics):
            update["topics"] = merged_topics
    return out.model_copy(update=update)


async def get_topic_prompts(
    session: AsyncSession,
    project: Project,
    *,
    topic_id: int,
    filters: AnalysisFilters,
    brand_id_override: int | None = None,
) -> TopicPromptsOut:
    brand_id = _effective_brand_id(project, brand_id_override)
    rows = (
        await _fact_rows(
            session,
            project,
            filters=filters,
            topic_id=topic_id,
            brand_id_override=brand_id,
        )
        if brand_id is not None
        else []
    )
    by_prompt: OrderedDict[int, dict[str, Any]] = OrderedDict()
    for row in rows:
        pid = _as_int(row.get("prompt_id"))
        if pid is None:
            continue
        if pid not in by_prompt:
            by_prompt[pid] = {
                "prompt_id": pid,
                "topic_id": topic_id,
                "prompt_text": row.get("prompt_text"),
                "intent": row.get("prompt_intent"),
                "language": row.get("prompt_language"),
                "status": row.get("prompt_status"),
                "prompt_scope": _prompt_scope_from_row(row),
                "query_ids": set(),
                "responses": set(),
                "success_count": 0,
                "engines": set(),
                "target_mentions": 0,
                "mention_denominator_response_ids": set(),
                "target_mention_response_ids": set(),
                "citations": 0,
                "cited_response_ids": set(),
                "ranks": [],
                "geo_scores": [],
                "sentiment": {"positive": 0, "neutral": 0, "negative": 0},
                "last_collected": None,
            }
        bucket = by_prompt[pid]
        qid = _as_int(row.get("query_id"))
        if qid is not None:
            bucket["query_ids"].add(qid)
            if str(row.get("query_status") or "").lower() in {"done", "success", "completed"}:
                bucket["success_count"] += 1
            if row.get("target_llm"):
                bucket["engines"].add(str(row["target_llm"]))
            last = (
                row.get("query_finished_at")
                or row.get("response_created_at")
                or row.get("query_created_at")
            )
            if last is not None and (
                bucket["last_collected"] is None or str(last) > str(bucket["last_collected"])
            ):
                bucket["last_collected"] = last
        rid = _as_int(row.get("response_id"))
        if rid is not None and rid not in bucket["responses"]:
            bucket["responses"].add(rid)
            target_mentions = _fact_target_mention_count(row)
            bucket["target_mentions"] += target_mentions
            if _is_non_branded_row(row):
                bucket["mention_denominator_response_ids"].add(rid)
                if target_mentions > 0:
                    bucket["target_mention_response_ids"].add(rid)
            bucket["citations"] += int(row.get("citation_count") or 0)
            if int(row.get("citation_count") or 0) > 0:
                bucket["cited_response_ids"].add(rid)
            rank = _as_int(row.get("min_position_rank") or row.get("target_brand_rank"))
            if rank is not None:
                bucket["ranks"].append(float(rank))
            geo = _as_float(row.get("geo_score"))
            if geo is not None:
                bucket["geo_scores"].append(geo)
            bucket["sentiment"]["positive"] += int(row.get("positive_mentions") or 0)
            bucket["sentiment"]["neutral"] += int(row.get("neutral_mentions") or 0)
            bucket["sentiment"]["negative"] += int(row.get("negative_mentions") or 0)

    buckets = list(by_prompt.values())
    if filters.explicit:
        buckets = [b for b in buckets if b["query_ids"]]
    items = [
        TopicPromptRow(
            prompt_id=b["prompt_id"],
            topic_id=b["topic_id"],
            prompt_text=b["prompt_text"],
            intent=b["intent"],
            language=b["language"],
            status=b["status"],
            prompt_scope=b["prompt_scope"],
            query_count=len(b["query_ids"]),
            response_count=len(b["responses"]),
            success_rate=_pct(b["success_count"], len(b["query_ids"])),
            engine_coverage=sorted(b["engines"]),
            mention_rate=_pct(
                len(b["target_mention_response_ids"]),
                len(b["mention_denominator_response_ids"]),
            ),
            visibility_rate=_pct(
                len(b["target_mention_response_ids"]),
                len(b["mention_denominator_response_ids"]),
            ),
            avg_rank=_mean(b["ranks"]),
            avg_geo_score=_mean(b["geo_scores"]),
            sentiment_distribution=b["sentiment"],
            citation_count=int(b["citations"]),
            citation_rate=_pct(len(b["cited_response_ids"]), len(b["responses"])),
            last_collected=_iso(b["last_collected"]),
        )
        for b in buckets
    ]
    return TopicPromptsOut(
        project_id=project.id,
        topic_id=topic_id,
        items=items,
        total=len(items),
        state="ok" if items else "empty",
    )


async def get_prompt_queries(
    session: AsyncSession,
    project: Project,
    *,
    prompt_id: int,
    filters: AnalysisFilters,
    brand_id_override: int | None = None,
) -> PromptQueriesOut:
    brand_id = _effective_brand_id(project, brand_id_override)
    rows = (
        await _fact_rows(
            session,
            project,
            filters=filters,
            prompt_id=prompt_id,
            brand_id_override=brand_id,
        )
        if brand_id is not None
        else []
    )
    rows = [row for row in rows if _as_int(row.get("response_id")) is not None]
    rows.sort(key=_row_attempt_sort_key, reverse=True)
    profile_names = await _profile_names_for_rows(session, rows)

    by_group: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for row in rows:
        qid = _as_int(row.get("query_id"))
        rid = _as_int(row.get("response_id"))
        if qid is None or rid is None:
            continue
        group_key = _logical_query_key(row)
        date_key = _date_key(_row_attempt_time(row)) or ""
        if group_key not in by_group:
            by_group[group_key] = {"rows": [], "daily": OrderedDict()}
        bucket = by_group[group_key]
        bucket["rows"].append(row)
        if date_key and date_key not in bucket["daily"]:
            bucket["daily"][date_key] = row

    items = [
        PromptQueryRow(
            query_id=int(row["query_id"]),
            prompt_id=_as_int(row.get("prompt_id")),
            query_group_key=group_key,
            query_text=row.get("query_text"),
            target_llm=row.get("target_llm"),
            status=(str(row.get("query_status")).lower() if row.get("query_status") else None),
            profile_id=str(row.get("profile_id")) if row.get("profile_id") is not None else None,
            profile_name=_profile_name(row.get("profile_id"), profile_names),
            created_at=_iso(row.get("query_created_at")),
            executed_at=_iso(row.get("query_executed_at")),
            finished_at=_iso(row.get("query_finished_at")),
            latency_ms=_as_int(row.get("latency_ms")),
            response_id=_as_int(row.get("response_id")),
            date=_date_key(_row_attempt_time(row)),
            attempt_count=len(bucket["rows"]),
            daily_latest=[
                PromptQueryDailyRow(
                    date=date_key,
                    query_id=int(day_row["query_id"]),
                    response_id=int(day_row["response_id"]),
                    query_text=day_row.get("query_text"),
                    target_llm=day_row.get("target_llm"),
                    status=str(day_row.get("query_status")).lower()
                    if day_row.get("query_status")
                    else None,
                    profile_id=str(day_row.get("profile_id"))
                    if day_row.get("profile_id") is not None
                    else None,
                    profile_name=_profile_name(day_row.get("profile_id"), profile_names),
                    executed_at=_iso(day_row.get("query_executed_at")),
                    finished_at=_iso(day_row.get("query_finished_at")),
                    latency_ms=_as_int(day_row.get("latency_ms")),
                    response_preview=_response_preview(day_row.get("response_raw_text")),
                    response_created_at=_iso(day_row.get("response_created_at")),
                    target_mentioned=_fact_target_mention_count(day_row) > 0,
                    citation_count=int(day_row.get("citation_count") or 0),
                    geo_score=_round(day_row.get("geo_score")),
                    sentiment_score=_round(day_row.get("sentiment_score")),
                )
                for date_key, day_row in bucket["daily"].items()
            ],
            target_mentioned=_fact_target_mention_count(row) > 0,
            citation_count=int(row.get("citation_count") or 0),
            geo_score=_round(row.get("geo_score")),
            sentiment_score=_round(row.get("sentiment_score")),
        )
        for group_key, bucket in by_group.items()
        for row in [next(iter(bucket["daily"].values()))]
    ]
    return PromptQueriesOut(
        project_id=project.id,
        prompt_id=prompt_id,
        items=items,
        total=len(items),
        state="ok" if items else "empty",
    )


async def _response_analysis_detail(
    session: AsyncSession,
    response_id: int,
) -> ResponseAnalysisDetail | None:
    if not await legacy_table_exists(session, "response_analyses"):
        return None
    arow = (
        (
            await session.execute(
                text(
                    """
                    SELECT id, target_brand_mentioned, target_brand_rank,
                           target_brand_sentiment, visibility_score, sentiment_score,
                           sov_score, citation_score, geo_score, analyzed_at
                    FROM response_analyses
                    WHERE response_id = :response_id
                    LIMIT 1
                    """
                ),
                {"response_id": response_id},
            )
        )
        .mappings()
        .first()
    )
    if not arow:
        return None
    a = dict(arow)
    return ResponseAnalysisDetail(
        analysis_id=_as_int(a.get("id")),
        target_brand_mentioned=bool(a.get("target_brand_mentioned"))
        if a.get("target_brand_mentioned") is not None
        else None,
        target_brand_rank=_as_int(a.get("target_brand_rank")),
        target_brand_sentiment=a.get("target_brand_sentiment"),
        visibility_score=_round(a.get("visibility_score")),
        sentiment_score=_round(a.get("sentiment_score")),
        sov_score=_round(a.get("sov_score")),
        citation_score=_round(a.get("citation_score")),
        geo_score=_round(a.get("geo_score")),
        analyzed_at=_iso(a.get("analyzed_at")),
    )


async def _brand_mentions_for_response(
    session: AsyncSession,
    response_id: int,
) -> list[BrandMentionDetail]:
    if not await legacy_table_exists(session, "brand_mentions"):
        return []
    mrows = (
        (
            await session.execute(
                text(
                    """
                    SELECT id, response_id, brand_id, brand_name, product_name, is_target,
                           position_rank, sentiment, sentiment_score, context_snippet,
                           mention_count, created_at
                    FROM brand_mentions
                    WHERE response_id = :response_id
                    ORDER BY COALESCE(position_rank, 9999), id
                    """
                ),
                {"response_id": response_id},
            )
        )
        .mappings()
        .all()
    )
    return [
        BrandMentionDetail(
            mention_id=int(m["id"]),
            response_id=int(m["response_id"]),
            brand_id=_as_int(m.get("brand_id")),
            brand_name=m.get("brand_name") or "",
            product_name=m.get("product_name"),
            is_target=bool(m.get("is_target")) if m.get("is_target") is not None else None,
            position_rank=_as_int(m.get("position_rank")),
            sentiment=m.get("sentiment"),
            sentiment_score=_round(m.get("sentiment_score")),
            context_snippet=m.get("context_snippet"),
            mention_count=_as_int(m.get("mention_count")),
            created_at=_iso(m.get("created_at")),
        )
        for m in mrows
    ]


async def _citations_for_response(
    session: AsyncSession,
    response_id: int,
) -> list[CitationDetail]:
    if not await legacy_table_exists(session, "citation_sources"):
        return []
    crows = (
        (
            await session.execute(
                text(
                    """
                    SELECT id, response_id, mention_id, url, domain, title,
                           citation_index, source_type, created_at
                    FROM citation_sources
                    WHERE response_id = :response_id
                    ORDER BY COALESCE(citation_index, 9999), id
                    """
                ),
                {"response_id": response_id},
            )
        )
        .mappings()
        .all()
    )
    return [
        CitationDetail(
            citation_id=int(c["id"]),
            response_id=int(c["response_id"]),
            mention_id=_as_int(c.get("mention_id")),
            url=c.get("url") or "",
            domain=c.get("domain"),
            title=c.get("title"),
            citation_index=_as_int(c.get("citation_index")),
            source_type=c.get("source_type"),
            created_at=_iso(c.get("created_at")),
        )
        for c in crows
    ]


async def _product_features_for_analysis(
    session: AsyncSession,
    analysis_id: int | None,
) -> list[ProductFeatureAttributeDetail]:
    if analysis_id is None or not await legacy_table_exists(session, "product_feature_mentions"):
        return []
    frows = (
        (
            await session.execute(
                text(
                    """
                    SELECT id, analysis_id, brand_name, product_name, feature_name,
                           feature_sentiment, context_snippet, scenario,
                           price_positioning, created_at
                    FROM product_feature_mentions
                    WHERE analysis_id = :analysis_id
                    ORDER BY id
                    """
                ),
                {"analysis_id": analysis_id},
            )
        )
        .mappings()
        .all()
    )
    return [
        ProductFeatureAttributeDetail(
            feature_id=int(row["id"]),
            analysis_id=_as_int(row.get("analysis_id")),
            brand_name=row.get("brand_name"),
            product_name=row.get("product_name"),
            feature_name=row.get("feature_name"),
            feature_sentiment=row.get("feature_sentiment"),
            context_snippet=row.get("context_snippet"),
            scenario=row.get("scenario"),
            price_positioning=row.get("price_positioning"),
            created_at=_iso(row.get("created_at")),
        )
        for row in frows
    ]


async def _sentiment_drivers_for_response(
    session: AsyncSession,
    response_id: int,
) -> list[SentimentDriverDetail]:
    if not await legacy_table_exists(session, "sentiment_drivers"):
        return []
    drows = (
        (
            await session.execute(
                text(
                    """
                    SELECT id, mention_id, response_id, brand_name, driver_text,
                           polarity, category, strength, source_quote, created_at
                    FROM sentiment_drivers
                    WHERE response_id = :response_id
                    ORDER BY COALESCE(strength, 0) DESC, id
                    """
                ),
                {"response_id": response_id},
            )
        )
        .mappings()
        .all()
    )
    return [
        SentimentDriverDetail(
            driver_id=int(row["id"]),
            mention_id=_as_int(row.get("mention_id")),
            response_id=_as_int(row.get("response_id")),
            brand_name=row.get("brand_name"),
            driver_text=row.get("driver_text") or "",
            polarity=row.get("polarity"),
            category=row.get("category"),
            strength=_round(row.get("strength")),
            source_quote=row.get("source_quote"),
            created_at=_iso(row.get("created_at")),
        )
        for row in drows
    ]


def _coerce_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _relation_response_matches(item: dict[str, Any], response_id: int) -> bool:
    raw_id = item.get("response_id") or item.get("responseId") or item.get("llm_response_id")
    if raw_id is None:
        return True
    return _as_int(raw_id) == response_id


def _json_mentions_response_id(value: Any, response_id: int) -> bool:
    if isinstance(value, dict):
        for key, raw in value.items():
            if key in {"response_id", "responseId", "llm_response_id"}:
                if _as_int(raw) == response_id:
                    return True
            if _json_mentions_response_id(raw, response_id):
                return True
    elif isinstance(value, list):
        return any(_json_mentions_response_id(item, response_id) for item in value)
    return False


def _relation_from_mapping(
    item: dict[str, Any],
    *,
    source: str,
    response_id: int,
) -> ResponseRelationDetail | None:
    relation_type = item.get("type") or item.get("relation_type") or item.get("relationType")
    if not relation_type:
        return None
    return ResponseRelationDetail(
        source=source,
        entity_kind=item.get("entity_kind") or item.get("entityKind"),
        type=str(relation_type),
        a_id=_as_int(item.get("a_id") or item.get("source_id") or item.get("from_id")),
        b_id=_as_int(item.get("b_id") or item.get("target_id") or item.get("to_id")),
        a_name=item.get("a_name") or item.get("source_name") or item.get("from_name"),
        b_name=item.get("b_name") or item.get("target_name") or item.get("to_name"),
        confidence=_round(item.get("confidence")),
        evidence=item.get("evidence") or item.get("quote") or item,
        response_id=response_id,
    )


async def _raw_analysis_relations(
    session: AsyncSession,
    response_id: int,
) -> list[ResponseRelationDetail]:
    if not await legacy_table_exists(session, "response_analyses"):
        return []
    raw = (
        await session.execute(
            text(
                """
                SELECT raw_analysis_json
                FROM response_analyses
                WHERE response_id = :response_id
                LIMIT 1
                """
            ),
            {"response_id": response_id},
        )
    ).scalar_one_or_none()
    payload = _coerce_json(raw)
    relation_items: list[Any] = []
    for key in (
        "relations",
        "response_relations",
        "brand_relations",
        "product_relations",
        "relation_facts",
    ):
        relation_items.extend(_coerce_list(payload.get(key)))

    relations: list[ResponseRelationDetail] = []
    for item in relation_items:
        if not isinstance(item, dict) or not _relation_response_matches(item, response_id):
            continue
        relation = _relation_from_mapping(
            item,
            source="response_analyses.raw_analysis_json",
            response_id=response_id,
        )
        if relation is not None:
            relations.append(relation)
    return relations


async def _kg_candidate_relations(
    session: AsyncSession,
    response_id: int,
) -> list[ResponseRelationDetail]:
    if not await legacy_table_exists(session, "kg_relation_candidates"):
        return []
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT entity_kind, a_id, b_id, type, confidence, evidence
                    FROM kg_relation_candidates
                    ORDER BY created_at DESC, id
                    """
                )
            )
        )
        .mappings()
        .all()
    )
    relations: list[ResponseRelationDetail] = []
    for row in rows:
        evidence = _coerce_json(row.get("evidence"))
        if not _json_mentions_response_id(evidence, response_id):
            continue
        relations.append(
            ResponseRelationDetail(
                source="kg_relation_candidates",
                entity_kind=row.get("entity_kind"),
                type=str(row.get("type") or ""),
                a_id=_as_int(row.get("a_id")),
                b_id=_as_int(row.get("b_id")),
                confidence=_round(row.get("confidence")),
                evidence=evidence,
                response_id=response_id,
            )
        )
    return relations


async def _analyzer_facts_for_response(
    session: AsyncSession,
    response_id: int,
    *,
    brand_mentions: list[BrandMentionDetail] | None = None,
    citations: list[CitationDetail] | None = None,
    analysis: ResponseAnalysisDetail | None = None,
) -> AnalyzerFacts:
    mentions = (
        brand_mentions
        if brand_mentions is not None
        else await _brand_mentions_for_response(session, response_id)
    )
    citation_rows = (
        citations if citations is not None else await _citations_for_response(session, response_id)
    )
    features = await _product_features_for_analysis(
        session,
        analysis.analysis_id if analysis is not None else None,
    )
    drivers = await _sentiment_drivers_for_response(session, response_id)
    relations = await _raw_analysis_relations(session, response_id)
    relations.extend(await _kg_candidate_relations(session, response_id))
    return AnalyzerFacts(
        citations=citation_rows,
        brands_mentioned=mentions,
        products_features_attributes=features,
        relations=relations,
        sentiment_drivers=drivers,
    )


async def get_query_response_detail(
    session: AsyncSession,
    project: Project,
    *,
    query_id: int,
    brand_id_override: int | None = None,
) -> QueryResponseDetailOut:
    if not await _has_admin_chain(session):
        raise not_found("query not found")

    query_cols = await legacy_table_columns(session, "queries")
    prompt_cols = await legacy_table_columns(session, "prompts")
    response_cols = await legacy_table_columns(session, "llm_responses")
    if "id" not in query_cols:
        raise not_found("query not found")

    params: dict[str, Any] = {"query_id": int(query_id)}
    where = ["q.id = :query_id"]

    prompt_join = "LEFT JOIN prompts p ON p.id = q.prompt_id" if "prompt_id" in query_cols else ""
    topic_join = (
        "LEFT JOIN topics t ON t.id = p.topic_id"
        if prompt_join and "topic_id" in prompt_cols
        else ""
    )
    topic_id_select = "t.id AS topic_id" if topic_join else "NULL AS topic_id"
    query_row = (
        (
            await session.execute(
                text(
                    f"""
                SELECT
                    q.id AS query_id,
                    {_select_col(query_cols, "q", "prompt_id", "prompt_id")},
                    {_query_text_expr(query_cols)} AS query_text,
                    {_select_col(query_cols, "q", "target_llm", "target_llm")},
                    {_select_col(query_cols, "q", "status", "status")},
                    {_select_col(query_cols, "q", "profile_id", "profile_id")},
                    {_select_col(query_cols, "q", "created_at", "created_at")},
                    {_select_col(query_cols, "q", "executed_at", "executed_at")},
                    {_select_col(query_cols, "q", "finished_at", "finished_at")},
                    {_select_col(query_cols, "q", "latency_ms", "latency_ms")},
                    {topic_id_select}
                FROM queries q
                {prompt_join}
                {topic_join}
                WHERE {" AND ".join(where)}
                LIMIT 1
                """
                ),
                params,
            )
        )
        .mappings()
        .first()
    )
    if not query_row:
        raise not_found("query not found")
    q = dict(query_row)
    prompt_scope_id = _as_int(q.get("prompt_id"))
    brand_id = _effective_brand_id(project, brand_id_override)
    if brand_id is None:
        raise not_found("query not found")
    scoped_rows = await _fact_rows(
        session,
        project,
        filters=AnalysisFilters(),
        prompt_id=prompt_scope_id,
        brand_id_override=brand_id,
    )
    scoped_rows.sort(key=_row_attempt_sort_key, reverse=True)
    selected_scope_row = next(
        (row for row in scoped_rows if _as_int(row.get("query_id")) == int(query_id)),
        None,
    )
    if selected_scope_row is None:
        raise not_found("query not found")

    response: ResponseDetail | None = None
    analysis: ResponseAnalysisDetail | None = None
    response_id: int | None = None
    if await legacy_table_exists(session, "llm_responses") and "id" in response_cols:
        response_where: list[str] = []
        selected_response_id = _as_int(selected_scope_row.get("response_id"))
        response_params = dict(params)
        if selected_response_id is not None:
            response_where.append("r.id = :selected_response_id")
            response_params["selected_response_id"] = selected_response_id
        elif "query_id" in response_cols:
            response_where.append("r.query_id = :query_id")
        elif _as_int(q.get("prompt_id")) is not None and "prompt_id" in response_cols:
            response_where.append("r.prompt_id = :prompt_id")
            response_params["prompt_id"] = int(q["prompt_id"])
        if response_where:
            rrow = (
                (
                    await session.execute(
                        text(
                            f"""
                        SELECT
                            r.id AS response_id,
                            {_select_col(response_cols, "r", "query_id", "query_id")},
                            {_select_col(response_cols, "r", "prompt_id", "prompt_id")},
                            {_response_text_expr(response_cols)} AS raw_text,
                            {_select_col(response_cols, "r", "target_llm", "target_llm")},
                            {_select_col(response_cols, "r", "intent", "intent")},
                            {_select_col(response_cols, "r", "llm_version", "llm_version")},
                            {_select_col(response_cols, "r", "citations_json", "citations_json")},
                            {_select_col(response_cols, "r", "created_at", "created_at")}
                        FROM llm_responses r
                        WHERE {" OR ".join(response_where)}
                        ORDER BY r.id DESC
                        LIMIT 1
                        """
                        ),
                        response_params,
                    )
                )
                .mappings()
                .first()
            )
            if rrow:
                r = dict(rrow)
                response_id = int(r["response_id"])
                response = ResponseDetail(
                    response_id=response_id,
                    query_id=_as_int(r.get("query_id")),
                    prompt_id=_as_int(r.get("prompt_id")),
                    raw_text=r.get("raw_text"),
                    target_llm=r.get("target_llm"),
                    intent=r.get("intent"),
                    llm_version=r.get("llm_version"),
                    citations_json=r.get("citations_json"),
                    created_at=_iso(r.get("created_at")),
                )

    if response_id is not None and await legacy_table_exists(session, "response_analyses"):
        arow = (
            (
                await session.execute(
                    text(
                        """
                    SELECT id, target_brand_mentioned, target_brand_rank,
                           target_brand_sentiment, visibility_score, sentiment_score,
                           sov_score, citation_score, geo_score, analyzed_at
                    FROM response_analyses
                    WHERE response_id = :response_id
                    LIMIT 1
                    """
                    ),
                    {"response_id": response_id},
                )
            )
            .mappings()
            .first()
        )
        if arow:
            a = dict(arow)
            analysis = ResponseAnalysisDetail(
                analysis_id=_as_int(a.get("id")),
                target_brand_mentioned=bool(a.get("target_brand_mentioned"))
                if a.get("target_brand_mentioned") is not None
                else None,
                target_brand_rank=_as_int(a.get("target_brand_rank")),
                target_brand_sentiment=a.get("target_brand_sentiment"),
                visibility_score=_round(a.get("visibility_score")),
                sentiment_score=_round(a.get("sentiment_score")),
                sov_score=_round(a.get("sov_score")),
                citation_score=_round(a.get("citation_score")),
                geo_score=_round(a.get("geo_score")),
                analyzed_at=_iso(a.get("analyzed_at")),
            )

    brand_mentions: list[BrandMentionDetail] = []
    if response_id is not None and await legacy_table_exists(session, "brand_mentions"):
        mrows = (
            (
                await session.execute(
                    text(
                        """
                    SELECT id, response_id, brand_id, brand_name, product_name, is_target,
                           position_rank, sentiment, sentiment_score, context_snippet,
                           mention_count, created_at
                    FROM brand_mentions
                    WHERE response_id = :response_id
                    ORDER BY COALESCE(position_rank, 9999), id
                    """
                    ),
                    {"response_id": response_id},
                )
            )
            .mappings()
            .all()
        )
        brand_mentions = [
            BrandMentionDetail(
                mention_id=int(m["id"]),
                response_id=int(m["response_id"]),
                brand_id=_as_int(m.get("brand_id")),
                brand_name=m.get("brand_name") or "",
                product_name=m.get("product_name"),
                is_target=bool(m.get("is_target")) if m.get("is_target") is not None else None,
                position_rank=_as_int(m.get("position_rank")),
                sentiment=m.get("sentiment"),
                sentiment_score=_round(m.get("sentiment_score")),
                context_snippet=m.get("context_snippet"),
                mention_count=_as_int(m.get("mention_count")),
                created_at=_iso(m.get("created_at")),
            )
            for m in mrows
        ]

    citations: list[CitationDetail] = []
    if response_id is not None and await legacy_table_exists(session, "citation_sources"):
        crows = (
            (
                await session.execute(
                    text(
                        """
                    SELECT id, response_id, mention_id, url, domain, title,
                           citation_index, source_type, created_at
                    FROM citation_sources
                    WHERE response_id = :response_id
                    ORDER BY COALESCE(citation_index, 9999), id
                    """
                    ),
                    {"response_id": response_id},
                )
            )
            .mappings()
            .all()
        )
        citations = [
            CitationDetail(
                citation_id=int(c["id"]),
                response_id=int(c["response_id"]),
                mention_id=_as_int(c.get("mention_id")),
                url=c.get("url") or "",
                domain=c.get("domain"),
                title=c.get("title"),
                citation_index=_as_int(c.get("citation_index")),
                source_type=c.get("source_type"),
                created_at=_iso(c.get("created_at")),
            )
            for c in crows
        ]

    profile_names = await _profile_names_for_ids(
        session,
        {str(row["profile_id"]) for row in [q, *scoped_rows] if row.get("profile_id") is not None},
    )
    analyzer_facts = (
        await _analyzer_facts_for_response(
            session,
            response_id,
            brand_mentions=brand_mentions,
            citations=citations,
            analysis=analysis,
        )
        if response_id is not None
        else AnalyzerFacts()
    )

    attempt_date = _date_key(_row_attempt_time(selected_scope_row))
    attempt_key = _logical_query_key(selected_scope_row)
    attempt_rows = [
        row
        for row in scoped_rows
        if _logical_query_key(row) == attempt_key
        and _date_key(_row_attempt_time(row)) == attempt_date
        and _as_int(row.get("response_id")) is not None
    ]
    attempt_rows.sort(key=_row_attempt_sort_key, reverse=True)
    attempts: list[ResponseAttemptDetail] = []
    for row in attempt_rows:
        attempt_response_id = _as_int(row.get("response_id"))
        attempt_query_id = _as_int(row.get("query_id"))
        if attempt_response_id is None or attempt_query_id is None:
            continue
        attempt_analysis = await _response_analysis_detail(session, attempt_response_id)
        attempt_citations = await _citations_for_response(session, attempt_response_id)
        attempt_mentions = await _brand_mentions_for_response(session, attempt_response_id)
        attempt_facts = await _analyzer_facts_for_response(
            session,
            attempt_response_id,
            brand_mentions=attempt_mentions,
            citations=attempt_citations,
            analysis=attempt_analysis,
        )
        attempts.append(
            ResponseAttemptDetail(
                query_id=attempt_query_id,
                response_id=attempt_response_id,
                query_text=row.get("query_text"),
                target_llm=row.get("target_llm") or row.get("response_target_llm"),
                status=str(row.get("query_status")).lower() if row.get("query_status") else None,
                profile_id=str(row.get("profile_id"))
                if row.get("profile_id") is not None
                else None,
                profile_name=_profile_name(row.get("profile_id"), profile_names),
                executed_at=_iso(row.get("query_executed_at")),
                finished_at=_iso(row.get("query_finished_at")),
                latency_ms=_as_int(row.get("latency_ms")),
                response=ResponseDetail(
                    response_id=attempt_response_id,
                    query_id=attempt_query_id,
                    prompt_id=_as_int(row.get("prompt_id")),
                    raw_text=row.get("response_raw_text"),
                    target_llm=row.get("response_target_llm") or row.get("target_llm"),
                    intent=row.get("response_intent"),
                    llm_version=row.get("response_llm_version"),
                    citations_json=None,
                    created_at=_iso(row.get("response_created_at")),
                ),
                analysis=attempt_analysis,
                citations=attempt_citations,
                analyzer_facts=attempt_facts,
            )
        )

    query = QueryDetail(
        query_id=int(q["query_id"]),
        prompt_id=_as_int(q.get("prompt_id")),
        topic_id=_as_int(q.get("topic_id")),
        query_text=q.get("query_text"),
        target_llm=q.get("target_llm"),
        status=(str(q.get("status")).lower() if q.get("status") else None),
        profile_id=str(q.get("profile_id")) if q.get("profile_id") is not None else None,
        profile_name=_profile_name(q.get("profile_id"), profile_names),
        created_at=_iso(q.get("created_at")),
        executed_at=_iso(q.get("executed_at")),
        finished_at=_iso(q.get("finished_at")),
        latency_ms=_as_int(q.get("latency_ms")),
    )
    from app.api.v1.projects._analytics_contract import build_contract_context

    selected_day_raw = _date_key(
        selected_scope_row.get("response_created_at")
        or selected_scope_row.get("query_finished_at")
        or selected_scope_row.get("query_created_at")
    )
    selected_day = (
        date.fromisoformat(selected_day_raw)
        if selected_day_raw is not None
        else datetime.now().date()
    )
    contract = await build_contract_context(
        session,
        project,
        brand_id=brand_id,
        from_date=selected_day,
        to_date=selected_day,
        has_data=response is not None,
        base_state="ok" if response is not None else "partial",
        base_state_reason="data_available" if response is not None else "missing_response",
        selected_filters={"query_id": int(query_id), "response_id": response_id},
        target_response_ids={response_id} if response_id is not None else None,
        source_provenance=[
            "admin_facts",
            "response_analyses",
            "brand_mentions",
            "citation_sources",
        ],
    )
    coverage = dict(contract.metric_formula_evidence.get("coverage") or {})
    coverage.update(
        {
            key: value
            for key, value in contract.evidence_counts.items()
            if key.startswith("analyzer_")
        }
    )
    return QueryResponseDetailOut(
        project_id=project.id,
        query=query,
        response=response,
        analysis=analysis,
        brand_mentions=brand_mentions,
        citations=citations,
        analyzer_facts=analyzer_facts,
        attempts=attempts,
        state="ok" if response is not None else "partial",
        formula_status=contract.formula_status,
        metric_formula_evidence=contract.metric_formula_evidence,
        selected_filters=contract.selected_filters,
        missing_reasons=contract.missing_reasons,
        analyzer_coverage=coverage,
    )


async def get_query_activity(
    session: AsyncSession,
    project: Project,
    *,
    filters: AnalysisFilters,
    brand_id_override: int | None = None,
) -> QueryActivityOut:
    from_d, to_d = _resolve_window(filters)
    brand_id = _effective_brand_id(project, brand_id_override)
    if brand_id is None:
        return QueryActivityOut(
            project_id=project.id,
            brand_id=None,
            period=_period(from_d, to_d),
            totals={
                "queries": 0,
                "responses": 0,
                "analyzed": 0,
                "mentions_target": 0,
                "mention_denominator": 0,
            },
            state="empty",
        )
    effective_filters = filters
    if filters.from_date is None and filters.to_date is None:
        effective_filters = AnalysisFilters(
            from_date=from_d,
            to_date=to_d,
            engines=filters.engines,
            segment_id=filters.segment_id,
            profile_id=filters.profile_id,
            dimensions=filters.dimensions,
            intents=filters.intents,
            prompt_scope=filters.prompt_scope,
        )
    rows = await _fact_rows(
        session,
        project,
        filters=effective_filters,
        brand_id_override=brand_id,
        successful_responses_only=False,
    )

    query_ids: set[int] = set()
    response_ids: set[int] = set()
    analysis_ids: set[int] = set()
    mention_response_ids: set[int] = set()
    mention_denominator_response_ids: set[int] = set()
    status_counts: Counter[str] = Counter()
    sentiment = {"positive": 0, "neutral": 0, "negative": 0}
    positions = {"Top1": 0, "Top3": 0, "Top5": 0, "Top10": 0, "Other": 0}
    engine_bucket: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "queries": set(),
            "responses": set(),
            "mention_denominator": set(),
            "target_mention_responses": set(),
            "geo": [],
        }
    )
    topic_bucket: OrderedDict[int, dict[str, Any]] = OrderedDict()
    daily_bucket: dict[str, dict[str, int]] = defaultdict(
        lambda: {"queries": 0, "responses": 0, "target_mentions": 0, "mention_denominator": 0}
    )

    seen_response_metrics: set[int] = set()
    seen_query_status: set[int] = set()
    seen_query_daily: set[int] = set()
    for row in rows:
        qid = _as_int(row.get("query_id"))
        if qid is None:
            continue
        query_ids.add(qid)
        if qid not in seen_query_status:
            status = str(row.get("query_status") or "unknown").lower()
            status_counts[status] += 1
            seen_query_status.add(qid)
        engine = str(row.get("target_llm") or row.get("response_target_llm") or "unknown")
        engine_bucket[engine]["queries"].add(qid)
        tid = _as_int(row.get("topic_id"))
        if tid is not None and tid not in topic_bucket:
            topic_bucket[tid] = {
                "topic_name": row.get("topic_name") or f"topic-{tid}",
                "queries": set(),
                "responses": set(),
                "mention_denominator": set(),
                "target_mention_responses": set(),
            }
        if tid is not None:
            topic_bucket[tid]["queries"].add(qid)
        day = _date_key(row.get("query_created_at"))
        if day and qid not in seen_query_daily:
            daily_bucket[day]["queries"] += 1
            seen_query_daily.add(qid)

        rid = _as_int(row.get("response_id"))
        if rid is None or rid in seen_response_metrics:
            continue
        seen_response_metrics.add(rid)
        response_ids.add(rid)
        engine_bucket[engine]["responses"].add(rid)
        if tid is not None:
            topic_bucket[tid]["responses"].add(rid)
        aid = _as_int(row.get("analysis_id"))
        if aid is not None:
            analysis_ids.add(aid)
        target_mentions = _fact_target_mention_count(row)
        is_non_branded = _is_non_branded_row(row)
        if is_non_branded:
            mention_denominator_response_ids.add(rid)
            engine_bucket[engine]["mention_denominator"].add(rid)
            if tid is not None:
                topic_bucket[tid]["mention_denominator"].add(rid)
        if target_mentions and is_non_branded:
            mention_response_ids.add(rid)
            engine_bucket[engine]["target_mention_responses"].add(rid)
            if tid is not None:
                topic_bucket[tid]["target_mention_responses"].add(rid)
        geo = _as_float(row.get("geo_score"))
        if geo is not None:
            engine_bucket[engine]["geo"].append(geo)
        sentiment["positive"] += int(row.get("positive_mentions") or 0)
        sentiment["neutral"] += int(row.get("neutral_mentions") or 0)
        sentiment["negative"] += int(row.get("negative_mentions") or 0)
        bucket = _bucket_position(_as_int(row.get("min_position_rank")))
        if bucket:
            positions[bucket] += 1
        if day:
            daily_bucket[day]["responses"] += 1
            if is_non_branded:
                daily_bucket[day]["mention_denominator"] += 1
                if target_mentions:
                    daily_bucket[day]["target_mentions"] += 1

    by_engine = [
        QueryActivityEngineRow(
            engine=engine,
            query_count=len(values["queries"]),
            response_count=len(values["responses"]),
            mention_rate=_pct(
                len(values["target_mention_responses"]),
                len(values["mention_denominator"]),
            ),
            avg_geo_score=_mean(values["geo"]),
        )
        for engine, values in sorted(engine_bucket.items())
    ]
    by_topic = [
        QueryActivityTopicRow(
            topic_id=tid,
            topic_name=values["topic_name"],
            query_count=len(values["queries"]),
            response_count=len(values["responses"]),
            mention_rate=_pct(
                len(values["target_mention_responses"]),
                len(values["mention_denominator"]),
            ),
        )
        for tid, values in topic_bucket.items()
        if values["queries"]
    ]
    by_topic.sort(key=lambda item: (-item.query_count, item.topic_id))
    daily = [
        QueryActivityDailyRow(
            date=day,
            queries=values["queries"],
            responses=values["responses"],
            target_mentions=values["target_mentions"],
            mention_denominator=values["mention_denominator"],
        )
        for day, values in sorted(daily_bucket.items())
    ]
    return QueryActivityOut(
        project_id=project.id,
        brand_id=brand_id,
        period=_period(from_d, to_d),
        totals={
            "queries": len(query_ids),
            "responses": len(response_ids),
            "analyzed": len(analysis_ids),
            "mentions_target": len(mention_response_ids),
            "mention_denominator": len(mention_denominator_response_ids),
        },
        by_status=dict(status_counts),
        by_engine=by_engine,
        by_topic=by_topic,
        daily=daily,
        sentiment_distribution=sentiment,
        position_distribution=positions,
        state="ok" if query_ids else "empty",
    )


async def get_project_segments(
    session: AsyncSession,
    project: Project,
    *,
    brand_id_override: int | None = None,
) -> ProjectSegmentsOut:
    if not await legacy_table_exists(session, "segments"):
        return ProjectSegmentsOut(project_id=project.id, items=[], total=0, state="empty")
    if not await legacy_table_exists(session, "profiles"):
        return ProjectSegmentsOut(project_id=project.id, items=[], total=0, state="empty")

    segment_cols = await legacy_table_columns(session, "segments")
    profile_cols = await legacy_table_columns(session, "profiles")
    if not {"id", "name"}.issubset(segment_cols):
        return ProjectSegmentsOut(project_id=project.id, items=[], total=0, state="empty")

    where = ["1 = 1"]
    params: dict[str, Any] = {}
    brand_id = _effective_brand_id(project, brand_id_override)
    if "is_deleted" in segment_cols:
        where.append(_not_deleted_condition("s"))
    if brand_id is not None and "brand_id" in segment_cols:
        where.append("(s.brand_id IS NULL OR CAST(s.brand_id AS TEXT) = :brand_id)")
        params["brand_id"] = str(brand_id)

    profile_join = ""
    profile_selects = [
        "NULL AS profile_id",
        "NULL AS profile_name",
        "NULL AS profile_status",
        "NULL AS profile_demographic",
        "NULL AS profile_need",
        "NULL AS profile_weight",
    ]
    if {"id", "segment_id", "name"}.issubset(profile_cols):
        profile_conditions = ["CAST(p.segment_id AS TEXT) = CAST(s.id AS TEXT)"]
        if "is_deleted" in profile_cols:
            profile_conditions.append(_not_deleted_condition("p"))
        if brand_id is not None and "brand_id" in profile_cols:
            profile_conditions.append(
                "(p.brand_id IS NULL OR CAST(p.brand_id AS TEXT) = :brand_id)"
            )
        profile_join = f"LEFT JOIN profiles p ON {' AND '.join(profile_conditions)}"
        profile_selects = [
            "p.id AS profile_id",
            "p.name AS profile_name",
            _select_col(profile_cols, "p", "status", "profile_status"),
            _select_col(profile_cols, "p", "demographic", "profile_demographic"),
            _select_col(profile_cols, "p", "need", "profile_need"),
            _select_col(profile_cols, "p", "weight", "profile_weight"),
        ]

    rows = (
        (
            await session.execute(
                text(
                    f"""
                SELECT
                    s.id AS segment_id,
                    {_select_col(segment_cols, "s", "code", "segment_code")},
                    s.name AS segment_name,
                    {_select_col(segment_cols, "s", "status", "segment_status")},
                    {_select_col(segment_cols, "s", "weight", "segment_weight")},
                    {", ".join(profile_selects)}
                FROM segments s
                {profile_join}
                WHERE {" AND ".join(where)}
                ORDER BY s.name, s.id
                """
                ),
                params,
            )
        )
        .mappings()
        .all()
    )

    segments: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for row in rows:
        sid = str(row["segment_id"])
        if sid not in segments:
            segments[sid] = {
                "segment_id": sid,
                "code": row.get("segment_code"),
                "name": row.get("segment_name") or sid,
                "status": row.get("segment_status"),
                "weight": row.get("segment_weight"),
                "profiles": [],
            }
        if row.get("profile_id") is not None:
            pstatus = row.get("profile_status")
            segments[sid]["profiles"].append(
                ProjectProfileRow(
                    profile_id=str(row["profile_id"]),
                    name=row.get("profile_name") or str(row["profile_id"]),
                    status=pstatus,
                    demographic=row.get("profile_demographic"),
                    need=row.get("profile_need"),
                    weight=_round(row.get("profile_weight"), 4),
                )
            )

    items = [
        ProjectSegmentRow(
            segment_id=sid,
            code=v["code"],
            name=v["name"],
            status=v["status"],
            weight=_round(v["weight"], 4),
            active_profile_count=sum(
                1 for profile in v["profiles"] if (profile.status or "active") == "active"
            ),
            profiles=v["profiles"],
        )
        for sid, v in segments.items()
    ]
    return ProjectSegmentsOut(
        project_id=project.id,
        items=items,
        total=len(items),
        state="ok" if items else "empty",
    )


def decimal_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    return value
