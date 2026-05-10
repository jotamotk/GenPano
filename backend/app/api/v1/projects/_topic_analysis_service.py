"""Project-scoped analytics over Admin Topic -> Prompt -> Query -> Response data."""

from __future__ import annotations

import re
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from genpano_models import Project
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._topic_analysis_dto import (
    BrandMentionDetail,
    CitationDetail,
    ProjectProfileRow,
    ProjectSegmentRow,
    ProjectSegmentsOut,
    PromptQueriesOut,
    PromptQueryRow,
    QueryActivityDailyRow,
    QueryActivityEngineRow,
    QueryActivityOut,
    QueryActivityTopicRow,
    QueryDetail,
    QueryResponseDetailOut,
    ResponseAnalysisDetail,
    ResponseDetail,
    TopicIntentMatrixRow,
    TopicMonitoringOut,
    TopicMonitoringRow,
    TopicMonitoringSummary,
    TopicPromptRow,
    TopicPromptsOut,
)
from app.core.errors import not_found

DEFAULT_WINDOW_DAYS = 30
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class AnalysisFilters:
    from_date: date | None = None
    to_date: date | None = None
    engines: tuple[str, ...] | None = None
    segment_id: str | None = None
    profile_id: str | None = None

    @property
    def explicit(self) -> bool:
        return any(
            [
                self.from_date is not None,
                self.to_date is not None,
                bool(self.engines),
                bool(self.segment_id),
                bool(self.profile_id),
            ]
        )


def _resolve_window(filters: AnalysisFilters) -> tuple[date, date]:
    today = date.today()
    to_d = filters.to_date or today
    from_d = filters.from_date or (to_d - timedelta(days=DEFAULT_WINDOW_DAYS - 1))
    if from_d > to_d:
        from_d, to_d = to_d, from_d
    return from_d, to_d


def _period(from_d: date, to_d: date) -> dict[str, str]:
    return {"from": from_d.isoformat(), "to": to_d.isoformat()}


def _dt_range(from_d: date, to_d: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(from_d, datetime.min.time()),
        datetime.combine(to_d, datetime.max.time()),
    )


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def _date_key(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _round(value: Any, digits: int = 4) -> float | None:
    num = _as_float(value)
    return round(num, digits) if num is not None else None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _pct(numerator: int | float, denominator: int | float, digits: int = 4) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), digits)


def _safe_ident(name: str) -> str:
    if not _IDENT_RE.match(name):
        raise ValueError(f"unsafe identifier: {name}")
    return name


async def legacy_table_exists(session: AsyncSession, name: str) -> bool:
    """Portable table existence probe for Postgres and sqlite tests."""
    _safe_ident(name)
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
                text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = :n LIMIT 1"),
                {"n": name},
            )
        ).first()
        return row is not None
    except Exception:
        return False


async def legacy_table_columns(session: AsyncSession, name: str) -> set[str]:
    """Return table columns without assuming a SQL dialect."""
    name = _safe_ident(name)
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
        cols = {str(r[0]) for r in rows}
        if cols:
            return cols
    except Exception:
        pass
    try:
        rows = (await session.execute(text(f"PRAGMA table_info({name})"))).all()
        return {str(r[1]) for r in rows}
    except Exception:
        return set()


def _select_col(
    cols: set[str],
    alias: str,
    column: str,
    out_name: str,
    default: str = "NULL",
) -> str:
    return f"{alias}.{column} AS {out_name}" if column in cols else f"{default} AS {out_name}"


def _topic_name_expr(cols: set[str]) -> str:
    if "text" in cols:
        return "t.text"
    if "name" in cols:
        return "t.name"
    if "title" in cols:
        return "t.title"
    return "CAST(t.id AS TEXT)"


def _prompt_text_expr(cols: set[str]) -> str:
    if "text" in cols:
        return "p.text"
    if "prompt_text" in cols:
        return "p.prompt_text"
    return "NULL"


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
) -> tuple[list[str], dict[str, Any]]:
    params: dict[str, Any] = {}
    conditions: list[str] = []

    if project.primary_brand_id is not None and "brand_id" in query_cols:
        conditions.append(f"{prefix}.brand_id = :primary_brand_id")
        params["primary_brand_id"] = int(project.primary_brand_id)

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
            conditions.append(f"CAST({prefix}.profile_id AS TEXT) = :profile_id")
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


def _empty_monitoring(project: Project, state: str = "empty") -> TopicMonitoringOut:
    return TopicMonitoringOut(
        project_id=project.id,
        brand_id=project.primary_brand_id,
        summary=TopicMonitoringSummary(),
        topics=[],
        intent_matrix=[],
        state=state,
    )


