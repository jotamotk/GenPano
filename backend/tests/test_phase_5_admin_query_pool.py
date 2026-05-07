"""Phase 5 (slice 1) — admin query_pool candidate review + run lifecycle.

Both ``QueryGenerationCandidate`` and ``QueryGenerationRun`` are real
backend ORM models, so this file runs end-to-end against sqlite — no
upstream stub mocking needed.

Also exercises the legacy ``/admin/api/v1/pipeline/query-pool/*`` alias
mount to confirm the SPA's older callers keep working during Phase 5.
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
        request_config={"max_candidates": 100},
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


def _candidate(
    *,
    run_id: str,
    seq: int = 1,
    status: str = "candidate",
    text: str = "test query",
) -> QueryGenerationCandidate:
    return QueryGenerationCandidate(
        id=_new_id(),
        run_id=run_id,
        candidate_seq=seq,
        prompt_id="p1",
        segment_id="s1",
        profile_id="prof1",
        rendered_query=text,
        render_hash=f"hash{seq}",
        generation_method="llm",
        candidate_status=status,
    )


# ── single review ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_review_unauth_401(client):
    resp = await client.post(
        "/api/admin/query-pool/candidates/x/review",
        json={"status": "review"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_review_to_review_status(
    client, admin_operator, db_session: AsyncSession, run: QueryGenerationRun
):
    cand = _candidate(run_id=run.id)
    db_session.add(cand)
    await db_session.commit()

    resp = await client.post(
        f"/api/admin/query-pool/candidates/{cand.id}/review",
        json={"status": "review", "reason": "needs human eyes"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["candidate"]["candidate_status"] == "review"

    await db_session.refresh(cand)
    assert cand.candidate_status == "review"
    assert cand.reviewed_by == admin_operator.id
    assert cand.review_reason == "needs human eyes"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "query_pool_candidate_review",
                    AdminAuditLog.resource_id == cand.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1
    assert audit[0].severity == "med"


@pytest.mark.asyncio
async def test_review_promote_to_ready(
    client, admin_operator, db_session: AsyncSession, run: QueryGenerationRun
):
    cand = _candidate(run_id=run.id, status="review")
    db_session.add(cand)
    await db_session.commit()

    resp = await client.post(
        f"/api/admin/query-pool/candidates/{cand.id}/review",
        json={"status": "ready"},
    )
    assert resp.status_code == 200
    assert resp.json()["candidate"]["candidate_status"] == "ready"


@pytest.mark.asyncio
async def test_review_invalid_status_422(
    client, admin_operator, db_session: AsyncSession, run: QueryGenerationRun
):
    cand = _candidate(run_id=run.id)
    db_session.add(cand)
    await db_session.commit()

    resp = await client.post(
        f"/api/admin/query-pool/candidates/{cand.id}/review",
        json={"status": "approved"},  # not in {candidate, review, ready}
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_review_unknown_404(client, admin_operator):
    resp = await client.post(
        "/api/admin/query-pool/candidates/no-such-id/review",
        json={"status": "review"},
    )
    assert resp.status_code == 404


# ── bulk review ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_review_all_succeed(
    client, admin_operator, db_session: AsyncSession, run: QueryGenerationRun
):
    cands = [_candidate(run_id=run.id, seq=i + 1) for i in range(3)]
    for c in cands:
        db_session.add(c)
    await db_session.commit()

    resp = await client.post(
        "/api/admin/query-pool/candidates/bulk-review",
        json={
            "candidate_ids": [c.id for c in cands],
            "status": "review",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["updated"]) == 3
    assert body["missing"] == []


@pytest.mark.asyncio
async def test_bulk_review_partial_missing(
    client, admin_operator, db_session: AsyncSession, run: QueryGenerationRun
):
    cand = _candidate(run_id=run.id)
    db_session.add(cand)
    await db_session.commit()

    resp = await client.post(
        "/api/admin/query-pool/candidates/bulk-review",
        json={"candidate_ids": [cand.id, "no-such-id"], "status": "ready"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["updated"]) == 1
    assert body["missing"] == ["no-such-id"]


@pytest.mark.asyncio
async def test_bulk_review_too_many_422(client, admin_operator):
    resp = await client.post(
        "/api/admin/query-pool/candidates/bulk-review",
        json={"candidate_ids": [f"id-{i}" for i in range(1001)], "status": "review"},
    )
    assert resp.status_code == 422


# ── runs ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_run_returns_run(client, admin_operator, run: QueryGenerationRun):
    resp = await client.get(f"/api/admin/query-pool/runs/{run.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run"]["id"] == run.id
    assert body["run"]["status"] == "completed"


@pytest.mark.asyncio
async def test_get_run_marks_stale_running_as_failed(
    client, admin_operator, db_session: AsyncSession
):
    very_old = _now() - timedelta(hours=8)
    r = QueryGenerationRun(
        id=_new_id(),
        admin_id=admin_operator.id,
        status="running",
        request_config={},
        started_at=very_old,
        created_at=very_old,
        updated_at=very_old,
    )
    db_session.add(r)
    await db_session.commit()

    resp = await client.get(f"/api/admin/query-pool/runs/{r.id}")
    assert resp.status_code == 200
    assert resp.json()["run"]["status"] == "failed"
    assert resp.json()["run"]["llm_error"] == "query_pool_run_timeout"


@pytest.mark.asyncio
async def test_get_run_unknown_404(client, admin_operator):
    resp = await client.get("/api/admin/query-pool/runs/no-such-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_stop_run_cancels_and_audits(client, admin_operator, db_session: AsyncSession):
    r = QueryGenerationRun(
        id=_new_id(),
        admin_id=admin_operator.id,
        status="running",
        request_config={},
        started_at=_now(),
    )
    db_session.add(r)
    await db_session.commit()

    resp = await client.post(f"/api/admin/query-pool/runs/{r.id}/stop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run"]["status"] == "cancelled"

    audit = list(
        (
            await db_session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.action == "query_pool_run_cancelled",
                    AdminAuditLog.resource_id == r.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(audit) == 1


@pytest.mark.asyncio
async def test_stop_run_already_finalized_no_op(client, admin_operator, run: QueryGenerationRun):
    resp = await client.post(f"/api/admin/query-pool/runs/{run.id}/stop")
    assert resp.status_code == 200
    body = resp.json()
    assert body["already_finalized"] is True


@pytest.mark.asyncio
async def test_stop_run_unknown_404(client, admin_operator):
    resp = await client.post("/api/admin/query-pool/runs/no-such-id/stop")
    assert resp.status_code == 404


# ── /admin/api/v1/pipeline/query-pool/* alias ────────────────


@pytest.mark.asyncio
async def test_legacy_alias_review(
    client, admin_operator, db_session: AsyncSession, run: QueryGenerationRun
):
    """The /admin/api/v1/pipeline/query-pool/* alias must hit the same
    handler as /api/admin/query-pool/*. Used by some still-Flask SPA
    callers in admin.html."""
    cand = _candidate(run_id=run.id)
    db_session.add(cand)
    await db_session.commit()

    resp = await client.post(
        f"/admin/api/v1/pipeline/query-pool/candidates/{cand.id}/review",
        json={"status": "ready"},
    )
    assert resp.status_code == 200
    assert resp.json()["candidate"]["candidate_status"] == "ready"


@pytest.mark.asyncio
async def test_legacy_alias_run_get(client, admin_operator, run: QueryGenerationRun):
    resp = await client.get(f"/admin/api/v1/pipeline/query-pool/runs/{run.id}")
    assert resp.status_code == 200
    assert resp.json()["run"]["id"] == run.id


# ── audit gate ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_phase_5_routes():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
