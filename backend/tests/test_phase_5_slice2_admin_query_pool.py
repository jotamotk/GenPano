"""Phase 5 slice 2 — admin query_pool runs list + candidate delete.

All routes use real backend ORM models — runs end-to-end against sqlite.
Also covers the `/admin/api/v1/pipeline/query-pool/*` legacy alias.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from genpano_models import (
    AdminAuditLog,
    AdminUser,
    QueryGenerationCandidate,
    QueryGenerationRun,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest_asyncio.fixture
async def admin_operator(
    db_session: AsyncSession,
) -> AsyncGenerator[AdminUser, None]:
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


@pytest_asyncio.fixture
async def run(db_session: AsyncSession, admin_operator: AdminUser) -> QueryGenerationRun:
    r = QueryGenerationRun(
        id=_new_id(),
        admin_id=admin_operator.id,
        status="completed",
        request_config={},
        prompt_ids=["p1"],
        segment_ids_selected=["s1"],
        profiles_per_prompt=2,
        candidates_estimated=50,
        candidates_assembled=10,
        started_at=_now() - timedelta(seconds=15),
        completed_at=_now(),
    )
    db_session.add(r)
    await db_session.commit()
    return r


def _candidate(*, run_id: str, seq: int = 1) -> QueryGenerationCandidate:
    return QueryGenerationCandidate(
        id=_new_id(),
        run_id=run_id,
        candidate_seq=seq,
        prompt_id="p1",
        segment_id="s1",
        profile_id="prof1",
        rendered_query=f"q-{seq}",
        render_hash=f"hash{seq}",
        generation_method="llm",
        candidate_status="candidate",
    )


# ── GET /runs ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_runs_unauth_401(client):
    resp = await client.get("/api/admin/query-pool/runs")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_runs_returns_recent(client, admin_operator, db_session: AsyncSession):
    """Most-recent-first; respects limit."""
    for i in range(3):
        db_session.add(
            QueryGenerationRun(
                id=_new_id(),
                admin_id=admin_operator.id,
                status="completed",
                request_config={},
                started_at=_now() - timedelta(seconds=i + 1),
                completed_at=_now(),
            )
        )
    await db_session.commit()

    resp = await client.get("/api/admin/query-pool/runs?limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["rows"]) == 2


@pytest.mark.asyncio
async def test_list_runs_via_legacy_alias(client, admin_operator, run):
    resp = await client.get("/admin/api/v1/pipeline/query-pool/runs")
    assert resp.status_code == 200
    ids = {r["id"] for r in resp.json()["rows"]}
    assert run.id in ids


# ── DELETE /candidates/{id} ───────────────────────────────────


@pytest.mark.asyncio
async def test_delete_unauth_401(client):
    resp = await client.delete("/api/admin/query-pool/candidates/x")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_unknown_404(client, admin_operator):
    resp = await client.delete("/api/admin/query-pool/candidates/no-such-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_existing_emits_audit(
    client, admin_operator, db_session: AsyncSession, run: QueryGenerationRun
):
    cand = _candidate(run_id=run.id)
    db_session.add(cand)
    await db_session.commit()

    resp = await client.delete(f"/api/admin/query-pool/candidates/{cand.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["deleted"] == [cand.id]

    # candidate row gone
    after = (
        await db_session.execute(
            select(QueryGenerationCandidate).where(QueryGenerationCandidate.id == cand.id)
        )
    ).scalar_one_or_none()
    assert after is None

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(AdminAuditLog.action == "query_pool_candidate_delete")
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "med"


# ── POST /candidates/bulk-delete ──────────────────────────────


@pytest.mark.asyncio
async def test_bulk_delete_missing_ids_422(client, admin_operator):
    resp = await client.post("/api/admin/query-pool/candidates/bulk-delete", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_delete_too_many_422(client, admin_operator):
    resp = await client.post(
        "/api/admin/query-pool/candidates/bulk-delete",
        json={"candidate_ids": [f"id-{i}" for i in range(1001)]},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_delete_partial_missing(
    client, admin_operator, db_session: AsyncSession, run: QueryGenerationRun
):
    cands = [_candidate(run_id=run.id, seq=i + 1) for i in range(2)]
    for c in cands:
        db_session.add(c)
    await db_session.commit()

    resp = await client.post(
        "/api/admin/query-pool/candidates/bulk-delete",
        json={"candidate_ids": [cands[0].id, cands[1].id, "no-such-id"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert sorted(body["deleted"]) == sorted([cands[0].id, cands[1].id])
    assert body["missing"] == ["no-such-id"]


@pytest.mark.asyncio
async def test_bulk_delete_via_legacy_alias(
    client, admin_operator, db_session: AsyncSession, run: QueryGenerationRun
):
    cand = _candidate(run_id=run.id)
    db_session.add(cand)
    await db_session.commit()

    resp = await client.post(
        "/admin/api/v1/pipeline/query-pool/candidates/bulk-delete",
        json={"candidate_ids": [cand.id]},
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == [cand.id]


# ── audit gate ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice2():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
