"""Async SQLAlchemy ports of admin_console.app.py's prompt_matrix SQL helpers.

Same pattern as ``app/admin/topic_plan/db.py`` — production postgres
schema assumed; sqlite tests mock these helpers. ``brands`` / ``topics``
/ ``prompts`` / ``queries`` are upstream stubs in backend's ORM (only
``id`` modeled per ADR-002), so all queries against them go through
``session.execute(text(...))``. ``prompt_candidates`` / ``prompt_generation_runs``
are real ORM models and exercised end-to-end in tests.

Helpers (parity with admin_console.app.py):
- fetch_brand_rows                     brands list with industry / aliases
- fetch_topics                         paged topics with prompt_count + intent /
                                        language coverage + dimension / coverage
- fetch_prompts                        paged prompts with topic+brand metadata
- fetch_candidates                     paged prompt_candidates (ORM-backed)
- candidate_status_counts              {pending, approved, rejected, all}
- prompts_distribution                 {intent: count} / {language: count}
- category_purity                      brand-leak count for category dimension
- compute_stats                        full /config + /prompts dashboard stats
- gaps_for_topics                      Phase 4 /gaps response
- quality_gates                        pure-Python gate cards for /config
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from genpano_models import PromptCandidate
from sqlalchemy import desc, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.prompt_matrix.lib import (
    ALLOWED_INTENTS,
    ALLOWED_LANGUAGES,
    detect_brand_leaks,
    intent_language_combinations,
)
from app.admin.topic_plan.db import map_dimension


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# brands
# ---------------------------------------------------------------------------


async def fetch_brand_rows(session: AsyncSession) -> list[dict[str, Any]]:
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT id,
                       name,
                       COALESCE(NULLIF(industry, ''), 'Uncategorized') AS industry,
                       aliases
                FROM brands
                ORDER BY name
                """
                )
            )
        )
        .mappings()
        .all()
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        aliases = r.get("aliases")
        if isinstance(aliases, str):
            try:
                aliases = json.loads(aliases)
            except Exception:
                aliases = [aliases]
        out.append(
            {
                "id": int(r["id"]),
                "name": r.get("name") or f"Brand #{r['id']}",
                "industry_id": r.get("industry") or "Uncategorized",
                "industry_name": r.get("industry") or "Uncategorized",
                "aliases": aliases if isinstance(aliases, list) else [],
            }
        )
    return out


# ---------------------------------------------------------------------------
# topics — paged, prompt-count / intent-language coverage enriched
# ---------------------------------------------------------------------------


def _topic_required_sets(
    intent_count: int | None, language_count: int | None
) -> tuple[set[str], set[str]]:
    """Resolve the intent / language coverage targets per filters."""
    from app.admin.prompt_matrix.lib import selected_intents, selected_languages

    return (
        set(selected_intents(intent_count or len(ALLOWED_INTENTS))),
        set(selected_languages(language_count or len(ALLOWED_LANGUAGES))),
    )


