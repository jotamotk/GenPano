"""Async SQLAlchemy ports of admin_console.app.py's topic_plan SQL helpers.

These query the legacy ``brands`` / ``topics`` / ``prompts`` / ``queries`` /
``products`` / ``kg_industries`` / ``topic_candidates`` tables. ``brands`` /
``topics`` / ``prompts`` are upstream stubs in backend's ORM (only ``id``
modeled per ADR-002), so all DB access here goes through
``session.execute(text(...))`` rather than ORM queries.

Production schema is assumed (postgres). Sqlite test environments are
unsupported for this module — Phase 3 B.2 routes that depend on it should
mock these helpers in unit tests, and exercise the real path via the
production smoke test described in the PR description.

Helpers (parity with admin_console.app.py):
- fetch_brands                  brands list with topic_count + industry
- fetch_categories              distinct topics.category list
- pending_summary               topic_candidates: pending + low_confidence
- build_coverage                per-brand coverage rows + gaps + summary
- fetch_topics                  paged list of topics with prompt/query counts
- fetch_candidates              paged list of topic_candidates
- mark_stale_run                flip stuck running → failed if past timeout
- run_to_dict                   wire-shape for a TopicPlanRun
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from genpano_models import TopicPlanRun
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.topic_plan.lib import bounded_int

ALLOWED_DIMENSIONS = {"brand", "product", "category", "scenario", "question"}


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def parse_int_list(value: str | list[Any] | None) -> list[int]:
    if value is None:
        return []
    raw_items = value if isinstance(value, list) else str(value).split(",")
    result: list[int] = []
    for item in raw_items:
        text_v = str(item).strip()
        if not text_v:
            continue
        try:
            n = int(text_v)
        except ValueError as exc:
            raise ValueError("invalid integer list") from exc
        if n not in result:
            result.append(n)
    return result


def map_dimension(raw_category: str | None) -> str:
    value = (raw_category or "").strip().lower()
    if value in ALLOWED_DIMENSIONS:
        return value
    legacy_map = {
        "awareness": "brand",
        "comparison": "category",
        "recommendation": "scenario",
        "problem_solving": "question",
        "problem-solving": "question",
        "non_brand": "category",
    }
    return legacy_map.get(value, "brand")


# ---------------------------------------------------------------------------
# brands + categories
# ---------------------------------------------------------------------------


async def fetch_brands(session: AsyncSession) -> list[dict[str, Any]]:
    """Return brands enriched with topic_count + primary category.

    Production columns assumed: id, name, industry, target_market,
    description, aliases. NULL-tolerant via COALESCE in SQL.
    """
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT id,
                       name,
                       COALESCE(NULLIF(industry, ''), 'Uncategorized') AS industry,
                       COALESCE(NULLIF(target_market, ''), '') AS target_market,
                       COALESCE(description, '') AS description,
                       aliases
                FROM brands
                ORDER BY id
                """
                )
            )
        )
        .mappings()
        .all()
    )
    brands = [dict(r) for r in rows]

    if not brands:
        return []

    counts_rows = (
        (
            await session.execute(
                text(
                    """
                SELECT brand_id, COUNT(*)::int AS topic_count
                FROM topics
                GROUP BY brand_id
                """
                )
            )
        )
        .mappings()
        .all()
    )
    topic_counts = {r["brand_id"]: int(r["topic_count"] or 0) for r in counts_rows}

    primary_category_rows = (
        (
            await session.execute(
                text(
                    """
                SELECT DISTINCT ON (brand_id) brand_id, category
                FROM topics
                WHERE category IS NOT NULL AND category <> ''
                ORDER BY brand_id, created_at DESC NULLS LAST, id DESC
                """
                )
            )
        )
        .mappings()
        .all()
    )
    primary_categories = {r["brand_id"]: r["category"] for r in primary_category_rows}

    for row in brands:
        industry = row.get("industry") or "Uncategorized"
        category = primary_categories.get(row["id"]) or ""
        row["id"] = int(row["id"])
        row["industry_id"] = industry
        row["industry_name"] = industry
        row["category_id"] = category
        row["category_name"] = category
        row["topic_count"] = int(topic_counts.get(row["id"], 0))
        aliases = row.get("aliases")
        if isinstance(aliases, str):
            try:
                aliases = json.loads(aliases)
            except Exception:
                aliases = [aliases]
        row["aliases"] = aliases if isinstance(aliases, list) else []
        row["selected"] = False
    return brands


