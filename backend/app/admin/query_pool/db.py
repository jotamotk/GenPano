"""DB-touching helpers for the Query Pool preflight + assemble flows.

Vendored from admin_console/app.py 1909-2019 (the prompt-row + profile-pool
queries). All queries use raw ``text()`` SQL because ``prompts`` is an
upstream stub in backend's ORM (ADR-002 — only ``id`` modeled). Defensive
``_table_exists`` / ``_table_columns`` checks via ``information_schema``
mirror admin_console: an empty test sqlite DB returns no rows, not an
exception.

Public API:
- ``fetch_prompt_ids_from_selection(session, selection, max_prompts)``
- ``fetch_query_pool_prompt_rows(session, prompt_ids)``
- ``fetch_query_pool_profile_pool(session, segment_ids=None)``
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _table_exists(session: AsyncSession, name: str) -> bool:
    """True iff ``public.<name>`` is registered in information_schema.

    Returns False on sqlite (which has no information_schema) so the
    surrounding helpers degrade to "no data" — matching admin_console.
    """
    try:
        row = (
            await session.execute(
                text(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = :n LIMIT 1"
                ),
                {"n": name},
            )
        ).first()
    except Exception:
        return False
    return row is not None


async def _table_columns(session: AsyncSession, name: str) -> set[str]:
    try:
        result = await session.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :n"
            ),
            {"n": name},
        )
    except Exception:
        return set()
    return {row[0] for row in result.all()}


def _parse_int_list(raw: Any) -> list[int]:
    """Accept comma-string / list / single int; ignore bad entries."""
    if raw is None or raw == "":
        return []
    items: list[Any]
    if isinstance(raw, str):
        items = raw.split(",")
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        items = [raw]
    out: list[int] = []
    for item in items:
        try:
            out.append(int(str(item).strip()))
        except (TypeError, ValueError):
            continue
    return out


async def fetch_prompt_ids_from_selection(
    session: AsyncSession,
    selection: dict[str, Any],
    max_prompts: int,
) -> list[str]:
    """Resolve the ``selection`` block to a concrete list of prompt ids.

    Explicit mode → returns the operator-supplied id list as-is.
    Filtered mode → executes a SELECT against ``prompts`` honoring
    intent / language / topic_ids / search and the ``status='active'``
    soft-delete column when present.
    """
    if selection["mode"] == "explicit":
        return list(selection["prompt_ids"])
    filters = selection.get("filters") or {}
    intent = (filters.get("intent") or "").strip().lower()
    language = (filters.get("language") or filters.get("lang") or "").strip()
    query = (filters.get("q") or filters.get("query") or "").strip()
    try:
        topic_ids = _parse_int_list(filters.get("topic_ids") or filters.get("topic_id"))
    except ValueError:
        topic_ids = []
    excluded = {str(x) for x in (selection.get("excluded_prompt_ids") or [])}
    if not await _table_exists(session, "prompts"):
        return []
    prompt_cols = await _table_columns(session, "prompts")
    if "id" not in prompt_cols:
        return []
    where: list[str] = []
    params: dict[str, Any] = {}
    if intent and "intent" in prompt_cols:
        where.append("p.intent = :intent")
        params["intent"] = intent
    if language and "language" in prompt_cols:
        where.append("p.language = :language")
        params["language"] = language
    if topic_ids and "topic_id" in prompt_cols:
        where.append("p.topic_id = ANY(:topic_ids)")
        params["topic_ids"] = topic_ids
    if query:
        where.append("(p.text ILIKE :like OR CAST(p.id AS TEXT) ILIKE :like)")
        params["like"] = f"%{query}%"
    if "status" in prompt_cols:
        where.append("COALESCE(p.status, 'active') = 'active'")
    where_clause = "WHERE " + " AND ".join(where) if where else ""
    params["limit"] = max_prompts
    sql = text(
        f"""
        SELECT CAST(p.id AS TEXT) AS id
        FROM prompts p
        {where_clause}
        ORDER BY p.id
        LIMIT :limit
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    return [str(row["id"]) for row in rows if str(row["id"]) not in excluded]


