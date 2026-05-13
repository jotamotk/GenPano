"""Issue #782 - Admin Attempts analyzer API foundation."""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import AdminUser
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture
async def admin_operator(db_session: AsyncSession) -> AsyncGenerator[AdminUser, None]:
    from app.api.admin.auth.router import current_admin
    from app.main import app

    admin = AdminUser(
        id=_new_id(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="$2b$04$dummyhashfortestsdummyhashfortestsdummyhashfortest",
        role="super_admin",
        status="active",
    )
    db_session.add(admin)
    await db_session.commit()

    async def _override_current_admin() -> AdminUser:
        return admin

    app.dependency_overrides[current_admin] = _override_current_admin
    try:
        yield admin
    finally:
        app.dependency_overrides.pop(current_admin, None)


def _admin_analyzer_router_module():
    import app.api.admin.analyzer.router  # noqa: F401

    return sys.modules["app.api.admin.analyzer.router"]


def _legacy_analyzer_router_module():
    import app.api.analyzer.router  # noqa: F401

    return sys.modules["app.api.analyzer.router"]


class _FakeMappingResult:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def mappings(self) -> _FakeMappingResult:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _CapturingSession:
    def __init__(self, rows: list[dict[str, Any]] | None = None):
        self.rows = rows or []
        self.statements: list[str] = []
        self.params: list[dict[str, Any]] = []

    async def execute(self, statement: Any, params: dict[str, Any] | None = None):
        self.statements.append(str(statement))
        self.params.append(dict(params or {}))
        return _FakeMappingResult(self.rows)


async def _analyzer_table_exists(_session: Any, name: str) -> bool:
    return name in {"queries", "llm_responses"}


async def _analyzer_response_columns(_session: Any, _name: str) -> set[str]:
    return {"analyzed_at"}


def test_attempts_analysis_fields_format_no_response_as_not_eligible() -> None:
    from app.admin.queries.db import format_attempt_analysis_fields

    item = format_attempt_analysis_fields({"id": 9001, "response": None, "response_id": None})

    assert item["response_id"] is None
    assert item["analysis_status"] == "not_eligible"
    assert item["analysis_error_code"] == "no_response_text"
    assert item["analysis_summary"] is None
    assert item["analysis_task"] == {
        "latest_task_id": None,
        "latest_run_id": None,
        "latest_batch_id": None,
        "queue_state": None,
    }


def test_attempts_analysis_fields_format_done_summary_without_fake_counts() -> None:
    from app.admin.queries.db import format_attempt_analysis_fields

    item = format_attempt_analysis_fields(
        {
            "id": 9002,
            "response_id": 123,
            "response": "answer text",
            "analysis_status": "done",
            "analysis_id": 456,
            "analyzer_model": "gpt-test",
            "analyzed_at": "2026-05-13T10:00:00",
            "geo_score": 0.8,
            "visibility_score": 0.7,
            "sentiment_score": None,
            "sov_score": None,
            "citation_score": None,
            "total_brands_mentioned": 3,
            "target_brand_mentioned": True,
            "target_brand_sentiment": "positive",
            "mentions_count": None,
            "citations_count": 2,
            "features_count": None,
        }
    )

    assert item["analysis_status"] == "done"
    assert item["analysis_id"] == 456
    assert item["analyzer_model"] == "gpt-test"
    assert item["analysis_summary"]["geo_score"] == 0.8
    assert item["analysis_summary"]["total_brands_mentioned"] == 3
    assert item["analysis_summary"]["mentions_count"] is None
    assert item["analysis_task"]["latest_task_id"] is None


def test_attempts_analysis_fields_format_latest_run_error_and_quality_flags() -> None:
    from app.admin.queries.db import format_attempt_analysis_fields

    item = format_attempt_analysis_fields(
        {
            "id": 9003,
            "response_id": 124,
            "response": "previous good answer",
            "analysis_status": "done",
            "analysis_id": 457,
            "analyzer_model": "gpt-test",
            "analyzer_run_id": 812,
            "analyzer_run_status": "failed",
            "analysis_schema_version": "analyzer_v4",
            "analysis_error_code": "persistence_failed",
            "analysis_error_message": "simulated fact write failure",
            "quality_flag_count": 2,
            "blocking_quality_flag_count": 1,
            "quality_flags": [
                {
                    "code": "persistence_failed",
                    "severity": "error",
                    "message": "simulated fact write failure",
                    "blocks_metric_readiness": True,
                }
            ],
        }
    )

    assert item["analysis_status"] == "done"
    assert item["analyzer_run_id"] == 812
    assert item["analyzer_run_status"] == "failed"
    assert item["analysis_error"] == "simulated fact write failure"
    assert item["analysis_task"]["latest_run_id"] == 812
    assert item["analysis_task"]["queue_state"] == "failed"
    assert item["metric_readiness_status"] == "blocked"
    assert item["metric_readiness_reasons"][0]["code"] == "persistence_failed"


def test_batch_dry_run_payload_requires_scope() -> None:
    from app.admin.analyzer.lib import AnalyzerValidationError, parse_batch_dry_run_payload

    with pytest.raises(AnalyzerValidationError) as exc:
        parse_batch_dry_run_payload({})

    assert exc.value.code == "empty_scope"


def test_batch_dry_run_payload_validates_bounds_and_modes() -> None:
    from app.admin.analyzer.lib import AnalyzerValidationError, parse_batch_dry_run_payload

    with pytest.raises(AnalyzerValidationError) as exc:
        parse_batch_dry_run_payload({"scope": {"response_ids": [1]}, "mode": "replace_all"})
    assert exc.value.code == "invalid_mode"

    with pytest.raises(AnalyzerValidationError) as exc:
        parse_batch_dry_run_payload({"scope": {"response_ids": [1]}, "max_count": 0})
    assert exc.value.code == "invalid_max_count"

    with pytest.raises(AnalyzerValidationError) as exc:
        parse_batch_dry_run_payload({"scope": {"response_ids": [1]}, "sample_limit": 0})
    assert exc.value.code == "invalid_sample_limit"


def test_build_batch_dry_run_result_counts_skips_and_caps() -> None:
    from app.admin.analyzer.lib import build_batch_dry_run_result, parse_batch_dry_run_payload

    payload = parse_batch_dry_run_payload(
        {
            "scope": {"response_ids": [105, 101, 101, 102, 103, 104, 106, 999]},
            "mode": "missing_or_failed_only",
            "max_count": 2,
            "sample_limit": 2,
        }
    )
    result = build_batch_dry_run_result(
        payload,
        [
            {
                "query_id": 9001,
                "response_id": 101,
                "raw_text": "eligible missing",
                "attempt_status": "done",
                "analysis_status": None,
                "analysis_id": None,
            },
            {
                "query_id": 9002,
                "response_id": 102,
                "raw_text": "already analyzed",
                "attempt_status": "done",
                "analysis_status": "done",
                "analysis_id": 502,
            },
            {
                "query_id": 9003,
                "response_id": 103,
                "raw_text": "",
                "attempt_status": "done",
                "analysis_status": "failed",
                "analysis_id": None,
            },
            {
                "query_id": 9004,
                "response_id": 104,
                "raw_text": "in progress",
                "attempt_status": "done",
                "analysis_status": "running",
                "analysis_id": None,
            },
            {
                "query_id": 9005,
                "response_id": 105,
                "raw_text": "eligible failed",
                "attempt_status": "done",
                "analysis_status": "failed",
                "analysis_id": None,
            },
            {
                "query_id": 9006,
                "response_id": 106,
                "raw_text": "eligible third",
                "attempt_status": "done",
                "analysis_status": None,
                "analysis_id": None,
            },
        ],
    )

    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["eligible_count"] == 3
    assert result["will_enqueue_count"] == 2
    assert result["cap_truncated"] is True
    assert result["eligible_response_ids_preview"] == [105, 101]
    assert result["already_done_count"] == 1
    assert result["skipped_invalid_count"] == 1
    assert result["skipped_counts"]["duplicate_response_id"] == 1
    assert result["skipped_counts"]["empty_response"] == 1
    assert result["skipped_counts"]["already_queued_or_running"] == 1


def test_build_batch_dry_run_skips_current_running_analyzer_run() -> None:
    from app.admin.analyzer.lib import build_batch_dry_run_result, parse_batch_dry_run_payload

    payload = parse_batch_dry_run_payload(
        {
            "scope": {"response_ids": [201]},
            "mode": "reanalyze_all",
            "max_count": 10,
            "sample_limit": 10,
        }
    )
    result = build_batch_dry_run_result(
        payload,
        [
            {
                "query_id": 9201,
                "response_id": 201,
                "raw_text": "current answer",
                "attempt_status": "done",
                "analysis_status": "done",
                "analysis_id": 601,
                "analyzer_run_status": "running",
            }
        ],
    )

    assert result["eligible_count"] == 0
    assert result["will_enqueue_count"] == 0
    assert result["skipped_counts"]["already_queued_or_running"] == 1


@pytest.mark.asyncio
async def test_preview_batch_dry_run_maps_virtual_pending_attempt_statuses(
    monkeypatch,
) -> None:
    from app.admin.analyzer import db as analyzer_db

    monkeypatch.setattr(analyzer_db, "_table_exists", _analyzer_table_exists)
    monkeypatch.setattr(analyzer_db, "_table_columns", _analyzer_response_columns)

    queued_session = _CapturingSession()
    await analyzer_db.preview_batch_analyzer_candidates(
        queued_session,
        scope={"filters": {"attempt_status": "queued"}},
    )

    assert (
        "LOWER(q.status) = 'pending' AND q.queued_at IS NOT NULL" in (queued_session.statements[-1])
    )
    assert "attempt_status" not in queued_session.params[-1]

    unqueued_session = _CapturingSession()
    await analyzer_db.preview_batch_analyzer_candidates(
        unqueued_session,
        scope={"filters": {"attempt_status": "unqueued"}},
    )

    assert (
        "LOWER(q.status) = 'pending' AND q.queued_at IS NULL" in (unqueued_session.statements[-1])
    )
    assert "attempt_status" not in unqueued_session.params[-1]


@pytest.mark.asyncio
async def test_batch_dry_run_large_scope_returns_too_large_state(monkeypatch) -> None:
    from app.admin.analyzer import db as analyzer_db
    from app.admin.analyzer.lib import build_batch_dry_run_result, parse_batch_dry_run_payload

    monkeypatch.setattr(analyzer_db, "_table_exists", _analyzer_table_exists)
    monkeypatch.setattr(analyzer_db, "_table_columns", _analyzer_response_columns)

    rows = [
        {
            "query_id": index,
            "attempt_status": "done",
            "target_llm": "deepseek",
            "brand_id": 12,
            "response_id": index,
            "raw_text": f"answer {index}",
            "analysis_status": None,
            "analyzed_at": None,
            "analysis_id": None,
            "analyzer_model": None,
            "analysis_analyzed_at": None,
        }
        for index in range(1, 5002)
    ]
    session = _CapturingSession(rows)

    preview_rows = await analyzer_db.preview_batch_analyzer_candidates(
        session,
        scope={"filters": {"attempt_status": "done"}},
    )

    assert "LIMIT 5001" in session.statements[-1]
    assert len(preview_rows) == 5000
    assert preview_rows.query_truncated is True
    assert preview_rows.query_limit == 5000

    payload = parse_batch_dry_run_payload(
        {
            "scope": {"filters": {"attempt_status": "done"}},
            "mode": "missing_or_failed_only",
            "max_count": 200,
            "sample_limit": 20,
        }
    )
    result = build_batch_dry_run_result(payload, preview_rows)

    assert result["success"] is False
    assert result["error"] == "dry_run_scope_too_large"
    assert result["scope_too_large"] is True
    assert result["query_truncated"] is True
    assert result["query_limit"] == 5000
    assert result["counts_complete"] is False
    assert result["matched_attempts"] is None
    assert result["matched_attempts_evaluated"] == 5000
    assert result["eligible_count"] is None
    assert result["eligible_count_evaluated"] == 5000
    assert result["cap_truncated"] is False
    assert result["will_enqueue_count"] == 0
    assert result["requires_confirmation"] is False


@pytest.mark.asyncio
async def test_admin_batch_dry_run_unauth_401(client) -> None:
    resp = await client.post(
        "/admin/api/analyzer/responses/batch/dry-run",
        json={"scope": {"response_ids": [1]}},
    )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_response_status_unauth_401(client) -> None:
    resp = await client.get("/admin/api/analyzer/responses/101/status")

    assert resp.status_code == 401
    assert "text/html" not in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_legacy_response_status_compat_unauth_401(client) -> None:
    resp = await client.get("/api/analyzer/responses/101/status")

    assert resp.status_code == 401
    assert "text/html" not in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_legacy_batch_dry_run_compat_unauth_401(client) -> None:
    resp = await client.post(
        "/api/analyzer/responses/batch/dry-run",
        json={"scope": {"response_ids": [1]}},
    )

    assert resp.status_code == 401
    assert "text/html" not in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_legacy_attempts_mutation_routes_keep_admin_auth_guard(client) -> None:
    single = await client.post(
        "/api/analyzer/responses/101/analyze",
        json={"mode": "missing_or_failed_only", "reason": "operator retry"},
    )
    batch = await client.post(
        "/api/analyzer/responses/batch",
        json={"scope": {"response_ids": [101]}, "confirm": True},
    )
    status = await client.get("/api/analyzer/batches/batch-123")

    assert single.status_code == 401
    assert batch.status_code == 401
    assert status.status_code == 401


@pytest.mark.asyncio
async def test_admin_batch_dry_run_returns_counts(client, admin_operator, monkeypatch) -> None:
    module = _admin_analyzer_router_module()
    monkeypatch.setattr(
        module.analyzer_db,
        "preview_batch_analyzer_candidates",
        AsyncMock(
            return_value=[
                {
                    "query_id": 9001,
                    "response_id": 101,
                    "raw_text": "eligible",
                    "attempt_status": "done",
                    "analysis_status": "failed",
                    "analysis_id": None,
                },
                {
                    "query_id": 9002,
                    "response_id": 102,
                    "raw_text": "done",
                    "attempt_status": "done",
                    "analysis_status": "done",
                    "analysis_id": 502,
                },
            ]
        ),
    )

    resp = await client.post(
        "/admin/api/analyzer/responses/batch/dry-run",
        json={
            "scope": {"response_ids": [101, 102, 999]},
            "mode": "missing_or_failed_only",
            "max_count": 200,
            "sample_limit": 20,
            "reason": "operator preview",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["eligible_count"] == 1
    assert body["already_done_count"] == 1
    assert body["skipped_invalid_count"] == 1
    assert body["eligible_response_ids_preview"] == [101]
    assert body["dry_run_id"]


@pytest.mark.asyncio
async def test_legacy_batch_dry_run_compat_returns_admin_counts(
    client, admin_operator, monkeypatch
) -> None:
    module = _admin_analyzer_router_module()
    preview = AsyncMock(
        return_value=[
            {
                "query_id": 9001,
                "response_id": 101,
                "raw_text": "eligible",
                "attempt_status": "done",
                "analysis_status": "failed",
                "analysis_id": None,
            }
        ]
    )
    monkeypatch.setattr(module.analyzer_db, "preview_batch_analyzer_candidates", preview)

    resp = await client.post(
        "/api/analyzer/responses/batch/dry-run",
        json={
            "scope": {"response_ids": [101]},
            "mode": "missing_or_failed_only",
            "max_count": 200,
            "sample_limit": 20,
            "reason": "operator preview",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["dry_run"] is True
    assert body["eligible_count"] == 1
    assert body["eligible_response_ids_preview"] == [101]
    preview.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_single_analyze_compat_validates_like_admin(
    client, admin_operator, monkeypatch
) -> None:
    module = _admin_analyzer_router_module()
    fetch_status = AsyncMock(return_value={"response_id": 101, "raw_text": "eligible"})
    monkeypatch.setattr(module.analyzer_db, "fetch_response_analyzer_status", fetch_status)

    resp = await client.post(
        "/api/analyzer/responses/101/analyze",
        json={"mode": "replace_all", "reason": "operator retry"},
    )

    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_mode"
    fetch_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_response_status_returns_run_and_quality_fields(
    client, admin_operator, monkeypatch
) -> None:
    module = _admin_analyzer_router_module()
    monkeypatch.setattr(
        module.analyzer_db,
        "fetch_response_analyzer_status",
        AsyncMock(
            return_value={
                "response_id": 101,
                "query_id": 9001,
                "raw_text": "eligible",
                "analysis_status": "done",
                "analysis_id": 501,
                "analyzer_model": "gpt-test",
                "analyzer_run_id": 701,
                "analyzer_run_status": "partial",
                "task_id": "task-701",
                "batch_id": "batch-701",
                "analysis_schema_version": "analyzer_v4",
                "analysis_error_code": None,
                "analysis_error_message": None,
                "quality_flag_count": 1,
                "blocking_quality_flag_count": 0,
                "quality_flags": [
                    {
                        "code": "citation_unlinked",
                        "severity": "warning",
                        "message": "citation was not linked to a fact",
                        "blocks_metric_readiness": False,
                    }
                ],
            }
        ),
    )

    resp = await client.get("/admin/api/analyzer/responses/101/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["response_id"] == 101
    assert body["analyzer_run_id"] == 701
    assert body["analysis_task"]["latest_run_id"] == 701
    assert body["analysis_task"]["latest_task_id"] == "task-701"
    assert body["analysis_task"]["latest_batch_id"] == "batch-701"
    assert body["analysis_task"]["queue_state"] == "complete"
    assert body["metric_readiness_status"] == "warning"
    assert body["metric_readiness_reasons"][0]["code"] == "citation_unlinked"


@pytest.mark.asyncio
async def test_admin_response_status_serializes_run_datetimes(
    client, admin_operator, monkeypatch
) -> None:
    started_at = datetime(2026, 5, 13, 8, 9, 10, tzinfo=UTC)
    completed_at = datetime(2026, 5, 13, 8, 10, 11, tzinfo=UTC)
    module = _admin_analyzer_router_module()
    monkeypatch.setattr(
        module.analyzer_db,
        "fetch_response_analyzer_status",
        AsyncMock(
            return_value={
                "response_id": 101,
                "query_id": 9001,
                "raw_text": "eligible",
                "analysis_status": "done",
                "analysis_id": 501,
                "analyzer_run_id": 701,
                "analyzer_run_status": "done",
                "analyzer_run_started_at": started_at,
                "analyzer_run_completed_at": completed_at,
            }
        ),
    )

    resp = await client.get("/admin/api/analyzer/responses/101/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["analyzer_run_started_at"] == started_at.isoformat()
    assert body["analyzer_run_completed_at"] == completed_at.isoformat()
    assert body["analyzed_at"] == completed_at.isoformat()


@pytest.mark.asyncio
async def test_legacy_response_status_compat_returns_admin_status_shape(
    client, admin_operator, monkeypatch
) -> None:
    module = _legacy_analyzer_router_module()
    fetch_status = AsyncMock(
        return_value={
            "response_id": 101,
            "query_id": 9001,
            "raw_text": "eligible",
            "analysis_status": "done",
            "analysis_id": 501,
            "analyzer_model": "gpt-test",
            "analyzer_run_id": 701,
            "analyzer_run_status": "partial",
            "analysis_schema_version": "analyzer_v4",
            "analysis_error_code": None,
            "analysis_error_message": None,
            "quality_flag_count": 1,
            "blocking_quality_flag_count": 0,
            "quality_flags": [
                {
                    "code": "citation_unlinked",
                    "severity": "warning",
                    "message": "citation was not linked to a fact",
                    "blocks_metric_readiness": False,
                }
            ],
        }
    )
    monkeypatch.setattr(module.analyzer_db, "fetch_response_analyzer_status", fetch_status)

    resp = await client.get("/api/analyzer/responses/101/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["response_id"] == 101
    assert body["analyzer_run_id"] == 701
    assert body["analysis_task"]["latest_run_id"] == 701
    assert body["analysis_task"]["queue_state"] == "complete"
    assert body["metric_readiness_status"] == "warning"
    assert body["metric_readiness_reasons"][0]["code"] == "citation_unlinked"
    fetch_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_response_status_compat_serializes_run_datetimes(
    client, admin_operator, monkeypatch
) -> None:
    started_at = datetime(2026, 5, 13, 8, 9, 10, tzinfo=UTC)
    completed_at = datetime(2026, 5, 13, 8, 10, 11, tzinfo=UTC)
    module = _legacy_analyzer_router_module()
    fetch_status = AsyncMock(
        return_value={
            "response_id": 101,
            "query_id": 9001,
            "raw_text": "eligible",
            "analysis_status": "done",
            "analysis_id": 501,
            "analyzer_run_id": 701,
            "analyzer_run_status": "done",
            "analyzer_run_started_at": started_at,
            "analyzer_run_completed_at": completed_at,
        }
    )
    monkeypatch.setattr(module.analyzer_db, "fetch_response_analyzer_status", fetch_status)

    resp = await client.get("/api/analyzer/responses/101/status")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["analyzer_run_started_at"] == started_at.isoformat()
    assert body["analyzer_run_completed_at"] == completed_at.isoformat()
    assert body["analyzed_at"] == completed_at.isoformat()
    fetch_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_single_analyze_records_enqueue_failure_when_celery_unavailable(
    client, admin_operator, monkeypatch
) -> None:
    module = _admin_analyzer_router_module()
    monkeypatch.setattr(
        module.analyzer_db,
        "fetch_response_analyzer_status",
        AsyncMock(
            return_value={
                "response_id": 101,
                "query_id": 9001,
                "raw_text": "eligible",
                "analysis_status": "failed",
                "analysis_id": None,
            }
        ),
    )

    resp = await client.post(
        "/admin/api/analyzer/responses/101/analyze",
        json={"mode": "missing_or_failed_only", "reason": "operator retry"},
    )

    assert resp.status_code == 503
    body = resp.json()
    assert body["success"] is False
    assert body["error"] == "analyzer_enqueue_failed"
    assert body["run_id"]


@pytest.mark.asyncio
async def test_batch_submit_with_no_candidates_completes_and_unknown_status_404(
    client, admin_operator
) -> None:
    submit = await client.post(
        "/admin/api/analyzer/responses/batch",
        json={
            "scope": {"response_ids": [101]},
            "confirm": True,
            "idempotency_key": "batch-no-candidates-101",
        },
    )
    status = await client.get("/admin/api/analyzer/batches/batch-123")

    assert submit.status_code == 200
    submit_body = submit.json()
    assert submit_body["success"] is True
    assert submit_body["accepted_count"] == 0
    assert submit_body["status"] == "complete"
    assert status.status_code == 404
    assert status.json()["error"] == "batch_not_found"
