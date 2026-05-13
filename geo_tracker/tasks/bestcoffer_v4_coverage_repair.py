"""Read-only export and exact-ID repair for BestCoffer analyzer v4 coverage.

Issue #827 is deliberately narrower than the older analyzer backfills: export
may inspect the scoped BestCoffer project/window, but repair apply must use exact
response IDs and trusted #827 approval. Apply only migrates already-stored raw
analyzer_v4 packages into first-class analyzer_runs/fact tables. Rows that only
have legacy v3 packages are reported as requiring reanalysis.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.request import Request, urlopen

from sqlalchemy import and_, delete, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from geo_tracker.agent.response_validation import (
    doubao_persistence_auth_reason,
    invalid_response_reason,
)
from geo_tracker.analyzer.cli import _persist_analyzer_v4_facts
from geo_tracker.analyzer.v4_contract import (
    ANALYZER_V4_SCHEMA_VERSION,
    validate_analyzer_v4_package,
)
from geo_tracker.config import create_task_engine, get_task_async_session
from geo_tracker.db.models import (
    AnalysisFactLink,
    AnalyzerQualityFlag,
    AnalyzerRun,
    LLMResponse,
    Prompt,
    Query,
    QueryStatus,
    ResponseAnalysis,
    ResponseEntity,
    ResponseRelationFact,
    Topic,
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_EXPORT_LIMIT = 500
MAX_APPLY_IDS = 200
GITHUB_ISSUE_COMMENT_RE = re.compile(
    r"^https://github\.com/jotamotk/trash_test/issues/827"
    r"#issuecomment-(?P<comment_id>[0-9]+)$",
    re.IGNORECASE,
)
APPROVAL_COMMENT_API = (
    "https://api.github.com/repos/jotamotk/trash_test/issues/comments/{comment_id}"
)
TRUSTED_APPROVAL_AUTHOR_ASSOCIATIONS = frozenset(
    {"OWNER", "MEMBER", "COLLABORATOR"}
)
ANALYZED_STATUSES = frozenset({"done", "partial"})

ApprovalCommentFetcher = Callable[[int], dict[str, Any]]

APPROVAL_REF_HELP = (
    "Run export first, attach the exact response_ids and dry-run repair plan to "
    "#827, then apply only with exact response_ids plus a trusted #827 AI Lead "
    "approval comment. Apply migrates existing raw analyzer_v4 packages into "
    "first-class analyzer_runs/fact tables; response IDs without a valid raw v4 "
    "package are reported as reanalysis_required and are not written by this task."
)

ROLLBACK_NOTE = (
    "Rollback is exact-ID scoped: delete analyzer_runs created by this task using "
    "trigger_source='issue_827_v4_coverage_repair' or idempotency_key prefix "
    "'issue-827:migrate-raw-v4:', which cascades first-class v4 fact rows. No "
    "response_analyses, citation_sources, GEO rows, scraper state, or legacy "
    "facts are rewritten by this repair path."
)


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass(frozen=True)
class BestCofferV4CoverageScope:
    project_id: str
    brand_id: int = 24
    competitor_brand_ids: tuple[int, ...] = field(default_factory=tuple)
    date_from: str | None = None
    date_to: str | None = None
    response_ids: tuple[int, ...] = field(default_factory=tuple)
    query_ids: tuple[int, ...] = field(default_factory=tuple)
    limit: int = MAX_EXPORT_LIMIT

    def normalized_response_ids(self) -> tuple[int, ...]:
        return tuple(sorted({int(value) for value in self.response_ids if int(value) > 0}))

    def normalized_query_ids(self) -> tuple[int, ...]:
        return tuple(sorted({int(value) for value in self.query_ids if int(value) > 0}))

    def normalized_competitor_brand_ids(self) -> tuple[int, ...]:
        return tuple(
            sorted({int(value) for value in self.competitor_brand_ids if int(value) > 0})
        )

    def allowed_brand_ids(self) -> tuple[int, ...]:
        return tuple(sorted({int(self.brand_id), *self.normalized_competitor_brand_ids()}))

    def validate(self, *, mode: str = "export") -> None:
        validate_scope(self, mode=mode)


@dataclass(frozen=True)
class V4CoverageRow:
    response_id: int
    query_id: int
    query_brand_id: int | None
    topic_brand_id: int | None
    topic_id: int | None
    prompt_id: int | None
    engine: str | None
    collected_at: str | None
    created_at: str | None
    analysis_status: str | None
    latest_run_id: int | None
    latest_run_status: str | None
    latest_run_failure_code: str | None
    latest_run_failure_message: str | None
    latest_run_completed_at: str | None
    latest_run_started_at: str | None
    repair_bucket: str
    has_raw_analysis_json: bool
    has_raw_analyzer_v4_package: bool
    has_raw_analyzer_v3_package: bool
    raw_v4_package_valid: bool
    raw_v4_validation_errors: tuple[str, ...]
    first_class_fact_counts: dict[str, int]
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


def validate_scope(scope: BestCofferV4CoverageScope, *, mode: str = "export") -> None:
    if mode not in {"export", "dry_run", "apply"}:
        raise ValueError("mode must be export, dry_run, or apply")
    if not str(scope.project_id or "").strip():
        raise ValueError("project_id is required")
    if int(scope.brand_id) <= 0:
        raise ValueError("brand_id must be positive")
    if int(scope.limit) < 1 or int(scope.limit) > MAX_EXPORT_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_EXPORT_LIMIT}")
    _parse_day(scope.date_from, "date_from")
    _parse_day(scope.date_to, "date_to")

    has_exact_ids = bool(scope.normalized_response_ids() or scope.normalized_query_ids())
    if mode in {"dry_run", "apply"} and not scope.normalized_response_ids():
        raise ValueError(f"{mode} mode requires explicit response_ids")
    if mode in {"dry_run", "apply"} and scope.normalized_query_ids():
        raise ValueError(f"{mode} mode does not accept query_ids; use exact response_ids")
    if mode == "apply" and len(scope.normalized_response_ids()) > MAX_APPLY_IDS:
        raise ValueError(f"apply mode supports at most {MAX_APPLY_IDS} exact response_ids")
    if has_exact_ids:
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
            "scope must include exact response_ids, query_ids, or date_from/date_to; "
            f"missing: {', '.join(missing)}"
        )


def _fetch_github_issue_comment(comment_id: int) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "genpano-issue-827-v4-coverage-repair",
    }
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        APPROVAL_COMMENT_API.format(comment_id=int(comment_id)),
        headers=headers,
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def _normalized_comment_body(comment: dict[str, Any]) -> str:
    return re.sub(r"[-_]+", " ", str(comment.get("body") or "").lower())


def _validate_comment_belongs_to_issue_827(
    comment: dict[str, Any],
    approval_ref: str,
) -> None:
    issue_url = str(comment.get("issue_url") or "")
    html_url = str(comment.get("html_url") or "")
    if not issue_url.endswith("/repos/jotamotk/trash_test/issues/827"):
        raise ValueError("approval_ref comment must belong to jotamotk/trash_test#827")
    if html_url and html_url.rstrip("/") != approval_ref.rstrip("/"):
        raise ValueError("approval_ref comment URL does not match fetched GitHub comment")


def _validate_comment_author_trusted(comment: dict[str, Any]) -> None:
    association = str(comment.get("author_association") or "").upper()
    if association in TRUSTED_APPROVAL_AUTHOR_ASSOCIATIONS:
        return
    user = comment.get("user") or {}
    login = user.get("login") if isinstance(user, dict) else None
    raise ValueError(
        "approval_ref comment must be from a trusted author with "
        "author_association OWNER, MEMBER, or COLLABORATOR; "
        f"got author_association={association or '<empty>'}, login={login or '<unknown>'}"
    )


def _validate_comment_has_write_approval(comment: dict[str, Any]) -> None:
    normalized = _normalized_comment_body(comment)
    has_write_approval = (
        "ai lead" in normalized
        and ("trusted approval" in normalized or "production write approval" in normalized)
        and "bestcoffer" in normalized
        and "analyzer v4" in normalized
        and "run coverage" in normalized
        and "repair" in normalized
        and "apply" in normalized
    )
    if not has_write_approval:
        raise ValueError(
            "approval_ref comment body must contain explicit AI Lead trusted "
            "production-write approval for BestCoffer analyzer v4 run coverage "
            "repair apply"
        )


def _validate_comment_covers_response_ids(
    comment: dict[str, Any],
    response_ids: tuple[int, ...],
) -> None:
    body = str(comment.get("body") or "")
    approved_ids = _extract_structured_response_ids(body)
    missing = [response_id for response_id in response_ids if response_id not in approved_ids]
    if missing:
        raise ValueError(
            "approval_ref comment must list every exact response_id approved for apply; "
            f"missing={missing}"
        )


def _extract_structured_response_ids(body: str) -> set[int]:
    lines = str(body or "").splitlines()
    approved: set[int] = set()
    label_re = re.compile(r"\bresponse[\s_-]*ids?\s*:", re.IGNORECASE)
    list_line_re = re.compile(r"^\s*(?:[-*]\s*)?[0-9,\s]+\s*$")
    for index, line in enumerate(lines):
        match = label_re.search(line)
        if not match:
            continue
        tail = line[match.end():]
        first_segment = re.split(r"(?<=[0-9])\.(?:\s|$)", tail, maxsplit=1)[0]
        approved.update(int(token) for token in re.findall(r"(?<!\d)\d+(?!\d)", first_segment))
        for follow in lines[index + 1:]:
            if label_re.search(follow):
                break
            if not list_line_re.match(follow):
                break
            approved.update(int(token) for token in re.findall(r"(?<!\d)\d+(?!\d)", follow))
    return approved


def validate_approval_ref(
    approval_ref: str | None,
    *,
    approval_comment_fetcher: ApprovalCommentFetcher | None = None,
    response_ids: tuple[int, ...] = tuple(),
) -> str:
    value = (approval_ref or "").strip()
    match = GITHUB_ISSUE_COMMENT_RE.match(value) if value else None
    if not match:
        raise ValueError(
            "apply mode requires approval_ref to be the exact #827 issue comment URL"
        )
    fetcher = approval_comment_fetcher or _fetch_github_issue_comment
    comment = fetcher(int(match.group("comment_id")))
    _validate_comment_belongs_to_issue_827(comment, value)
    _validate_comment_author_trusted(comment)
    _validate_comment_has_write_approval(comment)
    if response_ids:
        _validate_comment_covers_response_ids(comment, response_ids)
    return value


def _scope_dict(scope: BestCofferV4CoverageScope) -> dict[str, Any]:
    data = asdict(scope)
    data["response_ids"] = list(scope.normalized_response_ids())
    data["query_ids"] = list(scope.normalized_query_ids())
    data["competitor_brand_ids"] = list(scope.normalized_competitor_brand_ids())
    return data


async def _load_project_topic_ids(session: AsyncSession, project_id: str) -> set[int]:
    try:
        result = await session.execute(
            text(
                """
                SELECT topic_id
                FROM project_topic_pins
                WHERE CAST(project_id AS TEXT) = :project_id
                  AND COALESCE(state, 'tracked') <> 'ignored'
                """
            ),
            {"project_id": project_id},
        )
    except SQLAlchemyError:
        raise ValueError("project topic scope unavailable; refusing to fall back to brand scope")
    topic_ids = {int(row[0]) for row in result.all() if row[0] is not None}
    if not topic_ids:
        raise ValueError("project topic scope has no tracked topics; refusing brand fallback")
    return topic_ids


def _response_invalid_reason(response: LLMResponse, query: Query) -> str | None:
    llm_name = query.target_llm or ""
    if llm_name.lower() == "doubao" and response.response_html:
        reason = doubao_persistence_auth_reason(
            llm_name,
            response.raw_text,
            response.response_html,
        )
        if reason:
            return reason
    return invalid_response_reason(llm_name, response.raw_text)


def _target_scope_invalid_reason(
    scope: BestCofferV4CoverageScope,
    query: Query,
    topic: Topic | None,
    project_topic_ids: set[int],
) -> str | None:
    topic_id = int(topic.id) if topic and topic.id is not None else None
    if topic_id not in project_topic_ids:
        return "outside_project_topic_scope"
    allowed_brand_ids = set(scope.allowed_brand_ids())
    query_brand_id = int(query.brand_id) if query.brand_id is not None else None
    topic_brand_id = int(topic.brand_id) if topic and topic.brand_id is not None else None
    if query_brand_id in allowed_brand_ids or topic_brand_id in allowed_brand_ids:
        return None
    return "outside_brand_scope"


def _extract_raw_v4_package(raw: object) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    if isinstance(raw.get("analysis_meta"), dict):
        return raw
    for key in ("analyzer_v4_package", "analyzer_fact_package_v4"):
        package = raw.get(key)
        if isinstance(package, dict) and isinstance(package.get("analysis_meta"), dict):
            return package
    return None


def _has_v3_package(raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    package = raw.get("analyzer_fact_package_v3")
    if isinstance(package, dict) and package.get("analyzer_version") == "v3":
        return True
    packages = raw.get("analyzer_fact_packages")
    return isinstance(packages, dict) and bool(packages)


def _run_sort_key(run: AnalyzerRun) -> tuple[datetime, int]:
    at = run.completed_at or run.started_at or datetime.min
    return at, int(run.id or 0)


def _bucket_for_run(run: AnalyzerRun | None) -> str:
    if run is None:
        return "missing_v4_run"
    status = str(run.status or "").lower()
    if status == "failed":
        return "latest_v4_failed"
    if status in ANALYZED_STATUSES:
        return "latest_v4_analyzed"
    return "latest_v4_other"


async def _latest_runs_by_response(
    session: AsyncSession,
    response_ids: list[int],
) -> dict[int, AnalyzerRun]:
    if not response_ids:
        return {}
    runs = (
        await session.execute(
            select(AnalyzerRun).where(
                AnalyzerRun.response_id.in_(response_ids),
                AnalyzerRun.schema_version == ANALYZER_V4_SCHEMA_VERSION,
            )
        )
    ).scalars().all()
    latest: dict[int, AnalyzerRun] = {}
    for run in runs:
        response_id = int(run.response_id)
        existing = latest.get(response_id)
        if existing is None or _run_sort_key(run) > _run_sort_key(existing):
            latest[response_id] = run
    return latest


async def _fact_counts_by_run(
    session: AsyncSession,
    run_ids: list[int],
) -> dict[int, dict[str, int]]:
    counts = {
        run_id: {
            "response_entities": 0,
            "response_relation_facts": 0,
            "analysis_fact_links": 0,
            "analyzer_quality_flags": 0,
        }
        for run_id in run_ids
    }
    if not run_ids:
        return counts
    for model, key in (
        (ResponseEntity, "response_entities"),
        (ResponseRelationFact, "response_relation_facts"),
        (AnalysisFactLink, "analysis_fact_links"),
        (AnalyzerQualityFlag, "analyzer_quality_flags"),
    ):
        result = await session.execute(
            select(model.run_id, func.count(model.id))
            .where(model.run_id.in_(run_ids))
            .group_by(model.run_id)
        )
        for run_id, count in result.all():
            counts.setdefault(
                int(run_id),
                {
                    "response_entities": 0,
                    "response_relation_facts": 0,
                    "analysis_fact_links": 0,
                    "analyzer_quality_flags": 0,
                },
            )[key] = int(count or 0)
    return counts


async def collect_v4_coverage_rows(
    session: AsyncSession,
    scope: BestCofferV4CoverageScope,
) -> list[V4CoverageRow]:
    validate_scope(scope, mode="export")
    project_topic_ids = await _load_project_topic_ids(session, scope.project_id)
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
        if project_topic_ids:
            conditions.append(Topic.id.in_(project_topic_ids))
        else:
            allowed_brand_ids = list(scope.allowed_brand_ids())
            conditions.append(
                or_(
                    Query.brand_id.in_(allowed_brand_ids),
                    Topic.brand_id.in_(allowed_brand_ids),
                )
            )
        if start_at is not None:
            conditions.append(Query.created_at >= start_at)
        if end_at is not None:
            conditions.append(Query.created_at <= end_at)

    stmt = (
        select(LLMResponse, Query, Prompt, Topic, ResponseAnalysis)
        .join(Query, Query.id == LLMResponse.query_id)
        .outerjoin(Prompt, Prompt.id == Query.prompt_id)
        .outerjoin(Topic, Topic.id == Prompt.topic_id)
        .outerjoin(ResponseAnalysis, ResponseAnalysis.response_id == LLMResponse.id)
        .where(and_(*conditions))
        .order_by(Query.created_at.asc(), LLMResponse.id.asc())
        .limit(int(scope.limit) + 1)
    )
    rows = (await session.execute(stmt)).all()
    if len(rows) > int(scope.limit):
        raise ValueError(
            f"selected response candidates exceed limit={scope.limit}; tighten scope"
        )

    loaded_response_ids = [int(response.id) for response, *_rest in rows]
    latest_runs = await _latest_runs_by_response(session, loaded_response_ids)
    run_ids = [int(run.id) for run in latest_runs.values() if run.id is not None]
    fact_counts = await _fact_counts_by_run(session, run_ids)

    out: list[V4CoverageRow] = []
    for response, query, prompt, topic, analysis in rows:
        invalid_reason = _target_scope_invalid_reason(scope, query, topic, project_topic_ids)
        if invalid_reason is None:
            invalid_reason = _response_invalid_reason(response, query)
        raw = analysis.raw_analysis_json if analysis is not None else None
        raw_v4_package = _extract_raw_v4_package(raw)
        validation_errors: tuple[str, ...] = tuple()
        raw_v4_valid = False
        if raw_v4_package is not None:
            result = validate_analyzer_v4_package(
                raw_v4_package,
                response_text=response.raw_text or "",
                response_id=int(response.id),
                query_id=int(query.id),
            )
            raw_v4_valid = result.is_valid
            validation_errors = tuple(result.errors)

        latest = latest_runs.get(int(response.id))
        latest_run_id = int(latest.id) if latest and latest.id is not None else None
        out.append(
            V4CoverageRow(
                response_id=int(response.id),
                query_id=int(query.id),
                query_brand_id=int(query.brand_id) if query.brand_id is not None else None,
                topic_brand_id=(
                    int(topic.brand_id) if topic and topic.brand_id is not None else None
                ),
                topic_id=int(topic.id) if topic and topic.id is not None else None,
                prompt_id=int(prompt.id) if prompt and prompt.id is not None else None,
                engine=query.target_llm,
                collected_at=response.collected_at.isoformat() if response.collected_at else None,
                created_at=query.created_at.isoformat() if query.created_at else None,
                analysis_status=response.analysis_status,
                latest_run_id=latest_run_id,
                latest_run_status=latest.status if latest else None,
                latest_run_failure_code=latest.failure_code if latest else None,
                latest_run_failure_message=latest.failure_message if latest else None,
                latest_run_completed_at=(
                    latest.completed_at.isoformat()
                    if latest and latest.completed_at
                    else None
                ),
                latest_run_started_at=(
                    latest.started_at.isoformat() if latest and latest.started_at else None
                ),
                repair_bucket=_bucket_for_run(latest),
                has_raw_analysis_json=isinstance(raw, dict),
                has_raw_analyzer_v4_package=raw_v4_package is not None,
                has_raw_analyzer_v3_package=_has_v3_package(raw),
                raw_v4_package_valid=raw_v4_valid,
                raw_v4_validation_errors=validation_errors,
                first_class_fact_counts=fact_counts.get(
                    latest_run_id,
                    {
                        "response_entities": 0,
                        "response_relation_facts": 0,
                        "analysis_fact_links": 0,
                        "analyzer_quality_flags": 0,
                    },
                ),
                invalid_reason=invalid_reason,
            )
        )
    return out


def _row_to_dict(row: V4CoverageRow) -> dict[str, Any]:
    return {
        "response_id": row.response_id,
        "query_id": row.query_id,
        "query_brand_id": row.query_brand_id,
        "topic_brand_id": row.topic_brand_id,
        "topic_id": row.topic_id,
        "prompt_id": row.prompt_id,
        "engine": row.engine,
        "collected_at": row.collected_at,
        "created_at": row.created_at,
        "analysis_status": row.analysis_status,
        "repair_bucket": row.repair_bucket,
        "latest_v4_run": {
            "run_id": row.latest_run_id,
            "status": row.latest_run_status,
            "failure_code": row.latest_run_failure_code,
            "failure_message": row.latest_run_failure_message,
            "completed_at": row.latest_run_completed_at,
            "started_at": row.latest_run_started_at,
        },
        "raw_packages": {
            "has_raw_analysis_json": row.has_raw_analysis_json,
            "has_raw_analyzer_v4_package": row.has_raw_analyzer_v4_package,
            "has_raw_analyzer_v3_package": row.has_raw_analyzer_v3_package,
            "raw_v4_package_valid": row.raw_v4_package_valid,
            "raw_v4_validation_errors": list(row.raw_v4_validation_errors),
        },
        "first_class_fact_counts": dict(row.first_class_fact_counts),
        "invalid_reason": row.invalid_reason,
    }


def _expected_fact_counts(package: dict[str, Any]) -> dict[str, int]:
    citation_link_count = 0
    for citation in package.get("citations") or []:
        if isinstance(citation, dict):
            citation_link_count += len(citation.get("linked_fact_keys") or [])
    return {
        "response_entities": len(package.get("entities") or []),
        "response_relation_facts": len(package.get("relations") or []),
        "analysis_fact_links": citation_link_count,
        "analyzer_quality_flags": len(package.get("quality_flags") or []),
    }


def _facts_satisfy_package(actual: dict[str, int], expected: dict[str, int]) -> bool:
    return all(int(actual.get(key, 0)) >= int(value) for key, value in expected.items())


def _package_hash(package: dict[str, Any]) -> str:
    payload = json.dumps(package, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _load_response_analysis(session: AsyncSession, response_id: int) -> ResponseAnalysis | None:
    return await session.scalar(
        select(ResponseAnalysis).where(ResponseAnalysis.response_id == int(response_id))
    )


async def _find_existing_migration_run(
    session: AsyncSession,
    *,
    response_id: int,
    idempotency_key: str,
) -> AnalyzerRun | None:
    return await session.scalar(
        select(AnalyzerRun)
        .where(
            AnalyzerRun.response_id == int(response_id),
            AnalyzerRun.schema_version == ANALYZER_V4_SCHEMA_VERSION,
            AnalyzerRun.idempotency_key == idempotency_key,
        )
        .order_by(AnalyzerRun.id.desc())
    )


async def _delete_existing_v4_facts_for_run(session: AsyncSession, run_id: int) -> None:
    for model in (
        AnalysisFactLink,
        AnalyzerQualityFlag,
        ResponseRelationFact,
        ResponseEntity,
    ):
        await session.execute(delete(model).where(model.run_id == int(run_id)))
    await session.flush()


async def _migrate_raw_v4_package(
    session: AsyncSession,
    *,
    row: V4CoverageRow,
    approval_ref: str,
) -> tuple[str, int | None]:
    analysis = await _load_response_analysis(session, row.response_id)
    raw = analysis.raw_analysis_json if analysis is not None else None
    package = _extract_raw_v4_package(raw)
    if package is None:
        return "reanalysis_required", None
    result = validate_analyzer_v4_package(
        package,
        response_text=(await session.get(LLMResponse, row.response_id)).raw_text or "",
        response_id=row.response_id,
        query_id=row.query_id,
    )
    if not result.is_valid:
        return "reanalysis_required", None
    package = result.package
    idempotency_key = f"issue-827:migrate-raw-v4:{row.response_id}:{_package_hash(package)}"
    existing = await _find_existing_migration_run(
        session,
        response_id=row.response_id,
        idempotency_key=idempotency_key,
    )
    expected = _expected_fact_counts(package)
    if existing is not None:
        counts = await _fact_counts_by_run(session, [int(existing.id)])
        if _facts_satisfy_package(counts.get(int(existing.id), {}), expected):
            return "already_satisfied", int(existing.id)
        await _delete_existing_v4_facts_for_run(session, int(existing.id))
        rebuilt_existing = True
    else:
        rebuilt_existing = False

    run = existing or AnalyzerRun(
        response_id=row.response_id,
        schema_version=ANALYZER_V4_SCHEMA_VERSION,
        prompt_version=package.get("analysis_meta", {}).get("prompt_version"),
        provider=package.get("analysis_meta", {}).get("provider"),
        model=package.get("analysis_meta", {}).get("model"),
        status="running",
        trigger_source="issue_827_v4_coverage_repair",
        idempotency_key=idempotency_key,
        raw_output_sha256=result.raw_output_sha256,
        validator_summary_json={
            **result.validator_summary,
            "migrated_from": "response_analyses.raw_analysis_json",
            "approval_ref": approval_ref,
        },
        started_at=_utcnow_naive(),
    )
    if existing is None:
        session.add(run)
        await session.flush()
    await _persist_analyzer_v4_facts(
        session,
        analyzer_run=run,
        response_id=row.response_id,
        package=package,
        include_current_facts=True,
    )
    run.status = result.run_status
    run.completed_at = _utcnow_naive()
    run.failure_code = result.failure_code
    run.failure_message = result.failure_message
    run.raw_output_sha256 = result.raw_output_sha256
    run.validator_summary_json = {
        **result.validator_summary,
        "migrated_from": "response_analyses.raw_analysis_json",
        "approval_ref": approval_ref,
    }
    return "rebuilt" if rebuilt_existing else "migrated", int(run.id)


def _plan_for_row(row: V4CoverageRow) -> str:
    if row.invalid_reason:
        return "skip_invalid"
    if row.has_raw_analyzer_v4_package and row.raw_v4_package_valid:
        return "migrate_raw_v4_package"
    if row.repair_bucket == "latest_v4_analyzed" and any(row.first_class_fact_counts.values()):
        return "already_satisfied"
    return "reanalysis_required"


def _build_repair_plan(rows: list[V4CoverageRow]) -> dict[str, Any]:
    actions: dict[int, dict[str, Any]] = {}
    migrate_ids: list[int] = []
    reanalysis_ids: list[int] = []
    already_ids: list[int] = []
    skipped_ids: list[int] = []
    for row in rows:
        action = _plan_for_row(row)
        actions[row.response_id] = {
            "action": action,
            "repair_bucket": row.repair_bucket,
            "latest_run_id": row.latest_run_id,
            "latest_run_status": row.latest_run_status,
            "has_raw_analyzer_v4_package": row.has_raw_analyzer_v4_package,
            "has_raw_analyzer_v3_package": row.has_raw_analyzer_v3_package,
            "raw_v4_package_valid": row.raw_v4_package_valid,
            "raw_v4_validation_errors": list(row.raw_v4_validation_errors),
            "reason": (
                "valid_raw_v4_package_available"
                if action == "migrate_raw_v4_package"
                else "legacy_or_missing_raw_v4_requires_reanalysis"
                if action == "reanalysis_required"
                else row.invalid_reason
                if action == "skip_invalid"
                else "latest_v4_run_already_has_first_class_facts"
            ),
        }
        if action == "migrate_raw_v4_package":
            migrate_ids.append(row.response_id)
        elif action == "reanalysis_required":
            reanalysis_ids.append(row.response_id)
        elif action == "already_satisfied":
            already_ids.append(row.response_id)
        else:
            skipped_ids.append(row.response_id)
    return {
        "migrate_raw_v4_response_ids": migrate_ids,
        "reanalysis_required_response_ids": reanalysis_ids,
        "already_satisfied_response_ids": already_ids,
        "skipped_response_ids": skipped_ids,
        "actions_by_response": actions,
        "dry_run_only_reanalysis": True,
        "reanalysis_requires_separate_exact_id_approval": True,
        "no_fake_done_states": True,
    }


async def build_bestcoffer_v4_coverage_report(
    session: AsyncSession,
    scope: BestCofferV4CoverageScope,
    *,
    mode: str = "export",
    approval_ref: str | None = None,
    approval_comment_fetcher: ApprovalCommentFetcher | None = None,
) -> dict[str, Any]:
    validate_scope(scope, mode=mode)
    response_ids = scope.normalized_response_ids()
    if mode == "apply":
        approval_ref = validate_approval_ref(
            approval_ref,
            approval_comment_fetcher=approval_comment_fetcher,
            response_ids=response_ids,
        )
    rows = await collect_v4_coverage_rows(session, scope)
    selected = [row for row in rows if row.invalid_reason is None]
    if mode == "apply":
        selected_ids = {row.response_id for row in selected}
        missing_or_invalid_ids = [
            response_id for response_id in response_ids if response_id not in selected_ids
        ]
        if missing_or_invalid_ids:
            raise ValueError(
                "apply response_ids must all be inside the verified project topic scope "
                "and pass safety filters; blocked response_ids="
                f"{missing_or_invalid_ids}"
            )
    bucket_counts = Counter(row.repair_bucket for row in selected)
    for bucket in (
        "missing_v4_run",
        "latest_v4_failed",
        "latest_v4_other",
        "latest_v4_analyzed",
    ):
        bucket_counts.setdefault(bucket, 0)
    repair_plan = _build_repair_plan(selected)

    report: dict[str, Any] = {
        "issue": 827,
        "mode": mode,
        "write_performed": False,
        "approval_ref": approval_ref,
        "scope": _scope_dict(scope),
        "selected_response_ids": [row.response_id for row in selected],
        "bucket_counts": dict(bucket_counts),
        "rows": [_row_to_dict(row) for row in rows],
        "repair_plan": repair_plan,
        "safe_selection": {
            "export_is_read_only": mode == "export",
            "apply_requires_exact_response_ids": True,
            "apply_requires_trusted_issue_827_approval": True,
            "no_broad_scraper_rerun": True,
            "no_fake_citation_or_geo_rows": True,
            "no_silent_failed_run_done": True,
        },
        "rollback": ROLLBACK_NOTE,
        "apply_plan": APPROVAL_REF_HELP if mode != "apply" else None,
    }
    if mode != "apply":
        return report

    migrated_ids: list[int] = []
    already_ids: list[int] = []
    created_run_ids: list[int] = []
    rebuilt_run_ids: list[int] = []
    for row in selected:
        if _plan_for_row(row) != "migrate_raw_v4_package":
            continue
        action, run_id = await _migrate_raw_v4_package(
            session,
            row=row,
            approval_ref=approval_ref or "",
        )
        if action in {"migrated", "rebuilt"}:
            migrated_ids.append(row.response_id)
            if action == "migrated" and run_id is not None:
                created_run_ids.append(run_id)
            if action == "rebuilt" and run_id is not None:
                rebuilt_run_ids.append(run_id)
        elif action == "already_satisfied":
            already_ids.append(row.response_id)

    if migrated_ids:
        await session.commit()
    report["write_performed"] = bool(migrated_ids)
    repair_plan["migrated_response_ids"] = migrated_ids
    repair_plan["created_analyzer_run_ids"] = created_run_ids
    repair_plan["rebuilt_existing_run_ids"] = rebuilt_run_ids
    repair_plan["already_satisfied_response_ids"] = sorted(
        set(repair_plan["already_satisfied_response_ids"]) | set(already_ids)
    )
    return report


def _parse_int_csv(value: str | None) -> tuple[int, ...]:
    if not value:
        return tuple()
    out: list[int] = []
    for part in str(value).split(","):
        part = part.strip()
        if part:
            out.append(int(part))
    return tuple(out)


async def _run_cli(args: argparse.Namespace) -> dict[str, Any]:
    engine = create_task_engine()
    try:
        async with get_task_async_session(engine) as session:
            return await build_bestcoffer_v4_coverage_report(
                session,
                BestCofferV4CoverageScope(
                    project_id=args.project_id,
                    brand_id=int(args.brand_id),
                    competitor_brand_ids=_parse_int_csv(args.competitor_brand_ids),
                    date_from=args.date_from or None,
                    date_to=args.date_to or None,
                    response_ids=_parse_int_csv(args.response_ids),
                    query_ids=_parse_int_csv(args.query_ids),
                    limit=int(args.limit),
                ),
                mode=args.mode,
                approval_ref=args.approval_ref or None,
            )
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["export", "dry_run", "apply"], required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--brand-id", default="24")
    parser.add_argument("--competitor-brand-ids", default="")
    parser.add_argument("--date-from", default="")
    parser.add_argument("--date-to", default="")
    parser.add_argument("--response-ids", default="")
    parser.add_argument("--query-ids", default="")
    parser.add_argument("--limit", default=str(MAX_EXPORT_LIMIT))
    parser.add_argument("--approval-ref", default="")
    args = parser.parse_args()
    report = asyncio.run(_run_cli(args))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