async def fetch_query_pool_prompt_rows(
    session: AsyncSession,
    prompt_ids: list[str],
) -> list[dict[str, Any]]:
    """Fetch prompt + topic context rows ordered to match ``prompt_ids``."""
    prompt_ids = [str(item).strip() for item in prompt_ids if str(item).strip()]
    if not prompt_ids or not await _table_exists(session, "prompts"):
        return []
    prompt_cols = await _table_columns(session, "prompts")
    if not {"id", "text"}.issubset(prompt_cols):
        return []
    topic_join = ""
    topic_select = "NULL::text AS topic_text"
    if (
        "topic_id" in prompt_cols
        and await _table_exists(session, "topics")
        and "id" in await _table_columns(session, "topics")
    ):
        topic_join = "LEFT JOIN topics t ON t.id = p.topic_id"
        topic_select = "t.text AS topic_text"
    topic_id_select = "p.topic_id" if "topic_id" in prompt_cols else "NULL::text AS topic_id"
    status_where = "AND COALESCE(p.status, 'active') = 'active'" if "status" in prompt_cols else ""
    sql = text(
        f"""
        SELECT CAST(p.id AS TEXT) AS id, {topic_id_select}, p.text, {topic_select}
        FROM prompts p
        {topic_join}
        WHERE CAST(p.id AS TEXT) = ANY(:prompt_ids)
        {status_where}
        """
    )
    result = await session.execute(sql, {"prompt_ids": prompt_ids})
    rows_by_id = {str(row["id"]): dict(row) for row in result.mappings().all()}
    return [rows_by_id[pid] for pid in prompt_ids if pid in rows_by_id]


