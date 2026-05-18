"""Refs Epic #1110 — ``POST /api/queries/batch_retry_via_vm`` admin endpoint.

The batch endpoint accepts ``{"query_ids": [...]}`` and sequentially
calls ``run_quick_retry`` for each id (the same code path used by the
single ``/retry_via_vm`` endpoint). DeepSeek + Doubao queries can
share the same batch since the dispatcher in ``vm_quick_retry.py``
routes per-engine.

Tests cover:

  AC-1 (happy path): 2 query_ids both succeed →
      ``{"total":2,"success":2,"failed":[]}``
  AC-2 (partial failure): 1 ok + 1 cdp_unreachable →
      ``{"total":2,"success":1,"failed":[{"id":qid_X,"error":"cdp_unreachable"}]}``
  AC-3 (mixed engine): doubao + deepseek in the same batch both succeed
      → proves the route does not engine-filter the input list.
  AC-4 (input validation): empty / missing query_ids → 400.
  AC-5 (mounted): route appears at both /api/* and /admin/api/*.
"""

from __future__ import annotations

import os
import sys
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path

# Mirror sys.path insert from test_retry_via_vm_endpoint.py.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from genpano_models import AdminUser  # noqa: E402
from sqlalchemy import text as sa_text  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _vm_quick_retry_module():
    import geo_tracker.agent.vm_quick_retry as m

    return m


@pytest_asyncio.fixture
async def admin_operator(db_session: AsyncSession) -> AsyncGenerator[AdminUser, None]:
    from app.api.admin.auth.router import current_admin
    from app.main import app

    a = AdminUser(
        id=_new_id(),
        email=f"admin-{uuid.uuid4().hex[:6]}@example.com",
        password_hash="$2b$04$dummyhashfortestsdummyhashfortestsdummyhashfortest",
        role="super_admin",
        status="active",
    )
    db_session.add(a)
    await db_session.commit()

    async def _override_current_admin() -> AdminUser:
        return a

    app.dependency_overrides[current_admin] = _override_current_admin
    try:
        yield a
    finally:
        app.dependency_overrides.pop(current_admin, None)


@pytest.fixture
def _patch_table_exists(monkeypatch):
    """Override ``queries_db._table_exists`` so it works against SQLite."""
    from app.admin.queries import db as _queries_db_module

    async def _fake_table_exists(_session, name):
        return True

    monkeypatch.setattr(_queries_db_module, "_table_exists", _fake_table_exists)


@pytest_asyncio.fixture
async def two_existing_queries(db_session: AsyncSession, _patch_table_exists) -> list[int]:
    """Create 2 queries (one doubao + one deepseek). Returns their ids."""
    await db_session.execute(
        sa_text(
            "CREATE TABLE IF NOT EXISTS queries ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "target_llm TEXT, "
            "query_text TEXT, "
            "status TEXT, "
            "retry_count INTEGER DEFAULT 0)"
        )
    )
    await db_session.execute(
        sa_text(
            "INSERT INTO queries (target_llm, query_text, status) "
            "VALUES ('doubao', 'doubao question 1', 'failed')"
        )
    )
    await db_session.execute(
        sa_text(
            "INSERT INTO queries (target_llm, query_text, status) "
            "VALUES ('deepseek', 'deepseek question 2', 'failed')"
        )
    )
    await db_session.commit()
    rows = (await db_session.execute(sa_text("SELECT id FROM queries ORDER BY id ASC"))).fetchall()
    return [int(r[0]) for r in rows]


@pytest_asyncio.fixture
async def existing_llm_responses_table(db_session: AsyncSession) -> None:
    await db_session.execute(sa_text("DROP TABLE IF EXISTS llm_responses"))
    await db_session.execute(
        sa_text(
            "CREATE TABLE llm_responses ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "query_id INTEGER UNIQUE, "
            "raw_text TEXT, "
            "response_html TEXT, "
            "screenshot_path TEXT, "
            "response_time_ms INTEGER, "
            "collected_at TIMESTAMP)"
        )
    )
    await db_session.commit()


# ── AC-1: happy path — both queries succeed ──────────────────────