def _topic_row_to_dict(
    row: dict[str, Any],
    required_intents: set[str],
    required_languages: set[str],
) -> dict[str, Any]:
    raw_id = int(row["id"])
    dimension = map_dimension(row.get("category"))
    prompt_intents = {
        str(v) for v in (row.get("prompt_intents") or []) if v and str(v) in ALLOWED_INTENTS
    }
    prompt_languages = {
        str(v) for v in (row.get("prompt_languages") or []) if v and str(v) in ALLOWED_LANGUAGES
    }
    prompt_count = int(row.get("prompt_count") or 0)
    missing_intents = sorted(required_intents - prompt_intents)
    missing_languages = sorted(required_languages - prompt_languages)
    coverage = "covered"
    if prompt_count == 0:
        coverage = "gap"
    elif missing_intents or missing_languages:
        coverage = "partial"
    leak_count = int(row.get("brand_leak_count") or 0)
    if dimension == "category" and leak_count > 0:
        coverage = "risk"

    updated = row.get("updated_at") or row.get("created_at")
    return {
        "id": f"T-{raw_id}",
        "raw_id": raw_id,
        "title": row.get("text") or "",
        "brand": row.get("brand_name") or f"Brand #{row.get('brand_id')}",
        "brand_id": row.get("brand_id"),
        "industry": row.get("industry") or "Uncategorized",
        "industry_id": row.get("industry") or "Uncategorized",
        "dimension": {
            "brand": "品牌",
            "product": "产品",
            "category": "品类",
            "scenario": "场景",
            "question": "问题",
        }.get(dimension, dimension or "未分类"),
        "dimension_key": dimension,
        "coverage": coverage,
        "coverageLabel": {
            "gap": "No Prompt",
            "partial": "Intent / language gap",
            "risk": "Quality risk",
            "covered": "Covered",
        }.get(coverage, coverage),
        "priority": "P0"
        if coverage == "risk"
        else ("P1" if coverage == "gap" else ("P2" if coverage == "partial" else "P3")),
        "updatedAt": _isoformat(updated) or "",
        "prompt_count": prompt_count,
        "prompt_intents": sorted(prompt_intents),
        "prompt_languages": sorted(prompt_languages),
        "missing_intents": missing_intents,
        "missing_languages": missing_languages,
        "brand_leak_count": leak_count,
        "selected": False,
    }


async def fetch_topics(
    session: AsyncSession,
    *,
    filters: dict[str, Any] | None = None,
    page: int = 1,
    per_page: int = 20,
    topic_ids: list[int] | None = None,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    """Paged topic list with prompt-count + intent/language coverage.

    Heavy aggregation: joins topics + brands + prompts (group-by topic_id
    for prompt_count / distinct intents / distinct languages). The dimension
    + coverage filters are applied in Python after the SQL aggregation
    matches admin_console behavior.
    """
    filters = filters or {}
    required_intents, required_languages = _topic_required_sets(
        filters.get("intent_count"), filters.get("language_count")
    )

    where: list[str] = ["1=1"]
    params: dict[str, Any] = {}
    if topic_ids:
        where.append("t.id = ANY(:topic_ids)")
        params["topic_ids"] = topic_ids
    if filters.get("brand_id"):
        where.append("t.brand_id = :brand_id")
        params["brand_id"] = int(filters["brand_id"])
    if filters.get("industry_id"):
        where.append("COALESCE(NULLIF(b.industry, ''), 'Uncategorized') = :industry_id")
        params["industry_id"] = filters["industry_id"]
    query = filters.get("q")
    if query:
        where.append(
            "(t.text ILIKE :like OR b.name ILIKE :like OR ('T-' || t.id::text) ILIKE :like)"
        )
        params["like"] = f"%{query}%"

    sql = text(
        f"""
        SELECT t.id, t.brand_id, t.text, t.category,
               t.created_at, COALESCE(t.updated_at, t.created_at) AS updated_at,
               b.name AS brand_name,
               COALESCE(NULLIF(b.industry, ''), 'Uncategorized') AS industry,
               COALESCE(pm.prompt_count, 0)::int AS prompt_count,
               COALESCE(pm.prompt_intents, ARRAY[]::text[]) AS prompt_intents,
               COALESCE(pm.prompt_languages, ARRAY[]::text[]) AS prompt_languages,
               0::int AS brand_leak_count
        FROM topics t
        JOIN brands b ON b.id = t.brand_id
        LEFT JOIN (
            SELECT topic_id,
                   COUNT(id)::int AS prompt_count,
                   ARRAY_REMOVE(ARRAY_AGG(DISTINCT NULLIF(intent, '')), NULL) AS prompt_intents,
                   ARRAY_REMOVE(ARRAY_AGG(DISTINCT NULLIF(language, '')), NULL) AS prompt_languages
            FROM prompts
            WHERE COALESCE(status, 'active') = 'active'
            GROUP BY topic_id
        ) pm ON pm.topic_id = t.id
        WHERE {" AND ".join(where)}
          AND COALESCE(t.status, 'active') <> 'archived'
        ORDER BY t.created_at DESC NULLS LAST, t.id DESC
        """
    )
    raw_rows = (await session.execute(sql, params)).mappings().all()
    rows = [_topic_row_to_dict(dict(r), required_intents, required_languages) for r in raw_rows]
    dimension = filters.get("dimension")
    if dimension:
        rows = [r for r in rows if r.get("dimension_key") == dimension]
    coverage = filters.get("coverage") or "all"
    if coverage != "all":
        rows = [r for r in rows if r.get("coverage") == coverage]

    total = len(rows)
    page = max(int(page or 1), 1)
    per_page = max(1, min(int(per_page or 20), 20000))
    start = (page - 1) * per_page
    paged = rows[start : start + per_page]
    summary = {
        "topicsTotal": total,
        "matchingTopics": total,
        "topicsNoPrompt": sum(1 for r in rows if r["coverage"] == "gap"),
        "topicsPartialIntent": sum(1 for r in rows if r["coverage"] == "partial"),
        "topicsRisk": sum(1 for r in rows if r["coverage"] == "risk"),
    }
    return paged, total, summary


# ---------------------------------------------------------------------------
# prompts — paged list for SPA "Prompts" table
# ---------------------------------------------------------------------------


def _prompt_row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"P-{row['id']}",
        "raw_id": int(row["id"]),
        "topic_id": int(row.get("topic_id") or 0) or None,
        "topic_text": row.get("topic_text"),
        "brand_id": row.get("brand_id"),
        "brand_name": row.get("brand_name"),
        "intent": row.get("intent"),
        "language": row.get("language"),
        "text": row.get("text"),
        "status": row.get("status") or "active",
        "created_at": _isoformat(row.get("created_at")),
    }


