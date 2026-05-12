from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.config import create_task_engine, get_task_async_session
from geo_tracker.db.models import LLMAccount, LLMResponse, QuotaCounterRepair, Query
from geo_tracker.tasks.query_failure import INFRASTRUCTURE_FAILURE_REASONS


AUTO_REFUNDABLE_FAILURE_REASONS = frozenset(
    reason for reason in INFRASTRUCTURE_FAILURE_REASONS if reason != "exception"
)
MANUAL_REVIEW_FAILURE_REASONS = frozenset({"exception"})
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class RepairBlocked(RuntimeError):
    """Raised when a quota counter repair is not safe to apply."""


@dataclass(frozen=True)
class RepairCandidate:
    query_id: int
    engine: str
    account_id: int
    reason: str
    event_at: datetime | None
    account_engine: str | None = None


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
    unapplied_delta: int
    after_query_count_today: int
    safe_to_apply: bool
    reasons: dict[str, int]
    query_ids: list[int]
    account_engine: str | None = None
    unsafe_reasons: list[str] | None = None


@dataclass(frozen=True)
class QuotaRepairReport:
    service_day_start: datetime
    service_day_end: datetime
    non_consuming_reasons: list[str]
    manual_review_reasons: list[str]
    candidates: list[RepairCandidate]
    manual_review_candidates: list[RepairCandidate]
    repaired_query_ids: list[int]
    groups: list[RepairGroup]
    account_plans: list[AccountRepairPlan]

    @property
    def candidate_query_ids(self) -> list[int]:
        return [candidate.query_id for candidate in self.candidates]

    @property
    def manual_review_query_ids(self) -> list[int]:
        return [candidate.query_id for candidate in self.manual_review_candidates]

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
        data["manual_review_query_ids"] = self.manual_review_query_ids
        data["total_refundable_attempts"] = self.total_refundable_attempts
        return data


@dataclass(frozen=True)
class ApplyResult:
    total_delta: int
    account_ids: list[int]
    repaired_query_ids: list[int]


def validate_deployed_code_sha(expected_sha: str, deployed_sha: str) -> str:
    expected = (expected_sha or "").strip()
    deployed = (deployed_sha or "").strip()
    if not (_SHA_RE.match(expected) and _SHA_RE.match(deployed)):
        raise RepairBlocked("expected and deployed code values must be 40-character git SHA strings")
    if expected.lower() != deployed.lower():
        raise RepairBlocked(
            f"deployed code SHA mismatch: expected={expected} deployed={deployed}"
        )
    return deployed.lower()


def service_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)


def _current_service_day_start() -> datetime:
    return service_day_bounds(datetime.now(UTC).date())[0]


def _event_timestamp_expr():
    return func.coalesce(
        Query.started_at,
        Query.executed_at,
        Query.queued_at,
        Query.created_at,
        Query.finished_at,
    )


def _response_exists_expr():
    return exists(select(1).where(LLMResponse.query_id == Query.id))


def _repaired_exists_expr():
    return exists(select(1).where(QuotaCounterRepair.query_id == Query.id))


async def _candidate_rows(
    session: AsyncSession,
    *,
    service_day_start: datetime,
    service_day_end: datetime,
    reasons: frozenset[str],
) -> list[Any]:
    event_at = _event_timestamp_expr().label("event_at")
    stmt = (
        select(
            Query.id.label("query_id"),
            Query.target_llm.label("engine"),
            Query.account_id.label("account_id"),
            Query.retry_reason.label("reason"),
            LLMAccount.llm_name.label("account_engine"),
            event_at,
        )
        .select_from(Query)
        .outerjoin(LLMAccount, LLMAccount.id == Query.account_id)
        .where(
            func.lower(func.coalesce(Query.status, "")) == "failed",
            Query.account_id.is_not(None),
            Query.retry_reason.in_(sorted(reasons)),
            event_at >= service_day_start,
            event_at < service_day_end,
            ~_response_exists_expr(),
            ~_repaired_exists_expr(),
        )
        .order_by(Query.id.asc())
    )
    result = await session.execute(stmt)
    return list(result.mappings().all())


