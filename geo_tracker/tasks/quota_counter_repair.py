from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.config import create_task_engine, get_task_async_session
from geo_tracker.db.models import LLMAccount, LLMResponse, Query
from geo_tracker.tasks.query_failure import INFRASTRUCTURE_FAILURE_REASONS


class RepairBlocked(RuntimeError):
    """Raised when a quota counter repair is not safe to apply."""


@dataclass(frozen=True)
class RepairCandidate:
    query_id: int
    engine: str
    account_id: int
    reason: str
    event_at: datetime | None


@dataclass(frozen=True)
class RepairGroup:
    engine: str
    account_id: int
    reason: str
    refundable_attempts: int
    query_ids: list[int]


@dataclass(frozen=True)
class AccountRepairPlan:
    engine: str
    account_id: int
    current_query_count_today: int
    daily_limit: int
    proposed_delta: int
    after_query_count_today: int
    safe_to_apply: bool
    reasons: dict[str, int]
    query_ids: list[int]


@dataclass(frozen=True)
class QuotaRepairReport:
    service_day_start: datetime
    service_day_end: datetime
    non_consuming_reasons: list[str]
    candidates: list[RepairCandidate]
    groups: list[RepairGroup]
    account_plans: list[AccountRepairPlan]

    @property
    def candidate_query_ids(self) -> list[int]:
        return [candidate.query_id for candidate in self.candidates]

    @property
    def total_refundable_attempts(self) -> int:
        return len(self.candidates)

    def to_dict(self) -> dict[str, Any]:
        def convert(value: Any) -> Any:
            if isinstance(value, datetime):
                return value.isoformat()
            if isinstance(value, list):
                return [convert(item) for item in value]
            if isinstance(value, dict):
                return {k: convert(v) for k, v in value.items()}
            if hasattr(value, "__dataclass_fields__"):
                return {k: convert(v) for k, v in asdict(value).items()}
            return value

        data = convert(self)
        data["candidate_query_ids"] = self.candidate_query_ids
        data["total_refundable_attempts"] = self.total_refundable_attempts
        return data


@dataclass(frozen=True)
class ApplyResult:
    total_delta: int
    account_ids: list[int]


def service_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)


def _event_timestamp_expr():
    return func.coalesce(
        Query.finished_at,
        Query.started_at,
        Query.executed_at,
        Query.queued_at,
        Query.created_at,
    )