async def fetch_prompts(
    session: AsyncSession,
    *,
    intent: str | None = None,
    language: str | None = None,
    query: str | None = None,
    page: int = 1,
    per_page: int = 50,
    topic_ids: list[int] | None = None,
) -> tuple[list[dict[str, Any]], int]:
    where: list[str] = ["COALESCE(p.status, 'active') = 'active'"]
    params: dict[str, Any] = {}
    if intent:
        where.append("p.intent = :intent")
        params["intent"] = intent
    if language:
        where.append("p.language = :language")
        params["language"] = language
    if topic_ids:
        where.append("p.topic_id = ANY(:topic_ids)")
        params["topic_ids"] = topic_ids
    if query:
        where.append("p.text ILIKE :like")
        params["like"] = f"%{query}%"

    count_row = (
        (
            await session.execute(
                text(f"SELECT COUNT(*)::int AS cnt FROM prompts p WHERE {' AND '.join(where)}"),
                params,
            )
        )
        .mappings()
        .one()
    )
    total = int(count_row["cnt"] or 0)

    page = max(int(page or 1), 1)
    per_page = max(1, min(int(per_page or 50), 100))
    offset = (page - 1) * per_page
    list_params = dict(params)
    list_params["limit"] = per_page
    list_params["offset"] = offset

    sql = text(
        f"""
        SELECT p.id, p.topic_id, p.intent, p.language, p.text,
               COALESCE(p.status, 'active') AS status, p.created_at,
               t.text AS topic_text, t.brand_id,
               b.name AS brand_name
        FROM prompts p
        LEFT JOIN topics t ON t.id = p.topic_id
        LEFT JOIN brands b ON b.id = t.brand_id
        WHERE {" AND ".join(where)}
        ORDER BY p.created_at DESC NULLS LAST, p.id DESC
        LIMIT :limit OFFSET :offset
        """
    )
    raw = (await session.execute(sql, list_params)).mappings().all()
    return [_prompt_row_to_dict(dict(r)) for r in raw], total


# ---------------------------------------------------------------------------
# candidates — paged list (ORM-backed; prompt_candidates is a real model)
# ---------------------------------------------------------------------------


