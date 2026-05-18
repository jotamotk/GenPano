"""Controlled Topics analyzer backfill for issue #654.

This module deliberately avoids date-wide resets. It selects successful
responses by explicit response ids or by the concrete topic/prompt slice used
by the live `/brand/topics` E2E blocker, emits before/after evidence, and only
re-runs the analyzer for the selected response ids when apply mode is used.
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

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.config import create_task_engine, get_task_async_session
from geo_tracker.db.models import (
    AnalysisStatus,
    Brand,
    BrandMention,
    Competitor,
    LLMResponse,
    ProductFeatureMention,
    Profile,
    Prompt,
    Query,
    QueryStatus,
    ResponseAnalysis,
    SentimentDriver,
    Topic,
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
GITHUB_ISSUE_RE = re.compile(
    r"^https://github\.com/jotamotk/trash_test/issues/(654|590|585|1239)"
    r"(#issuecomment-[0-9]+)?$"
)
RELATION_KEYS = (
    "relations",
    "response_relations",
    "brand_relations",
    "product_relations",
    "relation_facts",
)

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
class TopicsAnalyzerBackfillScope:
    topic_id: int | None = None
    prompt_id: int | None = None
    date_from: str | None = None
    date_to: str | None = None
    prompt_intent: str | None = None
    prompt_language: str | None = None
    response_ids: tuple[int, ...] = field(default_factory=tuple)
    query_ids: tuple[int, ...] = field(default_factory=tuple)
    limit: int = 20

    def normalized_response_ids(self) -> tuple[int, ...]:
        return tuple(sorted({int(value) for value in self.response_ids if int(value) > 0}))

    def normalized_query_ids(self) -> tuple[int, ...]:
        return tuple(sorted({int(value) for value in self.query_ids if int(value) > 0}))


@dataclass(frozen=True)
class SelectedResponse:
    response_id: int
    query_id: int
    brand_id: int
    topic_id: int | None
    prompt_id: int | None
    collected_at: str | None


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


def _scope_dict(scope: TopicsAnalyzerBackfillScope) -> dict:
    data = asdict(scope)
    data["response_ids"] = list(scope.normalized_response_ids())
    data["query_ids"] = list(scope.normalized_query_ids())
    return data


def validate_scope(scope: TopicsAnalyzerBackfillScope, *, apply: bool = False) -> None:
    if scope.limit < 1 or scope.limit > 50:
        raise ValueError("limit must be between 1 and 50")
    _parse_day(scope.date_from, "date_from")
    _parse_day(scope.date_to, "date_to")
    response_ids = scope.normalized_response_ids()
    query_ids = scope.normalized_query_ids()
    if response_ids or query_ids:
        return
    missing = [
        name
        for name, value in (
            ("topic_id", scope.topic_id),
            ("prompt_id", scope.prompt_id),
            ("date_from", scope.date_from),
            ("date_to", scope.date_to),
        )
        if value in (None, "")
    ]
    if missing:
        raise ValueError(
            "scope must include explicit response_ids, query_ids, or topic_id, "
            f"prompt_id, date_from, and date_to; missing: {', '.join(missing)}"
        )
    if (
        apply
        and (scope.topic_id is None or scope.prompt_id is None)
        and not (response_ids or query_ids)
    ):
        raise ValueError("apply mode requires explicit response_ids or topic_id + prompt_id")


def validate_approval_ref(approval_ref: str | None) -> str:
    value = (approval_ref or "").strip()
    if not value or not GITHUB_ISSUE_RE.match(value):
        raise ValueError(
            "apply mode requires approval_ref in "
            "https://github.com/jotamotk/trash_test/issues/{654,590,585,1239}"
        )
    return value


async def select_successful_responses(
    session: AsyncSession,
    scope: TopicsAnalyzerBackfillScope,
) -> list[SelectedResponse]:
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
        conditions.extend(
            [
                Topic.id == int(scope.topic_id),
                Prompt.id == int(scope.prompt_id),
            ]
        )
        if start_at is not None:
            conditions.append(LLMResponse.collected_at >= start_at)
        if end_at is not None:
            conditions.append(LLMResponse.collected_at <= end_at)
        if scope.prompt_intent:
            conditions.append(Prompt.intent == scope.prompt_intent)
        if scope.prompt_language:
            conditions.append(Prompt.language == scope.prompt_language)

    stmt = (
        select(LLMResponse, Query, Prompt, Topic)
        .join(Query, Query.id == LLMResponse.query_id)
        .outerjoin(Prompt, Prompt.id == Query.prompt_id)
        .outerjoin(Topic, Topic.id == Prompt.topic_id)
        .where(and_(*conditions))
        .order_by(LLMResponse.collected_at.asc(), LLMResponse.id.asc())
        .limit(scope.limit + 1)
    )
    rows = (await session.execute(stmt)).all()
    if len(rows) > scope.limit:
        raise ValueError(
            f"selected responses exceed limit={scope.limit}; tighten the scope before apply"
        )
    return [
        SelectedResponse(
            response_id=int(response.id),
            query_id=int(query.id),
            brand_id=int(query.brand_id),
            topic_id=int(topic.id) if topic and topic.id is not None else None,
            prompt_id=int(prompt.id) if prompt and prompt.id is not None else None,
            collected_at=response.collected_at.isoformat() if response.collected_at else None,
        )
        for response, query, prompt, topic in rows
    ]


def _has_fact_packages(raw: object) -> bool:
    return isinstance(raw, dict) and isinstance(raw.get("analyzer_fact_packages"), dict)


def _relation_count(raw: object) -> int:
    if not isinstance(raw, dict):
        return 0
    count = 0
    for key in RELATION_KEYS:
        value = raw.get(key)
        if isinstance(value, list):
            count += len(value)
    return count


async def _profile_state(session: AsyncSession, query: Query) -> tuple[str, str, str | None]:
    if query.profile_id in (None, ""):
        return "query_profile_id_null", "Unknown profile", "query.profile_id is NULL"
    profile = await session.get(Profile, query.profile_id)
    if profile is None:
        return (
            "profile_row_missing",
            "Unknown profile",
            "profiles row missing for query.profile_id",
        )
    return "profile_found", profile.name or str(profile.id), None


async def build_evidence_rows(
    session: AsyncSession,
    selected: Iterable[SelectedResponse],
) -> list[dict]:
    rows: list[dict] = []
    for item in selected:
        response = await session.get(LLMResponse, item.response_id)
        query = await session.get(Query, item.query_id)
        if response is None or query is None:
            continue
        analysis = (
            await session.execute(
                select(ResponseAnalysis).where(
                    ResponseAnalysis.response_id == item.response_id
                )
            )
        ).scalar_one_or_none()
        mentions = (
            await session.execute(
                select(BrandMention).where(BrandMention.response_id == item.response_id)
            )
        ).scalars().all()
        mention_ids = [mention.id for mention in mentions]
        driver_count = 0
        if mention_ids:
            driver_count = len(
                (
                    await session.execute(
                        select(SentimentDriver).where(
                            SentimentDriver.mention_id.in_(mention_ids)
                        )
                    )
                ).scalars().all()
            )
        feature_count = 0
        if analysis is not None:
            feature_count = len(
                (
                    await session.execute(
                        select(ProductFeatureMention).where(
                            ProductFeatureMention.analysis_id == analysis.id
                        )
                    )
                ).scalars().all()
            )
        profile_state, profile_name, upstream_null_reason = await _profile_state(
            session,
            query,
        )
        raw = analysis.raw_analysis_json if analysis is not None else None
        rows.append(
            {
                "response_id": item.response_id,
                "query_id": item.query_id,
                "brand_id": item.brand_id,
                "topic_id": item.topic_id,
                "prompt_id": item.prompt_id,
                "engine": query.target_llm,
                "query_status": query.status,
                "analysis_status": response.analysis_status,
                "collected_at": item.collected_at,
                "profile_id": query.profile_id,
                "profile_name": profile_name,
                "profile_state": profile_state,
                "upstream_null_reason": upstream_null_reason,
                "has_analysis": analysis is not None,
                "has_fact_packages": _has_fact_packages(raw),
                "brand_mention_count": len(mentions),
                "product_feature_count": feature_count,
                "sentiment_driver_count": driver_count,
                "relation_count": _relation_count(raw),
                "raw_text_length": len(response.raw_text or ""),
            }
        )
    return rows


def summarize_evidence(rows: list[dict]) -> dict:
    analyzer_states = Counter()
    profile_states = Counter()
    for row in rows:
        profile_states[row["profile_state"]] += 1
        if not row["has_analysis"]:
            analyzer_states["missing_analysis"] += 1
        elif not row["has_fact_packages"]:
            analyzer_states["missing_fact_packages"] += 1
        else:
            analyzer_states["has_fact_packages"] += 1
    return {
        "selected_count": len(rows),
        "profile_state_counts": dict(sorted(profile_states.items())),
        "analyzer_state_counts": dict(sorted(analyzer_states.items())),
        "rows": rows,
    }


async def _load_analyzer_inputs(
    session: AsyncSession,
    item: SelectedResponse,
) -> tuple[LLMResponse, Brand, list[Competitor], str]:
    response = await session.get(LLMResponse, item.response_id)
    query = await session.get(Query, item.query_id)
    if response is None or query is None:
        raise ValueError(f"response/query not found for response_id={item.response_id}")
    brand = await session.get(Brand, query.brand_id)
    if brand is None:
        raise ValueError(f"brand not found for query_id={item.query_id}")
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
    selected: list[SelectedResponse],
) -> list[dict]:
    from geo_tracker.analyzer.aggregator import Aggregator

    pairs: set[tuple[str, int]] = set()
    for item in selected:
        if item.collected_at:
            pairs.add((item.collected_at[:10], item.brand_id))
    results: list[dict] = []
    aggregator = Aggregator(session)
    for date_str, brand_id in sorted(pairs):
        stats = await aggregator.aggregate_daily(datetime.strptime(date_str, "%Y-%m-%d"), brand_id)
        results.append({"date": date_str, "brand_id": brand_id, "stats": stats})
    return results


async def build_topics_analyzer_backfill_report(
    session: AsyncSession,
    scope: TopicsAnalyzerBackfillScope,
    *,
    apply: bool = False,
    approval_ref: str | None = None,
    aggregate: bool = False,
    analyze_func: AnalyzeFunc | None = None,
) -> dict:
    validate_scope(scope, apply=apply)
    if apply:
        approval_ref = validate_approval_ref(approval_ref)

    selected = await select_successful_responses(session, scope)
    before_rows = await build_evidence_rows(session, selected)
    report = {
        "issue": 654,
        "mode": "apply" if apply else "dry_run",
        "write_performed": False,
        "approval_ref": approval_ref,
        "scope": _scope_dict(scope),
        "safe_selection": {
            "successful_responses_only": True,
            "date_wide_reset": False,
            "selected_by_response_ids": bool(scope.normalized_response_ids()),
            "selected_by_query_ids": bool(scope.normalized_query_ids()),
            "selected_by_topic_prompt": bool(scope.topic_id and scope.prompt_id),
            "limit": scope.limit,
        },
        "selected_response_ids": [item.response_id for item in selected],
        "selected_query_ids": [item.query_id for item in selected],
        "before": summarize_evidence(before_rows),
        "apply_plan": (
            "Dry-run only. To apply, rerun with --apply and a GitHub approval_ref; "
            "the tool will re-run analyzer only for selected response_ids."
        ),
        "rollback": (
            "Apply mutates only selected response analyzer artifacts: "
            "llm_responses.analysis_status/analyzed_at, response_analyses, "
            "brand_mentions, citation_sources, sentiment_drivers, and "
            "product_feature_mentions for the selected response_ids. Roll back "
            "by restoring those rows from the pre-apply database backup or by "
            "rerunning the analyzer for the same selected response_ids."
        ),
    }
    if not apply:
        return report

    if analyze_func is None:
        from geo_tracker.analyzer.cli import analyze_single_response

        analyze_func = analyze_single_response

    apply_results: list[dict] = []
    for item in selected:
        response, brand, competitors, intent = await _load_analyzer_inputs(session, item)
        result = await analyze_func(session, response, brand, competitors, intent)
        apply_results.append(result)
        if result.get("status") != "done":
            after_rows = await build_evidence_rows(session, selected)
            report["write_performed"] = True
            report["write_attempted"] = True
            report["apply_failed"] = True
            report["failed_response_id"] = item.response_id
            report["failure_reason"] = (
                result.get("error") or result.get("reason") or "non_done_status"
            )
            report["partial_writes_possible"] = True
            report["apply_plan"] = (
                "Apply failed before all selected responses completed with status=done. "
                "Review apply_results and after evidence before retrying the same exact scope."
            )
            report["apply_results"] = apply_results
            report["after"] = summarize_evidence(after_rows)
            raise AnalyzerBackfillApplyError(report)
    after_rows = await build_evidence_rows(session, selected)
    report["write_performed"] = True
    report["apply_plan"] = "Applied only selected response_ids."
    report["apply_results"] = apply_results
    report["after"] = summarize_evidence(after_rows)
    if aggregate:
        report["aggregate_results"] = await _aggregate_selected_days(session, selected)
    return report


def _parse_int_csv(raw: str) -> tuple[int, ...]:
    if not raw.strip():
        return ()
    ids: list[int] = []
    for part in raw.split(","):
        value = part.strip()
        if value:
            ids.append(int(value))
    return tuple(ids)


async def run_from_args(args: argparse.Namespace) -> dict:
    scope = TopicsAnalyzerBackfillScope(
        topic_id=args.topic_id,
        prompt_id=args.prompt_id,
        date_from=args.date_from,
        date_to=args.date_to,
        prompt_intent=args.prompt_intent or None,
        prompt_language=args.prompt_language or None,
        response_ids=_parse_int_csv(args.response_ids),
        query_ids=_parse_int_csv(args.query_ids),
        limit=args.limit,
    )
    engine = create_task_engine()
    try:
        async with get_task_async_session(engine) as session:
            return await build_topics_analyzer_backfill_report(
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
        description="Controlled Topics analyzer/profile backfill for issue #654"
    )
    parser.add_argument("--topic-id", type=int)
    parser.add_argument("--prompt-id", type=int)
    parser.add_argument("--date-from")
    parser.add_argument("--date-to")
    parser.add_argument("--prompt-intent", default="")
    parser.add_argument("--prompt-language", default="")
    parser.add_argument("--response-ids", default="", help="Comma-separated response ids")
    parser.add_argument("--query-ids", default="", help="Comma-separated query ids")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--apply", action="store_true", help="Perform analyzer writes")
    parser.add_argument("--aggregate", action="store_true", help="Aggregate affected brand-days")
    parser.add_argument(
        "--approval-ref",
        default="",
        help="GitHub issue/comment URL required with --apply",
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