def _bucket_position(rank: int | None) -> str | None:
    if rank is None:
        return None
    if rank == 1:
        return "Top1"
    if rank <= 3:
        return "Top3"
    if rank <= 5:
        return "Top5"
    if rank <= 10:
        return "Top10"
    return "Other"


async def _fact_rows(
    session: AsyncSession,
    project: Project,
    *,
    filters: AnalysisFilters,
    topic_id: int | None = None,
    prompt_id: int | None = None,
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

    params: dict[str, Any] = {}
    topic_where: list[str] = []
    if project.primary_brand_id is not None and "brand_id" in topic_cols:
        topic_where.append("t.brand_id = :topic_brand_id")
        params["topic_brand_id"] = int(project.primary_brand_id)
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
    )
    query_join_conditions.extend(scoped_conditions)
    params.update(scoped_params)

    response_join = ""
    response_selects = [
        "NULL AS response_id",
        "NULL AS response_raw_text",
        "NULL AS response_target_llm",
        "NULL AS response_intent",
        "NULL AS response_llm_version",
        "NULL AS response_created_at",
    ]
    if has_responses:
        response_on: list[str] = []
        if "query_id" in response_cols:
            response_on.append("r.query_id = q.id")
        if not response_on and "prompt_id" in response_cols:
            response_on.append("r.prompt_id = p.id")
        if response_on:
            response_join = f"LEFT JOIN llm_responses r ON {' OR '.join(response_on)}"
            response_selects = [
                "r.id AS response_id",
                f"{_response_text_expr(response_cols)} AS response_raw_text",
                _select_col(response_cols, "r", "target_llm", "response_target_llm"),
                _select_col(response_cols, "r", "intent", "response_intent"),
                _select_col(response_cols, "r", "llm_version", "response_llm_version"),
                _select_col(response_cols, "r", "created_at", "response_created_at"),
            ]

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

    primary = int(project.primary_brand_id) if project.primary_brand_id is not None else None
    params["primary_brand_id"] = primary
    mention_selects = [
        "0 AS target_mention_count",
        "0 AS all_mention_count",
        "NULL AS min_position_rank",
        "0 AS positive_mentions",
        "0 AS neutral_mentions",
        "0 AS negative_mentions",
        "NULL AS negative_sample_snippet",
    ]
    if has_mentions and response_join and primary is not None:
        mention_selects = [
            "(SELECT COUNT(*) FROM brand_mentions bm "
            "WHERE bm.response_id = r.id AND bm.brand_id = :primary_brand_id) "
            "AS target_mention_count",
            "(SELECT COUNT(*) FROM brand_mentions bm WHERE bm.response_id = r.id) "
            "AS all_mention_count",
            "(SELECT MIN(bm.position_rank) FROM brand_mentions bm "
            "WHERE bm.response_id = r.id AND bm.brand_id = :primary_brand_id) "
            "AS min_position_rank",
            "(SELECT COUNT(*) FROM brand_mentions bm WHERE bm.response_id = r.id "
            "AND bm.brand_id = :primary_brand_id "
            "AND LOWER(COALESCE(bm.sentiment, 'neutral')) = 'positive') "
            "AS positive_mentions",
            "(SELECT COUNT(*) FROM brand_mentions bm WHERE bm.response_id = r.id "
            "AND bm.brand_id = :primary_brand_id "
            "AND LOWER(COALESCE(bm.sentiment, 'neutral')) = 'neutral') "
            "AS neutral_mentions",
            "(SELECT COUNT(*) FROM brand_mentions bm WHERE bm.response_id = r.id "
            "AND bm.brand_id = :primary_brand_id "
            "AND LOWER(COALESCE(bm.sentiment, 'neutral')) = 'negative') "
            "AS negative_mentions",
            "(SELECT bm.context_snippet FROM brand_mentions bm WHERE bm.response_id = r.id "
            "AND bm.brand_id = :primary_brand_id "
            "AND LOWER(COALESCE(bm.sentiment, 'neutral')) = 'negative' "
            "AND bm.context_snippet IS NOT NULL "
            "ORDER BY bm.id LIMIT 1) AS negative_sample_snippet",
        ]

    citation_select = "0 AS citation_count"
    if has_citations and response_join and has_mentions and primary is not None:
        citation_select = (
            "(SELECT COUNT(*) FROM citation_sources cs "
            "WHERE cs.response_id = r.id "
            "AND (cs.mention_id IS NULL OR cs.mention_id IN ("
            "SELECT bm.id FROM brand_mentions bm "
            "WHERE bm.response_id = r.id AND bm.brand_id = :primary_brand_id"
            "))) AS citation_count"
        )
    elif has_citations and response_join:
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
    return [dict(r) for r in rows]


