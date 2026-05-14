"""Scoped BestCoffer citation/GEO materialization repair for issue #760.

The dry-run path can inspect the BestCoffer date window and report exact
response IDs. Apply mode is intentionally narrower: it requires explicit
response_ids or query_ids plus issue #760 production-write approval evidence.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from geo_tracker.agent.response_validation import (
    doubao_persistence_auth_reason,
    invalid_response_reason,
)
from geo_tracker.config import create_task_engine, get_task_async_session
from geo_tracker.db.models import (
    AnalysisStatus,
    BrandMention,
    CitationSource,
    GEOScoreDaily,
    LLMResponse,
    Prompt,
    Query,
    QueryStatus,
    ResponseAnalysis,
    Topic,
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
GITHUB_ISSUE_COMMENT_RE = re.compile(
    r"^https://github\.com/jotamotk/trash_test/issues/760"
    r"#issuecomment-(?P<comment_id>[0-9]+)$",
    re.IGNORECASE,
)
MAX_LIMIT = 75
CITATION_CONTEXT_RADIUS = 160
APPROVAL_COMMENT_API = (
    "https://api.github.com/repos/jotamotk/trash_test/issues/comments/{comment_id}"
)
TRUSTED_APPROVAL_AUTHOR_ASSOCIATIONS = frozenset(
    {"OWNER", "MEMBER", "COLLABORATOR"}
)
ACCEPTED_V4_VALIDATOR_STATUSES = frozenset({"passed", "passed_with_flags"})

APPROVAL_REF_HELP = (
    "Dry-run first, attach exact response/query IDs and write plan evidence to "
    "#760, then use the exact #760 issue comment URL whose fetched GitHub body "
    "contains explicit AI Lead production-write approval for BestCoffer citation "
    "GEO materialization apply and whose author_association is OWNER, MEMBER, "
    "or COLLABORATOR. Do not append approval words to the URL."
)

ROLLBACK_NOTE = (
    "Rollback is scoped to selected response IDs and selected aggregate dates: "
    "restore response_analyses.raw_analysis_json from the pre-apply database "
    "backup/audit snapshot, remove citation_sources inserted by this run or "
    "clear only the mention_id updates listed in the report, then delete and "
    "rerun geo_score_daily/topic/product aggregates for the affected brand/date "
    "scope. Aggregation apply rewrites the full selected brand/date aggregate "
    "rows via Aggregator.aggregate_daily, not only rows tied to one response. "
    "No scraper rerun or broad response reset is required."
)

ApprovalCommentFetcher = Callable[[int], dict[str, Any]]


@dataclass(frozen=True)
class BestCofferCitationGeoScope:
    project_id: str
    brand_id: int = 24
    competitor_brand_ids: tuple[int, ...] = field(default_factory=tuple)
    date_from: str | None = None
    date_to: str | None = None
    response_ids: tuple[int, ...] = field(default_factory=tuple)
    query_ids: tuple[int, ...] = field(default_factory=tuple)
    limit: int = MAX_LIMIT

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
    raw_text: str | None
    has_response_analysis: bool
    has_v3_package: bool
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


def validate_scope(scope: BestCofferCitationGeoScope, *, apply: bool = False) -> None:
    if not str(scope.project_id or "").strip():
        raise ValueError("project_id is required")
    if int(scope.brand_id) <= 0:
        raise ValueError("brand_id must be positive")
    if int(scope.limit) < 1 or int(scope.limit) > MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    _parse_day(scope.date_from, "date_from")
    _parse_day(scope.date_to, "date_to")

    has_explicit_ids = bool(scope.normalized_response_ids() or scope.normalized_query_ids())
    if apply and not has_explicit_ids:
        raise ValueError("apply mode requires explicit response_ids or query_ids")
    if has_explicit_ids:
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


def _fetch_github_issue_comment(comment_id: int) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "genpano-issue-760-repair",
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


def _validate_comment_belongs_to_issue_760(
    comment: dict[str, Any],
    approval_ref: str,
) -> None:
    issue_url = str(comment.get("issue_url") or "")
    html_url = str(comment.get("html_url") or "")
    if not issue_url.endswith("/repos/jotamotk/trash_test/issues/760"):
        raise ValueError("approval_ref comment must belong to jotamotk/trash_test#760")
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
        and bool(re.search(r"\bproduction\s+writes?\b", normalized))
        and bool(re.search(r"\bapprov\w*\b", normalized))
        and "bestcoffer" in normalized
        and "citation" in normalized
        and "geo" in normalized
        and "materialization" in normalized
        and "apply" in normalized
    )
    if not has_write_approval:
        raise ValueError(
            "approval_ref comment body must contain explicit AI Lead "
            "production-write approval for BestCoffer citation GEO "
            "materialization apply"
        )


def _validate_comment_has_aggregate_approval(
    comment: dict[str, Any],
    *,
    dates: list[str],
) -> None:
    normalized = _normalized_comment_body(comment)
    raw_body = str(comment.get("body") or "").lower()
    has_aggregate_approval = (
        "aggregate" in normalized
        and ("recompute" in normalized or "aggregate_daily" in normalized)
        and bool(re.search(r"\bapprov\w*\b", normalized))
    )
    missing_dates = [date for date in dates if date not in raw_body]
    if not has_aggregate_approval or missing_dates:
        raise ValueError(
            "aggregate_approval_ref comment body must explicitly approve "
            f"aggregate recompute for selected dates; missing dates={missing_dates}"
        )


def validate_approval_ref(
    approval_ref: str | None,
    *,
    approval_comment_fetcher: ApprovalCommentFetcher | None = None,
) -> str:
    value = (approval_ref or "").strip()
    match = GITHUB_ISSUE_COMMENT_RE.match(value) if value else None
    if not match:
        raise ValueError(
            "approval_ref must be the exact #760 issue comment URL; do not "
            "append approval words to the URL string"
        )
    comment_id = int(match.group("comment_id"))
    fetcher = approval_comment_fetcher or _fetch_github_issue_comment
    comment = fetcher(comment_id)
    _validate_comment_belongs_to_issue_760(comment, value)
    _validate_comment_author_trusted(comment)
    _validate_comment_has_write_approval(comment)
    return value


def validate_aggregate_approval_ref(
    aggregate_approval_ref: str | None,
    *,
    dates: list[str],
    approval_comment_fetcher: ApprovalCommentFetcher | None = None,
) -> str:
    value = validate_approval_ref(
        aggregate_approval_ref,
        approval_comment_fetcher=approval_comment_fetcher,
    )
    match = GITHUB_ISSUE_COMMENT_RE.match(value)
    if not match:
        raise ValueError("aggregate_approval_ref must be a #760 issue comment URL")
    fetcher = approval_comment_fetcher or _fetch_github_issue_comment
    comment = fetcher(int(match.group("comment_id")))
    _validate_comment_has_aggregate_approval(comment, dates=dates)
    return value


def _scope_dict(scope: BestCofferCitationGeoScope) -> dict:
    data = asdict(scope)
    data["response_ids"] = list(scope.normalized_response_ids())
    data["query_ids"] = list(scope.normalized_query_ids())
    data["competitor_brand_ids"] = list(scope.normalized_competitor_brand_ids())
    data["allowed_brand_ids"] = list(scope.allowed_brand_ids())
    return data


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


def _has_v3_package(raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    package = raw.get("analyzer_fact_package_v3")
    return isinstance(package, dict) and package.get("analyzer_version") == "v3"


def _v4_package(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    candidates = [
        raw.get("analyzer_v4"),
        raw.get("analyzer_fact_package_v4"),
        raw.get("analyzer_fact_package"),
        raw,
    ]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        meta = candidate.get("analysis_meta")
        if isinstance(meta, dict) and meta.get("schema_version") == "analyzer_v4":
            validator_status = str(meta.get("validator_status") or "").lower()
            if validator_status not in ACCEPTED_V4_VALIDATOR_STATUSES:
                continue
            return candidate
    return None


def _has_v4_package(raw: object) -> bool:
    return _v4_package(raw) is not None


async def _load_project_topic_ids(
    session: AsyncSession,
    project_id: str,
) -> set[int]:
    try:
        result = await session.execute(
            text(
                """
                SELECT topic_id
                FROM project_topic_pins
                WHERE project_id = :project_id
                  AND COALESCE(state, 'tracked') = 'tracked'
                """
            ),
            {"project_id": project_id},
        )
    except SQLAlchemyError:
        return set()
    return {int(row[0]) for row in result.all() if row[0] is not None}


def _target_scope_invalid_reason(
    scope: BestCofferCitationGeoScope,
    query: Query,
    topic: Topic | None,
    project_topic_ids: set[int],
) -> str | None:
    topic_id = int(topic.id) if topic and topic.id is not None else None
    if project_topic_ids and topic_id not in project_topic_ids:
        return "outside_project_topic_scope"
    allowed_brand_ids = set(scope.allowed_brand_ids())
    query_brand_id = int(query.brand_id) if query.brand_id is not None else None
    topic_brand_id = int(topic.brand_id) if topic and topic.brand_id is not None else None
    if query_brand_id in allowed_brand_ids or topic_brand_id in allowed_brand_ids:
        return None
    return "outside_brand_scope"


async def collect_candidate_responses(
    session: AsyncSession,
    scope: BestCofferCitationGeoScope,
) -> list[CandidateResponse]:
    validate_scope(scope)
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
            conditions.append(LLMResponse.collected_at >= start_at)
        if end_at is not None:
            conditions.append(LLMResponse.collected_at <= end_at)

    stmt = (
        select(LLMResponse, Query, Prompt, Topic, ResponseAnalysis)
        .join(Query, Query.id == LLMResponse.query_id)
        .outerjoin(Prompt, Prompt.id == Query.prompt_id)
        .outerjoin(Topic, Topic.id == Prompt.topic_id)
        .outerjoin(ResponseAnalysis, ResponseAnalysis.response_id == LLMResponse.id)
        .where(and_(*conditions))
        .order_by(LLMResponse.collected_at.asc(), LLMResponse.id.asc())
        .limit(int(scope.limit) + 1)
    )
    rows = (await session.execute(stmt)).all()
    if len(rows) > int(scope.limit):
        raise ValueError(
            f"selected response candidates exceed limit={scope.limit}; tighten scope"
        )

    candidates: list[CandidateResponse] = []
    for response, query, prompt, topic, analysis in rows:
        invalid_reason = _target_scope_invalid_reason(scope, query, topic, project_topic_ids)
        if invalid_reason is None:
            invalid_reason = _response_invalid_reason(response, query)
        candidates.append(
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
                raw_text=response.raw_text,
                has_response_analysis=analysis is not None,
                has_v3_package=(
                    _has_v3_package(analysis.raw_analysis_json)
                    or _has_v4_package(analysis.raw_analysis_json)
                    if analysis is not None
                    else False
                ),
                invalid_reason=invalid_reason,
            )
        )
    return candidates


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
        "has_response_analysis": candidate.has_response_analysis,
        "has_v3_package": candidate.has_v3_package,
        "invalid_reason": candidate.invalid_reason,
    }


def _analyzer_state(candidate: CandidateResponse) -> str:
    if not candidate.has_response_analysis:
        return "missing_response_analysis"
    if not candidate.has_v3_package:
        return "missing_v3_package"
    if candidate.analysis_status != AnalysisStatus.DONE.value:
        return "analysis_status_not_done"
    return "has_v3_package"


def summarize_candidates(candidates: list[CandidateResponse]) -> dict:
    selected = [row for row in candidates if row.invalid_reason is None]
    excluded = [row for row in candidates if row.invalid_reason is not None]
    analyzer_states = Counter(_analyzer_state(row) for row in selected)
    invalid_reasons = Counter(row.invalid_reason for row in excluded if row.invalid_reason)
    return {
        "candidate_count": len(candidates),
        "selected_count": len(selected),
        "excluded_invalid_count": len(excluded),
        "invalid_reason_counts": dict(sorted(invalid_reasons.items())),
        "analyzer_state_counts": dict(sorted(analyzer_states.items())),
        "rows": [_candidate_to_dict(row) for row in selected],
        "excluded_rows": [_candidate_to_dict(row) for row in excluded],
    }


def _normalize_entity(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    return "".join(ch for ch in normalized if ch.isalnum())


def _normalize_url(value: object) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return None
    return raw


def _domain_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    return parsed.netloc.lower() if parsed.netloc else None


def _citation_key(citation: dict) -> tuple[str, int | None] | None:
    url = _normalize_url(citation.get("url"))
    if not url:
        return None
    index_value = citation.get("citation_index")
    try:
        index = int(index_value) if index_value is not None else None
    except (TypeError, ValueError):
        index = None
    return (url, index)


def _iter_v3_citations(package: dict) -> list[tuple[str, dict]]:
    citations = package.get("citations")
    if not isinstance(citations, dict):
        return []
    out: list[tuple[str, dict]] = []
    for bucket in ("attributed_citations", "unresolved_citations"):
        values = citations.get(bucket)
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict):
                out.append((bucket, item))
    return out


def _iter_v4_citations(package: dict) -> list[tuple[str, dict]]:
    values = package.get("citations")
    if not isinstance(values, list):
        return []
    out: list[tuple[str, dict]] = []
    for item in values:
        if isinstance(item, dict):
            out.append(("analyzer_v4", item))
    return out


def _iter_analyzer_citation_packages(raw: dict) -> list[tuple[str, dict]]:
    packages: list[tuple[str, dict]] = []
    v3_package = raw.get("analyzer_fact_package_v3")
    if isinstance(v3_package, dict):
        packages.append(("v3", v3_package))
    v4_package = _v4_package(raw)
    if isinstance(v4_package, dict):
        packages.append(("v4", v4_package))
    return packages


def _resolve_mention_id(
    citation: dict,
    mentions_by_id: dict[int, BrandMention],
    mentions_by_name: dict[str, list[BrandMention]],
) -> tuple[int | None, str | None]:
    mention_id = citation.get("mention_id")
    try:
        normalized_id = int(mention_id) if mention_id is not None else None
    except (TypeError, ValueError):
        normalized_id = None
    if normalized_id is not None and normalized_id in mentions_by_id:
        return normalized_id, None

    brand_name = _normalize_entity(citation.get("brand_name"))
    if not brand_name:
        return None, "missing_citation_brand_name"
    matches = mentions_by_name.get(brand_name, [])
    if len(matches) == 1:
        return int(matches[0].id), None
    if len(matches) > 1:
        return None, "ambiguous_brand_mention"
    return None, "no_matching_brand_mention"


def _citation_marker_contexts(
    response_text: str | None,
    citation_index: object,
    *,
    radius: int = CITATION_CONTEXT_RADIUS,
) -> list[str]:
    if not response_text or citation_index is None:
        return []
    index = str(citation_index).strip()
    if not index:
        return []
    patterns = [
        rf"\[\s*{re.escape(index)}\s*\]",
        rf"\(\s*{re.escape(index)}\s*\)",
        rf"\u3010\s*{re.escape(index)}\s*\u3011",
        rf"\uff08\s*{re.escape(index)}\s*\uff09",
    ]
    windows: list[tuple[int, str]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, response_text):
            start = max(0, match.start() - radius)
            end = min(len(response_text), match.end() + radius)
            windows.append((match.start(), response_text[start:end]))
    return [window for _, window in sorted(windows, key=lambda item: item[0])]


def _mentions_matching_context(
    text: str,
    mentions: list[BrandMention],
) -> list[BrandMention]:
    normalized_text = _normalize_entity(text) or ""
    if not normalized_text:
        return []
    matches: list[BrandMention] = []
    seen: set[int] = set()
    for mention in mentions:
        if mention.id is None:
            continue
        normalized_name = _normalize_entity(mention.brand_name)
        if not normalized_name or normalized_name not in normalized_text:
            continue
        mention_id = int(mention.id)
        if mention_id in seen:
            continue
        seen.add(mention_id)
        matches.append(mention)
    return matches


def _context_brand_ids(candidate: CandidateResponse, package: dict) -> set[int]:
    values: list[object] = [
        candidate.query_brand_id,
        candidate.topic_brand_id,
        package.get("target_brand_id"),
    ]
    out: set[int] = set()
    for value in values:
        try:
            brand_id = int(value) if value is not None else None
        except (TypeError, ValueError):
            brand_id = None
        if brand_id is not None and brand_id > 0:
            out.add(brand_id)
    return out


def _resolve_context_brand_mention(
    candidate: CandidateResponse,
    package: dict,
    mentions: list[BrandMention],
    mentions_by_brand_id: dict[int, list[BrandMention]],
) -> tuple[int | None, str | None, str | None]:
    brand_ids = _context_brand_ids(candidate, package)
    if not brand_ids:
        return None, "missing_context_brand_id", None
    if len(brand_ids) > 1:
        return None, "ambiguous_context_brand_id", None

    brand_id = next(iter(brand_ids))
    matches = mentions_by_brand_id.get(brand_id, [])
    if not matches:
        return None, "no_context_brand_mention", None
    if len(matches) > 1:
        return None, "ambiguous_context_brand_mention", None

    other_brand_mentions = [
        mention
        for mention in mentions
        if mention.id is not None and int(mention.id) != int(matches[0].id)
    ]
    if other_brand_mentions:
        return None, "ambiguous_response_brand_context", None
    return int(matches[0].id), None, "query_brand_context"


def _resolve_v3_mention_id(
    citation: dict,
    package: dict,
    candidate: CandidateResponse,
    mentions: list[BrandMention],
    mentions_by_id: dict[int, BrandMention],
    mentions_by_name: dict[str, list[BrandMention]],
    mentions_by_brand_id: dict[int, list[BrandMention]],
) -> tuple[int | None, str | None, str | None]:
    mention_id, unresolved_reason = _resolve_mention_id(
        citation,
        mentions_by_id,
        mentions_by_name,
    )
    if mention_id is not None:
        return mention_id, None, "citation_brand_name_or_mention_id"
    if unresolved_reason != "missing_citation_brand_name":
        return None, unresolved_reason, None

    marker_contexts = _citation_marker_contexts(
        candidate.raw_text,
        citation.get("citation_index"),
    )
    if marker_contexts:
        matches_by_id: dict[int, BrandMention] = {}
        for marker_context in marker_contexts:
            for match in _mentions_matching_context(marker_context, mentions):
                if match.id is not None:
                    matches_by_id.setdefault(int(match.id), match)
        matches = list(matches_by_id.values())
        if len(matches) == 1:
            return int(matches[0].id), None, "response_marker_context"
        return None, "ambiguous_response_marker_context", None

    return _resolve_context_brand_mention(
        candidate,
        package,
        mentions,
        mentions_by_brand_id,
    )


def _entity_keys_for_v4_citation(citation: dict, package: dict) -> set[str]:
    keys = {str(value) for value in citation.get("mentioned_entity_keys") or [] if value}
    entities_by_key = {
        str(entity.get("entity_key")): entity
        for entity in package.get("entities") or []
        if isinstance(entity, dict) and entity.get("entity_key")
    }
    mentions_by_key = {
        str(mention.get("mention_key")): mention
        for mention in package.get("mentions") or []
        if isinstance(mention, dict) and mention.get("mention_key")
    }
    drivers_by_key = {
        str(driver.get("driver_key")): driver
        for driver in package.get("sentiment_drivers") or []
        if isinstance(driver, dict) and driver.get("driver_key")
    }
    features_by_key = {
        str(feature.get("feature_key")): feature
        for feature in package.get("product_features") or []
        if isinstance(feature, dict) and feature.get("feature_key")
    }
    relations_by_key = {
        str(relation.get("relation_key")): relation
        for relation in package.get("relations") or []
        if isinstance(relation, dict) and relation.get("relation_key")
    }
    for linked_key in citation.get("linked_fact_keys") or []:
        key = str(linked_key)
        if key in entities_by_key:
            keys.add(key)
        mention = mentions_by_key.get(key)
        if mention and mention.get("entity_key"):
            keys.add(str(mention["entity_key"]))
        driver = drivers_by_key.get(key)
        if driver and driver.get("target_entity_key"):
            keys.add(str(driver["target_entity_key"]))
        feature = features_by_key.get(key)
        if feature:
            for field in ("brand_entity_key", "product_entity_key"):
                if feature.get(field):
                    keys.add(str(feature[field]))
        relation = relations_by_key.get(key)
        if relation:
            for field in ("subject_entity_key", "object_entity_key"):
                if relation.get(field):
                    keys.add(str(relation[field]))
    return keys


def _candidate_mentions_for_v4_brand_entity(
    entity: dict,
    mentions_by_name: dict[str, list[BrandMention]],
    mentions_by_brand_id: dict[int, list[BrandMention]],
) -> list[BrandMention]:
    canonical_id = entity.get("canonical_id")
    try:
        brand_id = int(canonical_id) if canonical_id is not None else None
    except (TypeError, ValueError):
        brand_id = None
    if brand_id is not None:
        matches = mentions_by_brand_id.get(brand_id, [])
        if matches:
            return matches

    for name in (entity.get("canonical_name"), entity.get("raw_name")):
        normalized = _normalize_entity(name)
        if not normalized:
            continue
        matches = mentions_by_name.get(normalized, [])
        if matches:
            return matches
    return []


def _resolve_v4_mention_id(
    citation: dict,
    package: dict,
    mentions_by_name: dict[str, list[BrandMention]],
    mentions_by_brand_id: dict[int, list[BrandMention]],
) -> tuple[int | None, str | None]:
    entity_keys = _entity_keys_for_v4_citation(citation, package)
    if not entity_keys:
        return None, "missing_v4_citation_entity_link"

    entities_by_key = {
        str(entity.get("entity_key")): entity
        for entity in package.get("entities") or []
        if isinstance(entity, dict) and entity.get("entity_key")
    }
    brand_entities = [
        entities_by_key[key]
        for key in entity_keys
        if key in entities_by_key
        and str(entities_by_key[key].get("entity_type") or "").lower() == "brand"
    ]
    if not brand_entities:
        return None, "missing_v4_citation_brand_entity"

    candidate_mentions: dict[int, BrandMention] = {}
    for entity in brand_entities:
        for mention in _candidate_mentions_for_v4_brand_entity(
            entity,
            mentions_by_name,
            mentions_by_brand_id,
        ):
            if mention.id is not None:
                candidate_mentions[int(mention.id)] = mention

    if len(candidate_mentions) == 1:
        return next(iter(candidate_mentions)), None
    if len(candidate_mentions) > 1:
        return None, "ambiguous_brand_mention"
    return None, "no_matching_brand_mention"


async def _load_analyses(
    session: AsyncSession,
    selected: list[CandidateResponse],
) -> dict[int, ResponseAnalysis]:
    response_ids = [row.response_id for row in selected]
    if not response_ids:
        return {}
    analyses = (
        await session.execute(
            select(ResponseAnalysis).where(ResponseAnalysis.response_id.in_(response_ids))
        )
    ).scalars().all()
    return {int(row.response_id): row for row in analyses if row.response_id is not None}


async def _load_mentions(
    session: AsyncSession,
    response_ids: list[int],
) -> dict[int, list[BrandMention]]:
    if not response_ids:
        return {}
    mentions = (
        await session.execute(
            select(BrandMention).where(BrandMention.response_id.in_(response_ids))
        )
    ).scalars().all()
    by_response: dict[int, list[BrandMention]] = {}
    for mention in mentions:
        by_response.setdefault(int(mention.response_id), []).append(mention)
    return by_response


async def _load_existing_citations(
    session: AsyncSession,
    response_ids: list[int],
) -> dict[int, list[CitationSource]]:
    if not response_ids:
        return {}
    citations = (
        await session.execute(
            select(CitationSource).where(CitationSource.response_id.in_(response_ids))
        )
    ).scalars().all()
    by_response: dict[int, list[CitationSource]] = {}
    for citation in citations:
        by_response.setdefault(int(citation.response_id), []).append(citation)
    return by_response


def _existing_by_key(citations: list[CitationSource]) -> dict[tuple[str, int | None], CitationSource]:
    out: dict[tuple[str, int | None], CitationSource] = {}
    for citation in citations:
        url = _normalize_url(citation.url)
        if not url:
            continue
        out[(url, citation.citation_index)] = citation
        out.setdefault((url, None), citation)
    return out


def _mentions_indexes(
    mentions: list[BrandMention],
) -> tuple[dict[int, BrandMention], dict[str, list[BrandMention]], dict[int, list[BrandMention]]]:
    by_id = {int(mention.id): mention for mention in mentions if mention.id is not None}
    by_name: dict[str, list[BrandMention]] = {}
    by_brand_id: dict[int, list[BrandMention]] = {}
    for mention in mentions:
        normalized = _normalize_entity(mention.brand_name)
        if normalized:
            by_name.setdefault(normalized, []).append(mention)
        if mention.brand_id is not None:
            by_brand_id.setdefault(int(mention.brand_id), []).append(mention)
    return by_id, by_name, by_brand_id


def _set_citation_defaults(citation: dict, source: CitationSource) -> dict:
    out = dict(citation)
    out["citation_id"] = source.id
    out["mention_id"] = source.mention_id
    out["url"] = source.url
    out["domain"] = source.domain or _domain_from_url(source.url)
    out["title"] = source.title
    out["citation_index"] = source.citation_index
    out["source_type"] = source.source_type
    return out


def _force_unresolved_citation(citation: dict) -> dict:
    out = dict(citation)
    out["citation_id"] = None
    out["mention_id"] = None
    return out


def _rebuild_citations_package(package: dict, updated: list[dict]) -> None:
    citations = package.setdefault("citations", {})
    attributed = [item for item in updated if item.get("mention_id") is not None]
    unresolved = [item for item in updated if item.get("mention_id") is None]
    domains = sorted(
        {
            item.get("domain") or _domain_from_url(str(item.get("url") or ""))
            for item in updated
            if item.get("domain") or item.get("url")
        }
    )
    source_types = sorted(
        {str(item.get("source_type")) for item in updated if item.get("source_type")}
    )
    citations["total_citations"] = len(updated)
    citations["attributed_citations"] = attributed
    citations["unresolved_citations"] = unresolved
    citations["domains"] = [domain for domain in domains if domain]
    citations["source_types"] = source_types
    citations["formula_status"] = "missing" if not updated else "partial" if unresolved else "ok"
    citations["reason_codes"] = ["unresolved_citation_attribution"] if unresolved else []


def _patch_citation_facts(container: dict, sources_by_key: dict[tuple[str, int | None], CitationSource]) -> bool:
    facts = container.get("citation_facts")
    if not isinstance(facts, list):
        return False
    changed = False
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        key = _citation_key(fact)
        if key is None:
            continue
        source = sources_by_key.get(key) or sources_by_key.get((key[0], None))
        if source is None:
            continue
        if fact.get("citation_id") != source.id:
            fact["citation_id"] = source.id
            changed = True
        if source.mention_id is not None and fact.get("mention_id") != source.mention_id:
            fact["mention_id"] = source.mention_id
            missing = [
                value
                for value in fact.get("missing_inputs", [])
                if value != "citation_sources.mention_id"
            ]
            fact["missing_inputs"] = missing
            changed = True
    return changed


def _patch_v4_citation(citation: dict, source: CitationSource) -> dict:
    out = dict(citation)
    out["citation_source_id"] = source.id
    out["mention_id"] = source.mention_id
    out["materialization_status"] = (
        "attributed" if source.mention_id is not None else "source_only"
    )
    out.pop("unresolved_materialization_reason", None)
    return out


def _mark_v4_citation_unresolved(citation: dict, reason: str | None) -> dict:
    out = dict(citation)
    out["citation_source_id"] = None
    out["mention_id"] = None
    out["materialization_status"] = "unresolved"
    out["unresolved_materialization_reason"] = reason or "unresolved"
    return out


async def _citation_plan_or_apply(
    session: AsyncSession,
    selected: list[CandidateResponse],
    *,
    apply: bool,
    approval_ref: str | None,
) -> dict:
    response_ids = [row.response_id for row in selected]
    analyses_by_response = await _load_analyses(session, selected)
    mentions_by_response = await _load_mentions(session, response_ids)
    existing_by_response = await _load_existing_citations(session, response_ids)

    stats = Counter()
    inserted_source_ids: list[int] = []
    updated_source_ids: list[int] = []
    patched_response_ids: list[int] = []
    unresolved_reasons = Counter()
    rows: list[dict] = []

    for candidate in selected:
        analysis = analyses_by_response.get(candidate.response_id)
        if analysis is None or not isinstance(analysis.raw_analysis_json, dict):
            continue
        raw = copy.deepcopy(analysis.raw_analysis_json)
        package_specs = _iter_analyzer_citation_packages(raw)
        if not package_specs:
            continue

        mentions = mentions_by_response.get(candidate.response_id, [])
        mentions_by_id, mentions_by_name, mentions_by_brand_id = _mentions_indexes(mentions)
        existing_sources = existing_by_response.setdefault(candidate.response_id, [])
        source_by_key = _existing_by_key(existing_sources)
        response_changed = False
        changed_package_kinds: list[str] = []

        for package_kind, active_package in package_specs:
            items = (
                _iter_v3_citations(active_package)
                if package_kind == "v3"
                else _iter_v4_citations(active_package)
            )
            if not items:
                continue

            package_source_by_key: dict[tuple[str, int | None], CitationSource] = {}
            updated_citations: list[dict] = []
            package_changed = False

            for bucket, citation in items:
                key = _citation_key(citation)
                if key is None:
                    stats["invalid_citation_count"] += 1
                    rows.append(
                        {
                            "response_id": candidate.response_id,
                            "bucket": bucket,
                            "package_kind": package_kind,
                            "url": citation.get("url"),
                            "action": "skip_invalid_url",
                        }
                    )
                    continue
                stats["candidate_citation_count"] += 1
                if package_kind == "v4":
                    stats["v4_citation_count"] += 1
                    mention_id, unresolved_reason = _resolve_v4_mention_id(
                        citation,
                        active_package,
                        mentions_by_name,
                        mentions_by_brand_id,
                    )
                    resolution_method = "v4_entity_link" if mention_id is not None else None
                else:
                    mention_id, unresolved_reason, resolution_method = _resolve_v3_mention_id(
                        citation,
                        active_package,
                        candidate,
                        mentions,
                        mentions_by_id,
                        mentions_by_name,
                        mentions_by_brand_id,
                    )
                if mention_id is None:
                    stats["unresolved_citation_count"] += 1
                    unresolved_reasons[unresolved_reason or "unresolved"] += 1
                else:
                    stats["resolvable_citation_count"] += 1

                source = source_by_key.get(key) or source_by_key.get((key[0], None))
                skip_ambiguous_marker_source = (
                    mention_id is None
                    and unresolved_reason == "ambiguous_response_marker_context"
                )
                planned_action = (
                    "report_unresolved_v4_citation"
                    if package_kind == "v4" and mention_id is None
                    else "skip_ambiguous_response_marker_context"
                    if skip_ambiguous_marker_source
                    else "noop_existing"
                )
                conflict = False
                if (
                    source is None
                    and not skip_ambiguous_marker_source
                    and not (package_kind == "v4" and mention_id is None)
                ):
                    stats["insert_citation_source_count"] += 1
                    planned_action = "insert_citation_source"
                    if apply:
                        source = CitationSource(
                            response_id=candidate.response_id,
                            mention_id=mention_id,
                            url=key[0],
                            domain=str(citation.get("domain") or _domain_from_url(key[0]) or ""),
                            title=citation.get("title"),
                            citation_index=key[1],
                            source_type=citation.get("source_type"),
                        )
                        session.add(source)
                        await session.flush()
                        existing_sources.append(source)
                        source_by_key[key] = source
                        source_by_key.setdefault((key[0], None), source)
                        inserted_source_ids.append(int(source.id))
                    else:
                        source = CitationSource(
                            response_id=candidate.response_id,
                            mention_id=mention_id,
                            url=key[0],
                            domain=str(citation.get("domain") or _domain_from_url(key[0]) or ""),
                            title=citation.get("title"),
                            citation_index=key[1],
                            source_type=citation.get("source_type"),
                        )
                        existing_sources.append(source)
                        source_by_key[key] = source
                        source_by_key.setdefault((key[0], None), source)
                elif mention_id is not None and source.mention_id is None:
                    stats["resolved_existing_citation_source_count"] += 1
                    planned_action = "set_existing_mention_id"
                    if apply:
                        source.mention_id = mention_id
                        updated_source_ids.append(int(source.id))
                elif (
                    mention_id is not None
                    and source.mention_id is not None
                    and int(source.mention_id) != int(mention_id)
                ):
                    stats["conflicting_existing_citation_source_count"] += 1
                    unresolved_reasons["conflicting_existing_mention_id"] += 1
                    planned_action = "skip_conflicting_existing_mention_id"
                    conflict = True

                if package_kind == "v4":
                    if conflict or mention_id is None:
                        updated = _mark_v4_citation_unresolved(
                            citation,
                            "conflicting_existing_mention_id" if conflict else unresolved_reason,
                        )
                        if apply and updated != citation:
                            package_changed = True
                        updated_citations.append(updated)
                    elif apply and source is not None:
                        package_source_by_key[key] = source
                        package_source_by_key.setdefault((key[0], None), source)
                        updated = _patch_v4_citation(citation, source)
                        if updated != citation:
                            package_changed = True
                        updated_citations.append(updated)
                    else:
                        updated_citations.append(dict(citation))
                elif conflict:
                    updated = _force_unresolved_citation(citation)
                    if updated != citation:
                        package_changed = True
                    updated_citations.append(updated)
                elif apply and source is not None:
                    package_source_by_key[key] = source
                    package_source_by_key.setdefault((key[0], None), source)
                    updated = _set_citation_defaults(citation, source)
                    if updated != citation:
                        package_changed = True
                    updated_citations.append(updated)
                else:
                    updated_citations.append(dict(citation))

                rows.append(
                    {
                        "response_id": candidate.response_id,
                        "bucket": bucket,
                        "package_kind": package_kind,
                        "url": key[0],
                        "citation_index": key[1],
                        "resolved_mention_id": mention_id,
                        "unresolved_reason": unresolved_reason,
                        "resolution_method": resolution_method,
                        "action": planned_action,
                    }
                )

            if apply and package_changed:
                if package_kind == "v3":
                    _rebuild_citations_package(active_package, updated_citations)
                    _patch_citation_facts(active_package, package_source_by_key)
                    _patch_citation_facts(raw, package_source_by_key)
                else:
                    active_package["citations"] = updated_citations
                response_changed = True
                changed_package_kinds.append(package_kind)

        if apply and response_changed:
            raw["issue_760_citation_geo_followup"] = {
                "applied_at": datetime.now(timezone.utc).isoformat(),
                "approval_ref": approval_ref,
                "response_id": candidate.response_id,
                "package_kinds": sorted(set(changed_package_kinds)),
                "inserted_citation_source_ids": inserted_source_ids,
                "updated_citation_source_ids": updated_source_ids,
                "no_fallback_values": True,
            }
            analysis.raw_analysis_json = raw
            flag_modified(analysis, "raw_analysis_json")
            patched_response_ids.append(candidate.response_id)

    if apply and (inserted_source_ids or updated_source_ids or patched_response_ids):
        await session.flush()

    stats["patched_response_analysis_count"] = len(set(patched_response_ids))
    return {
        "candidate_citation_count": stats["candidate_citation_count"],
        "v4_citation_count": stats["v4_citation_count"],
        "resolvable_citation_count": stats["resolvable_citation_count"],
        "unresolved_citation_count": stats["unresolved_citation_count"],
        "invalid_citation_count": stats["invalid_citation_count"],
        "insert_citation_source_count": stats["insert_citation_source_count"],
        "resolved_existing_citation_source_count": stats[
            "resolved_existing_citation_source_count"
        ],
        "conflicting_existing_citation_source_count": stats[
            "conflicting_existing_citation_source_count"
        ],
        "patched_response_analysis_count": stats["patched_response_analysis_count"],
        "inserted_citation_source_ids": inserted_source_ids,
        "updated_citation_source_ids": updated_source_ids,
        "patched_response_ids": sorted(set(patched_response_ids)),
        "unresolved_reason_counts": dict(sorted(unresolved_reasons.items())),
        "rows": rows,
    }


async def _aggregate_plan(
    session: AsyncSession,
    selected: list[CandidateResponse],
    *,
    brand_id: int,
    approved_dates: list[str] | None = None,
) -> dict:
    days = sorted(
        {
            candidate.collected_at[:10]
            for candidate in selected
            if candidate.collected_at
        }
    )
    rows_before: dict[str, int] = {}
    for day in days:
        date_start = datetime.strptime(day, "%Y-%m-%d")
        count = (
            await session.execute(
                select(func.count())
                .select_from(GEOScoreDaily)
                .where(GEOScoreDaily.brand_id == brand_id, GEOScoreDaily.date == date_start)
            )
        ).scalar_one()
        rows_before[day] = int(count or 0)
    return {
        "dates": days,
        "approved_dates": approved_dates or [],
        "geo_score_daily_rows_before": rows_before,
        "aggregate_from_real_analyzer_facts_only": True,
        "full_brand_date_side_effects": True,
        "requires_separate_aggregate_approval": True,
        "side_effect_summary": (
            "Aggregator.aggregate_daily deletes and rewrites full "
            "geo_score_daily/product_score_daily/topic_score_daily rows for "
            "the selected brand/date scope, then recomputes from all analyzed "
            "responses on each selected day."
        ),
        "rollback": (
            "Use the pre-apply DB backup or report rows to restore/delete the "
            "selected brand/date aggregate rows, then rerun aggregation for "
            "those same dates after reverting citation/analyzer changes."
        ),
    }


async def _aggregate_selected_days(
    session: AsyncSession,
    selected: list[CandidateResponse],
    *,
    brand_id: int,
    competitor_brand_ids: tuple[int, ...],
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
    competitive_brand_ids = {brand_id, *competitor_brand_ids}
    for day in days:
        stats = await aggregator.aggregate_daily(
            datetime.strptime(day, "%Y-%m-%d"),
            brand_id=brand_id,
            competitive_brand_ids=competitive_brand_ids,
        )
        results.append({"date": day, "brand_id": brand_id, "stats": stats})
    return results


async def build_bestcoffer_citation_geo_followup_report(
    session: AsyncSession,
    scope: BestCofferCitationGeoScope,
    *,
    apply: bool = False,
    approval_ref: str | None = None,
    approval_comment_fetcher: ApprovalCommentFetcher | None = None,
    aggregate: bool = False,
    aggregate_approval_ref: str | None = None,
) -> dict:
    validate_scope(scope, apply=apply)
    if apply:
        approval_ref = validate_approval_ref(
            approval_ref,
            approval_comment_fetcher=approval_comment_fetcher,
        )

    candidates = await collect_candidate_responses(session, scope)
    selected = [row for row in candidates if row.invalid_reason is None]
    missing_analyzer = [
        row.response_id for row in selected if not row.has_response_analysis
    ]
    missing_v3 = [
        row.response_id
        for row in selected
        if row.has_response_analysis and not row.has_v3_package
    ]

    citation_plan = await _citation_plan_or_apply(
        session,
        selected,
        apply=apply,
        approval_ref=approval_ref,
    )
    aggregate_plan = await _aggregate_plan(session, selected, brand_id=int(scope.brand_id))
    validated_aggregate_approval_ref: str | None = None
    if apply and aggregate:
        validated_aggregate_approval_ref = validate_aggregate_approval_ref(
            aggregate_approval_ref or approval_ref,
            dates=aggregate_plan["dates"],
            approval_comment_fetcher=approval_comment_fetcher,
        )
        aggregate_plan = await _aggregate_plan(
            session,
            selected,
            brand_id=int(scope.brand_id),
            approved_dates=aggregate_plan["dates"],
        )

    report = {
        "issue": 760,
        "mode": "apply" if apply else "dry_run",
        "write_performed": False,
        "approval_ref": approval_ref,
        "aggregate_approval_ref": validated_aggregate_approval_ref,
        "scope": _scope_dict(scope),
        "safe_selection": {
            "successful_responses_only": True,
            "invalid_artifacts_excluded": True,
            "selected_by_response_ids": bool(scope.normalized_response_ids()),
            "selected_by_query_ids": bool(scope.normalized_query_ids()),
            "selected_by_brand_date_window": not (
                scope.normalized_response_ids() or scope.normalized_query_ids()
            ),
            "apply_requires_explicit_ids": True,
            "date_wide_reset": False,
            "broad_600_query_scraper_run": False,
            "limit": int(scope.limit),
        },
        "selected_response_ids": [row.response_id for row in selected],
        "selected_query_ids": [row.query_id for row in selected],
        "missing_analyzer_response_ids": missing_analyzer,
        "missing_v3_package_response_ids": missing_v3,
        "before": summarize_candidates(candidates),
        "citation_plan": citation_plan,
        "aggregate_plan": aggregate_plan,
        "no_fallback_values": True,
        "root_cause": (
            "The scoped slice has durable successful responses, but analyzer and "
            "citation attribution materialization are incomplete; GEO daily rows "
            "must be recomputed from actual analyzer/mention/citation facts."
        ),
        "rollback": ROLLBACK_NOTE,
        "apply_plan": APPROVAL_REF_HELP if not apply else None,
    }

    if apply:
        report["write_performed"] = bool(
            citation_plan["inserted_citation_source_ids"]
            or citation_plan["updated_citation_source_ids"]
            or citation_plan["patched_response_ids"]
        )
        if aggregate:
            report["aggregate_results"] = await _aggregate_selected_days(
                session,
                selected,
                brand_id=int(scope.brand_id),
                competitor_brand_ids=scope.normalized_competitor_brand_ids(),
            )
            report["write_performed"] = True
        elif report["write_performed"]:
            await session.commit()
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


async def run_from_args(args: argparse.Namespace) -> dict:
    scope = BestCofferCitationGeoScope(
        project_id=args.project_id,
        brand_id=args.brand_id,
        competitor_brand_ids=tuple(args.competitor_brand_id or ()),
        date_from=args.date_from,
        date_to=args.date_to,
        response_ids=_parse_int_csv(args.response_ids),
        query_ids=_parse_int_csv(args.query_ids),
        limit=args.limit,
    )
    engine = create_task_engine()
    try:
        async with get_task_async_session(engine) as session:
            return await build_bestcoffer_citation_geo_followup_report(
                session,
                scope,
                apply=args.apply,
                approval_ref=args.approval_ref,
                aggregate=args.aggregate,
                aggregate_approval_ref=args.aggregate_approval_ref,
            )
    finally:
        await engine.dispose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Controlled BestCoffer citation/GEO materialization for issue #760"
    )
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--brand-id", type=int, default=24)
    parser.add_argument(
        "--competitor-brand-id",
        action="append",
        type=int,
        default=[],
        help="Competitive canonical brand ID for aggregation; repeatable.",
    )
    parser.add_argument("--from", dest="date_from")
    parser.add_argument("--to", dest="date_to")
    parser.add_argument("--response-ids", default="", help="Comma-separated response ids")
    parser.add_argument("--query-ids", default="", help="Comma-separated query ids")
    parser.add_argument("--limit", type=int, default=MAX_LIMIT)
    parser.add_argument("--apply", action="store_true", help="Perform scoped writes")
    parser.add_argument("--aggregate", action="store_true", help="Aggregate selected days")
    parser.add_argument("--approval-ref", default="", help=APPROVAL_REF_HELP)
    parser.add_argument(
        "--aggregate-approval-ref",
        default="",
        help=(
            "Required with --apply --aggregate unless --approval-ref itself "
            "fetches to a #760 comment body that explicitly approves aggregate "
            "recompute for every selected date."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = asyncio.run(run_from_args(args))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "APPROVAL_REF_HELP",
    "ROLLBACK_NOTE",
    "BestCofferCitationGeoScope",
    "build_bestcoffer_citation_geo_followup_report",
    "collect_candidate_responses",
    "summarize_candidates",
    "validate_aggregate_approval_ref",
    "validate_approval_ref",
]