async def _repaired_query_ids(
    session: AsyncSession,
    *,
    service_day_start: datetime,
    service_day_end: datetime,
) -> list[int]:
    event_at = _event_timestamp_expr().label("event_at")
    stmt = (
        select(QuotaCounterRepair.query_id)
        .join(Query, Query.id == QuotaCounterRepair.query_id)
        .where(event_at >= service_day_start, event_at < service_day_end)
        .order_by(QuotaCounterRepair.query_id.asc())
    )
    return [
        int(query_id)
        for query_id in (await session.execute(stmt)).scalars().all()
    ]


def _rows_to_candidates(rows: list[Any]) -> list[RepairCandidate]:
    return [
        RepairCandidate(
            query_id=int(row["query_id"]),
            engine=str(row["engine"] or ""),
            account_id=int(row["account_id"]),
            reason=str(row["reason"] or ""),
            event_at=row["event_at"],
            account_engine=str(row["account_engine"]) if row["account_engine"] else None,
        )
        for row in rows
    ]


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
        reasons=AUTO_REFUNDABLE_FAILURE_REASONS,
    )
    manual_rows = await _candidate_rows(
        session,
        service_day_start=service_day_start,
        service_day_end=service_day_end,
        reasons=MANUAL_REVIEW_FAILURE_REASONS,
    )

    candidates = _rows_to_candidates(rows)
    manual_review_candidates = _rows_to_candidates(manual_rows)

    grouped: dict[tuple[str, int, str], list[int]] = {}
    by_account: dict[tuple[str, int, str | None], dict[str, Any]] = {}
    for candidate in candidates:
        grouped.setdefault(
            (candidate.engine, candidate.account_id, candidate.reason), []
        ).append(candidate.query_id)
        entry = by_account.setdefault(
            (candidate.engine, candidate.account_id, candidate.account_engine),
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

    account_ids = [account_id for _, account_id, _ in sorted(by_account)]
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
    for (engine, account_id, account_engine), entry in sorted(by_account.items()):
        account = account_rows.get(account_id)
        current = int(getattr(account, "query_count_today", 0) or 0)
        daily_limit = int(getattr(account, "daily_limit", 0) or 0)
        real_account_engine = (
            str(getattr(account, "llm_name"))
            if account is not None and getattr(account, "llm_name", None)
            else account_engine
        )
        candidate_delta = len(entry["query_ids"])
        unsafe_reasons: list[str] = []
        if account is None:
            unsafe_reasons.append("missing_account")
        if current < 0:
            unsafe_reasons.append("current_counter_negative")
        if real_account_engine and engine != real_account_engine:
            unsafe_reasons.append("engine_mismatch")
        if current - candidate_delta < 0:
            unsafe_reasons.append("counter_underflow")
        proposed_delta = 0 if unsafe_reasons else candidate_delta
        after = max(current - proposed_delta, 0)
        plans.append(
            AccountRepairPlan(
                engine=engine,
                account_id=account_id,
                current_query_count_today=current,
                daily_limit=daily_limit,
                proposed_delta=proposed_delta,
                unapplied_delta=candidate_delta - proposed_delta,
                after_query_count_today=after,
                safe_to_apply=not unsafe_reasons,
                reasons=dict(sorted(entry["reasons"].items())),
                query_ids=sorted(entry["query_ids"]),
                account_engine=real_account_engine,
                unsafe_reasons=unsafe_reasons,
            )
        )

    return QuotaRepairReport(
        service_day_start=service_day_start,
        service_day_end=service_day_end,
        non_consuming_reasons=sorted(AUTO_REFUNDABLE_FAILURE_REASONS),
        manual_review_reasons=sorted(MANUAL_REVIEW_FAILURE_REASONS),
        candidates=candidates,
        manual_review_candidates=manual_review_candidates,
        repaired_query_ids=await _repaired_query_ids(
            session,
            service_day_start=service_day_start,
            service_day_end=service_day_end,
        ),
        groups=groups,
        account_plans=plans,
    )


def _unsafe_reasons(report: QuotaRepairReport) -> list[str]:
    return sorted(
        {
            reason
            for plan in report.account_plans
            if not plan.safe_to_apply
            for reason in (plan.unsafe_reasons or ["unsafe_plan"])
        }
    )


def _unsafe_error(reasons: list[str]) -> str:
    if "counter_underflow" in reasons:
        return "repair would drop below zero; unsafe reasons=" + ",".join(reasons)
    return "unsafe repair plan: " + ",".join(reasons)


def build_quota_repair_payload(
    report: QuotaRepairReport,
    *,
    mode: str,
) -> dict[str, Any]:
    reasons = _unsafe_reasons(report)
    payload: dict[str, Any] = {
        "ok": not reasons,
        "mode": mode,
        "blocked": bool(reasons),
        "blocking_reasons": reasons,
        "report": report.to_dict(),
    }
    if reasons:
        payload["error"] = _unsafe_error(reasons)
    return payload


async def _existing_repairs(session: AsyncSession, query_ids: list[int]) -> list[int]:
    if not query_ids:
        return []
    stmt = (
        select(QuotaCounterRepair.query_id)
        .where(QuotaCounterRepair.query_id.in_(query_ids))
        .order_by(QuotaCounterRepair.query_id.asc())
    )
    return [int(query_id) for query_id in (await session.execute(stmt)).scalars().all()]


def _ensure_current_service_day(
    report: QuotaRepairReport,
    *,
    current_service_day_start: datetime,
) -> None:
    current_service_day_end = current_service_day_start + timedelta(days=1)
    if (
        report.service_day_start < current_service_day_start
        or report.service_day_end > current_service_day_end
    ):
        raise RepairBlocked(
            "apply is current service day only; refusing to decrement live counters for an old window"
        )


async def apply_quota_repair_plan(
    session: AsyncSession,
    report: QuotaRepairReport,
    *,
    expected_total_delta: int,
    current_service_day_start: datetime | None = None,
    approval_ref: str = "",
) -> ApplyResult:
    reasons = _unsafe_reasons(report)
    if reasons:
        raise RepairBlocked(_unsafe_error(reasons))

    total_delta = sum(plan.proposed_delta for plan in report.account_plans)
    if total_delta != expected_total_delta:
        raise RepairBlocked(
            f"expected_total_delta={expected_total_delta} does not match report total={total_delta}"
        )

    if total_delta == 0:
        return ApplyResult(total_delta=0, account_ids=[], repaired_query_ids=[])

    existing = await _existing_repairs(session, report.candidate_query_ids)
    if existing:
        raise RepairBlocked(f"query IDs already repaired: {existing}")

    _ensure_current_service_day(
        report,
        current_service_day_start=current_service_day_start or _current_service_day_start(),
    )

    if not approval_ref:
        raise RepairBlocked("apply requires approval_ref")

    for candidate in report.candidates:
        session.add(
            QuotaCounterRepair(
                query_id=candidate.query_id,
                account_id=candidate.account_id,
                engine=candidate.engine,
                reason=candidate.reason,
                delta=1,
                service_day_start=report.service_day_start,
                service_day_end=report.service_day_end,
                approval_ref=approval_ref,
            )
        )

    for plan in report.account_plans:
        stmt = (
            update(LLMAccount)
            .where(
                LLMAccount.id == plan.account_id,
                LLMAccount.llm_name == plan.engine,
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
        repaired_query_ids=report.candidate_query_ids,
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
    parser.add_argument("--expected-deployed-sha", default="")
    return parser.parse_args(argv)


async def _run_cli(args: argparse.Namespace) -> dict[str, Any]:
    if args.expected_deployed_sha:
        validate_deployed_code_sha(
            args.expected_deployed_sha,
            os.getenv("GENPANO_DEPLOYED_SHA", ""),
        )
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
            payload = build_quota_repair_payload(
                report,
                mode="apply" if args.apply else "dry_run",
            )
            if args.apply:
                if args.expected_total_delta is None:
                    raise RepairBlocked("--apply requires --expected-total-delta")
                if not args.approval_ref:
                    raise RepairBlocked("--apply requires --approval-ref")
                result = await apply_quota_repair_plan(
                    session,
                    report,
                    expected_total_delta=args.expected_total_delta,
                    current_service_day_start=_current_service_day_start(),
                    approval_ref=args.approval_ref,
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
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload.get("ok", True) else 2


if __name__ == "__main__":
    raise SystemExit(main())
