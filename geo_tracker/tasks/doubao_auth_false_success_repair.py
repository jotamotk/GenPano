from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.config import create_task_engine, get_task_async_session
from geo_tracker.db.models import AnalysisStatus, LLMResponse, Query, QueryStatus

KNOWN_FALSE_SUCCESS_QUERY_IDS = (184409, 184518, 184524, 184988)
KNOWN_RESPONSE_IDS_BY_QUERY_ID = {184409: 532}
REPAIR_REASON = "doubao_not_logged_in:false_success_repair:#594"


@dataclass(frozen=True)
class DoubaoAuthFalseSuccessRepairReport:
    candidate_query_ids: list[int]
    repaired_query_ids: list[int]
    skipped_query_ids: list[int]
    rollback_sql: list[str]
    apply: bool
    approval_ref: str

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_query_ids": self.candidate_query_ids,
            "repaired_query_ids": self.repaired_query_ids,
            "skipped_query_ids": self.skipped_query_ids,
            "rollback_sql": self.rollback_sql,
            "apply": self.apply,
            "approval_ref": self.approval_ref,
        }


def _rollback_sql(query: Query, response: LLMResponse) -> str:
    finished_at = _finished_at_rollback_literal(query.finished_at)
    query_id = int(query.id)
    response_id = int(response.id)
    original_analysis_status = _sql_literal(
        response.analysis_status or AnalysisStatus.PENDING.value
    )
    done_status = _sql_literal(QueryStatus.DONE.value)
    failed_status = _sql_literal(QueryStatus.FAILED.value)
    repair_reason = _sql_literal(REPAIR_REASON)
    return (
        "BEGIN; "
        "UPDATE llm_responses SET analysis_status = "
        f"{original_analysis_status} "
        f"WHERE id = {response_id} "
        f"AND query_id = {query_id} "
        f"AND analysis_status = {_sql_literal(AnalysisStatus.FAILED.value)} "
        "AND EXISTS ("
        "SELECT 1 FROM queries "
        f"WHERE queries.id = {query_id} "
        "AND queries.target_llm = 'doubao' "
        f"AND queries.status = {failed_status} "
        f"AND queries.retry_reason = {repair_reason}"
        "); "
        f"UPDATE queries SET status = {done_status}, retry_reason = NULL, "
        f"finished_at = {finished_at} "
        f"WHERE id = {query_id} "
        "AND target_llm = 'doubao' "
        f"AND status = {failed_status} "
        f"AND retry_reason = {repair_reason}; "
        "COMMIT; "
        f"-- rollback_doubao_auth_false_success query_id={query_id} "
        f"response_id={response_id}"
    )


def _sql_literal(value: object) -> str:
    escaped = str(value).replace("'", "''")
    return f"'{escaped}'"


def _finished_at_rollback_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, datetime):
        value = value.replace(tzinfo=None).isoformat(sep=" ", timespec="microseconds")
    return _sql_literal(value)


def _validated_query_ids(query_ids: list[int] | tuple[int, ...]) -> tuple[int, ...]:
    ids = tuple(int(query_id) for query_id in query_ids)
    unsupported = [
        query_id for query_id in ids if query_id not in KNOWN_FALSE_SUCCESS_QUERY_IDS
    ]
    if unsupported:
        allowed = ", ".join(str(query_id) for query_id in KNOWN_FALSE_SUCCESS_QUERY_IDS)
        requested = ", ".join(str(query_id) for query_id in unsupported)
        raise ValueError(
            "unsupported query_id override without #594 evidence mapping: "
            f"{requested}; allowed query_ids: {allowed}"
        )
    return ids


async def repair_known_doubao_auth_false_successes(
    session: AsyncSession,
    *,
    apply: bool = False,
    approval_ref: str,
    query_ids: list[int] | tuple[int, ...] = KNOWN_FALSE_SUCCESS_QUERY_IDS,
) -> DoubaoAuthFalseSuccessRepairReport:
    if not approval_ref.strip():
        raise ValueError("approval_ref is required for auditability")

    evidence_query_ids = _validated_query_ids(query_ids)
    stmt = (
        select(Query, LLMResponse)
        .join(LLMResponse, LLMResponse.query_id == Query.id)
        .where(
            Query.id.in_(list(evidence_query_ids)),
            Query.target_llm == "doubao",
            Query.status == QueryStatus.DONE.value,
        )
        .order_by(Query.id.asc())
    )
    rows = list((await session.execute(stmt)).all())

    candidate_query_ids: list[int] = []
    repaired_query_ids: list[int] = []
    skipped_query_ids: list[int] = []
    rollback_sql: list[str] = []

    now = datetime.now(UTC).replace(tzinfo=None)
    for query, response in rows:
        expected_response_id = KNOWN_RESPONSE_IDS_BY_QUERY_ID.get(int(query.id))
        if (
            expected_response_id is not None
            and int(response.id) != expected_response_id
        ):
            skipped_query_ids.append(int(query.id))
            continue

        candidate_query_ids.append(int(query.id))
        rollback_sql.append(_rollback_sql(query, response))
        if not apply:
            continue

        query.status = QueryStatus.FAILED.value
        query.retry_reason = REPAIR_REASON
        query.finished_at = now
        response.analysis_status = AnalysisStatus.FAILED.value
        repaired_query_ids.append(int(query.id))

    if apply:
        await session.commit()

    return DoubaoAuthFalseSuccessRepairReport(
        candidate_query_ids=candidate_query_ids,
        repaired_query_ids=repaired_query_ids,
        skipped_query_ids=skipped_query_ids,
        rollback_sql=rollback_sql,
        apply=apply,
        approval_ref=approval_ref,
    )


async def _run_cli(args: argparse.Namespace) -> dict[str, object]:
    engine = create_task_engine()
    try:
        async with get_task_async_session(engine) as session:
            report = await repair_known_doubao_auth_false_successes(
                session,
                apply=bool(args.apply),
                approval_ref=args.approval_ref,
                query_ids=args.query_id or KNOWN_FALSE_SUCCESS_QUERY_IDS,
            )
            return report.to_dict()
    finally:
        await engine.dispose()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply the #594 Doubao auth false-success repair."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the repair. Omit for dry-run.",
    )
    parser.add_argument(
        "--approval-ref",
        default="Refs #594",
        help="Audit approval/reference string.",
    )
    parser.add_argument(
        "--query-id",
        action="append",
        type=int,
        help="Optional #594 evidence query ID subset. Can be repeated.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    report = asyncio.run(_run_cli(args))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
