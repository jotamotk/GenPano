"""Issue #797 - Admin analyzer durable submit and batch persistence."""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from genpano_models import AdminUser, AnalyzerBatch, AnalyzerBatchItem, AnalyzerRun
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
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


def _status_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "response_id": 101,
        "query_id": 9001,
        "raw_text": "eligible response text",
        "analysis_status": "failed",
        "analysis_id": None,
        "analyzer_run_id": None,
        "analyzer_run_status": None,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_single_analyze_creates_queued_run_and_dispatches_task(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    monkeypatch.setattr(
        module.analyzer_db,
        "fetch_response_analyzer_status",
        AsyncMock(return_value=_status_row()),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "create_or_get_queued_analyzer_run",
        AsyncMock(
            return_value={
                "run_id": 701,
                "response_id": 101,
                "status": "queued",
                "task_id": None,
                "idempotent": False,
                "previous_analysis_status": "failed",
            }
        ),
    )
    mark_enqueued = AsyncMock(return_value=None)
    monkeypatch.setattr(module.analyzer_db, "mark_analyzer_run_enqueued", mark_enqueued)
    monkeypatch.setattr(
        module.analyzer_db,
        "claim_analyzer_run_for_dispatch",
        AsyncMock(return_value={"claimed": True, "reason": "claimed"}),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "mark_analyzer_run_enqueue_failed",
        AsyncMock(return_value=None),
    )
    dispatch = Mock(return_value="task-701")
    monkeypatch.setattr(module, "dispatch_analyze_response", dispatch)

    resp = await client.post(
        "/admin/api/analyzer/responses/101/analyze",
        json={
            "mode": "missing_or_failed_only",
            "reason": "operator retry",
            "idempotency_key": "retry-101",
        },
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["success"] is True
    assert body["accepted"] is True
    assert body["response_id"] == 101
    assert body["run_id"] == 701
    assert body["task_id"] == "task-701"
    assert body["status"] == "queued"
    dispatch.assert_called_once_with(101, analyzer_run_id=701)
    mark_enqueued.assert_awaited_once()


@pytest.mark.asyncio
async def test_single_analyze_duplicate_active_run_is_idempotent_without_dispatch(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    monkeypatch.setattr(
        module.analyzer_db,
        "fetch_response_analyzer_status",
        AsyncMock(return_value=_status_row(analysis_status="queued")),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "create_or_get_queued_analyzer_run",
        AsyncMock(
            return_value={
                "run_id": 702,
                "response_id": 101,
                "status": "queued",
                "task_id": "task-existing",
                "idempotent": True,
                "previous_analysis_status": "queued",
            }
        ),
    )
    dispatch = Mock(return_value="task-new")
    monkeypatch.setattr(module, "dispatch_analyze_response", dispatch)

    resp = await client.post(
        "/admin/api/analyzer/responses/101/analyze",
        json={"mode": "missing_or_failed_only", "idempotency_key": "retry-101"},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["accepted"] is True
    assert body["idempotent"] is True
    assert body["run_id"] == 702
    assert body["task_id"] == "task-existing"
    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_single_analyze_idempotent_queued_run_without_task_is_redispatched(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    monkeypatch.setattr(
        module.analyzer_db,
        "fetch_response_analyzer_status",
        AsyncMock(return_value=_status_row(analysis_status="queued")),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "create_or_get_queued_analyzer_run",
        AsyncMock(
            return_value={
                "run_id": 704,
                "response_id": 101,
                "status": "queued",
                "task_id": None,
                "idempotent": True,
                "previous_analysis_status": "queued",
            }
        ),
    )
    mark_enqueued = AsyncMock(return_value=None)
    monkeypatch.setattr(module.analyzer_db, "mark_analyzer_run_enqueued", mark_enqueued)
    monkeypatch.setattr(
        module.analyzer_db,
        "claim_analyzer_run_for_dispatch",
        AsyncMock(return_value={"claimed": True, "reason": "claimed"}),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "mark_analyzer_run_enqueue_failed",
        AsyncMock(return_value=None),
    )
    dispatch = Mock(return_value="task-recovered-704")
    monkeypatch.setattr(module, "dispatch_analyze_response", dispatch)

    resp = await client.post(
        "/admin/api/analyzer/responses/101/analyze",
        json={"mode": "missing_or_failed_only", "idempotency_key": "retry-101"},
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["success"] is True
    assert body["accepted"] is True
    assert body["idempotent"] is True
    assert body["run_id"] == 704
    assert body["task_id"] == "task-recovered-704"
    dispatch.assert_called_once_with(101, analyzer_run_id=704)
    mark_enqueued.assert_awaited_once()


@pytest.mark.asyncio
async def test_single_analyze_same_key_after_enqueue_failure_returns_failed_idempotent_status(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    monkeypatch.setattr(
        module.analyzer_db,
        "fetch_response_analyzer_status",
        AsyncMock(return_value=_status_row(analysis_status="failed")),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "create_or_get_queued_analyzer_run",
        AsyncMock(
            return_value={
                "run_id": 799,
                "response_id": 101,
                "status": "failed",
                "task_id": None,
                "idempotent": True,
                "failure_code": "enqueue_failed",
                "failure_message": "Analyzer task enqueue failed.",
                "previous_analysis_status": "failed",
            }
        ),
    )
    dispatch = Mock(return_value="task-should-not-run")
    monkeypatch.setattr(module, "dispatch_analyze_response", dispatch)

    resp = await client.post(
        "/admin/api/analyzer/responses/101/analyze",
        json={"mode": "missing_or_failed_only", "idempotency_key": "retry-failed-101"},
    )

    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert body["accepted"] is False
    assert body["idempotent"] is True
    assert body["error"] == "analyzer_run_already_failed"
    assert body["run_id"] == 799
    assert body["status"] == "failed"
    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_single_analyze_enqueue_failure_marks_run_failed_without_losing_done_status(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    monkeypatch.setattr(
        module.analyzer_db,
        "fetch_response_analyzer_status",
        AsyncMock(
            return_value=_status_row(
                analysis_status="done",
                analysis_id=501,
                analyzer_run_status="failed",
            )
        ),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "create_or_get_queued_analyzer_run",
        AsyncMock(
            return_value={
                "run_id": 703,
                "response_id": 101,
                "status": "queued",
                "task_id": None,
                "idempotent": False,
                "previous_analysis_status": "done",
            }
        ),
    )
    mark_failed = AsyncMock(return_value=None)
    monkeypatch.setattr(module.analyzer_db, "mark_analyzer_run_enqueue_failed", mark_failed)
    monkeypatch.setattr(
        module.analyzer_db,
        "claim_analyzer_run_for_dispatch",
        AsyncMock(return_value={"claimed": True, "reason": "claimed"}),
    )
    monkeypatch.setattr(module, "dispatch_analyze_response", Mock(return_value=None))

    resp = await client.post(
        "/admin/api/analyzer/responses/101/analyze",
        json={"mode": "reanalyze_current", "idempotency_key": "reanalyze-101"},
    )

    assert resp.status_code == 503
    body = resp.json()
    assert body["success"] is False
    assert body["error"] == "analyzer_enqueue_failed"
    assert body["run_id"] == 703
    mark_failed.assert_awaited_once()
    _, kwargs = mark_failed.await_args
    assert kwargs["run_id"] == 703
    assert kwargs["previous_analysis_status"] == "done"


@pytest.mark.asyncio
async def test_single_analyze_returns_dependency_gate_when_run_columns_missing(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    monkeypatch.setattr(
        module.analyzer_db,
        "fetch_response_analyzer_status",
        AsyncMock(return_value=_status_row()),
    )
    readiness = AsyncMock(return_value=False)
    create_run = AsyncMock(
        return_value={
            "run_id": 701,
            "response_id": 101,
            "status": "queued",
            "task_id": None,
            "idempotent": False,
        }
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "analyzer_single_submit_ready",
        readiness,
        raising=False,
    )
    monkeypatch.setattr(module.analyzer_db, "create_or_get_queued_analyzer_run", create_run)
    dispatch = Mock(return_value="task-701")
    monkeypatch.setattr(module, "dispatch_analyze_response", dispatch)

    resp = await client.post(
        "/admin/api/analyzer/responses/101/analyze",
        json={"mode": "missing_or_failed_only", "idempotency_key": "retry-101"},
    )

    assert resp.status_code == 409
    assert resp.json()["error"] == "analyzer_run_persistence_required"
    readiness.assert_awaited_once()
    create_run.assert_not_awaited()
    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_batch_submit_persists_preview_and_dispatches_submitted_items(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    preview_rows = [
        _status_row(response_id=101, query_id=9001, analysis_status="failed"),
        _status_row(response_id=102, query_id=9002, analysis_status=None),
        _status_row(response_id=103, query_id=9003, analysis_status="done", analysis_id=503),
    ]
    monkeypatch.setattr(
        module.analyzer_db,
        "preview_batch_analyzer_candidates",
        AsyncMock(return_value=preview_rows),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "create_analyzer_batch_submission",
        AsyncMock(
            return_value={
                "batch_id": "batch-797",
                "dry_run_id": "dry-797",
                "status": "queued",
                "submitted_count": 2,
                "skipped_count": 1,
                "items": [
                    {"item_id": 1, "response_id": 101, "run_id": 801, "status": "queued"},
                    {"item_id": 2, "response_id": 102, "run_id": 802, "status": "queued"},
                ],
            }
        ),
    )
    mark_item = AsyncMock(return_value=None)
    monkeypatch.setattr(module.analyzer_db, "mark_analyzer_batch_item_enqueued", mark_item)
    monkeypatch.setattr(
        module.analyzer_db,
        "claim_analyzer_run_for_dispatch",
        AsyncMock(return_value={"claimed": True, "reason": "claimed"}),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "mark_analyzer_batch_item_enqueue_failed",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "refresh_analyzer_batch_status",
        AsyncMock(return_value={"batch_id": "batch-797", "status": "queued"}),
    )
    dispatch = Mock(side_effect=["task-801", "task-802"])
    monkeypatch.setattr(module, "dispatch_analyze_response", dispatch)

    resp = await client.post(
        "/admin/api/analyzer/responses/batch",
        json={
            "scope": {"response_ids": [101, 102, 103]},
            "mode": "missing_or_failed_only",
            "max_count": 10,
            "confirm": True,
            "reason": "operator batch",
            "idempotency_key": "batch-key",
        },
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["success"] is True
    assert body["batch_id"] == "batch-797"
    assert body["accepted_count"] == 2
    assert body["submitted_response_ids"] == [101, 102]
    assert body["skipped_count"] == 1
    assert body["status"] == "queued"
    assert dispatch.call_args_list[0].args == (101,)
    assert dispatch.call_args_list[0].kwargs == {"analyzer_run_id": 801}
    assert dispatch.call_args_list[1].args == (102,)
    assert dispatch.call_args_list[1].kwargs == {"analyzer_run_id": 802}
    assert mark_item.await_count == 2


@pytest.mark.asyncio
async def test_batch_submit_reused_active_run_with_task_id_is_not_redispatched(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    monkeypatch.setattr(
        module.analyzer_db,
        "preview_batch_analyzer_candidates",
        AsyncMock(return_value=[_status_row(response_id=101, query_id=9001)]),
    )
    existing_item = {
        "item_id": 1,
        "response_id": 101,
        "run_id": 801,
        "task_id": "task-existing",
        "status": "queued",
        "dispatch_required": False,
        "reused_active_run": True,
    }
    monkeypatch.setattr(
        module.analyzer_db,
        "create_analyzer_batch_submission",
        AsyncMock(
            return_value={
                "batch_id": "batch-reused",
                "dry_run_id": "dry-reused",
                "status": "queued",
                "submitted_count": 1,
                "accepted_count": 1,
                "skipped_count": 0,
                "items": [existing_item],
            }
        ),
    )
    mark_item = AsyncMock(return_value=None)
    monkeypatch.setattr(module.analyzer_db, "mark_analyzer_batch_item_enqueued", mark_item)
    monkeypatch.setattr(
        module.analyzer_db,
        "claim_analyzer_run_for_dispatch",
        AsyncMock(return_value={"claimed": True, "reason": "claimed"}),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "mark_analyzer_batch_item_enqueue_failed",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "refresh_analyzer_batch_status",
        AsyncMock(
            return_value={
                "batch_id": "batch-reused",
                "status": "queued",
                "submitted_count": 1,
                "accepted_count": 1,
                "submitted_response_ids": [101],
                "items": [existing_item],
            }
        ),
    )
    dispatch = Mock(return_value="task-duplicate")
    monkeypatch.setattr(module, "dispatch_analyze_response", dispatch)

    resp = await client.post(
        "/admin/api/analyzer/responses/batch",
        json={
            "scope": {"response_ids": [101]},
            "mode": "missing_or_failed_only",
            "max_count": 10,
            "confirm": True,
            "idempotency_key": "batch-reused",
        },
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted_count"] == 1
    assert body["items"][0]["task_id"] == "task-existing"
    assert body["items"][0]["reused_active_run"] is True
    dispatch.assert_not_called()
    mark_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_submit_reused_queued_run_without_task_is_redispatched(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    monkeypatch.setattr(
        module.analyzer_db,
        "preview_batch_analyzer_candidates",
        AsyncMock(return_value=[_status_row(response_id=101, query_id=9001)]),
    )
    existing_item = {
        "item_id": 1,
        "response_id": 101,
        "run_id": 801,
        "task_id": None,
        "status": "queued",
        "dispatch_required": False,
        "reused_active_run": True,
    }
    monkeypatch.setattr(
        module.analyzer_db,
        "create_analyzer_batch_submission",
        AsyncMock(
            return_value={
                "batch_id": "batch-reused-missing-task",
                "dry_run_id": "dry-reused-missing-task",
                "status": "queued",
                "submitted_count": 1,
                "accepted_count": 0,
                "skipped_count": 0,
                "items": [existing_item],
            }
        ),
    )
    mark_item = AsyncMock(return_value=None)
    monkeypatch.setattr(module.analyzer_db, "mark_analyzer_batch_item_enqueued", mark_item)
    monkeypatch.setattr(
        module.analyzer_db,
        "claim_analyzer_run_for_dispatch",
        AsyncMock(return_value={"claimed": True, "reason": "claimed"}),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "mark_analyzer_batch_item_enqueue_failed",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "refresh_analyzer_batch_status",
        AsyncMock(
            return_value={
                "batch_id": "batch-reused-missing-task",
                "status": "queued",
                "submitted_count": 1,
                "accepted_count": 1,
                "submitted_response_ids": [101],
                "accepted_response_ids": [101],
                "items": [{**existing_item, "task_id": "task-recovered-801"}],
            }
        ),
    )
    dispatch = Mock(return_value="task-recovered-801")
    monkeypatch.setattr(module, "dispatch_analyze_response", dispatch)

    resp = await client.post(
        "/admin/api/analyzer/responses/batch",
        json={
            "scope": {"response_ids": [101]},
            "mode": "missing_or_failed_only",
            "max_count": 10,
            "confirm": True,
            "idempotency_key": "batch-reused-missing-task",
        },
    )

    assert resp.status_code == 202
    body = resp.json()
    assert body["accepted_count"] == 1
    assert body["submitted_response_ids"] == [101]
    assert body["accepted_response_ids"] == [101]
    dispatch.assert_called_once_with(101, analyzer_run_id=801)
    mark_item.assert_awaited_once()


@pytest.mark.asyncio
async def test_batch_submit_all_enqueue_failed_is_clear_and_preserves_done_status(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    monkeypatch.setattr(
        module.analyzer_db,
        "preview_batch_analyzer_candidates",
        AsyncMock(
            return_value=[
                _status_row(response_id=101, query_id=9001, analysis_status="done"),
                _status_row(response_id=102, query_id=9002, analysis_status="failed"),
            ]
        ),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "create_analyzer_batch_submission",
        AsyncMock(
            return_value={
                "batch_id": "batch-enqueue-failed",
                "dry_run_id": "dry-enqueue-failed",
                "status": "queued",
                "submitted_count": 2,
                "skipped_count": 0,
                "items": [
                    {
                        "item_id": 1,
                        "response_id": 101,
                        "run_id": 801,
                        "status": "queued",
                        "previous_analysis_status": "done",
                        "dispatch_required": True,
                    },
                    {
                        "item_id": 2,
                        "response_id": 102,
                        "run_id": 802,
                        "status": "queued",
                        "previous_analysis_status": "failed",
                        "dispatch_required": True,
                    },
                ],
            }
        ),
    )
    mark_failed = AsyncMock(return_value=None)
    monkeypatch.setattr(module.analyzer_db, "mark_analyzer_batch_item_enqueue_failed", mark_failed)
    monkeypatch.setattr(
        module.analyzer_db,
        "claim_analyzer_run_for_dispatch",
        AsyncMock(return_value={"claimed": True, "reason": "claimed"}),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "mark_analyzer_batch_item_enqueued",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        module.analyzer_db,
        "refresh_analyzer_batch_status",
        AsyncMock(
            return_value={
                "batch_id": "batch-enqueue-failed",
                "status": "failed",
                "submitted_count": 2,
                "accepted_count": 0,
                "failed_count": 2,
                "submitted_response_ids": [101, 102],
                "accepted_response_ids": [],
                "failed_response_ids": [101, 102],
                "items": [
                    {"item_id": 1, "response_id": 101, "run_id": 801, "status": "failed"},
                    {"item_id": 2, "response_id": 102, "run_id": 802, "status": "failed"},
                ],
            }
        ),
    )
    monkeypatch.setattr(module, "dispatch_analyze_response", Mock(return_value=None))

    resp = await client.post(
        "/admin/api/analyzer/responses/batch",
        json={
            "scope": {"response_ids": [101, 102]},
            "mode": "reanalyze_all",
            "max_count": 10,
            "confirm": True,
            "idempotency_key": "batch-enqueue-failed",
        },
    )

    assert resp.status_code == 503
    body = resp.json()
    assert body["success"] is False
    assert body["accepted"] is False
    assert body["error"] == "analyzer_batch_enqueue_failed"
    assert body["accepted_count"] == 0
    assert body["submitted_response_ids"] == [101, 102]
    assert body["accepted_response_ids"] == []
    assert body["failed_response_ids"] == [101, 102]
    assert mark_failed.await_count == 2
    assert mark_failed.await_args_list[0].kwargs["previous_analysis_status"] == "done"
    assert mark_failed.await_args_list[1].kwargs["previous_analysis_status"] == "failed"


@pytest.mark.asyncio
async def test_batch_submit_idempotent_failed_replay_preserves_failure_contract(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    monkeypatch.setattr(
        module.analyzer_db,
        "preview_batch_analyzer_candidates",
        AsyncMock(return_value=[_status_row(response_id=101, query_id=9001)]),
    )
    create_batch = AsyncMock(
        return_value={
            "success": True,
            "idempotent": True,
            "batch_id": "batch-enqueue-failed",
            "dry_run_id": "dry-enqueue-failed",
            "status": "failed",
            "submitted_count": 1,
            "accepted_count": 0,
            "failed_count": 1,
            "submitted_response_ids": [101],
            "accepted_response_ids": [],
            "failed_response_ids": [101],
            "items": [
                {
                    "item_id": 1,
                    "response_id": 101,
                    "run_id": 801,
                    "task_id": None,
                    "status": "failed",
                    "skipped_reason": "enqueue_failed",
                }
            ],
        }
    )
    monkeypatch.setattr(module.analyzer_db, "create_analyzer_batch_submission", create_batch)
    dispatch = Mock(return_value="task-should-not-run")
    monkeypatch.setattr(module, "dispatch_analyze_response", dispatch)

    resp = await client.post(
        "/admin/api/analyzer/responses/batch",
        json={
            "scope": {"response_ids": [101]},
            "mode": "missing_or_failed_only",
            "max_count": 10,
            "confirm": True,
            "idempotency_key": "batch-enqueue-failed",
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["accepted"] is False
    assert body["idempotent"] is True
    assert body["error"] == "analyzer_batch_enqueue_failed"
    assert body["submitted_response_ids"] == [101]
    assert body["accepted_response_ids"] == []
    assert body["failed_response_ids"] == [101]
    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_batch_submit_returns_dependency_gate_when_batch_tables_missing(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    readiness = AsyncMock(return_value=False)
    preview = AsyncMock(return_value=[_status_row(response_id=101)])
    create_batch = AsyncMock(return_value={"batch_id": "batch-not-ready"})
    monkeypatch.setattr(module.analyzer_db, "analyzer_batch_submit_ready", readiness, raising=False)
    monkeypatch.setattr(module.analyzer_db, "preview_batch_analyzer_candidates", preview)
    monkeypatch.setattr(module.analyzer_db, "create_analyzer_batch_submission", create_batch)
    dispatch = Mock(return_value="task-801")
    monkeypatch.setattr(module, "dispatch_analyze_response", dispatch)

    resp = await client.post(
        "/admin/api/analyzer/responses/batch",
        json={
            "scope": {"response_ids": [101]},
            "mode": "missing_or_failed_only",
            "max_count": 10,
            "confirm": True,
            "idempotency_key": "batch-not-ready",
        },
    )

    assert resp.status_code == 409
    assert resp.json()["error"] == "analyzer_batch_persistence_required"
    readiness.assert_awaited_once()
    preview.assert_not_awaited()
    create_batch.assert_not_awaited()
    dispatch.assert_not_called()


@pytest.mark.asyncio
async def test_batch_submit_requires_idempotency_key_for_confirmed_mutation(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    readiness = AsyncMock(return_value=True)
    preview = AsyncMock(return_value=[_status_row(response_id=101)])
    create_batch = AsyncMock(return_value={"batch_id": "batch-without-key"})
    monkeypatch.setattr(module.analyzer_db, "analyzer_batch_submit_ready", readiness, raising=False)
    monkeypatch.setattr(module.analyzer_db, "preview_batch_analyzer_candidates", preview)
    monkeypatch.setattr(module.analyzer_db, "create_analyzer_batch_submission", create_batch)

    resp = await client.post(
        "/admin/api/analyzer/responses/batch",
        json={
            "scope": {"response_ids": [101]},
            "mode": "missing_or_failed_only",
            "max_count": 10,
            "confirm": True,
        },
    )

    assert resp.status_code == 400
    assert resp.json()["error"] == "idempotency_key_required"
    readiness.assert_not_awaited()
    preview.assert_not_awaited()
    create_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_status_returns_durable_batch_after_refresh(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    monkeypatch.setattr(
        module.analyzer_db,
        "fetch_analyzer_batch_status",
        AsyncMock(
            return_value={
                "success": True,
                "batch_id": "batch-797",
                "status": "partial",
                "submitted_count": 2,
                "completed_count": 1,
                "failed_count": 1,
                "skipped_count": 3,
                "items": [
                    {"response_id": 101, "run_id": 801, "status": "done"},
                    {"response_id": 102, "run_id": 802, "status": "failed"},
                ],
            }
        ),
    )

    resp = await client.get("/admin/api/analyzer/batches/batch-797")

    assert resp.status_code == 200
    body = resp.json()
    assert body["batch_id"] == "batch-797"
    assert body["status"] == "partial"
    assert body["completed_count"] == 1
    assert body["failed_count"] == 1


@pytest.mark.asyncio
async def test_batch_submit_unauth_401(client) -> None:
    resp = await client.post(
        "/admin/api/analyzer/responses/batch",
        json={"scope": {"response_ids": [101]}, "confirm": True},
    )

    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_legacy_api_analyzer_batch_paths_keep_admin_auth_guard(client) -> None:
    submit = await client.post(
        "/api/analyzer/responses/batch",
        json={"scope": {"response_ids": [101]}, "confirm": True},
    )
    status = await client.get("/api/analyzer/batches/batch-797")

    assert submit.status_code == 401
    assert status.status_code == 401


@pytest.mark.asyncio
async def test_legacy_batch_submit_compat_preserves_admin_validation(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    readiness = AsyncMock(return_value=True)
    preview = AsyncMock(return_value=[_status_row(response_id=101)])
    create_batch = AsyncMock(return_value={"batch_id": "batch-without-key"})
    monkeypatch.setattr(module.analyzer_db, "analyzer_batch_submit_ready", readiness, raising=False)
    monkeypatch.setattr(module.analyzer_db, "preview_batch_analyzer_candidates", preview)
    monkeypatch.setattr(module.analyzer_db, "create_analyzer_batch_submission", create_batch)

    resp = await client.post(
        "/api/analyzer/responses/batch",
        json={
            "scope": {"response_ids": [101]},
            "mode": "missing_or_failed_only",
            "max_count": 10,
            "confirm": True,
        },
    )

    assert resp.status_code == 400
    assert resp.json()["error"] == "idempotency_key_required"
    readiness.assert_not_awaited()
    preview.assert_not_awaited()
    create_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_batch_status_compat_returns_admin_status_shape(
    client,
    admin_operator,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _admin_analyzer_router_module()
    fetch_status = AsyncMock(
        return_value={
            "success": True,
            "batch_id": "batch-797",
            "status": "partial",
            "submitted_count": 2,
            "completed_count": 1,
            "failed_count": 1,
            "skipped_count": 0,
            "items": [
                {"response_id": 101, "run_id": 801, "status": "done"},
                {"response_id": 102, "run_id": 802, "status": "failed"},
            ],
        }
    )
    monkeypatch.setattr(module.analyzer_db, "fetch_analyzer_batch_status", fetch_status)

    resp = await client.get("/api/analyzer/batches/batch-797")

    assert resp.status_code == 200
    body = resp.json()
    assert body["batch_id"] == "batch-797"
    assert body["status"] == "partial"
    assert body["completed_count"] == 1
    fetch_status.assert_awaited_once()


@pytest.mark.asyncio
async def test_db_queued_run_is_idempotent_by_key_and_active_status(
    db_session: AsyncSession,
) -> None:
    from app.admin.analyzer import db as analyzer_db

    first = await analyzer_db.create_or_get_queued_analyzer_run(
        db_session,
        response_id=79701,
        mode="missing_or_failed_only",
        trigger_source="admin_single",
        previous_analysis_status="failed",
        idempotency_key="retry-79701",
    )
    duplicate = await analyzer_db.create_or_get_queued_analyzer_run(
        db_session,
        response_id=79701,
        mode="missing_or_failed_only",
        trigger_source="admin_single",
        previous_analysis_status="queued",
        idempotency_key="retry-79701",
    )

    assert duplicate["idempotent"] is True
    assert duplicate["run_id"] == first["run_id"]
    assert await db_session.scalar(select(func.count(AnalyzerRun.id))) == 1

    await analyzer_db.mark_analyzer_run_enqueued(
        db_session,
        run_id=first["run_id"],
        task_id="task-79701",
    )
    run = await db_session.get(AnalyzerRun, first["run_id"])
    assert run is not None
    assert run.status == "queued"
    assert run.task_id == "task-79701"


@pytest.mark.asyncio
async def test_db_enqueue_failure_records_failed_run(
    db_session: AsyncSession,
) -> None:
    from app.admin.analyzer import db as analyzer_db

    queued = await analyzer_db.create_or_get_queued_analyzer_run(
        db_session,
        response_id=79702,
        mode="reanalyze_current",
        trigger_source="admin_single",
        previous_analysis_status="done",
        idempotency_key="reanalyze-79702",
    )

    await analyzer_db.mark_analyzer_run_enqueue_failed(
        db_session,
        run_id=queued["run_id"],
        previous_analysis_status="done",
    )

    run = await db_session.get(AnalyzerRun, queued["run_id"])
    assert run is not None
    assert run.status == "failed"
    assert run.failure_code == "enqueue_failed"
    assert run.completed_at is not None


@pytest.mark.asyncio
async def test_db_enqueue_failure_restores_prior_done_response_status(
    db_session: AsyncSession,
) -> None:
    from app.admin.analyzer import db as analyzer_db

    await db_session.execute(
        text("ALTER TABLE llm_responses ADD COLUMN analysis_status VARCHAR(32)")
    )
    await db_session.execute(
        text("INSERT INTO llm_responses (id, analysis_status) VALUES (79703, 'done')")
    )
    await db_session.commit()
    queued = await analyzer_db.create_or_get_queued_analyzer_run(
        db_session,
        response_id=79703,
        mode="reanalyze_current",
        trigger_source="admin_batch",
        previous_analysis_status="done",
        idempotency_key="reanalyze-79703",
    )

    await analyzer_db.mark_analyzer_run_enqueue_failed(
        db_session,
        run_id=queued["run_id"],
        previous_analysis_status="done",
    )

    status = await db_session.scalar(
        text("SELECT analysis_status FROM llm_responses WHERE id = 79703")
    )
    assert status == "done"


@pytest.mark.asyncio
async def test_db_batch_submission_persists_items_and_refreshes_status(
    db_session: AsyncSession,
) -> None:
    from app.admin.analyzer import db as analyzer_db

    normalized = {
        "scope": {"response_ids": [79710, 79711, 79712], "query_ids": [], "filters": {}},
        "mode": "missing_or_failed_only",
        "max_count": 10,
        "sample_limit": 10,
        "reason": "operator batch",
        "idempotency_key": "batch-797",
        "confirm": True,
    }
    preview = {
        "success": True,
        "dry_run": True,
        "dry_run_id": "dry-797",
        "mode": "missing_or_failed_only",
        "eligible_response_ids": [79710, 79711],
        "will_enqueue_count": 2,
        "skipped_counts": {"already_done": 1},
        "skipped_samples": {
            "already_done": [{"response_id": 79712, "query_id": 99712, "reason": "already_done"}]
        },
        "_candidate_rows": [
            {"response_id": 79710, "query_id": 99710},
            {"response_id": 79711, "query_id": 99711},
            {"response_id": 79712, "query_id": 99712},
        ],
    }

    batch = await analyzer_db.create_analyzer_batch_submission(
        db_session,
        normalized=normalized,
        preview=preview,
        operator_id="admin-797",
    )

    assert batch["status"] == "queued"
    assert batch["submitted_response_ids"] == [79710, 79711]
    assert batch["submitted_count"] == 2
    assert batch["skipped_count"] == 1
    assert await db_session.scalar(select(func.count(AnalyzerBatch.batch_id))) == 1
    assert await db_session.scalar(select(func.count(AnalyzerBatchItem.id))) == 3
    assert await db_session.scalar(select(func.count(AnalyzerRun.id))) == 2

    for item in batch["items"]:
        if item["run_id"]:
            run = await db_session.get(AnalyzerRun, item["run_id"])
            assert run is not None
            run.status = "done" if item["response_id"] == 79710 else "failed"
    await db_session.commit()

    refreshed = await analyzer_db.refresh_analyzer_batch_status(
        db_session,
        batch["batch_id"],
    )

    assert refreshed is not None
    assert refreshed["status"] == "partial"
    assert refreshed["completed_count"] == 1
    assert refreshed["failed_count"] == 1
    assert refreshed["skipped_count"] == 1
    by_response_id = {
        item["response_id"]: item
        for item in refreshed["items"]
        if item.get("response_id") in {79710, 79711}
    }
    assert by_response_id[79710]["status"] == "done"
    assert by_response_id[79711]["status"] == "failed"


@pytest.mark.asyncio
async def test_db_batch_idempotency_reuses_terminal_key_without_new_work(
    db_session: AsyncSession,
) -> None:
    from app.admin.analyzer import db as analyzer_db

    normalized = {
        "scope": {"response_ids": [79720], "query_ids": [], "filters": {}},
        "mode": "missing_or_failed_only",
        "max_count": 10,
        "sample_limit": 10,
        "reason": "operator batch",
        "idempotency_key": "batch-terminal-797",
        "confirm": True,
    }
    preview = {
        "success": True,
        "dry_run": True,
        "dry_run_id": "dry-terminal-797-a",
        "mode": "missing_or_failed_only",
        "eligible_response_ids": [79720],
        "will_enqueue_count": 1,
        "skipped_counts": {},
        "skipped_samples": {},
        "_candidate_rows": [{"response_id": 79720, "query_id": 99720}],
    }
    first = await analyzer_db.create_analyzer_batch_submission(
        db_session,
        normalized=normalized,
        preview=preview,
        operator_id="admin-797",
    )
    batch_row = await db_session.get(AnalyzerBatch, first["batch_id"])
    assert batch_row is not None
    batch_row.status = "failed"
    await db_session.commit()

    second = await analyzer_db.create_analyzer_batch_submission(
        db_session,
        normalized=normalized,
        preview={**preview, "dry_run_id": "dry-terminal-797-b"},
        operator_id="admin-797",
    )

    assert second["idempotent"] is True
    assert second["batch_id"] == first["batch_id"]
    assert await db_session.scalar(select(func.count(AnalyzerBatch.batch_id))) == 1
    assert await db_session.scalar(select(func.count(AnalyzerRun.id))) == 1


@pytest.mark.asyncio
async def test_db_batch_submission_reused_active_run_does_not_require_dispatch(
    db_session: AsyncSession,
) -> None:
    from app.admin.analyzer import db as analyzer_db

    existing_run = AnalyzerRun(
        response_id=79730,
        status="queued",
        task_id="task-existing-79730",
        trigger_source="admin_batch",
    )
    db_session.add(existing_run)
    await db_session.commit()
    await db_session.refresh(existing_run)

    normalized = {
        "scope": {"response_ids": [79730], "query_ids": [], "filters": {}},
        "mode": "missing_or_failed_only",
        "max_count": 10,
        "sample_limit": 10,
        "reason": "operator batch",
        "idempotency_key": "batch-reuse-run-797",
        "confirm": True,
    }
    preview = {
        "success": True,
        "dry_run": True,
        "dry_run_id": "dry-reuse-run-797",
        "mode": "missing_or_failed_only",
        "eligible_response_ids": [79730],
        "will_enqueue_count": 1,
        "skipped_counts": {},
        "skipped_samples": {},
        "_candidate_rows": [{"response_id": 79730, "query_id": 99730}],
    }

    batch = await analyzer_db.create_analyzer_batch_submission(
        db_session,
        normalized=normalized,
        preview=preview,
        operator_id="admin-797",
    )

    assert batch["items"][0]["run_id"] == existing_run.id
    assert batch["items"][0]["task_id"] == "task-existing-79730"
    assert batch["items"][0]["reused_active_run"] is True
    assert batch["items"][0]["dispatch_required"] is False
    assert await db_session.scalar(select(func.count(AnalyzerRun.id))) == 1


@pytest.mark.asyncio
async def test_db_batch_submission_reused_queued_run_without_task_requires_dispatch(
    db_session: AsyncSession,
) -> None:
    from app.admin.analyzer import db as analyzer_db

    existing_run = AnalyzerRun(
        response_id=79731,
        status="queued",
        task_id=None,
        trigger_source="admin_batch",
    )
    db_session.add(existing_run)
    await db_session.commit()
    await db_session.refresh(existing_run)

    normalized = {
        "scope": {"response_ids": [79731], "query_ids": [], "filters": {}},
        "mode": "missing_or_failed_only",
        "max_count": 10,
        "sample_limit": 10,
        "reason": "operator batch",
        "idempotency_key": "batch-reuse-run-no-task-797",
        "confirm": True,
    }
    preview = {
        "success": True,
        "dry_run": True,
        "dry_run_id": "dry-reuse-run-no-task-797",
        "mode": "missing_or_failed_only",
        "eligible_response_ids": [79731],
        "will_enqueue_count": 1,
        "skipped_counts": {},
        "skipped_samples": {},
        "_candidate_rows": [{"response_id": 79731, "query_id": 99731}],
    }

    batch = await analyzer_db.create_analyzer_batch_submission(
        db_session,
        normalized=normalized,
        preview=preview,
        operator_id="admin-797",
    )

    assert batch["items"][0]["run_id"] == existing_run.id
    assert batch["items"][0]["task_id"] is None
    assert batch["items"][0]["reused_active_run"] is True
    assert batch["items"][0]["dispatch_required"] is True
    assert await db_session.scalar(select(func.count(AnalyzerRun.id))) == 1


@pytest.mark.asyncio
async def test_db_unique_constraints_prevent_duplicate_idempotency_and_active_runs(
    db_session: AsyncSession,
) -> None:
    db_session.add_all(
        [
            AnalyzerRun(
                response_id=79740,
                status="failed",
                trigger_source="admin_single",
                idempotency_key="single-unique-79740",
            ),
            AnalyzerRun(
                response_id=79740,
                status="failed",
                trigger_source="admin_single",
                idempotency_key="single-unique-79740",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    db_session.add_all(
        [
            AnalyzerRun(response_id=79741, status="queued", trigger_source="admin_single"),
            AnalyzerRun(response_id=79741, status="queued", trigger_source="pipeline_worker"),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()

    db_session.add_all(
        [
            AnalyzerBatch(
                batch_id="batch-unique-a-79742",
                mode="missing_or_failed_only",
                status="failed",
                idempotency_key="batch-unique-79742",
                dry_run_id="dry-unique-a-79742",
            ),
            AnalyzerBatch(
                batch_id="batch-unique-b-79742",
                mode="missing_or_failed_only",
                status="failed",
                idempotency_key="batch-unique-79742",
                dry_run_id="dry-unique-b-79742",
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_db_dispatch_claim_allows_only_one_redispatch_for_unenqueued_run(
    db_session: AsyncSession,
) -> None:
    from app.admin.analyzer import db as analyzer_db

    existing_run = AnalyzerRun(
        response_id=79750,
        status="queued",
        task_id=None,
        trigger_source="admin_single",
    )
    db_session.add(existing_run)
    await db_session.commit()
    await db_session.refresh(existing_run)

    first = await analyzer_db.claim_analyzer_run_for_dispatch(db_session, run_id=existing_run.id)
    second = await analyzer_db.claim_analyzer_run_for_dispatch(db_session, run_id=existing_run.id)

    assert first["claimed"] is True
    assert second["claimed"] is False
    assert second["reason"] == "already_claimed"
    run = await db_session.get(AnalyzerRun, existing_run.id)
    assert run is not None
    assert run.task_id is None
    assert run.dispatch_claim_token
    assert run.dispatch_claimed_at is not None

    await analyzer_db.mark_analyzer_run_enqueued(
        db_session,
        run_id=existing_run.id,
        task_id="task-79750",
    )
    run = await db_session.get(AnalyzerRun, existing_run.id)
    assert run is not None
    assert run.task_id == "task-79750"
    assert run.dispatch_claim_token is None
    assert run.dispatch_claimed_at is None


@pytest.mark.asyncio
async def test_db_batch_submit_ready_requires_all_written_columns(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.admin.analyzer import db as analyzer_db

    async def _exists(_session: AsyncSession, _name: str) -> bool:
        return True

    async def _columns(_session: AsyncSession, name: str) -> set[str]:
        if name == "analyzer_runs":
            return set(analyzer_db.REQUIRED_ANALYZER_RUN_SUBMIT_COLUMNS)
        if name == "analyzer_batches":
            return set(analyzer_db.REQUIRED_ANALYZER_BATCH_COLUMNS) - {
                "submitted_response_ids_json"
            }
        if name == "analyzer_batch_items":
            return set(analyzer_db.REQUIRED_ANALYZER_BATCH_ITEM_COLUMNS)
        return set()

    monkeypatch.setattr(analyzer_db, "_table_exists", _exists)
    monkeypatch.setattr(analyzer_db, "_table_columns", _columns)

    assert await analyzer_db.analyzer_batch_submit_ready(db_session) is False


@pytest.mark.asyncio
async def test_db_batch_submit_ready_requires_unique_indexes(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.admin.analyzer import db as analyzer_db

    async def _exists(_session: AsyncSession, _name: str) -> bool:
        return True

    async def _columns(_session: AsyncSession, name: str) -> set[str]:
        if name == "analyzer_runs":
            return set(analyzer_db.REQUIRED_ANALYZER_RUN_SUBMIT_COLUMNS)
        if name == "analyzer_batches":
            return set(analyzer_db.REQUIRED_ANALYZER_BATCH_COLUMNS)
        if name == "analyzer_batch_items":
            return set(analyzer_db.REQUIRED_ANALYZER_BATCH_ITEM_COLUMNS)
        return set()

    async def _indexes_ready(_session: AsyncSession, _required_indexes: set[str]) -> bool:
        return False

    monkeypatch.setattr(analyzer_db, "_table_exists", _exists)
    monkeypatch.setattr(analyzer_db, "_table_columns", _columns)
    monkeypatch.setattr(analyzer_db, "_submit_unique_indexes_ready", _indexes_ready)

    assert await analyzer_db.analyzer_batch_submit_ready(db_session) is False
