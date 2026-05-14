"""Controlled BestCoffer analyzer backfill for issue #686.

This module is intentionally dry-run first. Apply mode requires explicit
issue #686 production-write approval evidence and only touches selected
successful response ids plus their analyzer artifacts and requested aggregate rows.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Awaitable, Callable, Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.agent.response_validation import (
    doubao_persistence_auth_reason,
    invalid_response_reason,
)
from geo_tracker.config import create_task_engine, get_task_async_session
from geo_tracker.db.models import (
    AnalysisStatus,
    Brand,
    BrandMention,
    Competitor,
    LLMResponse,
    Prompt,
    Query,
    QueryStatus,
    ResponseAnalysis,
    Topic,
)
from geo_tracker.tasks.analyzer_run_recovery import (
    DEFAULT_STALE_ACTIVE_ANALYZER_RUN_SECONDS,
    recover_stale_active_analyzer_run,
    summarize_active_analyzer_run,
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
GITHUB_ISSUE_COMMENT_RE = re.compile(
    r"^https://github\.com/jotamotk/trash_test/issues/686"
    r"#issuecomment-[0-9]+(?P<evidence>.*)$",
    re.IGNORECASE,
)
MAX_LIMIT = 75

AnalyzeFunc = Callable[
    [AsyncSession, LLMResponse, Brand, list[Competitor], str],
    Awaitable[dict],
]


class AnalyzerBackfillApplyError(RuntimeError):
    """Raised when apply mode cannot complete every selected analyzer rerun."""

    def __init__(self, report: dict) -> None:
        self.report = report
        failed_response_id = report.get("failed_response_id")
        super().__init__(f"analyzer apply failed for response_id={failed_response_id}")


@dataclass(frozen=True)
class BestCofferAnalyzerBackfillScope:
    brand_id: int = 24
    date_from: str | None = None
    date_to: str | None = None
    response_ids: tuple[int, ...] = field(default_factory=tuple)
    query_ids: tuple[int, ...] = field(default_factory=tuple)
    source_brand_id: int | None = None
    competitive_brand_ids: tuple[int, ...] = field(default_factory=tuple)
    limit: int = MAX_LIMIT

    def normalized_response_ids(self) -> tuple[int, ...]:
        return tuple(sorted({int(value) for value in self.response_ids if int(value) > 0}))

    def normalized_query_ids(self) -> tuple[int, ...]:
        return tuple(sorted({int(value) for value in self.query_ids if int(value) > 0}))

    def normalized_competitive_brand_ids(self) -> tuple[int, ...]:
        return tuple(
            sorted({int(value) for value in self.competitive_brand_ids if int(value) > 0})
        )


@dataclass(frozen=True)
class CandidateResponse:
    response_id: int
    query_id: int
    query_brand_id: int | None
    topic_brand_id: int | None
    topic_id: int | None
    prompt_id: int | None
    engine: str | None
    collected_at: str | None
    analysis_status: str | None
    has_analysis: bool
    active_analyzer_run: dict | None
    invalid_reason: str | None


def _parse_day(value: str | None, name: str) -> datetime | None:
    if not value:
        return None
    if not DATE_RE.match(value):
        raise ValueError(f"{name} must be YYYY-MM-DD")
    return datetime.strptime(value, "%Y-%m-%d")


def _end_of_day(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(hour=23, minute=59, second=59, microsecond=999999)


def validate_scope(scope: BestCofferAnalyzerBackfillScope, *, apply: bool = False) -> None:
    if int(scope.brand_id) <= 0:
        raise ValueError("brand_id must be positive")
    if int(scope.limit) < 1 or int(scope.limit) > MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    _parse_day(scope.date_from, "date_from")
    _parse_day(scope.date_to, "date_to")
    if scope.normalized_response_ids() or scope.normalized_query_ids():
        return
    missing = [
        name
        for name, value in (
            ("date_from", scope.date_from),
            ("date_to", scope.date_to),
        )
        if value in (None, "")
    ]
    if missing:
        raise ValueError(
            "scope must include explicit response_ids, query_ids, or date_from/date_to; "
            f"missing: {', '.join(missing)}"
        )
    if apply and scope.limit > MAX_LIMIT:
        raise ValueError(f"apply mode limit must be <= {MAX_LIMIT}")


def validate_approval_ref(approval_ref: str | None) -> str:
    value = (approval_ref or "").strip()
    match = GITHUB_ISSUE_COMMENT_RE.match(value) if value else None
    normalized = re.sub(r"[-_]+", " ", value.lower())
    has_write_approval = (
        bool(re.search(r"\bproduction\s+writes?\b", normalized))
        and bool(re.search(r"\bapprov\w*\b", normalized))
        and "bestcoffer" in normalized
        and ("apply" in normalized or "backfill" in normalized)
    )
    if not match or not has_write_approval:
        raise ValueError(
            "apply mode requires approval_ref to include a #686 issue comment URL "
            "and explicit production-write approval evidence for BestCoffer "
            "apply/backfill"
        )
    return value


def _scope_dict(scope: BestCofferAnalyzerBackfillScope) -> dict:
    data = asdict(scope)
    data["response_ids"] = list(scope.normalized_response_ids())
    data["query_ids"] = list(scope.normalized_query_ids())
    data["competitive_brand_ids"] = list(scope.normalized_competitive_brand_ids())
    return data


def _response_invalid_reason(response: LLMResponse, query: Query) -> str | None:
    llm_name = query.target_llm or ""
    if (llm_name or "").lower() == "doubao" and response.response_html:
        reason = doubao_persistence_auth_reason(
            llm_name,
            response.raw_text,
            response.response_html,
        )
        if reason:
            return reason
    return invalid_response_reason(llm_name, response.raw_text)


def _target_scope_invalid_reason(
    scope: BestCofferAnalyzerBackfillScope,
    query: Query,
    topic: Topic | None,
) -> str | None:
    if not (scope.normalized_response_ids() or scope.normalized_query_ids()):
        return None
    target_brand_id = int(scope.brand_id)
    query_brand_id = int(query.brand_id) if query.brand_id is not None else None
    topic_brand_id = int(topic.brand_id) if topic and topic.brand_id is not None else None
    if query_brand_id == target_brand_id or topic_brand_id == target_brand_id:
        return None
    return "outside_target_brand_scope"


async def _load_candidates(
    session: AsyncSession,
    scope: BestCofferAnalyzerBackfillScope,
) -> list[tuple[LLMResponse, Query, Prompt | None, Topic | None]]:
    validate_scope(scope)
    start_at = _parse_day(scope.date_from, "date_from")
    end_at = _end_of_day(_parse_day(scope.date_to, "date_to"))
    response_ids = scope.normalized_response_ids()
    query_ids = scope.normalized_query_ids()

    conditions = [
        Query.status == QueryStatus.DONE.value,
        LLMResponse.raw_text.is_not(None),
        LLMResponse.raw_text != "",
    ]
    if response_ids:
        conditions.append(LLMResponse.id.in_(response_ids))
    elif query_ids:
        conditions.append(Query.id.in_(query_ids))
    else:
        conditions.append(
            or_(
                Query.brand_id == int(scope.brand_id),
                Topic.brand_id == int(scope.brand_id),
            )
        )
        if start_at is not None:
            conditions.append(LLMResponse.collected_at >= start_at)
        if end_at is not None:
            conditions.append(LLMResponse.collected_at <= end_at)
        if scope.source_brand_id is not None:
            conditions.append(Query.brand_id == int(scope.source_brand_id))

    stmt = (
        select(LLMResponse, Query, Prompt, Topic)
        .join(Query, Query.id == LLMResponse.query_id)
        .outerjoin(Prompt, Prompt.id == Query.prompt_id)
        .outerjoin(Topic, Topic.id == Prompt.topic_id)
        .where(and_(*conditions))
        .order_by(LLMResponse.collected_at.asc(), LLMResponse.id.asc())
        .limit(int(scope.limit) + 1)
    )
    rows = (await session.execute(stmt)).all()
    if len(rows) > int(scope.limit):
        raise ValueError(
            f"selected response candidates exceed limit={scope.limit}; tighten scope"
        )
    return rows


async def collect_candidate_responses(
    session: AsyncSession,
    scope: BestCofferAnalyzerBackfillScope,
) -> list[CandidateResponse]:
    rows = await _load_candidates(session, scope)
    response_ids = [int(response.id) for response, _query, _prompt, _topic in rows]
    analysis_response_ids: set[int] = set()
    active_run_summaries: dict[int, dict] = {}
    allow_existing_analysis_recovery = bool(scope.normalized_response_ids())
    if response_ids:
        analyses = (
            await session.execute(
                select(ResponseAnalysis.response_id).where(
                    ResponseAnalysis.response_id.in_(response_ids)
                )
            )
        ).all()
        analysis_response_ids = {int(row[0]) for row in analyses}
        for response_id in response_ids:
            summary = await summarize_active_analyzer_run(
                session,
                response_id=int(response_id),
                allow_existing_analysis_recovery=allow_existing_analysis_recovery,
            )
            if summary.active_run_id is not None:
                active_run_summaries[int(response_id)] = summary.to_dict()

    out: list[CandidateResponse] = []
    for response, query, prompt, topic in rows:
        invalid_reason = _target_scope_invalid_reason(scope, query, topic)
        if invalid_reason is None:
            invalid_reason = _response_invalid_reason(response, query)
        out.append(
            CandidateResponse(
                response_id=int(response.id),
                query_id=int(query.id),
                query_brand_id=int(query.brand_id) if query.brand_id is not None else None,
                topic_brand_id=int(topic.brand_id) if topic and topic.brand_id is not None else None,
                topic_id=int(topic.id) if topic and topic.id is not None else None,
                prompt_id=int(prompt.id) if prompt and prompt.id is not None else None,
                engine=query.target_llm,
                collected_at=response.collected_at.isoformat() if response.collected_at else None,
                analysis_status=response.analysis_status,
                has_analysis=int(response.id) in analysis_response_ids,
                active_analyzer_run=active_run_summaries.get(int(response.id)),
                invalid_reason=invalid_reason,
            )
        )
    return out


def _candidate_to_dict(candidate: CandidateResponse) -> dict:
    return {
        "response_id": candidate.response_id,
        "query_id": candidate.query_id,
        "query_brand_id": candidate.query_brand_id,
        "topic_brand_id": candidate.topic_brand_id,
        "topic_id": candidate.topic_id,
        "prompt_id": candidate.prompt_id,
        "engine": candidate.engine,
        "collected_at": candidate.collected_at,
        "analysis_status": candidate.analysis_status,
        "has_analysis": candidate.has_analysis,
        "active_analyzer_run": candidate.active_analyzer_run,
        "invalid_reason": candidate.invalid_reason,
    }


def _analysis_state(candidate: CandidateResponse) -> str:
    if not candidate.has_analysis:
        return "missing_analysis"
    if candidate.analysis_status != AnalysisStatus.DONE.value:
        return "analysis_row_status_not_done"
    return "has_analysis"


def summarize_candidates(candidates: Iterable[CandidateResponse]) -> dict:
    rows = list(candidates)
    selected = [row for row in rows if row.invalid_reason is None]
    excluded = [row for row in rows if row.invalid_reason is not None]
    analyzer_states = Counter(_analysis_state(row) for row in selected)
    invalid_reasons = Counter(row.invalid_reason for row in excluded if row.invalid_reason)
    return {
        "candidate_count": len(rows),
        "selected_count": len(selected),
        "excluded_invalid_count": len(excluded),
        "invalid_reason_counts": dict(sorted(invalid_reasons.items())),
        "analyzer_state_counts": dict(sorted(analyzer_states.items())),
        "rows": [_candidate_to_dict(row) for row in selected],
        "excluded_rows": [_candidate_to_dict(row) for row in excluded],
    }


async def _load_analyzer_inputs(
    session: AsyncSession,
    candidate: CandidateResponse,
    *,
    target_brand_id: int,
) -> tuple[LLMResponse, Brand, list[Competitor], str]:
    response = await session.get(LLMResponse, candidate.response_id)
    query = await session.get(Query, candidate.query_id)
    brand = await session.get(Brand, int(target_brand_id))
    if response is None or query is None:
        raise ValueError(f"response/query not found for response_id={candidate.response_id}")
    if brand is None:
        raise ValueError(f"brand_id {target_brand_id} not found")

    competitors = (
        await session.execute(select(Competitor).where(Competitor.brand_id == brand.id))
    ).scalars().all()

    intent = "non_brand"
    if query.prompt_id:
        prompt = await session.get(Prompt, query.prompt_id)
        if prompt and prompt.intent:
            intent = prompt.intent
    return response, brand, competitors, intent


async def _aggregate_selected_days(
    session: AsyncSession,
    selected: list[CandidateResponse],
    *,
    brand_id: int,
    competitive_brand_ids: tuple[int, ...],
) -> list[dict]:
    from geo_tracker.analyzer.aggregator import Aggregator

    days = sorted(
        {
            candidate.collected_at[:10]
            for candidate in selected
            if candidate.collected_at
        }
    )
    aggregator = Aggregator(session)
    results: list[dict] = []
    for day in days:
        stats = await aggregator.aggregate_daily(
            datetime.strptime(day, "%Y-%m-%d"),
            brand_id,
            competitive_brand_ids=set(competitive_brand_ids),
        )
        results.append({"date": day, "brand_id": brand_id, "stats": stats})
    return results


async def build_bestcoffer_analyzer_backfill_report(
    session: AsyncSession,
    scope: BestCofferAnalyzerBackfillScope,
    *,
    apply: bool = False,
    approval_ref: str | None = None,
    aggregate: bool = False,
    analyze_func: AnalyzeFunc | None = None,
) -> dict:
    validate_scope(scope, apply=apply)
    if apply:
        approval_ref = validate_approval_ref(approval_ref)

    candidates = await collect_candidate_responses(session, scope)
    before = summarize_candidates(candidates)
    selected = [row for row in candidates if row.invalid_reason is None]
    report = {
        "issue": 686,
        "mode": "apply" if apply else "dry_run",
        "write_performed": False,
        "approval_ref": approval_ref,
        "scope": _scope_dict(scope),
        "safe_selection": {
            "successful_responses_only": True,
            "invalid_artifacts_excluded": True,
            "date_wide_reset": False,
            "broad_600_query_scraper_run": False,
            "selected_by_response_ids": bool(scope.normalized_response_ids()),
            "selected_by_query_ids": bool(scope.normalized_query_ids()),
            "selected_by_brand_date_window": not (
                scope.normalized_response_ids() or scope.normalized_query_ids()
            ),
            "active_run_existing_analysis_recovery_requires_response_ids": True,
            "limit": int(scope.limit),
        },
        "selected_response_ids": [row.response_id for row in selected],
        "selected_query_ids": [row.query_id for row in selected],
        "before": before,
        "root_cause": (
            "Existing successful responses have no durable analyzer artifacts; "
            "the scraper enqueue is best-effort, and the date-only analyzer runner "
            "does not catch up this brand slice automatically."
        ),
        "apply_plan": (
            "Dry-run only. To apply, rerun with --apply and an approval_ref that "
            "includes a #686 issue comment URL plus explicit production-write "
            "approval evidence for BestCoffer apply/backfill."
        ),
        "rollback": (
            "Apply mutates only selected response analyzer artifacts "
            "(llm_responses.analysis_status/analyzed_at, response_analyses, "
            "brand_mentions, citation_sources, sentiment_drivers, "
            "product_feature_mentions) and requested brand-day aggregate rows. "
            "Roll back from the pre-apply database backup, or rerun the analyzer "
            "for the same selected response_ids and re-aggregate the same dates."
        ),
    }
    if not apply:
        return report

    if analyze_func is None:
        from geo_tracker.analyzer.cli import analyze_single_response

        analyze_func = analyze_single_response

    apply_results: list[dict] = []
    analyzer_run_recoveries: list[dict] = []
    if not selected:
        report["apply_results"] = apply_results
        report["after"] = before
        report["apply_plan"] = (
            "No selected response_ids after validation; no analyzer writes performed."
        )
        return report

    for candidate in selected:
        recovery = await recover_stale_active_analyzer_run(
            session,
            response_id=candidate.response_id,
            stale_after_seconds=DEFAULT_STALE_ACTIVE_ANALYZER_RUN_SECONDS,
            allow_existing_analysis_recovery=bool(scope.normalized_response_ids()),
        )
        if recovery.active_run_id is not None:
            recovery_row = recovery.to_dict()
            analyzer_run_recoveries.append(recovery_row)
            if recovery.blocked:
                result = {
                    "response_id": candidate.response_id,
                    "status": "failed",
                    "error": recovery.reason,
                    "analyzer_run_recovery": recovery_row,
                }
                apply_results.append(result)
                after = summarize_candidates(await collect_candidate_responses(session, scope))
                report["write_attempted"] = True
                report["apply_failed"] = True
                report["failed_response_id"] = candidate.response_id
                report["failure_reason"] = recovery.reason
                report["partial_writes_possible"] = True
                report["analyzer_run_recoveries"] = analyzer_run_recoveries
                report["apply_plan"] = (
                    "Apply found an active analyzer run that was not recoverable. "
                    "Review analyzer_run_recoveries before retrying this exact scope."
                )
                report["apply_results"] = apply_results
                report["after"] = after
                raise AnalyzerBackfillApplyError(report)

        response, brand, competitors, intent = await _load_analyzer_inputs(
            session,
            candidate,
            target_brand_id=int(scope.brand_id),
        )
        result = await analyze_func(session, response, brand, competitors, intent)
        apply_results.append(result)
        if result.get("status") != "done":
            after = summarize_candidates(await collect_candidate_responses(session, scope))
            report["write_performed"] = True
            report["write_attempted"] = True
            report["apply_failed"] = True
            report["failed_response_id"] = candidate.response_id
            report["failure_reason"] = (
                result.get("error") or result.get("reason") or "non_done_status"
            )
            report["partial_writes_possible"] = True
            report["analyzer_run_recoveries"] = analyzer_run_recoveries
            report["apply_plan"] = (
                "Apply failed before all selected responses completed with status=done. "
                "Review apply_results and after evidence before retrying the exact scope."
            )
            report["apply_results"] = apply_results
            report["after"] = after
            raise AnalyzerBackfillApplyError(report)

    report["write_performed"] = True
    report["apply_plan"] = "Applied only selected response_ids."
    report["apply_results"] = apply_results
    report["analyzer_run_recoveries"] = analyzer_run_recoveries
    report["after"] = summarize_candidates(await collect_candidate_responses(session, scope))
    if aggregate:
        report["aggregate_results"] = await _aggregate_selected_days(
            session,
            selected,
            brand_id=int(scope.brand_id),
            competitive_brand_ids=scope.normalized_competitive_brand_ids(),
        )
    return report


def _parse_int_csv(raw: str) -> tuple[int, ...]:
    if not raw.strip():
        return ()
    return tuple(int(part.strip()) for part in raw.split(",") if part.strip())


async def run_from_args(args: argparse.Namespace) -> dict:
    scope = BestCofferAnalyzerBackfillScope(
        brand_id=args.brand_id,
        date_from=args.date_from,
        date_to=args.date_to,
        response_ids=_parse_int_csv(args.response_ids),
        query_ids=_parse_int_csv(args.query_ids),
        source_brand_id=args.source_brand_id,
        competitive_brand_ids=tuple(args.competitive_brand_id or ()),
        limit=args.limit,
    )
    engine = create_task_engine()
    try:
        async with get_task_async_session(engine) as session:
            return await build_bestcoffer_analyzer_backfill_report(
                session,
                scope,
                apply=args.apply,
                approval_ref=args.approval_ref,
                aggregate=args.aggregate,
            )
    finally:
        await engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Controlled BestCoffer analyzer backfill for issue #686"
    )
    parser.add_argument("--brand-id", type=int, default=24)
    parser.add_argument("--from", dest="date_from")
    parser.add_argument("--to", dest="date_to")
    parser.add_argument("--response-ids", default="", help="Comma-separated response ids")
    parser.add_argument("--query-ids", default="", help="Comma-separated query ids")
    parser.add_argument("--source-brand-id", type=int)
    parser.add_argument(
        "--competitive-brand-id",
        action="append",
        type=int,
        default=[],
        help="Competitive canonical brand ID for aggregation; repeatable.",
    )
    parser.add_argument("--limit", type=int, default=MAX_LIMIT)
    parser.add_argument("--apply", action="store_true", help="Perform analyzer writes")
    parser.add_argument("--aggregate", action="store_true", help="Aggregate selected days")
    parser.add_argument(
        "--approval-ref",
        default="",
        help=(
            "Issue #686 comment URL plus explicit production-write approval evidence "
            "required with --apply"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = asyncio.run(run_from_args(args))
    except AnalyzerBackfillApplyError as exc:
        print(json.dumps(exc.report, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AnalyzerBackfillApplyError",
    "BestCofferAnalyzerBackfillScope",
    "build_bestcoffer_analyzer_backfill_report",
    "collect_candidate_responses",
    "summarize_candidates",
    "validate_approval_ref",
]
