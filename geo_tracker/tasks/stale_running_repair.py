from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.db.models import LLMResponse, Query, QueryStatus


DEFAULT_STALE_RUNNING_SECONDS = 60 * 60
DEFAULT_REPAIR_REASON = "stale_running_timeout"
DEFAULT_PENDING_DISPATCH_SECONDS = 60 * 60
DEFAULT_PENDING_DISPATCH_REASON = "pending_dispatch_timeout"


@dataclass(frozen=True)
class StaleRunningRepairReport:
    matched: int
    repaired: int
    query_ids: list[int]
    by_engine: dict[str, int]
    reason: str
    cutoff: datetime
    dry_run: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "matched": self.matched,
            "repaired": self.repaired,
            "query_ids": self.query_ids,
            "by_engine": self.by_engine,
            "reason": self.reason,
            "cutoff": self.cutoff.isoformat(),
            "dry_run": self.dry_run,
        }


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _query_activity_at(query: Query) -> datetime | None:
    for field in ("started_at", "executed_at", "queued_at", "created_at"):
        value = getattr(query, field, None)
        if value is not None:
            return value
    return None


def _latency_ms(started_at: datetime | None, finished_at: datetime) -> int | None:
    if started_at is None:
        return None
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


async def repair_stale_running_queries(
    session: AsyncSession,
    *,
    max_age_seconds: int = DEFAULT_STALE_RUNNING_SECONDS,
    reason: str = DEFAULT_REPAIR_REASON,
    now: datetime | None = None,
    brand_id: int | None = None,
    target_llm: str | None = None,
    dry_run: bool = False,
) -> StaleRunningRepairReport:
    """Move stale running queries with no saved response to retryable failure.

    A saved ``llm_responses`` row is the guardrail: rows that have persisted
    response evidence are never rewritten by this repair path.
    """
    finished_at = now or _utcnow_naive()
    seconds = max(60, int(max_age_seconds or DEFAULT_STALE_RUNNING_SECONDS))
    cutoff = finished_at - timedelta(seconds=seconds)
    repair_reason = (reason or DEFAULT_REPAIR_REASON).strip() or DEFAULT_REPAIR_REASON

    stmt = select(Query).where(func.lower(Query.status) == QueryStatus.RUNNING.value)
    if brand_id is not None:
        stmt = stmt.where(Query.brand_id == brand_id)
    if target_llm:
        stmt = stmt.where(Query.target_llm == target_llm)
    stmt = stmt.where(~exists().where(LLMResponse.query_id == Query.id)).order_by(Query.id)

    rows = list((await session.execute(stmt)).scalars().all())
    candidates = [query for query in rows if (_query_activity_at(query) or finished_at) < cutoff]

    query_ids = [int(query.id) for query in candidates]
    by_engine: dict[str, int] = {}
    for query in candidates:
        engine = str(query.target_llm or "unknown")
        by_engine[engine] = by_engine.get(engine, 0) + 1

    if dry_run or not candidates:
        return StaleRunningRepairReport(
            matched=len(candidates),
            repaired=0,
            query_ids=query_ids,
            by_engine=by_engine,
            reason=repair_reason,
            cutoff=cutoff,
            dry_run=dry_run,
        )

    for query in candidates:
        query.status = QueryStatus.FAILED.value
        query.finished_at = finished_at
        query.retry_reason = repair_reason
        latency = _latency_ms(query.started_at, finished_at)
        if latency is not None:
            query.latency_ms = latency

    await session.commit()
    return StaleRunningRepairReport(
        matched=len(candidates),
        repaired=len(candidates),
        query_ids=query_ids,
        by_engine=by_engine,
        reason=repair_reason,
        cutoff=cutoff,
        dry_run=False,
    )


async def repair_stale_pending_dispatch_queries(
    session: AsyncSession,
    *,
    max_age_seconds: int = DEFAULT_PENDING_DISPATCH_SECONDS,
    reason: str = DEFAULT_PENDING_DISPATCH_REASON,
    now: datetime | None = None,
    brand_id: int | None = None,
    target_llm: str | None = None,
    dry_run: bool = False,
) -> StaleRunningRepairReport:
    """Fail old queued pending queries that never reached a worker.

    ``queued_at`` is the guardrail: unqueued pending rows are not rewritten by
    this repair path because they may be drafts/orphans that were never meant
    to have a broker delivery.
    """
    finished_at = now or _utcnow_naive()
    seconds = max(60, int(max_age_seconds or DEFAULT_PENDING_DISPATCH_SECONDS))
    cutoff = finished_at - timedelta(seconds=seconds)
    repair_reason = (
        (reason or DEFAULT_PENDING_DISPATCH_REASON).strip()
        or DEFAULT_PENDING_DISPATCH_REASON
    )

    stmt = (
        select(Query)
        .where(func.lower(Query.status) == QueryStatus.PENDING.value)
        .where(Query.queued_at.is_not(None))
        .where(Query.started_at.is_(None))
    )
    if brand_id is not None:
        stmt = stmt.where(Query.brand_id == brand_id)
    if target_llm:
        stmt = stmt.where(Query.target_llm == target_llm)
    stmt = stmt.where(~exists().where(LLMResponse.query_id == Query.id)).order_by(Query.id)

    rows = list((await session.execute(stmt)).scalars().all())
    candidates = [query for query in rows if (query.queued_at or finished_at) < cutoff]

    query_ids = [int(query.id) for query in candidates]
    by_engine: dict[str, int] = {}
    for query in candidates:
        engine = str(query.target_llm or "unknown")
        by_engine[engine] = by_engine.get(engine, 0) + 1

    if dry_run or not candidates:
        return StaleRunningRepairReport(
            matched=len(candidates),
            repaired=0,
            query_ids=query_ids,
            by_engine=by_engine,
            reason=repair_reason,
            cutoff=cutoff,
            dry_run=dry_run,
        )

    for query in candidates:
        query.status = QueryStatus.FAILED.value
        query.finished_at = finished_at
        query.retry_reason = repair_reason
        query.latency_ms = None

    await session.commit()
    return StaleRunningRepairReport(
        matched=len(candidates),
        repaired=len(candidates),
        query_ids=query_ids,
        by_engine=by_engine,
        reason=repair_reason,
        cutoff=cutoff,
        dry_run=False,
    )
