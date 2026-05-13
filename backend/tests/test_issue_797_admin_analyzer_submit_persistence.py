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
from sqlalchemy import func, select
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
async def test_legacy_api_analyzer_paths_do_not_gain_admin_batch_mutations(client) -> None:
    submit = await client.post(
        "/api/analyzer/responses/batch",
        json={"scope": {"response_ids": [101]}, "confirm": True},
    )
    status = await client.get("/api/analyzer/batches/batch-797")

    assert submit.status_code == 404
    assert status.status_code == 404


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