async def fetch_query_pool_profile_pool(
    session: AsyncSession,
    *,
    segment_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Active segments JOIN active profiles, weight-prioritized.

    Filters: ``is_deleted=False`` on both, ``status='active'`` on both,
    weight > 0 on both. Ordering matches admin_console — segment weight
    DESC then profile weight DESC then ids — so deterministic samplers
    upstream get a stable seed.
    """
    if not (await _table_exists(session, "segments") and await _table_exists(session, "profiles")):
        return []
    sids = [str(s).strip().upper() for s in (segment_ids or []) if str(s).strip()]
    where = [
        "COALESCE(s.is_deleted, FALSE) = FALSE",
        "COALESCE(p.is_deleted, FALSE) = FALSE",
        "COALESCE(s.status, 'draft') = 'active'",
        "COALESCE(p.status, 'draft') = 'active'",
        "COALESCE(s.weight, 0) > 0",
        "COALESCE(p.weight, 0) > 0",
    ]
    params: dict[str, Any] = {}
    if sids:
        where.append("s.id = ANY(:sids)")
        params["sids"] = sids
    sql = text(
        f"""
        SELECT
            s.id AS segment_id,
            s.name AS segment_name,
            COALESCE(s.weight, 0) AS segment_weight,
            COALESCE(p.code, CAST(p.id AS TEXT)) AS profile_id,
            p.name AS profile_name,
            p.demographic AS profile_demographic,
            p.need AS profile_need,
            COALESCE(p.weight, 0) AS profile_weight
        FROM segments s
        JOIN profiles p ON p.segment_id = s.id
        WHERE {" AND ".join(where)}
        ORDER BY s.weight DESC, p.weight DESC, s.id, p.id
        """
    )
    return [dict(r) for r in (await session.execute(sql, params)).mappings().all()]


# ---------------------------------------------------------------------------
# Writer helpers (Phase 5 slice 3b-ii) — callers: assemble route, worker.
# Routes don't land yet; slice 3b-iii wires them up. ORM ops are used here
# instead of raw text() so the writes work against the test sqlite fixture
# (which has both query_generation_runs and query_generation_candidates
# registered with Base.metadata).
# ---------------------------------------------------------------------------


import uuid as _uuid  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

from genpano_models import QueryGenerationCandidate, QueryGenerationRun  # noqa: E402

from app.admin.query_pool.lib import query_pool_summary  # noqa: E402


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def insert_query_pool_candidates(
    session: AsyncSession,
    run_id: str,
    candidates: list[dict[str, Any]],
) -> None:
    """Bulk-insert assembled candidates onto an existing run.

    Pre-populated dicts (id / candidate_seq / render_hash / etc) are
    written verbatim; ``llm_usage`` defaults to ``{}`` and
    ``generation_method`` defaults to ``llm`` so legacy callers that
    omitted them still match admin_console behaviour.
    """
    for c in candidates:
        session.add(
            QueryGenerationCandidate(
                id=c["id"],
                run_id=run_id,
                candidate_seq=c["candidate_seq"],
                prompt_id=c["prompt_id"],
                segment_id=c.get("segment_id"),
                profile_id=c.get("profile_id"),
                rendered_query=c["rendered_query"],
                render_hash=c["render_hash"],
                generation_method=c.get("generation_method") or "llm",
                llm_model=c.get("llm_model"),
                llm_usage_json=c.get("llm_usage") or {},
                candidate_status=c["candidate_status"],
                created_at=_now(),
            )
        )
    await session.commit()


async def update_query_pool_run_progress(
    session: AsyncSession,
    *,
    run_id: str,
    candidates: list[dict[str, Any]],
    preflight_summary: dict[str, Any],
) -> None:
    """Worker progress UPDATE — never touches terminal runs.

    Mirrors admin_console: the WHERE clause excludes both ``cancelled``
    and ``failed`` so a parallel ``stop_run`` / fatal-LLM-error doesn't
    get clobbered by streaming progress writes.
    """
    run = await session.get(QueryGenerationRun, run_id)
    if run is None or run.status in {"cancelled", "failed"}:
        return
    run.candidates_estimated = int(
        preflight_summary.get("raw_candidates_estimated") or len(candidates)
    )
    run.candidates_assembled = len(candidates)
    run.preflight_summary = preflight_summary
    run.llm_model = preflight_summary.get("llm_model")
    run.llm_usage_json = preflight_summary.get("llm_usage") or {}
    run.updated_at = _now()
    await session.commit()


async def insert_query_pool_run_completed(
    session: AsyncSession,
    *,
    admin_id: str,
    selection: dict[str, Any],
    config: dict[str, Any],
    candidates: list[dict[str, Any]],
    preflight_summary: dict[str, Any],
) -> str:
    """Single-shot path: create a finished run + insert all candidates.

    Used when the assemble flow runs synchronously (e.g. tests, small
    pools where the worker stage finishes inside the request). Status
    is ``completed`` immediately.
    """
    run_id = str(_uuid.uuid4())
    prompt_ids = [c["prompt_id"] for c in candidates]
    segment_ids = sorted({c["segment_id"] for c in candidates if c.get("segment_id")})
    run = QueryGenerationRun(
        id=run_id,
        admin_id=admin_id,
        status="completed",
        request_config={"selection": selection, "config": config},
        prompt_ids=prompt_ids,
        segment_ids_selected=segment_ids,
        profiles_per_prompt=config["profiles_per_prompt"],
        desired_engine_policy=config["desired_engine_policy"],
        engine_panel_id=config.get("engine_panel_id"),
        max_candidates=config["max_candidates"],
        overflow_policy=config["overflow_policy"],
        candidates_estimated=int(
            preflight_summary.get("raw_candidates_estimated") or len(candidates)
        ),
        candidates_assembled=len(candidates),
        preflight_summary=preflight_summary,
        llm_model=preflight_summary.get("llm_model"),
        llm_usage_json=preflight_summary.get("llm_usage") or {},
        started_at=_now(),
        completed_at=_now(),
    )
    session.add(run)
    await session.commit()
    await insert_query_pool_candidates(session, run_id, candidates)
    return run_id


async def start_query_pool_assembly_run(
    session: AsyncSession,
    *,
    admin_id: str,
    config: dict[str, Any],
    selection: dict[str, Any],
    prompt_ids: list[str],
    contexts: list[dict[str, Any]],
    preflight_summary: dict[str, Any],
) -> dict[str, Any]:
    """Create a 'running' run row that the worker will progressively
    update.

    Mutates ``preflight_summary`` to reset the assembled-side fields
    (``candidate_ready=0``, ``render_pass_rate=0``,
    ``scheduler_intake='running'``) so the SPA can show "0 / N" while
    the worker streams.
    """
    preflight_summary["candidate_ready"] = 0
    preflight_summary["render_pass_rate"] = 0
    preflight_summary["scheduler_intake"] = "running"
    run_id = str(_uuid.uuid4())
    run_prompt_ids = list(prompt_ids)
    run_segment_ids = sorted({c["segment_id"] for c in contexts if c.get("segment_id")})
    raw_estimated = int(preflight_summary.get("raw_candidates_estimated") or len(contexts))
    run = QueryGenerationRun(
        id=run_id,
        admin_id=admin_id,
        status="running",
        request_config={"selection": selection, "config": config},
        prompt_ids=run_prompt_ids,
        segment_ids_selected=run_segment_ids,
        profiles_per_prompt=config["profiles_per_prompt"],
        desired_engine_policy=config["desired_engine_policy"],
        engine_panel_id=config.get("engine_panel_id"),
        max_candidates=config["max_candidates"],
        overflow_policy=config["overflow_policy"],
        candidates_estimated=raw_estimated,
        candidates_assembled=0,
        preflight_summary=preflight_summary,
        started_at=_now(),
    )
    session.add(run)
    await session.commit()
    return {
        "id": run_id,
        "status": "running",
        "candidates_estimated": raw_estimated,
        "candidates_assembled": 0,
        "preflight_summary": preflight_summary,
    }


async def finalize_query_pool_run(
    session: AsyncSession,
    *,
    run_id: str,
    candidates: list[dict[str, Any]],
    preflight_summary: dict[str, Any],
) -> None:
    """Worker happy-path terminator: 'running' → 'completed'.

    No-op on cancelled runs (matches admin_console's
    ``status <> 'cancelled'`` guard) so a concurrent stop_run sticks.
    """
    run = await session.get(QueryGenerationRun, run_id)
    if run is None or run.status == "cancelled":
        return
    run.status = "completed"
    run.candidates_estimated = int(
        preflight_summary.get("raw_candidates_estimated") or len(candidates)
    )
    run.candidates_assembled = len(candidates)
    run.preflight_summary = preflight_summary
    run.llm_model = preflight_summary.get("llm_model")
    run.llm_usage_json = preflight_summary.get("llm_usage") or {}
    run.llm_error = None
    run.completed_at = _now()
    run.updated_at = _now()
    await session.commit()


async def complete_query_pool_run(
    session: AsyncSession,
    *,
    run_id: str,
    candidates: list[dict[str, Any]],
    preflight_summary: dict[str, Any],
) -> None:
    """Insert candidates + flip status to 'completed'."""
    await insert_query_pool_candidates(session, run_id, candidates)
    await finalize_query_pool_run(
        session,
        run_id=run_id,
        candidates=candidates,
        preflight_summary=preflight_summary,
    )


async def mark_query_pool_run_failed(
    session: AsyncSession,
    *,
    run_id: str,
    error_code: str,
    error_message: str,
    preflight_summary: dict[str, Any] | None = None,
) -> None:
    """Worker error terminator: 'running' → 'failed' + recorded reason.

    ``preflight_summary`` is optional: if the failure happens before any
    LLM batch returned anything (e.g., LLM auth error on the first
    request), the worker will pass None and we just stamp ``llm_error``;
    otherwise we persist the partial summary so the SPA can show "got
    M/N before failing".
    """
    run = await session.get(QueryGenerationRun, run_id)
    if run is None or run.status == "cancelled":
        return
    detail = f"{error_code}: {error_message}".strip()
    run.status = "failed"
    run.llm_error = detail
    run.completed_at = _now()
    run.updated_at = _now()
    if preflight_summary is not None:
        run.candidates_estimated = int(preflight_summary.get("raw_candidates_estimated") or 0)
        run.candidates_assembled = int(preflight_summary.get("candidate_ready") or 0)
        run.preflight_summary = preflight_summary
        run.llm_model = preflight_summary.get("llm_model")
        run.llm_usage_json = preflight_summary.get("llm_usage") or {}
    await session.commit()


async def mark_query_pool_run_cancelled(
    session: AsyncSession,
    *,
    run_id: str,
    candidates: list[dict[str, Any]],
    preflight_summary: dict[str, Any],
) -> None:
    """Worker-side cancel ack — preserves any prior completed_at.

    ``stop_run`` (slice 1) flips status to 'cancelled' and stamps
    completed_at. If the worker observes the cancel mid-stream and
    calls this helper to record the partial progress, we keep the
    earlier completed_at via COALESCE — matches admin_console.
    """
    run = await session.get(QueryGenerationRun, run_id)
    if run is None:
        return
    run.status = "cancelled"
    run.candidates_estimated = int(
        preflight_summary.get("raw_candidates_estimated") or len(candidates)
    )
    run.candidates_assembled = len(candidates)
    run.preflight_summary = preflight_summary
    run.llm_model = preflight_summary.get("llm_model")
    run.llm_usage_json = preflight_summary.get("llm_usage") or {}
    if run.completed_at is None:
        run.completed_at = _now()
    run.updated_at = _now()
    await session.commit()


# Re-export so callers can import everything from app.admin.query_pool.db.
# query_pool_summary lives in lib.py but is the universal preflight builder
# so re-export here keeps `from app.admin.query_pool import db; db.summary()`
# pattern symmetrical with the rest of the writer surface.
__all__ = [
    "complete_query_pool_run",
    "fetch_prompt_ids_from_selection",
    "fetch_query_pool_profile_pool",
    "fetch_query_pool_prompt_rows",
    "finalize_query_pool_run",
    "insert_query_pool_candidates",
    "insert_query_pool_run_completed",
    "mark_query_pool_run_cancelled",
    "mark_query_pool_run_failed",
    "query_pool_summary",
    "start_query_pool_assembly_run",
    "update_query_pool_run_progress",
]
