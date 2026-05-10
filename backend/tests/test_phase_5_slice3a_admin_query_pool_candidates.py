"""Phase 5 slice 3a — GET /api/admin/query-pool/candidates (cursor list).

The handler issues raw SQL with LEFT JOINs against `prompts`, `topics`,
`segments`, `profiles`. Tests mock ``_fetch_candidates_paged`` so we avoid
schema dependencies that don't exist in the sqlite fixture (``topics`` is
not registered with Base.metadata).

Coverage:
- 401 unauth
- 422 on invalid status / direction / cursor
- empty result when DB has no run yet
- happy-path wire shape (mock fetcher) — defaults to most-recent run_id
- next/prev cursor encoding
- legacy alias /admin/api/v1/pipeline/query-pool/candidates
- _encode_cursor / _decode_cursor round-trip + invalid cursor raises ValueError
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from genpano_models import AdminUser, QueryGenerationCandidate, QueryGenerationRun
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


# ── auth + validation ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_candidates_unauth_401(client):
    resp = await client.get("/api/admin/query-pool/candidates")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_candidates_invalid_status_422(client, admin_operator):
    resp = await client.get("/api/admin/query-pool/candidates?status=bogus")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_candidates_invalid_direction_422(client, admin_operator):
    resp = await client.get("/api/admin/query-pool/candidates?direction=sideways")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_candidates_invalid_cursor_422(client, admin_operator):
    resp = await client.get("/api/admin/query-pool/candidates?cursor=not-base64-json!!")
    assert resp.status_code == 422


# ── empty path ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_candidates_no_runs_returns_empty(client, admin_operator):
    """No runs in DB → 200 with empty rows + no cursors."""
    resp = await client.get("/api/admin/query-pool/candidates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["rows"] == []
    assert body["next_cursor"] is None
    assert body["prev_cursor"] is None
    assert body["approx_total"] == 0


# ── happy path with mocked fetcher ────────────────────────────


@pytest.mark.asyncio
async def test_list_candidates_real_sql_tolerates_prompt_stub(
    client, admin_operator, run, db_session: AsyncSession
):
    candidate = QueryGenerationCandidate(
        id=_new_id(),
        run_id=run.id,
        candidate_seq=1,
        prompt_id="1",
        segment_id="s1",
        profile_id="prof1",
        rendered_query="Rendered query",
        render_hash="hash-real-sql",
        generation_method="llm",
        candidate_status="candidate",
    )
    db_session.add(candidate)
    await db_session.commit()

    resp = await client.get(f"/api/admin/query-pool/candidates?run_id={run.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["rows"][0]["prompt_text"] == ""
    assert body["rows"][0]["topic_text"] == ""


@pytest.mark.asyncio
async def test_list_candidates_all_runs_without_filters_uses_true_where(
    client, admin_operator, run, db_session: AsyncSession
):
    candidate = QueryGenerationCandidate(
        id=_new_id(),
        run_id=run.id,
        candidate_seq=1,
        prompt_id="1",
        segment_id="s1",
        profile_id="prof1",
        rendered_query="Rendered query",
        render_hash="hash-all-runs-no-filter",
        generation_method="llm",
        candidate_status="candidate",
    )
    db_session.add(candidate)
    await db_session.commit()

    resp = await client.get("/api/admin/query-pool/candidates?all_runs=1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["approx_total"] >= 1
    assert [row["id"] for row in body["rows"]] == [candidate.id]


@pytest.mark.asyncio
async def test_list_candidates_all_runs_cursor_keeps_duplicate_candidate_seq(
    client, admin_operator, run, db_session: AsyncSession
):
    """all_runs=1 must not skip rows when candidate_seq repeats across runs."""
    second_run = QueryGenerationRun(
        id=_new_id(),
        admin_id=admin_operator.id,
        status="completed",
        request_config={},
        prompt_ids=["p1"],
        segment_ids_selected=["s1"],
        profiles_per_prompt=1,
        candidates_estimated=1,
        candidates_assembled=1,
        started_at=_now() - timedelta(seconds=10),
        completed_at=_now(),
    )
    first_candidate = QueryGenerationCandidate(
        id="00000000-0000-0000-0000-000000000001",
        run_id=run.id,
        candidate_seq=1,
        prompt_id="1",
        segment_id="s1",
        profile_id="prof1",
        rendered_query="first duplicate seq",
        render_hash="hash-duplicate-seq-1",
        generation_method="llm",
        candidate_status="ready",
    )
    second_candidate = QueryGenerationCandidate(
        id="00000000-0000-0000-0000-000000000002",
        run_id=second_run.id,
        candidate_seq=1,
        prompt_id="1",
        segment_id="s1",
        profile_id="prof2",
        rendered_query="second duplicate seq",
        render_hash="hash-duplicate-seq-2",
        generation_method="llm",
        candidate_status="ready",
    )
    db_session.add_all([second_run, first_candidate, second_candidate])
    await db_session.commit()

    first_resp = await client.get(
        "/api/admin/query-pool/candidates?all_runs=1&status=ready&limit=1"
    )

    assert first_resp.status_code == 200
    first_body = first_resp.json()
    assert [row["id"] for row in first_body["rows"]] == [first_candidate.id]
    assert first_body["next_cursor"]

    second_resp = await client.get(
        "/api/admin/query-pool/candidates"
        f"?all_runs=1&status=ready&limit=1&cursor={first_body['next_cursor']}"
    )

    assert second_resp.status_code == 200
    second_body = second_resp.json()
    assert [row["id"] for row in second_body["rows"]] == [second_candidate.id]


@pytest.mark.asyncio
async def test_list_candidates_happy_uses_latest_run(client, admin_operator, run, monkeypatch):
    """When run_id is omitted, falls back to most-recent run."""
    import sys

    import app.api.admin.query_pool.router  # noqa: F401  — ensure module loaded

    qp_router = sys.modules["app.api.admin.query_pool.router"]

    captured: dict[str, object] = {}

    async def fake_fetch(
        session,
        *,
        run_id,
        status,
        segment_id,
        profile_id,
        brand_id,
        query,
        limit,
        cursor_seq,
        cursor_id,
        direction,
    ):
        captured["run_id"] = run_id
        captured["direction"] = direction
        captured["brand_id"] = brand_id
        captured["cursor_id"] = cursor_id
        return (
            [
                {
                    "id": "cand-1",
                    "run_id": run_id,
                    "candidate_seq": 1,
                    "prompt_id": "p1",
                    "prompt_text": "How safe is X?",
                    "topic_id": "t1",
                    "topic_text": "safety",
                    "segment_id": "s1",
                    "segment_name": "young-pros",
                    "profile_id": "prof1",
                    "profile_name": "Anna",
                    "profile_demographic": "30F",
                    "profile_need": "trust",
                    "rendered_query": "Is X safe?",
                    "metadata_json": {
                        "prompt_scope": "competitive",
                        "competitive_type": "direct_comparison",
                        "product_name": "Acme Vault",
                        "scenario_axis": "secure file sharing",
                        "competitor_name": "BetaVault",
                        "comparison_axis": "security posture",
                        "brand_context_version": "ctx-1",
                    },
                    "generation_method": "llm",
                    "llm_model": "gpt-4",
                    "llm_usage_json": {"tokens": 12},
                    "candidate_status": "candidate",
                    "scheduler_intake_batch_id": None,
                    "reviewed_by": None,
                    "reviewed_at": None,
                    "review_reason": None,
                    "created_at": _now(),
                }
            ],
            7,
            False,
        )

    monkeypatch.setattr(qp_router, "_fetch_candidates_paged", fake_fetch)
    resp = await client.get("/api/admin/query-pool/candidates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["approx_total"] == 7
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["id"] == "cand-1"
    assert row["candidate_seq"] == 1
    assert row["prompt_text"] == "How safe is X?"
    assert row["topic_text"] == "safety"
    assert row["segment_name"] == "young-pros"
    assert row["profile_name"] == "Anna"
    assert row["metadata"]["prompt_scope"] == "competitive"
    assert row["prompt_scope"] == "competitive"
    assert row["competitor_name"] == "BetaVault"
    assert row["comparison_axis"] == "security posture"
    assert row["brand_context_version"] == "ctx-1"
    assert row["llm_usage"] == {"tokens": 12}
    # No cursor pagination state when no cursor was given and !has_more
    assert body["next_cursor"] is None
    assert body["prev_cursor"] is None
    # Captured fallback to latest run
    assert captured["run_id"] == run.id
    assert captured["direction"] == "next"
    assert captured["brand_id"] is None


@pytest.mark.asyncio
async def test_list_candidates_filters_by_brand_id(client, admin_operator, run, monkeypatch):
    import sys

    import app.api.admin.query_pool.router  # noqa: F401  ensure module loaded

    qp_router = sys.modules["app.api.admin.query_pool.router"]
    captured: dict[str, object] = {}

    async def fake_fetch(session, *, run_id, brand_id, **_):
        captured["run_id"] = run_id
        captured["brand_id"] = brand_id
        return (
            [
                {
                    "id": "brand-candidate",
                    "run_id": run_id,
                    "candidate_seq": 1,
                    "prompt_id": "p-brand",
                    "rendered_query": "brand scoped query",
                    "metadata_json": {"brand_id": 42, "brand_name": "Acme"},
                    "generation_method": "llm",
                    "candidate_status": "candidate",
                    "created_at": _now(),
                    "llm_usage_json": {},
                }
            ],
            1,
            False,
        )

    monkeypatch.setattr(qp_router, "_fetch_candidates_paged", fake_fetch)

    resp = await client.get("/api/admin/query-pool/candidates?brand_id=42")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["rows"][0]["metadata"]["brand_id"] == 42
    assert captured["brand_id"] == 42


@pytest.mark.asyncio
async def test_list_candidates_all_runs_skips_latest_run_default(
    client, admin_operator, run, monkeypatch
):
    import sys

    import app.api.admin.query_pool.router  # noqa: F401  ensure module loaded

    qp_router = sys.modules["app.api.admin.query_pool.router"]
    captured: dict[str, object] = {}

    async def fake_fetch(session, *, run_id, brand_id, **_):
        captured["run_id"] = run_id
        captured["brand_id"] = brand_id
        return (
            [
                {
                    "id": "brand-candidate",
                    "run_id": "older-run",
                    "candidate_seq": 1,
                    "prompt_id": "p-brand",
                    "rendered_query": "brand scoped query",
                    "metadata_json": {"brand_id": 42, "brand_name": "Acme"},
                    "generation_method": "llm",
                    "candidate_status": "candidate",
                    "created_at": _now(),
                    "llm_usage_json": {},
                }
            ],
            1,
            False,
        )

    monkeypatch.setattr(qp_router, "_fetch_candidates_paged", fake_fetch)

    resp = await client.get("/api/admin/query-pool/candidates?brand_id=42&all_runs=1")

    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert captured["run_id"] is None
    assert captured["brand_id"] == 42


@pytest.mark.asyncio
async def test_list_candidates_next_cursor_when_has_more(client, admin_operator, run, monkeypatch):
    """has_more=True + next direction → next_cursor encodes last seq."""
    import sys

    import app.api.admin.query_pool.router  # noqa: F401  — ensure module loaded

    qp_router = sys.modules["app.api.admin.query_pool.router"]

    async def fake_fetch(session, *, run_id, **_):
        return (
            [
                {
                    "id": f"c-{i}",
                    "run_id": run_id,
                    "candidate_seq": i,
                    "prompt_id": "p1",
                    "rendered_query": f"q{i}",
                    "generation_method": "llm",
                    "candidate_status": "candidate",
                    "created_at": _now(),
                    "llm_usage_json": {},
                }
                for i in (1, 2, 3)
            ],
            10,
            True,
        )

    monkeypatch.setattr(qp_router, "_fetch_candidates_paged", fake_fetch)
    resp = await client.get("/api/admin/query-pool/candidates?limit=3")
    assert resp.status_code == 200
    body = resp.json()
    assert body["next_cursor"] is not None
    # decode it back — should be candidate_seq 3 (the last row)
    from app.api.admin.query_pool.router import _decode_cursor

    assert _decode_cursor(body["next_cursor"])[0] == 3


@pytest.mark.asyncio
async def test_list_candidates_via_legacy_alias(client, admin_operator, run, monkeypatch):
    """The /admin/api/v1/pipeline/query-pool/candidates legacy alias works."""
    import sys

    import app.api.admin.query_pool.router  # noqa: F401  — ensure module loaded

    qp_router = sys.modules["app.api.admin.query_pool.router"]

    monkeypatch.setattr(
        qp_router,
        "_fetch_candidates_paged",
        AsyncMock(return_value=([], 0, False)),
    )
    resp = await client.get("/admin/api/v1/pipeline/query-pool/candidates")
    assert resp.status_code == 200
    assert resp.json()["success"] is True


# ── helpers: cursor encode / decode ───────────────────────────


def test_encode_decode_cursor_round_trip():
    from app.api.admin.query_pool.router import _decode_cursor, _encode_cursor

    encoded = _encode_cursor(42, "candidate-42")
    assert encoded is not None
    assert "=" not in encoded  # urlsafe + stripped padding
    assert _decode_cursor(encoded) == (42, "candidate-42")


def test_encode_cursor_none_passthrough():
    from app.api.admin.query_pool.router import _encode_cursor

    assert _encode_cursor(None) is None


def test_decode_cursor_empty_returns_none():
    from app.api.admin.query_pool.router import _decode_cursor

    assert _decode_cursor(None) == (None, None)
    assert _decode_cursor("") == (None, None)


def test_decode_cursor_invalid_raises_value_error():
    import pytest as _pt

    from app.api.admin.query_pool.router import _decode_cursor

    with _pt.raises(ValueError, match="invalid_cursor"):
        _decode_cursor("not-base64-json!!")


# ── audit gate ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_coverage_gate_after_slice3a():
    from tests.test_audit_emit_coverage import test_admin_write_routes_call_emit_audit

    test_admin_write_routes_call_emit_audit()
