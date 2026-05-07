"""Phase 5 slice 3b-ii — Query Pool writer helper tests.

Tests run end-to-end against the sqlite test fixture: ``query_generation_runs``
and ``query_generation_candidates`` are both real ORM models in
``Base.metadata``, so writer ops execute as ORM inserts/updates without
needing a postgres-only feature.

Coverage:
- insert_query_pool_run_completed: inserts run row + child candidates,
  status='completed', counts populated, candidates linked
- insert_query_pool_candidates: child rows materialise as ORM objects
- update_query_pool_run_progress: streams counters; no-op on terminal runs
- start_query_pool_assembly_run: 'running' row + preflight_summary mutated
  (candidate_ready=0, scheduler_intake='running')
- finalize_query_pool_run: 'running' → 'completed'; respects 'cancelled'
- mark_query_pool_run_failed: stamps llm_error; respects 'cancelled'
- mark_query_pool_run_cancelled: preserves prior completed_at via no-op
- complete_query_pool_run: insert_candidates + finalize composed
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC

import pytest
from genpano_models import QueryGenerationCandidate, QueryGenerationRun
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.query_pool import db as qp_db

os.environ.setdefault("USER_JWT_SECRET", "x" * 64)


def _new_id() -> str:
    return str(uuid.uuid4())


def _summary(*, raw=10, ready=4, model="gpt-4"):
    return {
        "raw_candidates_estimated": raw,
        "candidate_ready": ready,
        "scheduler_intake": "ready" if ready else "blocked",
        "llm_model": model,
        "llm_usage": {"tokens": 12},
        "render_pass_rate": 0.5 if ready else 0,
        "by_reason": {},
    }


def _candidate(seq, *, prompt_id="p1", segment_id="s1"):
    return {
        "id": _new_id(),
        "candidate_seq": seq,
        "prompt_id": prompt_id,
        "segment_id": segment_id,
        "profile_id": "prof1",
        "rendered_query": f"q-{seq}",
        "render_hash": f"hash{seq}",
        "candidate_status": "candidate",
        "generation_method": "llm",
        "llm_model": "gpt-4",
        "llm_usage": {"tokens": 12},
    }


# ── insert_query_pool_run_completed ──────────────────────────


@pytest.mark.asyncio
async def test_insert_completed_writes_run_and_candidates(db_session: AsyncSession):
    config = {
        "profiles_per_prompt": 2,
        "desired_engine_policy": "inherit",
        "engine_panel_id": None,
        "max_candidates": 100,
        "overflow_policy": "split",
    }
    selection = {"mode": "explicit", "prompt_ids": ["p1", "p2"]}
    candidates = [_candidate(1), _candidate(2, prompt_id="p2")]
    summary = _summary(raw=2, ready=2)

    run_id = await qp_db.insert_query_pool_run_completed(
        db_session,
        admin_id="admin-1",
        selection=selection,
        config=config,
        candidates=candidates,
        preflight_summary=summary,
    )

    run = await db_session.get(QueryGenerationRun, run_id)
    assert run is not None
    assert run.status == "completed"
    assert run.candidates_assembled == 2
    assert run.candidates_estimated == 2
    assert run.llm_model == "gpt-4"
    assert run.preflight_summary["candidate_ready"] == 2

    rows = list(
        (
            await db_session.execute(
                select(QueryGenerationCandidate).where(QueryGenerationCandidate.run_id == run_id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2
    seqs = sorted(r.candidate_seq for r in rows)
    assert seqs == [1, 2]


# ── start_query_pool_assembly_run ────────────────────────────


@pytest.mark.asyncio
async def test_start_assembly_writes_running_row_and_mutates_summary(
    db_session: AsyncSession,
):
    config = {
        "profiles_per_prompt": 2,
        "desired_engine_policy": "balanced",
        "engine_panel_id": None,
        "max_candidates": 50,
        "overflow_policy": "split",
    }
    selection = {"mode": "explicit", "prompt_ids": ["p1"]}
    contexts = [
        {"segment_id": "s1", "profile_id": "prof1"},
        {"segment_id": "s2", "profile_id": "prof2"},
    ]
    summary = _summary(raw=2, ready=2)

    out = await qp_db.start_query_pool_assembly_run(
        db_session,
        admin_id="admin-1",
        config=config,
        selection=selection,
        prompt_ids=["p1"],
        contexts=contexts,
        preflight_summary=summary,
    )

    assert out["status"] == "running"
    # Mutated by the helper:
    assert summary["candidate_ready"] == 0
    assert summary["render_pass_rate"] == 0
    assert summary["scheduler_intake"] == "running"

    run = await db_session.get(QueryGenerationRun, out["id"])
    assert run is not None
    assert run.status == "running"
    assert run.candidates_assembled == 0
    assert sorted(run.segment_ids_selected) == ["s1", "s2"]
    assert run.started_at is not None
    assert run.completed_at is None


# ── update_query_pool_run_progress ───────────────────────────


@pytest.mark.asyncio
async def test_progress_update_streams_counters(db_session: AsyncSession):
    run = QueryGenerationRun(
        id=_new_id(),
        admin_id="admin-1",
        status="running",
        request_config={},
        prompt_ids=["p1"],
        segment_ids_selected=["s1"],
        profiles_per_prompt=2,
        desired_engine_policy="inherit",
        max_candidates=100,
        overflow_policy="split",
        candidates_estimated=10,
        candidates_assembled=0,
        preflight_summary={},
    )
    db_session.add(run)
    await db_session.commit()

    summary = _summary(raw=10, ready=3)
    candidates = [_candidate(i) for i in (1, 2, 3)]
    await qp_db.update_query_pool_run_progress(
        db_session, run_id=run.id, candidates=candidates, preflight_summary=summary
    )
    await db_session.refresh(run)
    assert run.candidates_assembled == 3
    assert run.candidates_estimated == 10
    assert run.llm_model == "gpt-4"


@pytest.mark.asyncio
async def test_progress_no_op_on_terminal_run(db_session: AsyncSession):
    run = QueryGenerationRun(
        id=_new_id(),
        admin_id="admin-1",
        status="cancelled",
        request_config={},
        prompt_ids=[],
        segment_ids_selected=[],
        profiles_per_prompt=1,
        desired_engine_policy="inherit",
        max_candidates=10,
        overflow_policy="split",
        candidates_estimated=5,
        candidates_assembled=2,
        preflight_summary={},
    )
    db_session.add(run)
    await db_session.commit()

    summary = _summary(raw=5, ready=99)
    await qp_db.update_query_pool_run_progress(
        db_session, run_id=run.id, candidates=[_candidate(1)], preflight_summary=summary
    )
    await db_session.refresh(run)
    # nothing was written:
    assert run.candidates_assembled == 2
    assert run.status == "cancelled"


# ── finalize / complete ──────────────────────────────────────


@pytest.mark.asyncio
async def test_finalize_running_to_completed(db_session: AsyncSession):
    run = QueryGenerationRun(
        id=_new_id(),
        admin_id="admin-1",
        status="running",
        request_config={},
        prompt_ids=[],
        segment_ids_selected=[],
        profiles_per_prompt=1,
        desired_engine_policy="inherit",
        max_candidates=10,
        overflow_policy="split",
        candidates_estimated=2,
        candidates_assembled=0,
        preflight_summary={},
    )
    db_session.add(run)
    await db_session.commit()

    await qp_db.finalize_query_pool_run(
        db_session,
        run_id=run.id,
        candidates=[_candidate(1), _candidate(2)],
        preflight_summary=_summary(raw=2, ready=2),
    )
    await db_session.refresh(run)
    assert run.status == "completed"
    assert run.candidates_assembled == 2
    assert run.completed_at is not None
    assert run.llm_error is None


@pytest.mark.asyncio
async def test_finalize_no_op_on_cancelled(db_session: AsyncSession):
    run = QueryGenerationRun(
        id=_new_id(),
        admin_id="admin-1",
        status="cancelled",
        request_config={},
        prompt_ids=[],
        segment_ids_selected=[],
        profiles_per_prompt=1,
        desired_engine_policy="inherit",
        max_candidates=10,
        overflow_policy="split",
        candidates_estimated=2,
        candidates_assembled=2,
        preflight_summary={},
    )
    db_session.add(run)
    await db_session.commit()

    await qp_db.finalize_query_pool_run(
        db_session,
        run_id=run.id,
        candidates=[],
        preflight_summary=_summary(raw=2, ready=0),
    )
    await db_session.refresh(run)
    assert run.status == "cancelled"  # untouched


@pytest.mark.asyncio
async def test_complete_writes_candidates_then_finalizes(db_session: AsyncSession):
    run = QueryGenerationRun(
        id=_new_id(),
        admin_id="admin-1",
        status="running",
        request_config={},
        prompt_ids=[],
        segment_ids_selected=[],
        profiles_per_prompt=1,
        desired_engine_policy="inherit",
        max_candidates=10,
        overflow_policy="split",
        candidates_estimated=2,
        candidates_assembled=0,
        preflight_summary={},
    )
    db_session.add(run)
    await db_session.commit()

    candidates = [_candidate(1), _candidate(2)]
    await qp_db.complete_query_pool_run(
        db_session,
        run_id=run.id,
        candidates=candidates,
        preflight_summary=_summary(raw=2, ready=2),
    )
    await db_session.refresh(run)
    assert run.status == "completed"
    assert run.candidates_assembled == 2

    rows = list(
        (
            await db_session.execute(
                select(QueryGenerationCandidate).where(QueryGenerationCandidate.run_id == run.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2


# ── mark_failed / mark_cancelled ─────────────────────────────


@pytest.mark.asyncio
async def test_mark_failed_records_llm_error_and_summary(db_session: AsyncSession):
    run = QueryGenerationRun(
        id=_new_id(),
        admin_id="admin-1",
        status="running",
        request_config={},
        prompt_ids=[],
        segment_ids_selected=[],
        profiles_per_prompt=1,
        desired_engine_policy="inherit",
        max_candidates=10,
        overflow_policy="split",
        candidates_estimated=2,
        candidates_assembled=0,
        preflight_summary={},
    )
    db_session.add(run)
    await db_session.commit()

    summary = _summary(raw=2, ready=1)
    await qp_db.mark_query_pool_run_failed(
        db_session,
        run_id=run.id,
        error_code="llm_auth",
        error_message="API key invalid",
        preflight_summary=summary,
    )
    await db_session.refresh(run)
    assert run.status == "failed"
    assert run.llm_error == "llm_auth: API key invalid"
    assert run.candidates_assembled == 1


@pytest.mark.asyncio
async def test_mark_failed_no_summary_only_stamps_error(db_session: AsyncSession):
    run = QueryGenerationRun(
        id=_new_id(),
        admin_id="admin-1",
        status="running",
        request_config={},
        prompt_ids=[],
        segment_ids_selected=[],
        profiles_per_prompt=1,
        desired_engine_policy="inherit",
        max_candidates=10,
        overflow_policy="split",
        candidates_estimated=5,
        candidates_assembled=0,
        preflight_summary={"existing": "kept"},
    )
    db_session.add(run)
    await db_session.commit()

    await qp_db.mark_query_pool_run_failed(
        db_session,
        run_id=run.id,
        error_code="llm_auth",
        error_message="API key invalid",
    )
    await db_session.refresh(run)
    assert run.status == "failed"
    assert run.llm_error == "llm_auth: API key invalid"
    # preflight_summary preserved when no replacement passed
    assert run.preflight_summary == {"existing": "kept"}
    # estimates NOT zeroed when no replacement summary
    assert run.candidates_estimated == 5


@pytest.mark.asyncio
async def test_mark_failed_no_op_on_cancelled(db_session: AsyncSession):
    run = QueryGenerationRun(
        id=_new_id(),
        admin_id="admin-1",
        status="cancelled",
        request_config={},
        prompt_ids=[],
        segment_ids_selected=[],
        profiles_per_prompt=1,
        desired_engine_policy="inherit",
        max_candidates=10,
        overflow_policy="split",
        candidates_estimated=2,
        candidates_assembled=0,
        preflight_summary={},
    )
    db_session.add(run)
    await db_session.commit()

    await qp_db.mark_query_pool_run_failed(
        db_session, run_id=run.id, error_code="x", error_message="y"
    )
    await db_session.refresh(run)
    assert run.status == "cancelled"
    assert run.llm_error is None


@pytest.mark.asyncio
async def test_mark_cancelled_preserves_completed_at(db_session: AsyncSession):
    from datetime import datetime, timedelta

    earlier = datetime.now(UTC).replace(tzinfo=None) - timedelta(seconds=42)
    run = QueryGenerationRun(
        id=_new_id(),
        admin_id="admin-1",
        status="cancelled",
        request_config={},
        prompt_ids=[],
        segment_ids_selected=[],
        profiles_per_prompt=1,
        desired_engine_policy="inherit",
        max_candidates=10,
        overflow_policy="split",
        candidates_estimated=2,
        candidates_assembled=0,
        preflight_summary={},
        completed_at=earlier,
    )
    db_session.add(run)
    await db_session.commit()

    await qp_db.mark_query_pool_run_cancelled(
        db_session,
        run_id=run.id,
        candidates=[_candidate(1)],
        preflight_summary=_summary(raw=2, ready=1),
    )
    await db_session.refresh(run)
    assert run.status == "cancelled"
    assert run.candidates_assembled == 1
    # completed_at preserved (not overwritten)
    assert abs((run.completed_at - earlier).total_seconds()) < 1


# ── audit gate ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice3b_ii():
    """No new admin write routes were added in slice 3b-ii — pure helpers
    only — so the existing source-scan gate must keep passing.
    """
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