def _topic_aggregates(
    rows: list[dict[str, Any]],
    *,
    project: Project,
    filters: AnalysisFilters,
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
                "status": row.get("topic_status"),
                "prompt_ids": set(),
                "query_ids": set(),
                "response_ids": set(),
                "analysis_ids": set(),
                "success_count": 0,
                "engines": set(),
                "target_mentions": 0,
                "all_mentions": 0,
                "citation_count": 0,
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
            target_mentions = int(row.get("target_mention_count") or 0)
            all_mentions = int(row.get("all_mention_count") or 0)
            bucket["target_mentions"] += target_mentions
            bucket["all_mentions"] += all_mentions
            bucket["citation_count"] += int(row.get("citation_count") or 0)
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
        items.append(
            TopicMonitoringRow(
                topic_id=tid,
                topic_name=bucket["topic_name"],
                dimension=bucket["dimension"],
                status=bucket["status"],
                prompt_count=prompt_count,
                query_count=query_count,
                response_count=response_count,
                success_rate=_pct(bucket["success_count"], query_count),
                engine_coverage=sorted(bucket["engines"]),
                mention_rate=_pct(target_mentions, response_count),
                sov=_pct(target_mentions, all_mentions),
                avg_rank=_mean(bucket["ranks"]),
                avg_geo_score=_mean(bucket["geo_scores"]),
                sentiment_distribution=bucket["sentiment"],
                citation_rate=_pct(citations, response_count),
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
) -> TopicMonitoringOut:
    if project.primary_brand_id is None:
        return _empty_monitoring(project)
    rows = await _fact_rows(session, project, filters=filters)
    topics, summary, intent_matrix = _topic_aggregates(rows, project=project, filters=filters)
    return TopicMonitoringOut(
        project_id=project.id,
        brand_id=project.primary_brand_id,
        summary=summary,
        topics=topics,
        intent_matrix=intent_matrix,
        state="ok" if summary.query_count or (topics and not filters.explicit) else "empty",
    )


async def get_topic_prompts(
    session: AsyncSession,
    project: Project,
    *,
    topic_id: int,
    filters: AnalysisFilters,
) -> TopicPromptsOut:
    rows = await _fact_rows(session, project, filters=filters, topic_id=topic_id)
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
                "query_ids": set(),
                "responses": set(),
                "success_count": 0,
                "engines": set(),
                "target_mentions": 0,
                "citations": 0,
                "ranks": [],
                "geo_scores": [],
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
            bucket["target_mentions"] += int(row.get("target_mention_count") or 0)
            bucket["citations"] += int(row.get("citation_count") or 0)
            rank = _as_int(row.get("min_position_rank") or row.get("target_brand_rank"))
            if rank is not None:
                bucket["ranks"].append(float(rank))
            geo = _as_float(row.get("geo_score"))
            if geo is not None:
                bucket["geo_scores"].append(geo)

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
            query_count=len(b["query_ids"]),
            response_count=len(b["responses"]),
            success_rate=_pct(b["success_count"], len(b["query_ids"])),
            engine_coverage=sorted(b["engines"]),
            mention_rate=_pct(b["target_mentions"], len(b["responses"])),
            avg_rank=_mean(b["ranks"]),
            avg_geo_score=_mean(b["geo_scores"]),
            citation_rate=_pct(b["citations"], len(b["responses"])),
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
) -> PromptQueriesOut:
    rows = await _fact_rows(session, project, filters=filters, prompt_id=prompt_id)
    by_query: OrderedDict[int, dict[str, Any]] = OrderedDict()
    for row in rows:
        qid = _as_int(row.get("query_id"))
        if qid is None:
            continue
        if qid not in by_query:
            by_query[qid] = row
    items = [
        PromptQueryRow(
            query_id=qid,
            prompt_id=_as_int(row.get("prompt_id")),
            query_text=row.get("query_text"),
            target_llm=row.get("target_llm"),
            status=(str(row.get("query_status")).lower() if row.get("query_status") else None),
            profile_id=str(row.get("profile_id")) if row.get("profile_id") is not None else None,
            created_at=_iso(row.get("query_created_at")),
            executed_at=_iso(row.get("query_executed_at")),
            finished_at=_iso(row.get("query_finished_at")),
            latency_ms=_as_int(row.get("latency_ms")),
            response_id=_as_int(row.get("response_id")),
            target_mentioned=bool(int(row.get("target_mention_count") or 0)),
            citation_count=int(row.get("citation_count") or 0),
            geo_score=_round(row.get("geo_score")),
            sentiment_score=_round(row.get("sentiment_score")),
        )
        for qid, row in by_query.items()
    ]
    return PromptQueriesOut(
        project_id=project.id,
        prompt_id=prompt_id,
        items=items,
        total=len(items),
        state="ok" if items else "empty",
    )


async def get_query_response_detail(
    session: AsyncSession,
    project: Project,
    *,
    query_id: int,
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
    if project.primary_brand_id is not None and "brand_id" in query_cols:
        where.append("q.brand_id = :primary_brand_id")
        params["primary_brand_id"] = int(project.primary_brand_id)

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

    response: ResponseDetail | None = None
    analysis: ResponseAnalysisDetail | None = None
    response_id: int | None = None
    if await legacy_table_exists(session, "llm_responses") and "id" in response_cols:
        response_where: list[str] = []
        if "query_id" in response_cols:
            response_where.append("r.query_id = :query_id")
        elif _as_int(q.get("prompt_id")) is not None and "prompt_id" in response_cols:
            response_where.append("r.prompt_id = :prompt_id")
            params["prompt_id"] = int(q["prompt_id"])
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
                        params,
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

    query = QueryDetail(
        query_id=int(q["query_id"]),
        prompt_id=_as_int(q.get("prompt_id")),
        topic_id=_as_int(q.get("topic_id")),
        query_text=q.get("query_text"),
        target_llm=q.get("target_llm"),
        status=(str(q.get("status")).lower() if q.get("status") else None),
        profile_id=str(q.get("profile_id")) if q.get("profile_id") is not None else None,
        created_at=_iso(q.get("created_at")),
        executed_at=_iso(q.get("executed_at")),
        finished_at=_iso(q.get("finished_at")),
        latency_ms=_as_int(q.get("latency_ms")),
    )
    return QueryResponseDetailOut(
        project_id=project.id,
        query=query,
        response=response,
        analysis=analysis,
        brand_mentions=brand_mentions,
        citations=citations,
        state="ok" if response is not None else "partial",
    )


async def get_query_activity(
    session: AsyncSession,
    project: Project,
    *,
    filters: AnalysisFilters,
) -> QueryActivityOut:
    from_d, to_d = _resolve_window(filters)
    if project.primary_brand_id is None:
        return QueryActivityOut(
            project_id=project.id,
            brand_id=None,
            period=_period(from_d, to_d),
            totals={"queries": 0, "responses": 0, "analyzed": 0, "mentions_target": 0},
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
        )
    rows = await _fact_rows(session, project, filters=effective_filters)

    query_ids: set[int] = set()
    response_ids: set[int] = set()
    analysis_ids: set[int] = set()
    mention_response_ids: set[int] = set()
    status_counts: Counter[str] = Counter()
    sentiment = {"positive": 0, "neutral": 0, "negative": 0}
    positions = {"Top1": 0, "Top3": 0, "Top5": 0, "Top10": 0, "Other": 0}
    engine_bucket: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"queries": set(), "responses": set(), "mentions": 0, "geo": []}
    )
    topic_bucket: OrderedDict[int, dict[str, Any]] = OrderedDict()
    daily_bucket: dict[str, dict[str, int]] = defaultdict(
        lambda: {"queries": 0, "responses": 0, "target_mentions": 0}
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
                "mentions": 0,
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
        target_mentions = int(row.get("target_mention_count") or 0)
        if target_mentions:
            mention_response_ids.add(rid)
        engine_bucket[engine]["mentions"] += target_mentions
        if tid is not None:
            topic_bucket[tid]["mentions"] += target_mentions
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
            daily_bucket[day]["target_mentions"] += target_mentions

    by_engine = [
        QueryActivityEngineRow(
            engine=engine,
            query_count=len(values["queries"]),
            response_count=len(values["responses"]),
            mention_rate=_pct(values["mentions"], len(values["responses"])),
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
            mention_rate=_pct(values["mentions"], len(values["responses"])),
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
        )
        for day, values in sorted(daily_bucket.items())
    ]
    return QueryActivityOut(
        project_id=project.id,
        brand_id=project.primary_brand_id,
        period=_period(from_d, to_d),
        totals={
            "queries": len(query_ids),
            "responses": len(response_ids),
            "analyzed": len(analysis_ids),
            "mentions_target": len(mention_response_ids),
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
    if "is_deleted" in segment_cols:
        where.append(
            "(s.is_deleted IS NULL OR s.is_deleted = 0 "
            "OR LOWER(CAST(s.is_deleted AS TEXT)) = 'false')"
        )
    if project.primary_brand_id is not None and "brand_id" in segment_cols:
        where.append("(s.brand_id IS NULL OR CAST(s.brand_id AS TEXT) = :brand_id)")
        params["brand_id"] = str(project.primary_brand_id)

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
            profile_conditions.append(
                "(p.is_deleted IS NULL OR p.is_deleted = 0 "
                "OR LOWER(CAST(p.is_deleted AS TEXT)) = 'false')"
            )
        if project.primary_brand_id is not None and "brand_id" in profile_cols:
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
