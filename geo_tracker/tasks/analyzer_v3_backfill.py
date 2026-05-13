"""Chunked Analyzer v3 historical backfill for issue #711."""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Awaitable, Callable

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.agent.response_validation import invalid_response_reason
from geo_tracker.config import create_task_engine, get_task_async_session
from geo_tracker.db.models import (
    AnalysisStatus,
    Brand,
    BrandMention,
    CitationSource,
    Competitor,
    GEOScoreDaily,
    LLMResponse,
    ProductFeatureMention,
    Prompt,
    Query,
    QueryStatus,
    ResponseAnalysis,
    SentimentDriver,
    Topic,
    TopicScoreDaily,
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ANALYZER_VERSION = "v3"
ANALYZER_V3_APPROVAL_RE = re.compile(
    r"^https://github\.com/jotamotk/trash_test/issues/(711|707)"
    r"#issuecomment-[0-9]+(?P<evidence>.*)$",
    re.IGNORECASE,
)
MAX_BATCH_SIZE = 100

AnalyzeFunc = Callable[
    [AsyncSession, LLMResponse, Brand, list[Competitor], str],
    Awaitable[dict],
]


class AnalyzerV3BackfillApplyError(RuntimeError):
    """Raised when apply mode stops before every selected response is done."""

    def __init__(self, report: dict) -> None:
        self.report = report
        super().__init__(
            f"analyzer v3 apply failed for response_id={report.get('failed_response_id')}"
        )


@dataclass(frozen=True)
class AnalyzerV3BackfillScope:
    response_ids: tuple[int, ...] = field(default_factory=tuple)
    query_ids: tuple[int, ...] = field(default_factory=tuple)
    project_id: str | None = None
    brand_id: int | None = None
    topic_id: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    batch_size: int = 25
    resume_cursor: int | None = None

    def normalized_response_ids(self) -> tuple[int, ...]:
        return tuple(
            sorted({int(value) for value in self.response_ids if int(value) > 0})
        )

    def normalized_query_ids(self) -> tuple[int, ...]:
        return tuple(sorted({int(value) for value in self.query_ids if int(value) > 0}))


@dataclass(frozen=True)
class BackfillCandidate:
    response_id: int
    query_id: int
    brand_id: int | None
    topic_id: int | None
    prompt_id: int | None
    engine: str | None
    collected_at: str | None
    analysis_status: str | None
    has_response_analysis: bool
    has_v3_package: bool
    idempotency_key: str | None
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


def validate_scope(scope: AnalyzerV3BackfillScope) -> None:
    if scope.batch_size < 1 or scope.batch_size > MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
    _parse_day(scope.date_from, "date_from")
    _parse_day(scope.date_to, "date_to")
    if scope.normalized_response_ids() or scope.normalized_query_ids():
        return
    missing = [
        name
        for name, value in (
            ("brand_id", scope.brand_id),
            ("date_from", scope.date_from),
            ("date_to", scope.date_to),
        )
        if value in (None, "")
    ]
    if missing:
        raise ValueError(
            "scope must include response_ids, query_ids, or brand_id/date_from/date_to; "
            f"missing: {', '.join(missing)}"
        )


def validate_approval_ref(approval_ref: str | None) -> str:
    value = (approval_ref or "").strip()
    match = ANALYZER_V3_APPROVAL_RE.match(value) if value else None
    normalized = re.sub(r"[-_]+", " ", value.lower())
    has_write_approval = (
        "ai lead" in normalized
        and bool(re.search(r"\bproduction\s+writes?\b", normalized))
        and bool(re.search(r"\bapprov\w*\b", normalized))
        and "analyzer v3" in normalized
        and "apply" in normalized
    )
    if not match or not has_write_approval:
        raise ValueError(
            "approval_ref must be a #707/#711 issue comment URL with explicit "
            "AI Lead production-write approval for Analyzer v3 apply"
        )
    return value


def _scope_dict(scope: AnalyzerV3BackfillScope) -> dict:
    data = asdict(scope)
    data["response_ids"] = list(scope.normalized_response_ids())
    data["query_ids"] = list(scope.normalized_query_ids())
    return data


def _project_scope_has_explicit_boundary(scope: AnalyzerV3BackfillScope) -> bool:
    return bool(scope.normalized_response_ids() or scope.normalized_query_ids())


def _project_scope_is_broad_apply(scope: AnalyzerV3BackfillScope) -> bool:
    return bool(scope.project_id and not _project_scope_has_explicit_boundary(scope))


def _has_v3_package(raw: object) -> tuple[bool, str | None]:
    if not isinstance(raw, dict):
        return False, None
    package = raw.get("analyzer_fact_package_v3")
    if not isinstance(package, dict):
        return False, None
    return package.get("analyzer_version") == ANALYZER_VERSION, package.get(
        "idempotency_key"
    )


def _candidate_state(candidate: BackfillCandidate) -> str:
    if candidate.invalid_reason:
        return "FAILED"
    if candidate.has_v3_package:
        return "DONE"
    if (candidate.analysis_status or "").lower() == AnalysisStatus.RUNNING.value:
        return "RUNNING"
    return "PENDING"


def _candidate_dict(candidate: BackfillCandidate) -> dict:
    return {
        "response_id": candidate.response_id,
        "query_id": candidate.query_id,
        "brand_id": candidate.brand_id,
        "topic_id": candidate.topic_id,
        "prompt_id": candidate.prompt_id,
        "engine": candidate.engine,
        "collected_at": candidate.collected_at,
        "analysis_status": candidate.analysis_status,
        "has_response_analysis": candidate.has_response_analysis,
        "has_v3_package": candidate.has_v3_package,
        "idempotency_key": candidate.idempotency_key,
        "invalid_reason": candidate.invalid_reason,
        "state": _candidate_state(candidate),
    }


async def collect_candidates(
    session: AsyncSession,
    scope: AnalyzerV3BackfillScope,
) -> list[BackfillCandidate]:
    validate_scope(scope)
    response_ids = scope.normalized_response_ids()
    query_ids = scope.normalized_query_ids()
    start_at = _parse_day(scope.date_from, "date_from")
    end_at = _end_of_day(_parse_day(scope.date_to, "date_to"))

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
        if scope.brand_id is not None:
            conditions.append(Query.brand_id == int(scope.brand_id))
        if scope.topic_id is not None:
            conditions.append(Topic.id == int(scope.topic_id))
        if start_at is not None:
            conditions.append(LLMResponse.collected_at >= start_at)
        if end_at is not None:
            conditions.append(LLMResponse.collected_at <= end_at)
    if scope.resume_cursor is not None:
        conditions.append(LLMResponse.id > int(scope.resume_cursor))

    stmt = (
        select(LLMResponse, Query, Prompt, Topic, ResponseAnalysis)
        .join(Query, Query.id == LLMResponse.query_id)
        .outerjoin(Prompt, Prompt.id == Query.prompt_id)
        .outerjoin(Topic, Topic.id == Prompt.topic_id)
        .outerjoin(ResponseAnalysis, ResponseAnalysis.response_id == LLMResponse.id)
        .where(and_(*conditions))
        .order_by(LLMResponse.id.asc())
    )
    rows = (await session.execute(stmt)).all()
    candidates: list[BackfillCandidate] = []
    for response, query, prompt, topic, analysis in rows:
        invalid_reason = invalid_response_reason(
            query.target_llm or "", response.raw_text
        )
        if scope.brand_id is not None and int(query.brand_id) != int(scope.brand_id):
            invalid_reason = invalid_reason or "outside_brand_scope"
        if scope.topic_id is not None and (
            topic is None or int(topic.id) != int(scope.topic_id)
        ):
            invalid_reason = invalid_reason or "outside_topic_scope"
        has_v3, idempotency_key = _has_v3_package(
            analysis.raw_analysis_json if analysis is not None else None
        )
        candidates.append(
            BackfillCandidate(
                response_id=int(response.id),
                query_id=int(query.id),
                brand_id=int(query.brand_id) if query.brand_id is not None else None,
                topic_id=int(topic.id) if topic and topic.id is not None else None,
                prompt_id=int(prompt.id) if prompt and prompt.id is not None else None,
                engine=query.target_llm,
                collected_at=response.collected_at.isoformat()
                if response.collected_at
                else None,
                analysis_status=response.analysis_status,
                has_response_analysis=analysis is not None,
                has_v3_package=has_v3,
                idempotency_key=idempotency_key,
                invalid_reason=invalid_reason,
            )
        )
    return candidates


async def _artifact_counts(
    session: AsyncSession,
    candidates: list[BackfillCandidate],
) -> dict:
    response_ids = [candidate.response_id for candidate in candidates]
    if not response_ids:
        return {
            "response_analyses": 0,
            "analyzer_packages": 0,
            "brand_mentions": 0,
            "sentiment_drivers": 0,
            "citation_attribution": 0,
            "product_facts": 0,
            "aggregate_rows": {
                "scoped": False,
                "reason": "no selected response candidates to derive aggregate scope",
                "geo_score_daily": None,
                "topic_score_daily": None,
                "total": None,
            },
        }
    analyses = (
        (
            await session.execute(
                select(ResponseAnalysis).where(
                    ResponseAnalysis.response_id.in_(response_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    analysis_ids = [analysis.id for analysis in analyses if analysis.id is not None]
    mentions = (
        (
            await session.execute(
                select(BrandMention).where(BrandMention.response_id.in_(response_ids))
            )
        )
        .scalars()
        .all()
    )
    mention_ids = [mention.id for mention in mentions if mention.id is not None]
    citation_count = len(
        (
            await session.execute(
                select(CitationSource).where(
                    CitationSource.response_id.in_(response_ids)
                )
            )
        )
        .scalars()
        .all()
    )
    driver_count = 0
    if mention_ids:
        driver_count = len(
            (
                await session.execute(
                    select(SentimentDriver).where(
                        SentimentDriver.mention_id.in_(mention_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
    product_count = 0
    if analysis_ids:
        product_count = len(
            (
                await session.execute(
                    select(ProductFeatureMention).where(
                        ProductFeatureMention.analysis_id.in_(analysis_ids)
                    )
                )
            )
            .scalars()
            .all()
        )
    analyzer_packages = sum(
        1 for analysis in analyses if _has_v3_package(analysis.raw_analysis_json)[0]
    )
    aggregate_rows = await _scoped_aggregate_counts(session, candidates)
    return {
        "response_analyses": len(analyses),
        "analyzer_packages": analyzer_packages,
        "brand_mentions": len(mentions),
        "sentiment_drivers": driver_count,
        "citation_attribution": citation_count,
        "product_facts": product_count,
        "aggregate_rows": aggregate_rows,
    }


async def _scoped_aggregate_counts(
    session: AsyncSession,
    candidates: list[BackfillCandidate],
) -> dict:
    brand_ids = sorted(
        {
            int(candidate.brand_id)
            for candidate in candidates
            if candidate.brand_id is not None
        }
    )
    dates = sorted(
        {
            candidate.collected_at[:10]
            for candidate in candidates
            if candidate.collected_at
        }
    )
    topic_ids = sorted(
        {
            int(candidate.topic_id)
            for candidate in candidates
            if candidate.topic_id is not None
        }
    )
    if not brand_ids or not dates:
        return {
            "scoped": False,
            "reason": (
                "candidate response set lacks brand_id or collected_at dates; "
                "global aggregate rows are intentionally not counted"
            ),
            "geo_score_daily": None,
            "topic_score_daily": None,
            "total": None,
        }

    geo_count = int(
        (
            await session.execute(
                select(func.count())
                .select_from(GEOScoreDaily)
                .where(
                    GEOScoreDaily.brand_id.in_(brand_ids),
                    func.date(GEOScoreDaily.date).in_(dates),
                )
            )
        ).scalar()
        or 0
    )
    topic_query = (
        select(func.count())
        .select_from(TopicScoreDaily)
        .where(
            TopicScoreDaily.brand_id.in_(brand_ids),
            func.date(TopicScoreDaily.date).in_(dates),
        )
    )
    topic_scope_reason = None
    if topic_ids:
        topic_query = topic_query.where(TopicScoreDaily.topic_id.in_(topic_ids))
    else:
        topic_scope_reason = "topic_id unavailable for selected candidates"
    topic_count = int((await session.execute(topic_query)).scalar() or 0)
    return {
        "scoped": True,
        "scope": {
            "brand_ids": brand_ids,
            "dates": dates,
            "topic_ids": topic_ids,
        },
        "topic_scope_reason": topic_scope_reason,
        "geo_score_daily": geo_count,
        "topic_score_daily": topic_count,
        "total": geo_count + topic_count,
    }


async def summarize_candidates(
    session: AsyncSession,
    candidates: list[BackfillCandidate],
) -> dict:
    rows = [_candidate_dict(candidate) for candidate in candidates]
    state_counts = Counter(row["state"] for row in rows)
    return {
        "state_counts": dict(sorted(state_counts.items())),
        "artifact_counts": await _artifact_counts(session, candidates),
        "partial_state": {
            "completed_response_ids": [
                row["response_id"] for row in rows if row["state"] == "DONE"
            ],
            "running_response_ids": [
                row["response_id"] for row in rows if row["state"] == "RUNNING"
            ],
            "failed_response_ids": [
                row["response_id"] for row in rows if row["state"] == "FAILED"
            ],
            "pending_response_ids": [
                row["response_id"] for row in rows if row["state"] == "PENDING"
            ],
        },
        "rows": rows,
    }


async def _load_analyzer_inputs(
    session: AsyncSession,
    candidate: BackfillCandidate,
) -> tuple[LLMResponse, Brand, list[Competitor], str]:
    response = await session.get(LLMResponse, candidate.response_id)
    query = await session.get(Query, candidate.query_id)
    if response is None or query is None:
        raise ValueError(
            f"response/query not found for response_id={candidate.response_id}"
        )
    brand = await session.get(Brand, candidate.brand_id)
    if brand is None:
        raise ValueError(f"brand not found for response_id={candidate.response_id}")
    competitors = (
        (
            await session.execute(
                select(Competitor).where(Competitor.brand_id == brand.id)
            )
        )
        .scalars()
        .all()
    )
    intent = "non_brand"
    if query.prompt_id:
        prompt = await session.get(Prompt, query.prompt_id)
        if prompt and prompt.intent:
            intent = prompt.intent
    return response, brand, competitors, intent


async def build_analyzer_v3_backfill_report(
    session: AsyncSession,
    scope: AnalyzerV3BackfillScope,
    *,
    apply: bool = False,
    approval_ref: str | None = None,
    analyze_func: AnalyzeFunc | None = None,
) -> dict:
    validate_scope(scope)
    if apply:
        approval_ref = validate_approval_ref(approval_ref)

    candidates = await collect_candidates(session, scope)
    before = await summarize_candidates(session, candidates)
    pending = [
        candidate
        for candidate in candidates
        if _candidate_state(candidate) == "PENDING"
    ]
    selected = pending[: int(scope.batch_size)]
    skipped = [candidate for candidate in candidates if candidate not in selected]
    next_cursor = selected[-1].response_id if selected else scope.resume_cursor
    project_scope_enforced = False
    project_scope_note = (
        "No queries.project_id column exists in this pipeline schema; project_id "
        "is operator traceability only for dry-run reports and is not an apply "
        "boundary unless explicit response_ids or query_ids are supplied."
    )
    broad_project_apply = apply and _project_scope_is_broad_apply(scope)
    if broad_project_apply:
        skipped = list(candidates)
        selected = []
        next_cursor = scope.resume_cursor
    report = {
        "issue": 711,
        "mode": "apply" if apply else "dry_run",
        "write_performed": False,
        "approval_ref": approval_ref,
        "scope": _scope_dict(scope),
        "safe_selection": {
            "successful_responses_only": True,
            "versioned_analyzer_artifacts_only": True,
            "production_apply_requires_approval_ref": True,
            "non_destructive_v3_apply_required": True,
            "project_scope": scope.project_id,
            "project_scope_enforced": project_scope_enforced,
            "project_filter_note": project_scope_note if scope.project_id else None,
            "selected_by_response_ids": bool(scope.normalized_response_ids()),
            "selected_by_query_ids": bool(scope.normalized_query_ids()),
        },
        "selected_response_ids": [candidate.response_id for candidate in selected],
        "skipped_response_ids": [candidate.response_id for candidate in skipped],
        "before": before,
        "resume": {
            "resume_cursor": scope.resume_cursor,
            "next_resume_cursor": next_cursor,
            "batch_size": int(scope.batch_size),
            "has_more": len(selected) >= int(scope.batch_size),
        },
        "apply_plan": (
            "Dry-run only. To apply, rerun with --apply and a #707/#711 AI Lead "
            "approval_ref after attaching dry-run evidence."
        ),
        "rollback": (
            "Apply mutates only selected response analyzer artifacts and writes "
            "versioned Analyzer v3 packages through the analyzer pipeline. Restore "
            "from the pre-apply database backup or rerun the same response_ids."
        ),
    }
    if broad_project_apply:
        report.update(
            {
                "apply_blocked": True,
                "block_reason": "project_scope_requires_explicit_response_or_query_ids",
                "write_performed": False,
                "apply_plan": (
                    "Apply blocked before analyzer writes because project_id cannot "
                    "be enforced by this schema without explicit response_ids or "
                    "query_ids. Rerun dry-run, attach evidence, then apply with "
                    "explicit ids."
                ),
            }
        )
        return report
    if not apply:
        return report

    if analyze_func is None:
        report.update(
            {
                "apply_blocked": True,
                "block_reason": "non_destructive_v3_apply_not_implemented",
                "write_performed": False,
                "write_attempted": False,
                "apply_plan": (
                    "Production apply is blocked because the legacy analyzer "
                    "replacement path deletes existing evidence before the LLM "
                    "pass completes. Implement a v3 staging/commit path before "
                    "enabling writes."
                ),
            }
        )
        return report

    apply_results: list[dict] = []
    for candidate in selected:
        response, brand, competitors, intent = await _load_analyzer_inputs(
            session, candidate
        )
        result = await analyze_func(session, response, brand, competitors, intent)
        apply_results.append(result)
        if result.get("status") != "done":
            after = await summarize_candidates(
                session, await collect_candidates(session, scope)
            )
            report.update(
                {
                    "write_performed": True,
                    "write_attempted": True,
                    "apply_failed": True,
                    "failed_response_id": candidate.response_id,
                    "failure_reason": result.get("error")
                    or result.get("reason")
                    or "non_done_status",
                    "partial_writes_possible": True,
                    "apply_results": apply_results,
                    "after": after,
                    "apply_plan": (
                        "Apply failed before all selected responses completed. "
                        "Review partial_state and retry with the same scope/resume cursor."
                    ),
                }
            )
            raise AnalyzerV3BackfillApplyError(report)
    report["write_performed"] = bool(selected)
    report["apply_results"] = apply_results
    report["after"] = await summarize_candidates(
        session, await collect_candidates(session, scope)
    )
    report["apply_plan"] = "Applied only selected pending response_ids."
    return report


def _parse_int_csv(raw: str) -> tuple[int, ...]:
    if not raw.strip():
        return ()
    return tuple(int(part.strip()) for part in raw.split(",") if part.strip())


async def run_from_args(args: argparse.Namespace) -> dict:
    scope = AnalyzerV3BackfillScope(
        response_ids=_parse_int_csv(args.response_ids),
        query_ids=_parse_int_csv(args.query_ids),
        project_id=args.project_id,
        brand_id=args.brand_id,
        topic_id=args.topic_id,
        date_from=args.date_from,
        date_to=args.date_to,
        batch_size=args.batch_size,
        resume_cursor=args.resume_cursor,
    )
    engine = create_task_engine()
    try:
        async with get_task_async_session(engine) as session:
            return await build_analyzer_v3_backfill_report(
                session,
                scope,
                apply=args.apply,
                approval_ref=args.approval_ref,
            )
    finally:
        await engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyzer v3 backfill for issue #711")
    parser.add_argument(
        "--response-ids", default="", help="Comma-separated response ids"
    )
    parser.add_argument("--query-ids", default="", help="Comma-separated query ids")
    parser.add_argument("--project-id")
    parser.add_argument("--brand-id", type=int)
    parser.add_argument("--topic-id", type=int)
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--batch-size", type=int, default=25)
    parser.add_argument("--resume-cursor", type=int)
    parser.add_argument("--apply", action="store_true", help="Perform analyzer writes")
    parser.add_argument("--approval-ref", default="", help="Required with --apply")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        report = asyncio.run(run_from_args(args))
    except AnalyzerV3BackfillApplyError as exc:
        print(json.dumps(exc.report, ensure_ascii=False, indent=2, sort_keys=True))
        return 1
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