def _candidate_row_to_dict(c: PromptCandidate) -> dict[str, Any]:
    return {
        "id": c.id,
        "run_id": c.run_id,
        "topic_id": c.topic_id,
        "topic_text": c.topic_text,
        "brand_id": c.brand_id,
        "brand_name": c.brand_name,
        "dimension": c.dimension,
        "intent": c.intent,
        "language": c.language,
        "template_strategy": c.template_strategy,
        "template_version": c.template_version,
        "text": c.text,
        "status": c.status,
        "confidence": float(c.confidence or 0),
        "reason": c.reason,
        "duplicate_of": c.duplicate_of,
        "tags": c.tags or {},
        "review_reason": c.review_reason,
        "approved_prompt_id": c.approved_prompt_id,
        "created_at": _isoformat(c.created_at),
        "reviewed_at": _isoformat(c.reviewed_at),
    }


async def fetch_candidates(
    session: AsyncSession,
    *,
    status: str = "pending",
    query: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    base = select(PromptCandidate)
    count_stmt = select(func.count(PromptCandidate.id))
    if status and status != "all":
        base = base.where(PromptCandidate.status == status)
        count_stmt = count_stmt.where(PromptCandidate.status == status)
    if query:
        like = f"%{query}%"
        cond = or_(
            PromptCandidate.text.ilike(like),
            PromptCandidate.brand_name.ilike(like),
            PromptCandidate.id.ilike(like),
        )
        base = base.where(cond)
        count_stmt = count_stmt.where(cond)

    total = int((await session.execute(count_stmt)).scalar() or 0)
    base = base.order_by(desc(PromptCandidate.created_at)).limit(limit).offset(offset)
    rows = list((await session.execute(base)).scalars().all())
    return [_candidate_row_to_dict(c) for c in rows], total


async def candidate_status_counts(
    session: AsyncSession, *, query: str | None = None
) -> dict[str, int]:
    base = select(PromptCandidate.status, func.count(PromptCandidate.id)).group_by(
        PromptCandidate.status
    )
    if query:
        like = f"%{query}%"
        base = base.where(
            or_(
                PromptCandidate.text.ilike(like),
                PromptCandidate.brand_name.ilike(like),
                PromptCandidate.id.ilike(like),
            )
        )
    rows = (await session.execute(base)).all()
    counts: dict[str, int] = {"pending": 0, "approved": 0, "rejected": 0}
    for status_val, count in rows:
        counts[str(status_val)] = int(count or 0)
    counts["all"] = sum(counts.values())
    return counts


# ---------------------------------------------------------------------------
# stats / quality gates / category purity
# ---------------------------------------------------------------------------


async def prompts_distribution(
    session: AsyncSession, *, column: str, allowed_values: tuple[str, ...]
) -> dict[str, int]:
    if column not in {"intent", "language"}:
        raise ValueError("invalid column")
    rows = (
        (
            await session.execute(
                text(
                    f"""
                SELECT {column} AS value, COUNT(*)::int AS count
                FROM prompts
                WHERE COALESCE(status, 'active') = 'active'
                GROUP BY {column}
                """
                )
            )
        )
        .mappings()
        .all()
    )
    out = dict.fromkeys(allowed_values, 0)
    for r in rows:
        v = r.get("value")
        if v in out:
            out[v] = int(r.get("count") or 0)
    return out


async def category_purity(
    session: AsyncSession, known_brands: list[dict[str, Any]]
) -> dict[str, Any]:
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT p.id, p.text, t.category
                FROM prompts p
                JOIN topics t ON t.id = p.topic_id
                WHERE t.category IS NOT NULL
                  AND COALESCE(p.status, 'active') = 'active'
                """
                )
            )
        )
        .mappings()
        .all()
    )
    total = 0
    leaks = 0
    for r in rows:
        if map_dimension(r.get("category")) != "category":
            continue
        total += 1
        if detect_brand_leaks(r.get("text") or "", known_brands):
            leaks += 1
    return {"total": total, "brandLeaks": leaks, "status": "pass" if leaks == 0 else "fail"}


async def compute_stats(session: AsyncSession) -> dict[str, Any]:
    """Aggregate /config + /prompts dashboard stats."""
    known_brands = await fetch_brand_rows(session)
    all_rows, total_topics, topic_summary = await fetch_topics(
        session,
        filters={"intent_count": len(ALLOWED_INTENTS), "language_count": len(ALLOWED_LANGUAGES)},
        page=1,
        per_page=20000,
    )
    prompts_count_row = (
        (
            await session.execute(
                text(
                    "SELECT COUNT(*)::int AS cnt FROM prompts "
                    "WHERE COALESCE(status, 'active') = 'active'"
                )
            )
        )
        .mappings()
        .one()
    )
    total_prompts = int(prompts_count_row["cnt"] or 0)

    topics_with_prompt = sum(1 for r in all_rows if int(r.get("prompt_count") or 0) > 0)
    coverage_pct = round((topics_with_prompt / total_topics) * 100, 1) if total_topics else 0
    intent_counts = await prompts_distribution(
        session, column="intent", allowed_values=ALLOWED_INTENTS
    )
    lang_counts = await prompts_distribution(
        session, column="language", allowed_values=ALLOWED_LANGUAGES
    )
    total_intent = sum(intent_counts.values()) or 1
    total_lang = sum(lang_counts.values()) or 1

    colors = {
        "informational": "#3B82F6",
        "commercial": "#8B5CF6",
        "transactional": "#0ABB87",
        "navigational": "#F5A623",
    }
    labels = {
        "informational": "信息了解",
        "commercial": "购买决策",
        "transactional": "行动导向",
        "navigational": "定向查找",
    }
    lang_labels = {"zh-CN": "中文", "en-US": "英文"}
    lang_routing = {"zh-CN": "调度时路由", "en-US": "调度时路由"}

    last_run_row = (
        (
            await session.execute(
                text(
                    "SELECT created_at FROM prompt_generation_runs ORDER BY created_at DESC LIMIT 1"
                )
            )
        )
        .mappings()
        .first()
    )
    last_run_at = _isoformat(last_run_row["created_at"]) if last_run_row else None

    return {
        "lastRunAt": last_run_at or "Never",
        "topicsWithPrompt": topics_with_prompt,
        "topicsTotal": total_topics,
        "topicsNoPrompt": topic_summary.get("topicsNoPrompt", 0),
        "topicsPartialIntent": topic_summary.get("topicsPartialIntent", 0),
        "coveragePct": coverage_pct,
        "totalPrompts": total_prompts,
        "intentDist": [
            {
                "intent": intent,
                "label": labels[intent],
                "count": intent_counts[intent],
                "pct": round((intent_counts[intent] / total_intent) * 100),
                "color": colors[intent],
            }
            for intent in ALLOWED_INTENTS
        ],
        "langDist": [
            {
                "lang": lang,
                "label": lang_labels[lang],
                "count": lang_counts[lang],
                "pct": round((lang_counts[lang] / total_lang) * 100),
                "engines": lang_routing[lang],
                "routing": "deferred_to_query_pool",
            }
            for lang in ALLOWED_LANGUAGES
        ],
        "categoryPromptPurity": await category_purity(session, known_brands),
    }


def quality_gates(
    stats: dict[str, Any], pending_count: int = 0, duplicate_count: int = 0
) -> list[dict[str, Any]]:
    purity = stats.get("categoryPromptPurity") or {}
    brand_leaks = int(purity.get("brandLeaks") or 0)
    return [
        {
            "title": "矩阵覆盖",
            "value": f"{stats.get('coveragePct', 0)}%",
            "tone": "success" if float(stats.get("coveragePct") or 0) >= 80 else "warning",
            "meta": f"{stats.get('topicsWithPrompt', 0)} / {stats.get('topicsTotal', 0)} topics",
        },
        {
            "title": "待审核",
            "value": str(pending_count),
            "tone": "warning" if pending_count else "success",
            "meta": "Prompt candidates",
        },
        {
            "title": "品类纯净",
            "value": "0 泄露" if brand_leaks == 0 else f"{brand_leaks} 泄露",
            "tone": "success" if brand_leaks == 0 else "danger",
            "meta": "Category topics must not mention brands",
        },
        {
            "title": "相似重复",
            "value": str(duplicate_count),
            "tone": "warning" if duplicate_count else "success",
            "meta": "Duplicate candidates / prompts",
        },
    ]


# ---------------------------------------------------------------------------
# gaps — Phase 4 /gaps response
# ---------------------------------------------------------------------------


async def gaps_for_topics(
    session: AsyncSession,
    *,
    topic_ids: list[int] | None = None,
    filters: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    cfg = config or {
        "intent_count": len(ALLOWED_INTENTS),
        "language_count": len(ALLOWED_LANGUAGES),
        "max_per_topic": 4,
    }
    if topic_ids:
        topics, _total, _summary = await fetch_topics(
            session, filters={**cfg, **(filters or {})}, page=1, per_page=limit, topic_ids=topic_ids
        )
    else:
        merged = {**(filters or {}), **cfg}
        topics, _total, _summary = await fetch_topics(
            session, filters=merged, page=1, per_page=limit
        )
    combo_count = len(
        intent_language_combinations(
            cfg.get("intent_count"),
            cfg.get("language_count"),
            cfg.get("max_per_topic", 4),
        )
    )
    gaps: list[dict[str, Any]] = []
    for topic in topics:
        reasons: list[str] = []
        if topic["coverage"] == "gap":
            reasons.append("No Prompt")
        if topic.get("missing_intents"):
            reasons.append("Missing intent: " + ", ".join(topic["missing_intents"]))
        if topic.get("missing_languages"):
            reasons.append("Missing language: " + ", ".join(topic["missing_languages"]))
        if topic.get("brand_leak_count"):
            reasons.append("Category brand leak risk")
        if not reasons:
            continue
        gaps.append(
            {
                "id": f"PG-{topic['raw_id']}",
                "topic_id": topic["raw_id"],
                "topic": topic["title"],
                "gap": " / ".join(reasons),
                "priority": topic["priority"],
                "estimate": combo_count
                if topic["coverage"] == "gap"
                else max(
                    1,
                    len(topic.get("missing_intents") or [])
                    + len(topic.get("missing_languages") or []),
                ),
            }
        )
    return gaps[:limit]


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------


def parse_int_list(value: Any) -> list[int]:
    if value is None:
        return []
    raw = value if isinstance(value, list) else str(value).split(",")
    out: list[int] = []
    for item in raw:
        text_v = str(item).strip()
        if not text_v:
            continue
        try:
            n = int(text_v)
        except ValueError as exc:
            raise ValueError("invalid integer list") from exc
        if n not in out:
            out.append(n)
    return out


def parse_topic_id(value: Any) -> int:
    text_v = str(value or "").strip()
    if text_v.upper().startswith("T-"):
        text_v = text_v[2:]
    if not text_v.isdigit():
        raise ValueError("invalid_topic_id")
    return int(text_v)


def parse_topic_ids(value: Any) -> list[int]:
    if value is None:
        return []
    raw = value if isinstance(value, list) else str(value).split(",")
    out: list[int] = []
    for item in raw:
        text_v = str(item).strip()
        if not text_v:
            continue
        out.append(parse_topic_id(text_v))
    return out


def filter_payload_from_query(source: dict[str, Any]) -> dict[str, Any]:
    """Mirror admin_console._prompt_matrix_filter_payload — accepts a plain
    dict (request.args / payload). Raises ValueError on bad input."""
    brand_id_raw = source.get("brand_id")
    if brand_id_raw in ("", None, "all") or isinstance(brand_id_raw, list):
        brand_id: int | None = None
    else:
        try:
            brand_id = int(str(brand_id_raw))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_brand_id") from exc

    dimension = (source.get("dimension") or "").strip().lower() or None
    if dimension and dimension not in {"brand", "product", "category", "scenario", "question"}:
        raise ValueError("invalid_dimension")

    coverage = (source.get("coverage") or "all").strip().lower()
    if coverage not in {"all", "gap", "partial", "covered", "risk"}:
        raise ValueError("invalid_coverage")

    def _clamp(value: Any, default: int, lo: int, hi: int) -> int:
        try:
            n = int(value)
        except (TypeError, ValueError):
            n = default
        return max(lo, min(n, hi))

    return {
        "q": (source.get("q") or source.get("search") or "").strip(),
        "brand_id": brand_id,
        "industry_id": (source.get("industry_id") or "").strip() or None,
        "dimension": dimension,
        "coverage": coverage,
        "intent_count": _clamp(source.get("intent_count"), 4, 1, len(ALLOWED_INTENTS)),
        "language_count": _clamp(source.get("language_count"), 2, 1, len(ALLOWED_LANGUAGES)),
    }


# ---------------------------------------------------------------------------
# generate-route helpers (Phase 4 slice 3)
# ---------------------------------------------------------------------------


async def fetch_topic_rows_by_ids(
    session: AsyncSession, topic_ids: list[int], config: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Fetch enriched topic rows by id (preserves order requested)."""
    if not topic_ids:
        return []
    config = config or {
        "intent_count": len(ALLOWED_INTENTS),
        "language_count": len(ALLOWED_LANGUAGES),
    }
    rows, _total, _summary = await fetch_topics(
        session,
        filters={
            "intent_count": config["intent_count"],
            "language_count": config["language_count"],
        },
        page=1,
        per_page=len(topic_ids) + 50,
        topic_ids=topic_ids,
    )
    by_id = {int(r["raw_id"]): r for r in rows}
    return [by_id[i] for i in topic_ids if i in by_id]


async def fetch_existing_prompt_texts(session: AsyncSession, *, topic_ids: list[int]) -> list[str]:
    """Active prompt + pending candidate texts for de-dupe seed."""
    if not topic_ids:
        return []
    prompt_rows = (
        await session.execute(
            text(
                """
                SELECT text FROM prompts
                WHERE topic_id = ANY(:ids)
                  AND COALESCE(status, 'active') = 'active'
                  AND text IS NOT NULL AND text <> ''
                """
            ),
            {"ids": topic_ids},
        )
    ).all()
    candidate_rows = (
        await session.execute(
            select(PromptCandidate.text).where(
                PromptCandidate.topic_id.in_(topic_ids),
                PromptCandidate.status == "pending",
            )
        )
    ).all()
    return [r[0] for r in prompt_rows if r[0]] + [r[0] for r in candidate_rows if r[0]]


def parse_selection(payload: dict[str, Any]) -> tuple[list[int], dict[str, Any]]:
    """Pull topic_ids out of an operator's /generate POST body.

    Two shapes accepted (matching admin_console):
    - explicit ``{"topic_ids": [1, "T-2", ...]}``
    - implicit selection ``{"selection": {"topic_ids": [...]}}``

    Returns ``(topic_ids, snapshot)``. snapshot is preserved into
    ``request_config`` for audit trail.
    """
    explicit = payload.get("topic_ids")
    if explicit is not None:
        try:
            ids = [parse_topic_id(x) for x in (explicit if isinstance(explicit, list) else [])]
        except ValueError as exc:
            raise ValueError("invalid_topic_ids") from exc
        return list(dict.fromkeys(ids)), {"topic_ids": list(dict.fromkeys(ids))}

    selection = payload.get("selection")
    if isinstance(selection, dict) and isinstance(selection.get("topic_ids"), list):
        try:
            ids = [parse_topic_id(x) for x in selection["topic_ids"]]
        except ValueError as exc:
            raise ValueError("invalid_topic_ids") from exc
        return list(dict.fromkeys(ids)), dict(selection)

    return [], {}