async def _candidate_rows(
    session: AsyncSession,
    *,
    service_day_start: datetime,
    service_day_end: datetime,
) -> list[Any]:
    event_at = _event_timestamp_expr().label("event_at")
    response_exists = exists(
        select(1).where(LLMResponse.query_id == Query.id)
    )
    stmt = (
        select(
            Query.id.label("query_id"),
            Query.target_llm.label("engine"),
            Query.account_id.label("account_id"),
            Query.retry_reason.label("reason"),
            event_at,
        )
        .where(
            func.lower(func.coalesce(Query.status, "")) == "failed",
            Query.account_id.is_not(None),
            Query.retry_reason.in_(sorted(INFRASTRUCTURE_FAILURE_REASONS)),
            event_at >= service_day_start,
            event_at < service_day_end,
            ~response_exists,
        )
        .order_by(Query.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.mappings().all())


async def build_quota_repair_report(
    session: AsyncSession,
    *,
    service_day_start: datetime,
    service_day_end: datetime,
) -> QuotaRepairReport:
    rows = await _candidate_rows(
        session,
        service_day_start=service_day_start,
        service_day_end=service_day_end,
    )

    candidates = [
        RepairCandidate(
            query_id=int(row["query_id"]),
            engine=str(row["engine"] or ""),
            account_id=int(row["account_id"]),
            reason=str(row["reason"] or ""),
            event_at=row["event_at"],
        )
        for row in rows
    ]

    grouped: dict[tuple[str, int, str], list[int]] = {}
    by_account: dict[tuple[str, int], dict[str, Any]] = {}
    for candidate in candidates:
        grouped.setdefault(
            (candidate.engine, candidate.account_id, candidate.reason), []
        ).append(candidate.query_id)
        entry = by_account.setdefault(
            (candidate.engine, candidate.account_id),
            {"reasons": {}, "query_ids": []},
        )
        entry["reasons"][candidate.reason] = entry["reasons"].get(candidate.reason, 0) + 1
        entry["query_ids"].append(candidate.query_id)

    groups = [
        RepairGroup(
            engine=engine,
            account_id=account_id,
            reason=reason,
            refundable_attempts=len(query_ids),
            query_ids=sorted(query_ids),
        )
        for (engine, account_id, reason), query_ids in sorted(grouped.items())
    ]

    account_ids = [account_id for _, account_id in sorted(by_account)]
    account_rows: dict[int, Any] = {}
    if account_ids:
        result = await session.execute(
            select(
                LLMAccount.id,
                LLMAccount.llm_name,
                LLMAccount.query_count_today,
                LLMAccount.daily_limit,
            ).where(LLMAccount.id.in_(account_ids))
        )
        account_rows = {int(row.id): row for row in result.all()}

    plans: list[AccountRepairPlan] = []
    for (engine, account_id), entry in sorted(by_account.items()):
        account = account_rows.get(account_id)
        current = int(getattr(account, "query_count_today", 0) or 0)
        daily_limit = int(getattr(account, "daily_limit", 0) or 0)
        delta = len(entry["query_ids"])
        after = current - delta
        plans.append(
            AccountRepairPlan(
                engine=engine,
                account_id=account_id,
                current_query_count_today=current,
                daily_limit=daily_limit,
                proposed_delta=delta,
                after_query_count_today=after,
                safe_to_apply=after >= 0 and account is not None,
                reasons=dict(sorted(entry["reasons"].items())),
                query_ids=sorted(entry["query_ids"]),
            )
        )

    return QuotaRepairReport(
        service_day_start=service_day_start,
        service_day_end=service_day_end,
        non_consuming_reasons=sorted(INFRASTRUCTURE_FAILURE_REASONS),
        candidates=candidates,
        groups=groups,
        account_plans=plans,
    )


async def apply_quota_repair_plan(
    session: AsyncSession,
    report: QuotaRepairReport,
    *,
    expected_total_delta: int,
) -> ApplyResult:
    total_delta = sum(plan.proposed_delta for plan in report.account_plans)
    if total_delta != expected_total_delta:
        raise RepairBlocked(
            f"expected_total_delta={expected_total_delta} does not match report total={total_delta}"
        )

    unsafe = [plan for plan in report.account_plans if not plan.safe_to_apply]
    if unsafe:
        ids = ", ".join(str(plan.account_id) for plan in unsafe)
        raise RepairBlocked(f"repair would drop below zero or target a missing account: {ids}")

    for plan in report.account_plans:
        stmt = (
            update(LLMAccount)
            .where(
                LLMAccount.id == plan.account_id,
                func.coalesce(LLMAccount.query_count_today, 0) >= plan.proposed_delta,
            )
            .values(
                query_count_today=func.coalesce(LLMAccount.query_count_today, 0)
                - plan.proposed_delta
            )
        )
        result = await session.execute(stmt)
        if result.rowcount != 1:
            await session.rollback()
            raise RepairBlocked(
                f"account_id={plan.account_id} changed or would drop below zero"
            )

    await session.commit()
    return ApplyResult(
        total_delta=total_delta,
        account_ids=[plan.account_id for plan in report.account_plans],
    )


def _parse_day(value: str) -> date:
    return date.fromisoformat(value)


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit and optionally repair same-day non-consuming quota burns."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Apply approved repair.")
    mode.add_argument("--dry-run", action="store_true", help="Report only. Default.")
    parser.add_argument("--service-day", type=_parse_day, help="UTC service day YYYY-MM-DD.")
    parser.add_argument("--start", type=_parse_dt, help="Explicit inclusive UTC start timestamp.")
    parser.add_argument("--end", type=_parse_dt, help="Explicit exclusive UTC end timestamp.")
    parser.add_argument("--expected-total-delta", type=int, default=None)
    parser.add_argument("--approval-ref", default="")
    return parser.parse_args(argv)


async def _run_cli(args: argparse.Namespace) -> dict[str, Any]:
    if bool(args.start) != bool(args.end):
        raise RepairBlocked("--start and --end must be provided together")
    if args.apply and not args.start:
        raise RepairBlocked("--apply requires explicit --start and --end")
    if args.start and args.end:
        service_day_start, service_day_end = args.start, args.end
    else:
        day = args.service_day or datetime.now(UTC).date()
        service_day_start, service_day_end = service_day_bounds(day)

    engine = create_task_engine()
    try:
        async with get_task_async_session(engine) as session:
            report = await build_quota_repair_report(
                session,
                service_day_start=service_day_start,
                service_day_end=service_day_end,
            )
            payload: dict[str, Any] = {
                "mode": "apply" if args.apply else "dry_run",
                "report": report.to_dict(),
            }
            if args.apply:
                if args.expected_total_delta is None:
                    raise RepairBlocked("--apply requires --expected-total-delta")
                if not args.approval_ref:
                    raise RepairBlocked("--apply requires --approval-ref")
                result = await apply_quota_repair_plan(
                    session,
                    report,
                    expected_total_delta=args.expected_total_delta,
                )
                payload["applied"] = asdict(result)
            return payload
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        payload = asyncio.run(_run_cli(args))
    except RepairBlocked as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        return 2
    print(json.dumps({"ok": True, **payload}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