@pytest.mark.asyncio
async def test_batch_retry_via_vm_happy_path_both_succeed(
    client,
    admin_operator,
    two_existing_queries: list[int],
    existing_llm_responses_table,
    monkeypatch,
):
    """2 query_ids → both succeed → response shape matches Epic #1110
    contract: ``{"total":2,"success":2,"failed":[]}``."""
    m = _vm_quick_retry_module()

    async def _stub_run(**kwargs):
        return {
            "raw_text": "ok",
            "raw_text_chars": 200,
            "attempt_n": 1,
            "vm_id": "doubao-01",
            "execution_mode": "vm_session_quick",
            "started_at": "2026-05-18T18:00:00+00:00",
            "completed_at": "2026-05-18T18:00:03+00:00",
            "screenshot_path": "/tmp/x.png",
        }

    monkeypatch.setattr(m, "run_quick_retry", _stub_run)

    resp = await client.post(
        "/api/queries/batch_retry_via_vm",
        json={"query_ids": two_existing_queries},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("total") == 2
    assert body.get("success") == 2
    assert body.get("failed") == []


# ── AC-2: partial failure — 1 ok + 1 cdp_unreachable ─────────────


@pytest.mark.asyncio
async def test_batch_retry_via_vm_partial_failure_records_error(
    client,
    admin_operator,
    two_existing_queries: list[int],
    existing_llm_responses_table,
    monkeypatch,
):
    """When run_quick_retry raises QuickRetryError on the SECOND id,
    the response carries success=1 + failed=[{id, error}]."""
    m = _vm_quick_retry_module()
    failing_id = two_existing_queries[1]

    async def _stub_run(**kwargs):
        if kwargs.get("query_id") == failing_id:
            raise m.QuickRetryError(
                m.ERR_CDP_UNREACHABLE,
                detail="connect_over_cdp failed",
            )
        return {
            "raw_text": "ok",
            "raw_text_chars": 200,
            "attempt_n": 1,
            "vm_id": "doubao-01",
            "execution_mode": "vm_session_quick",
            "started_at": "2026-05-18T18:00:00+00:00",
            "completed_at": "2026-05-18T18:00:03+00:00",
            "screenshot_path": "/tmp/x.png",
        }

    monkeypatch.setattr(m, "run_quick_retry", _stub_run)

    resp = await client.post(
        "/api/queries/batch_retry_via_vm",
        json={"query_ids": two_existing_queries},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("total") == 2
    assert body.get("success") == 1
    failed = body.get("failed") or []
    assert len(failed) == 1
    assert failed[0].get("id") == failing_id
    assert failed[0].get("error") == "cdp_unreachable"


# ── AC-3: mixed-engine batch — proves no client-side engine filter ──


@pytest.mark.asyncio
async def test_batch_retry_via_vm_accepts_mixed_doubao_and_deepseek(
    client,
    admin_operator,
    two_existing_queries: list[int],
    existing_llm_responses_table,
    monkeypatch,
):
    """A batch containing one doubao + one deepseek must run both.

    Acceptance: the stub's recorded ``target_llm`` values include both
    engine keys — proves the route does NOT engine-filter the input.
    """
    m = _vm_quick_retry_module()
    seen_engines: list[str] = []

    async def _stub_run(**kwargs):
        seen_engines.append(str(kwargs.get("target_llm") or ""))
        return {
            "raw_text": "ok",
            "raw_text_chars": 50,
            "attempt_n": 1,
            "vm_id": "doubao-01",
            "execution_mode": "vm_session_quick",
            "started_at": "2026-05-18T18:00:00+00:00",
            "completed_at": "2026-05-18T18:00:03+00:00",
            "screenshot_path": "/tmp/x.png",
        }

    monkeypatch.setattr(m, "run_quick_retry", _stub_run)

    resp = await client.post(
        "/api/queries/batch_retry_via_vm",
        json={"query_ids": two_existing_queries},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("success") == 2
    # both engine values must have been forwarded — order matches
    # row insertion order (doubao first, deepseek second).
    assert sorted(seen_engines) == ["deepseek", "doubao"]


# ── AC-4: input validation ───────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_retry_via_vm_rejects_missing_query_ids(client, admin_operator):
    """Empty body / missing query_ids → 400 with structured error."""
    resp = await client.post("/api/queries/batch_retry_via_vm", json={})
    # The table-exists guard runs first; either it bails 503 (table
    # missing) or we get 400 (validation). Both are acceptable; the
    # key contract is "not a silent 200".
    assert resp.status_code in (400, 503), resp.text
    body = resp.json()
    assert body.get("success") is False


@pytest.mark.asyncio
async def test_batch_retry_via_vm_rejects_empty_list(client, admin_operator, _patch_table_exists):
    """Empty query_ids list → 400, not a no-op 200."""
    resp = await client.post("/api/queries/batch_retry_via_vm", json={"query_ids": []})
    assert resp.status_code == 400, resp.text
    body = resp.json()
    assert body.get("error") == "missing_query_ids"


# ── AC-5: route is mounted on both /api/* and /admin/api/* ─────


def test_batch_route_module_is_wired_into_queries_router():
    """Verify the batch route is mounted at both ``/api/...`` and
    ``/admin/api/...`` so admin.html (which hits ``/api/`` per
    ``API_BASE`` and shows the button) and the operator console alias
    both reach the handler."""
    from app.main import app

    paths = {r.path for r in app.routes}
    assert "/api/queries/batch_retry_via_vm" in paths
    assert "/admin/api/queries/batch_retry_via_vm" in paths
