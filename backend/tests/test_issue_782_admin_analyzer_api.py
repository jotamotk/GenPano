"""Issue #782 - Admin Attempts analyzer API foundation."""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncGenerator
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


def test_attempts_analysis_fields_format_no_response_as_not_eligible() -> None:
    from app.admin.queries.db import format_attempt_analysis_fields

    item = format_attempt_analysis_fields({"id": 9001, "response": None, "response_id": None})

    assert item["response_id"] is None
    assert item["analysis_status"] == "not_eligible"
    assert item["analysis_error_code"] == "no_response_text"
    assert item["analysis_summary"] is None
    assert item["analysis_task"] == {
        "latest_task_id": None,
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


@pytest.mark.asyncio
async def test_admin_batch_dry_run_unauth_401(client) -> None:
    resp = await client.post(
        "/admin/api/analyzer/responses/batch/dry-run",
        json={"scope": {"response_ids": [1]}},
    )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_batch_dry_run_is_not_added_to_legacy_api_analyzer(client) -> None:
    resp = await client.post(
        "/api/analyzer/responses/batch/dry-run",
        json={"scope": {"response_ids": [1]}},
    )

    assert resp.status_code == 404


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
async def test_single_analyze_is_dependency_blocked_without_run_persistence(
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

    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert body["error"] == "analyzer_run_persistence_required"
    assert body["blocked_by_issue"] == 781


@pytest.mark.asyncio
async def test_batch_submit_and_status_are_dependency_blocked(client, admin_operator) -> None:
    submit = await client.post(
        "/admin/api/analyzer/responses/batch",
        json={"scope": {"response_ids": [101]}, "confirm": True},
    )
    status = await client.get("/admin/api/analyzer/batches/batch-123")

    assert submit.status_code == 409
    assert submit.json()["blocked_by_issue"] == 781
    assert status.status_code == 409
    assert status.json()["blocked_by_issue"] == 781