async def fetch_categories(session: AsyncSession) -> list[dict[str, str]]:
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT DISTINCT category
                FROM topics
                WHERE category IS NOT NULL AND category <> ''
                ORDER BY category
                LIMIT 200
                """
                )
            )
        )
        .mappings()
        .all()
    )
    return [{"id": r["category"], "name": r["category"]} for r in rows]


def scope_brands(
    all_brands: list[dict[str, Any]],
    *,
    industry_id: str | None = None,
    brand_ids: list[int] | None = None,
) -> list[dict[str, Any]]:
    brand_id_set = {int(x) for x in brand_ids or []}
    out: list[dict[str, Any]] = []
    for brand in all_brands:
        if industry_id and brand.get("industry_id") != industry_id:
            continue
        if brand_id_set and int(brand["id"]) not in brand_id_set:
            continue
        out.append(brand)
    return out


# ---------------------------------------------------------------------------
# pending summary + coverage
# ---------------------------------------------------------------------------


async def pending_summary(
    session: AsyncSession,
    *,
    brand_ids: list[int] | None = None,
    run_id: str | None = None,
) -> dict[str, int]:
    where: list[str] = ["status = 'pending'"]
    params: dict[str, Any] = {}
    if run_id:
        where.append("run_id = :run_id")
        params["run_id"] = run_id
    elif brand_ids:
        where.append("brand_id = ANY(:brand_ids)")
        params["brand_ids"] = brand_ids
    sql = text(
        f"""
        SELECT COUNT(*)::int AS pending,
               SUM(CASE WHEN COALESCE(confidence, 0) < 0.75 THEN 1 ELSE 0 END)::int
                   AS low_confidence
        FROM topic_candidates
        WHERE {" AND ".join(where)}
        """
    )
    row = (await session.execute(sql, params)).mappings().one()
    return {
        "pending": int(row.get("pending") or 0),
        "low_confidence": int(row.get("low_confidence") or 0),
    }


async def _no_prompt_count(session: AsyncSession, brand_ids: list[int]) -> int:
    if not brand_ids:
        return 0
    row = (
        (
            await session.execute(
                text(
                    """
                SELECT COUNT(*)::int AS cnt
                FROM topics t
                LEFT JOIN prompts p ON p.topic_id = t.id
                WHERE t.brand_id = ANY(:brand_ids) AND p.id IS NULL
                """
                ),
                {"brand_ids": brand_ids},
            )
        )
        .mappings()
        .one()
    )
    return int(row.get("cnt") or 0)


async def _topic_rows_for_brands(
    session: AsyncSession,
    brand_ids: list[int],
    category_id: str | None = None,
) -> list[dict[str, Any]]:
    if not brand_ids:
        return []
    where = ["brand_id = ANY(:brand_ids)"]
    params: dict[str, Any] = {"brand_ids": brand_ids}
    if category_id:
        where.append("category = :category_id")
        params["category_id"] = category_id
    sql = text(
        f"""
        SELECT id, brand_id, text, category
        FROM topics
        WHERE {" AND ".join(where)}
        ORDER BY brand_id, id
        """
    )
    return [dict(r) for r in (await session.execute(sql, params)).mappings().all()]


async def build_coverage(
    session: AsyncSession,
    brands: list[dict[str, Any]],
    *,
    category_id: str | None = None,
    max_per_brand: int = 40,
) -> dict[str, Any]:
    """Compute per-brand coverage rows + gaps + summary stats."""
    selected_brand_ids = [int(b["id"]) for b in brands]
    topic_rows = await _topic_rows_for_brands(session, selected_brand_ids, category_id)
    topics_by_brand: dict[int, list[dict[str, Any]]] = {bid: [] for bid in selected_brand_ids}
    for topic in topic_rows:
        topics_by_brand.setdefault(int(topic["brand_id"]), []).append(topic)

    desired_dimensions = ["brand", "product", "category", "scenario", "question"]
    per_dim_target = max(1, round(max_per_brand / len(desired_dimensions)))
    rows: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    total_rate = 0.0
    for brand in brands:
        brand_id = int(brand["id"])
        brand_topics = topics_by_brand.get(brand_id, [])
        dim_counts = {d: 0 for d in desired_dimensions}
        for t in brand_topics:
            d = map_dimension(t.get("category"))
            dim_counts[d] = dim_counts.get(d, 0) + 1

        coverage_rate = min(1.0, len(brand_topics) / max(max_per_brand, 1))
        total_rate += coverage_rate
        brand_gap_count = 0
        for dimension in desired_dimensions:
            missing = max(per_dim_target - dim_counts.get(dimension, 0), 0)
            if missing <= 0:
                continue
            brand_gap_count += missing
            priority = "P1" if coverage_rate < 0.6 else "P2"
            gaps.append(
                {
                    "brand_id": brand_id,
                    "brand": brand["name"],
                    "type": dimension,
                    "count": missing,
                    "priority": priority,
                    "coverage_gap": f"{brand['name']}:{dimension}",
                }
            )

        rows.append(
            {
                "brand_id": brand_id,
                "brand": brand["name"],
                "topics": len(brand_topics),
                "coverage_rate": round(coverage_rate, 4),
                "coverage": f"{round(coverage_rate * 100)}%",
                "gaps": brand_gap_count,
                "status": "达标" if coverage_rate >= 0.8 else "待补齐",
                "status_key": "ok" if coverage_rate >= 0.8 else "gap",
                "dimension_counts": dim_counts,
            }
        )

    pending = await pending_summary(session, brand_ids=selected_brand_ids)
    no_prompt = await _no_prompt_count(session, selected_brand_ids)
    avg_rate = total_rate / len(brands) if brands else 0.0
    summary = {
        "brand_count": len(brands),
        "topic_count": sum(r["topics"] for r in rows),
        "average_coverage": round(avg_rate, 4),
        "coverage_label": f"{round(avg_rate * 100)}%",
        "gap_count": sum(r["gaps"] for r in rows),
        "pending_candidates": pending["pending"],
        "low_confidence": pending["low_confidence"],
        "no_prompt_topics": no_prompt,
    }
    return {"rows": rows, "gaps": gaps, "summary": summary, "existing_topics": topic_rows}


# ---------------------------------------------------------------------------
# topics list (heaviest read)
# ---------------------------------------------------------------------------


def _dimension_label(dimension: str | None) -> str:
    return {
        "brand": "品牌",
        "product": "产品",
        "category": "品类",
        "scenario": "场景",
        "question": "问题",
    }.get(dimension or "", dimension or "未分类")


def _source_label(generated_by: str | None) -> str:
    value = (generated_by or "").strip().lower()
    if value == "topic_plan":
        return "审核通过"
    if value.startswith("seed"):
        return "初始化"
    return "已有 Topic"


def _topic_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    dimension = map_dimension(row.get("category"))
    prompt_count = int(row.get("prompt_count") or 0)
    query_count = int(row.get("query_count") or 0)
    brand_name = row.get("brand_name") or f"Brand #{row.get('brand_id')}"
    return {
        "id": f"T-{row.get('id')}",
        "raw_id": row.get("id"),
        "title": row.get("text") or "",
        "dimension": _dimension_label(dimension),
        "dimension_key": dimension,
        "industry": row.get("industry") or "Uncategorized",
        "source": _source_label(row.get("generated_by")),
        "status": row.get("status") or "active",
        "promptCount": prompt_count,
        "queryCount": query_count,
        "brands": [brand_name],
        "brand": brand_name,
        "brand_id": row.get("brand_id"),
        "createdAt": _isoformat(row.get("created_at")),
        "confidence": 1.0,
    }


def _topics_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    with_prompt = sum(1 for r in rows if r.get("promptCount", 0) > 0)
    category_count = sum(1 for r in rows if r.get("dimension_key") == "category")
    generated_count = sum(1 for r in rows if r.get("source") in {"初始化", "审核通过"})
    prompt_rate = (with_prompt / total) if total else 0
    category_rate = (category_count / total) if total else 0
    generated_rate = (generated_count / total) if total else 0
    return {
        "totalTopics": total,
        "visibleTopics": total,
        "promptCoverageLabel": f"{round(prompt_rate * 100)}%",
        "promptCoverageMeta": f"{with_prompt} / {total}",
        "categoryShareLabel": f"{round(category_rate * 100)}%",
        "llmGeneratedLabel": f"{round(generated_rate * 100)}%",
    }


async def fetch_topics(
    session: AsyncSession,
    *,
    industry_id: str | None = None,
    category_id: str | None = None,
    brand_ids: list[int] | None = None,
    dimension: str | None = None,
    status: str | None = None,
    query: str | None = None,
    limit: int = 200,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    where = ["1=1"]
    params: dict[str, Any] = {"limit": limit}
    if brand_ids:
        where.append("t.brand_id = ANY(:brand_ids)")
        params["brand_ids"] = brand_ids
    if industry_id:
        where.append("b.industry = :industry_id")
        params["industry_id"] = industry_id
    if category_id:
        where.append("t.category = :category_id")
        params["category_id"] = category_id
    if status and status != "all":
        where.append("COALESCE(t.status, 'active') = :status")
        params["status"] = status
    if query:
        where.append(
            "(t.text ILIKE :like OR b.name ILIKE :like OR ('T-' || t.id::text) ILIKE :like)"
        )
        params["like"] = f"%{query}%"

    sql = text(
        f"""
        SELECT t.id, t.brand_id, t.text, t.category, t.generated_by,
               COALESCE(t.status, 'active') AS status, t.created_at,
               b.name AS brand_name,
               COALESCE(NULLIF(b.industry, ''), 'Uncategorized') AS industry,
               COALESCE(pc.prompt_count, 0)::int AS prompt_count,
               COALESCE(qc.query_count, 0)::int AS query_count
        FROM topics t
        JOIN brands b ON b.id = t.brand_id
        LEFT JOIN (
            SELECT topic_id, COUNT(*)::int AS prompt_count
            FROM prompts GROUP BY topic_id
        ) pc ON pc.topic_id = t.id
        LEFT JOIN (
            SELECT p.topic_id, COUNT(q.id)::int AS query_count
            FROM prompts p
            LEFT JOIN queries q ON q.prompt_id = p.id
            GROUP BY p.topic_id
        ) qc ON qc.topic_id = t.id
        WHERE {" AND ".join(where)}
        ORDER BY t.created_at DESC NULLS LAST, t.id DESC
        LIMIT :limit
        """
    )
    raw = [dict(r) for r in (await session.execute(sql, params)).mappings().all()]
    rows = [_topic_row_to_dict(r) for r in raw]
    if dimension:
        rows = [r for r in rows if r.get("dimension_key") == dimension]
    return rows, _topics_summary(rows)


# ---------------------------------------------------------------------------
# candidates list (uses ORM via session.execute(text)) — same shape as the
# ``_topic_plan_candidate_row`` helper in admin_console.app.py
# ---------------------------------------------------------------------------


def _candidate_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "run_id": row.get("run_id"),
        "title": row.get("title"),
        "brand_id": row.get("brand_id"),
        "brand": row.get("brand_name"),
        "dimension": row.get("dimension"),
        "reason": row.get("reason"),
        "confidence": float(row.get("confidence") or 0),
        "coverage_gap": row.get("coverage_gap"),
        "status": row.get("status"),
        "review_reason": row.get("review_reason"),
        "approved_topic_id": row.get("approved_topic_id"),
        "created_at": _isoformat(row.get("created_at")),
        "reviewed_at": _isoformat(row.get("reviewed_at")),
    }


async def fetch_candidates(
    session: AsyncSession,
    *,
    status: str = "pending",
    brand_ids: list[int] | None = None,
    query: str | None = None,
    limit: int = 100,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: dict[str, Any] = {"limit": limit}
    if run_id:
        where.append("run_id = :run_id")
        params["run_id"] = run_id
    if status and status != "all":
        where.append("status = :status")
        params["status"] = status
    if brand_ids:
        where.append("brand_id = ANY(:brand_ids)")
        params["brand_ids"] = brand_ids
    if query:
        where.append(
            "(title ILIKE :like OR brand_name ILIKE :like "
            "OR reason ILIKE :like OR coverage_gap ILIKE :like OR id ILIKE :like)"
        )
        params["like"] = f"%{query}%"
    where_clause = "WHERE " + " AND ".join(where) if where else ""
    sql = text(
        f"""
        SELECT *
        FROM topic_candidates
        {where_clause}
        ORDER BY created_at DESC
        LIMIT :limit
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    return [_candidate_row_to_dict(dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# topic_plan_runs
# ---------------------------------------------------------------------------


def run_to_dict(run: TopicPlanRun, *, elapsed_seconds: float | None = None) -> dict[str, Any]:
    request_config = run.request_config if isinstance(run.request_config, dict) else {}
    metrics = run.metrics_json if isinstance(run.metrics_json, dict) else {}
    if elapsed_seconds is None:
        end = run.completed_at or _now()
        start = run.started_at or run.created_at or _now()
        elapsed_seconds = max(0.0, (end - start).total_seconds())
    return {
        "id": run.id,
        "status": run.status,
        "admin_id": run.admin_id,
        "industry_id": run.industry_id,
        "category_id": run.category_id,
        "brand_ids": run.brand_ids if isinstance(run.brand_ids, list) else [],
        "request_config": request_config,
        "estimated_topics": int(request_config.get("max_topics") or 0),
        "candidates_generated": int(run.candidates_generated or 0),
        "llm_model": run.llm_model,
        "llm_usage": run.llm_usage_json if isinstance(run.llm_usage_json, dict) else {},
        "llm_error": run.llm_error,
        "metrics": metrics,
        "started_at": _isoformat(run.started_at),
        "completed_at": _isoformat(run.completed_at),
        "created_at": _isoformat(run.created_at),
        "updated_at": _isoformat(run.updated_at),
        "elapsed_seconds": float(elapsed_seconds or 0),
    }


def run_timeout_seconds(run: TopicPlanRun) -> int:
    request_config = run.request_config if isinstance(run.request_config, dict) else {}
    estimated = bounded_int(request_config.get("max_topics"), 180, 1, 2000)
    default_timeout = max(600, min(3600, estimated * 10))
    return bounded_int(os.getenv("TOPIC_PLAN_RUN_TIMEOUT_SECONDS"), default_timeout, 120, 7200)


async def mark_stale_run(session: AsyncSession, run: TopicPlanRun) -> bool:
    """If ``run.status == 'running'`` and last-progress is older than the
    configured timeout, flip it to ``failed`` with ``llm_error =
    'topic_plan_run_timeout'``. Returns True iff a flip happened.
    """
    if run.status != "running":
        return False
    last_progress = run.updated_at or run.started_at or run.created_at
    if not last_progress:
        return False
    elapsed = (_now() - last_progress).total_seconds()
    if elapsed <= run_timeout_seconds(run):
        return False
    run.status = "failed"
    run.llm_error = "topic_plan_run_timeout"
    run.completed_at = _now()
    run.updated_at = _now()
    await session.commit()
    await session.refresh(run)
    return True


# ---------------------------------------------------------------------------
# generation orchestration helpers (used by Phase 3 B.2.b POST /generate)
# ---------------------------------------------------------------------------


def merge_usage(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Sum numeric ``usage`` fields across LLM calls; preserve other keys."""
    merged = dict(left or {})
    for key, value in (right or {}).items():
        if isinstance(value, int | float) and isinstance(merged.get(key), int | float):
            merged[key] += value
        elif key not in merged:
            merged[key] = value
    return merged


def compute_generation_metrics(
    *,
    requested: int,
    accepted: int,
    skipped: list[dict[str, Any]],
    batches: int,
    llm_model: str | None,
    llm_returned: int | None = None,
    rejected_sample_size: int = 20,
) -> dict[str, Any]:
    """Aggregate per-reason rejection counts + a small rejected-item sample.

    Sample is capped (default 20 × ~200B = ~4 KB) so the JSONB column
    stays compact. ``quality_blocked`` flips True iff every LLM-returned
    candidate was rejected.
    """
    by_reason: dict[str, int] = {}
    for s in skipped or []:
        r = s.get("reason") or "unknown"
        by_reason[r] = by_reason.get(r, 0) + 1
    rejected_sample: list[dict[str, str]] = []
    seen_reasons: dict[str, int] = {}
    per_reason_cap = max(1, rejected_sample_size // max(len(by_reason), 1))
    for s in skipped or []:
        r = s.get("reason") or "unknown"
        if seen_reasons.get(r, 0) >= per_reason_cap:
            continue
        rejected_sample.append({"text": s.get("title") or s.get("text") or "", "reason": r})
        seen_reasons[r] = seen_reasons.get(r, 0) + 1
        if len(rejected_sample) >= rejected_sample_size:
            break
    rejected_total = len(skipped or [])
    accepted_total = int(accepted or 0)
    return {
        "requested": int(requested or 0),
        "accepted": accepted_total,
        "rejected_total": rejected_total,
        "by_reason": by_reason,
        "batches": int(batches or 0),
        "llm_model": llm_model,
        "llm_returned": int(llm_returned) if llm_returned is not None else None,
        "rejected_sample": rejected_sample,
        "quality_blocked": accepted_total == 0 and rejected_total > 0,
    }


def topic_plan_brand_batches(
    brands: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    *,
    max_topics: int,
    max_per_brand: int,
) -> Iterator[tuple[list[dict[str, Any]], list[dict[str, Any]], int]]:
    """Yield (batch_brands, batch_gaps, batch_cap) — one slice per LLM call.

    Brands without gaps are skipped entirely (no LLM call). Batch size is
    controlled by ``TOPIC_PLAN_LLM_BRANDS_PER_REQUEST`` (default 1, max 5).
    """
    batch_size = bounded_int(os.getenv("TOPIC_PLAN_LLM_BRANDS_PER_REQUEST"), 1, 1, 5)
    gaps_by_brand: dict[int, list[dict[str, Any]]] = {}
    for gap in gaps or []:
        try:
            brand_id = int(gap.get("brand_id"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        gaps_by_brand.setdefault(brand_id, []).append(gap)
    if not gaps_by_brand:
        return

    gap_brands = [b for b in brands if int(b["id"]) in gaps_by_brand]
    for index in range(0, len(gap_brands), batch_size):
        batch_brands = gap_brands[index : index + batch_size]
        batch_brand_ids = {int(b["id"]) for b in batch_brands}
        batch_gaps = [
            g
            for g in gaps
            if str(g.get("brand_id") or "").isdigit() and int(g.get("brand_id")) in batch_brand_ids  # type: ignore[arg-type]
        ]
        gap_count = sum(bounded_int(g.get("count"), 1, 1, max_per_brand) for g in batch_gaps)
        batch_cap = min(max_topics, max_per_brand * max(len(batch_brands), 1), max(gap_count, 1))
        yield batch_brands, batch_gaps, batch_cap


async def is_run_cancelled(session: AsyncSession, run_id: str) -> bool:
    """Return True iff topic_plan_runs.status == 'cancelled' for ``run_id``."""
    if not run_id:
        return False
    try:
        row = (
            await session.execute(
                text("SELECT status FROM topic_plan_runs WHERE id = :run_id"),
                {"run_id": run_id},
            )
        ).first()
    except Exception:
        return False
    if row is None:
        return False
    return str(row[0] or "").lower() == "cancelled"


async def fetch_products_by_brand(
    session: AsyncSession, product_ids: list[int]
) -> dict[int, list[dict[str, Any]]]:
    """Group active rows from ``products`` (upstream stub) by brand_id."""
    if not product_ids:
        return {}
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT id, brand_id, name, sku, category, description, aliases
                FROM products
                WHERE id = ANY(:ids) AND status = 'active'
                """
                ),
                {"ids": product_ids},
            )
        )
        .mappings()
        .all()
    )
    out: dict[int, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(int(r["brand_id"]), []).append(
            {
                "id": int(r["id"]),
                "name": r["name"],
                "sku": r["sku"],
                "category": r["category"],
                "description": r["description"],
                "aliases": r["aliases"] or [],
            }
        )
    return out


async def fetch_pending_candidate_titles(session: AsyncSession, brand_ids: list[int]) -> list[str]:
    """Pending TopicCandidate titles for the given brand_ids (real ORM table)."""
    if not brand_ids:
        return []
    from genpano_models import TopicCandidate
    from sqlalchemy import select

    stmt = select(TopicCandidate.title).where(
        TopicCandidate.brand_id.in_(brand_ids),
        TopicCandidate.status == "pending",
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [t for t in rows if t]


async def update_run_progress(
    session: AsyncSession,
    *,
    run_id: str,
    llm_model: str | None,
    usage: dict[str, Any],
    candidates_generated: int,
) -> None:
    """Write LLM model / usage / candidates_generated to a still-active run."""
    from genpano_models import TopicPlanRun
    from sqlalchemy import select

    run = (
        await session.execute(select(TopicPlanRun).where(TopicPlanRun.id == run_id))
    ).scalar_one_or_none()
    if run is None or run.status in {"cancelled", "failed"}:
        return
    run.llm_model = llm_model
    run.llm_usage_json = dict(usage)
    run.candidates_generated = candidates_generated
    run.updated_at = _now()
    await session.commit()


async def finalize_run(
    session: AsyncSession,
    *,
    run_id: str,
    status: str,
    llm_model: str | None,
    usage: dict[str, Any],
    candidates_generated: int,
    metrics: dict[str, Any] | None = None,
    llm_error: str | None = None,
) -> None:
    """Mark a run terminal (status ∈ {completed, failed, cancelled})."""
    from genpano_models import TopicPlanRun
    from sqlalchemy import select

    run = (
        await session.execute(select(TopicPlanRun).where(TopicPlanRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        return
    # Don't override cancelled with failed if a stop landed mid-batch.
    if run.status == "cancelled" and status == "failed":
        return
    run.status = status
    run.llm_model = llm_model
    if usage:
        run.llm_usage_json = dict(usage)
    run.candidates_generated = candidates_generated
    if metrics is not None:
        run.metrics_json = dict(metrics)
    if llm_error is not None:
        run.llm_error = llm_error
    run.completed_at = _now()
    run.updated_at = _now()
    await session.commit()


def topic_plan_run_failed_status_code(error_code: str | None) -> int:
    """Map a TopicPlanLLMError code to an HTTP status (mirrors admin_console)."""
    return 503 if str(error_code or "").startswith("llm_") else 502


# ---------------------------------------------------------------------------
# topic delete (Phase 3 B.3)
# ---------------------------------------------------------------------------


def parse_topic_id(value: Any) -> int:
    """Accept ``42``, ``"42"`` or ``"T-42"``; raise ValueError on garbage."""
    text_v = str(value or "").strip()
    if text_v.upper().startswith("T-"):
        text_v = text_v[2:]
    if not text_v.isdigit():
        raise ValueError("invalid_topic_id")
    return int(text_v)


def parse_topic_ids(value: Any) -> list[int]:
    """Validate + dedupe a list of topic ids."""
    if not isinstance(value, list):
        raise ValueError("topic_ids_required")
    out: list[int] = []
    for item in value:
        topic_id = parse_topic_id(item)
        if topic_id not in out:
            out.append(topic_id)
    return out


async def topic_dependency_counts(
    session: AsyncSession, topic_ids: list[int]
) -> dict[int, dict[str, int]]:
    """For each topic id, return {prompt_count, query_count}.

    Joined raw SQL against the ``prompts`` / ``queries`` upstream stubs;
    a topic is considered "blocked" iff prompt_count > 0 OR query_count > 0.
    """
    counts = {int(t): {"prompt_count": 0, "query_count": 0} for t in topic_ids}
    if not topic_ids:
        return counts
    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT p.topic_id,
                           COUNT(DISTINCT p.id)::int AS prompt_count,
                           COUNT(q.id)::int AS query_count
                    FROM prompts p
                    LEFT JOIN queries q ON q.prompt_id = p.id
                    WHERE p.topic_id = ANY(:ids)
                    GROUP BY p.topic_id
                    """
                ),
                {"ids": topic_ids},
            )
        )
        .mappings()
        .all()
    )
    for row in rows:
        topic_id = int(row["topic_id"])
        counts[topic_id] = {
            "prompt_count": int(row.get("prompt_count") or 0),
            "query_count": int(row.get("query_count") or 0),
        }
    return counts


async def delete_topic_plan_topics(
    session: AsyncSession, topic_ids: list[int]
) -> dict[str, list[Any]]:
    """Delete topics by id with FK-aware blocking.

    Returns ``{deleted: [...], blocked: [...], missing: [...]}``:
    - ``deleted``: topics that had no prompts/queries and were removed
    - ``blocked``: topics with downstream dependencies — kept, with counts
    - ``missing``: ids that didn't exist in the topics table

    Side-effect: clears ``topic_candidates.approved_topic_id`` on the
    deleted ids so review history doesn't reference gone rows.
    """
    if not topic_ids:
        return {"deleted": [], "blocked": [], "missing": []}

    rows = (
        (
            await session.execute(
                text(
                    """
                    SELECT t.id, t.brand_id, t.text, t.category,
                           COALESCE(t.status, 'active') AS status,
                           b.name AS brand_name,
                           COALESCE(NULLIF(b.industry, ''), 'Uncategorized') AS industry
                    FROM topics t
                    LEFT JOIN brands b ON b.id = t.brand_id
                    WHERE t.id = ANY(:ids)
                    ORDER BY t.id
                    """
                ),
                {"ids": topic_ids},
            )
        )
        .mappings()
        .all()
    )
    found_ids = {int(row["id"]) for row in rows}
    missing = [t for t in topic_ids if t not in found_ids]
    deps = await topic_dependency_counts(session, list(found_ids))

    blocked: list[dict[str, Any]] = []
    deletable_ids: list[int] = []
    for row in rows:
        topic_id = int(row["id"])
        dep = deps.get(topic_id, {"prompt_count": 0, "query_count": 0})
        if dep["prompt_count"] > 0 or dep["query_count"] > 0:
            blocked.append(
                {
                    "id": f"T-{topic_id}",
                    "raw_id": topic_id,
                    "title": row.get("text"),
                    "brand": row.get("brand_name"),
                    "prompt_count": dep["prompt_count"],
                    "query_count": dep["query_count"],
                    "reason": "has_downstream_dependencies",
                }
            )
        else:
            deletable_ids.append(topic_id)

    deleted: list[dict[str, Any]] = []
    if deletable_ids:
        await session.execute(
            text(
                """
                UPDATE topic_candidates
                SET approved_topic_id = NULL,
                    updated_at = NOW()
                WHERE approved_topic_id = ANY(:ids)
                """
            ),
            {"ids": deletable_ids},
        )
        result = await session.execute(
            text("DELETE FROM topics WHERE id = ANY(:ids) RETURNING id"),
            {"ids": deletable_ids},
        )
        deleted_ids = {int(r[0]) for r in result.fetchall()}
        deleted = [
            {
                "id": f"T-{int(row['id'])}",
                "raw_id": int(row["id"]),
                "title": row.get("text"),
                "brand": row.get("brand_name"),
                "industry": row.get("industry"),
            }
            for row in rows
            if int(row["id"]) in deleted_ids
        ]
        await session.commit()

    return {"deleted": deleted, "blocked": blocked, "missing": missing}
