"""Async response-id queries for the analytics contract layer.

Phase 5 of splitting `_analytics_contract.py` (Epic #885, design #888).
Hosts the three async response-id selectors:

- `_target_response_ids`: target brand mentions in window
- `_pinned_topic_response_ids`: dialed-down to pinned-topic queries
- `_project_eligible_response_ids`: project-scoped eligibility composing
  the two above
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from genpano_models import BrandMention, Project, ProjectTopicPin
from sqlalchemy import and_, bindparam, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.projects._mention_rollups import brand_mention_match_condition
from app.api.v1.projects._topic_analysis_service import (
    AnalysisFilters,
    _fact_rows,
    legacy_table_columns,
    legacy_table_exists,
)


async def _target_response_ids(
    session: AsyncSession,
    brand_id: int,
    *,
    from_dt: datetime,
    to_dt: datetime,
) -> set[int]:
    brand_filter = await brand_mention_match_condition(session, brand_id)
    rows = (
        await session.execute(
            select(BrandMention.response_id).where(
                and_(
                    brand_filter,
                    BrandMention.created_at >= from_dt,
                    BrandMention.created_at <= to_dt,
                )
            )
        )
    ).all()
    return {int(row[0]) for row in rows if row[0] is not None}


async def _pinned_topic_response_ids(
    session: AsyncSession,
    project: Project,
    *,
    from_date: date,
    to_date: date,
) -> set[int] | None:
    if not all(
        [
            await legacy_table_exists(session, "topics"),
            await legacy_table_exists(session, "prompts"),
            await legacy_table_exists(session, "queries"),
            await legacy_table_exists(session, "llm_responses"),
        ]
    ):
        return None
    topic_ids = [
        int(row[0])
        for row in (
            await session.execute(
                select(ProjectTopicPin.topic_id).where(
                    and_(
                        ProjectTopicPin.project_id == project.id,
                        ProjectTopicPin.state != "ignored",
                    )
                )
            )
        ).all()
        if row[0] is not None
    ]
    if not topic_ids:
        return None

    topic_cols = await legacy_table_columns(session, "topics")
    prompt_cols = await legacy_table_columns(session, "prompts")
    query_cols = await legacy_table_columns(session, "queries")
    response_cols = await legacy_table_columns(session, "llm_responses")
    if not (
        {"id"}.issubset(topic_cols)
        and {"id", "topic_id"}.issubset(prompt_cols)
        and {"id", "prompt_id"}.issubset(query_cols)
        and "id" in response_cols
    ):
        return set()

    response_on: list[str] = []
    if "query_id" in response_cols:
        response_on.append("r.query_id = q.id")
    if not response_on and "prompt_id" in response_cols:
        response_on.append("r.prompt_id = p.id")
    if not response_on:
        return set()

    predicates = ["t.id IN :topic_ids"]
    params: dict[str, Any] = {
        "topic_ids": topic_ids,
        "from_dt": datetime.combine(from_date, datetime.min.time()),
        "to_dt": datetime.combine(to_date, datetime.max.time()),
    }
    if "status" in topic_cols:
        predicates.append("COALESCE(t.status, 'active') <> 'archived'")
    if "status" in prompt_cols:
        predicates.append("COALESCE(p.status, 'active') <> 'archived'")
    if "status" in query_cols:
        predicates.append(
            "LOWER(COALESCE(q.status, 'done')) IN ('done', 'success', 'succeeded', 'completed')"
        )
    if "created_at" in query_cols:
        predicates.append("q.created_at >= :from_dt")
        predicates.append("q.created_at <= :to_dt")
    elif "created_at" in response_cols:
        predicates.append("r.created_at >= :from_dt")
        predicates.append("r.created_at <= :to_dt")

    rows = (
        await session.execute(
            text(
                f"""
                SELECT DISTINCT r.id
                FROM topics t
                JOIN prompts p ON p.topic_id = t.id
                JOIN queries q ON q.prompt_id = p.id
                JOIN llm_responses r ON {" OR ".join(response_on)}
                WHERE {" AND ".join(predicates)}
                """
            ).bindparams(bindparam("topic_ids", expanding=True)),
            params,
        )
    ).all()
    return {int(row[0]) for row in rows if row[0] is not None}


async def _project_eligible_response_ids(
    session: AsyncSession,
    project: Project,
    brand_id: int,
    *,
    from_date: date,
    to_date: date,
    from_dt: datetime,
    to_dt: datetime,
) -> set[int]:
    pinned_response_ids = await _pinned_topic_response_ids(
        session,
        project,
        from_date=from_date,
        to_date=to_date,
    )
    if pinned_response_ids is not None:
        if project.primary_brand_id is None or int(project.primary_brand_id) != int(brand_id):
            rows = await _fact_rows(
                session,
                project,
                filters=AnalysisFilters(from_date=from_date, to_date=to_date),
                brand_id_override=brand_id,
            )
            scoped_response_ids = {
                int(response_id)
                for row in rows
                if (response_id := row.get("response_id")) is not None
            }
            return pinned_response_ids & scoped_response_ids
        return pinned_response_ids
    if all(
        [
            await legacy_table_exists(session, "topics"),
            await legacy_table_exists(session, "prompts"),
            await legacy_table_exists(session, "queries"),
        ]
    ):
        rows = await _fact_rows(
            session,
            project,
            filters=AnalysisFilters(from_date=from_date, to_date=to_date),
            brand_id_override=brand_id,
        )
        return {
            int(response_id) for row in rows if (response_id := row.get("response_id")) is not None
        }
    return await _target_response_ids(
        session,
        brand_id,
        from_dt=from_dt,
        to_dt=to_dt,
    )
