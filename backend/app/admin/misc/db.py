"""DB operations for misc admin routes (Phase 9 slice 9f).

Backs queries-by-day (calendar + grouped list) and backfill_citations.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.misc.lib import (
    deduplicate_citations,
    extract_citations_from_text,
    extract_hrefs,
)

logger = logging.getLogger(__name__)


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


async def _table_exists(session: AsyncSession, name: str) -> bool:
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


async def queries_by_day_month(
    session: AsyncSession,
    *,
    month: str,
    llm: str | None = None,
    profile_id: str | None = None,
) -> list[dict[str, Any]]:
    """Calendar heat-map data — one row per day for the given YYYY-MM."""
    if not await _table_exists(session, "queries"):
        return []
    where = ["to_char(q.created_at, 'YYYY-MM') = :month"]
    params: dict[str, Any] = {"month": month}
    if llm:
        where.append("q.target_llm = :llm")
        params["llm"] = llm
    if profile_id:
        where.append("q.profile_id::text = :profile_id")
        params["profile_id"] = profile_id
    sql = text(
        f"""
        SELECT q.created_at::date AS day,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE LOWER(q.status)='done')    AS done,
               COUNT(*) FILTER (WHERE LOWER(q.status)='failed')  AS failed,
               COUNT(*) FILTER (WHERE LOWER(q.status)='running') AS running,
               COUNT(*) FILTER (WHERE LOWER(q.status)='pending') AS pending
        FROM queries q
        WHERE {" AND ".join(where)}
        GROUP BY q.created_at::date
        ORDER BY q.created_at::date
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    days: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        total = int(item.get("total") or 0)
        done = int(item.get("done") or 0)
        days.append(
            {
                "date": _isoformat(item.get("day")),
                "total": total,
                "done": done,
                "failed": int(item.get("failed") or 0),
                "running": int(item.get("running") or 0),
                "pending": int(item.get("pending") or 0),
                "completion_rate": (round(done * 100 / total, 1) if total else 0.0),
            }
        )
    return days


async def queries_by_day_date(
    session: AsyncSession,
    *,
    date: str,
    llm: str | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Grouped list view for a single YYYY-MM-DD. Returns
    ``{groups, totals}`` where each group is keyed by (target_llm,
    profile_id)."""
    if not await _table_exists(session, "queries"):
        return {
            "groups": [],
            "totals": {"total": 0, "done": 0, "failed": 0, "running": 0, "pending": 0},
        }
    where = ["q.created_at::date = :date"]
    params: dict[str, Any] = {"date": date}
    if llm:
        where.append("q.target_llm = :llm")
        params["llm"] = llm
    if profile_id:
        where.append("q.profile_id::text = :profile_id")
        params["profile_id"] = profile_id
    sql = text(
        f"""
        SELECT q.id,
               q.target_llm,
               LOWER(q.status) AS status,
               q.profile_id::text AS profile_id,
               p.code AS profile_code,
               p.name AS profile_name,
               q.account_id,
               a.phone_number AS account_label,
               q.query_text,
               q.created_at,
               q.executed_at,
               q.finished_at,
               q.latency_ms,
               q.retry_count,
               (SELECT COUNT(*) FROM citation_sources cs
                  JOIN llm_responses r ON r.id = cs.response_id
                 WHERE r.query_id = q.id) AS citation_count,
               (SELECT COUNT(*) FROM llm_responses r
                 WHERE r.query_id = q.id AND r.screenshot_path IS NOT NULL)
                    AS has_screenshot
        FROM queries q
        LEFT JOIN profiles p ON p.id::text = q.profile_id::text
        LEFT JOIN llm_accounts a ON a.id = q.account_id
        WHERE {" AND ".join(where)}
        ORDER BY q.target_llm, q.profile_id, q.id
        """
    )
    rows = (await session.execute(sql, params)).mappings().all()
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    totals = {"total": 0, "done": 0, "failed": 0, "running": 0, "pending": 0}
    for row in rows:
        item = dict(row)
        key = (item.get("target_llm") or "unknown", item.get("profile_id") or "—")
        bucket = groups.setdefault(
            key,
            {
                "engine": key[0],
                "profile_id": key[1],
                "profile_code": item.get("profile_code"),
                "profile_name": item.get("profile_name"),
                "queries": [],
                "done": 0,
                "failed": 0,
                "running": 0,
                "pending": 0,
                "total": 0,
            },
        )
        bucket["queries"].append(
            {
                "id": item.get("id"),
                "status": item.get("status"),
                "query_text": (item.get("query_text") or "")[:200],
                "account_id": item.get("account_id"),
                "account_label": item.get("account_label"),
                "created_at": _isoformat(item.get("created_at")),
                "executed_at": _isoformat(item.get("executed_at")),
                "finished_at": _isoformat(item.get("finished_at")),
                "latency_ms": item.get("latency_ms"),
                "retry_count": int(item.get("retry_count") or 0),
                "citation_count": int(item.get("citation_count") or 0),
                "has_screenshot": bool(item.get("has_screenshot") or 0),
            }
        )
        bucket["total"] += 1
        totals["total"] += 1
        st = item.get("status") or "pending"
        if st in bucket:
            bucket[st] += 1
        if st in totals:
            totals[st] += 1
    return {
        "groups": sorted(groups.values(), key=lambda g: (g["engine"], g["profile_id"])),
        "totals": totals,
    }


# ── backfill_citations ─────────────────────────────────────


async def backfill_citations_from_responses(
    session: AsyncSession, *, screenshot_dir: str | None = None
) -> dict[str, int]:
    """Fill llm_responses.citations_json by extracting URLs from
    raw_text + response_html + saved HTML debug files. Returns
    ``{scanned, updated}``. Empty when llm_responses is missing."""
    if not await _table_exists(session, "llm_responses"):
        return {"scanned": 0, "updated": 0}
    rows = (
        (
            await session.execute(
                text(
                    """
                SELECT r.id, r.query_id, r.raw_text, r.response_html
                FROM llm_responses r
                WHERE r.citations_json IS NULL
                  AND r.raw_text IS NOT NULL
                  AND LENGTH(r.raw_text) > 20
                """
                )
            )
        )
        .mappings()
        .all()
    )

    updated = 0
    for row in rows:
        item = dict(row)
        urls = extract_citations_from_text(item.get("raw_text"))
        if item.get("response_html"):
            urls.extend(extract_hrefs(item.get("response_html")))
        if screenshot_dir:
            urls.extend(_extract_urls_from_html_debug_files(item["query_id"], screenshot_dir))
        citations = deduplicate_citations(urls)
        if citations:
            await session.execute(
                text(
                    "UPDATE llm_responses SET citations_json = CAST(:cit AS jsonb) WHERE id = :id"
                ),
                {"cit": json.dumps(citations, ensure_ascii=False), "id": item["id"]},
            )
            updated += 1
    await session.commit()
    return {"scanned": len(rows), "updated": updated}


def _extract_urls_from_html_debug_files(query_id: int | str, screenshot_dir: str) -> list[str]:
    urls: list[str] = []
    if not os.path.isdir(screenshot_dir):
        return urls
    qid = str(query_id)
    for fname in os.listdir(screenshot_dir):
        if not fname.endswith(".html"):
            continue
        if f"query_{qid}_" not in fname:
            continue
        if "extract_fail" in fname or "content" in fname:
            fpath = os.path.join(screenshot_dir, fname)
            try:
                with open(fpath, encoding="utf-8", errors="replace") as fh:
                    urls.extend(extract_hrefs(fh.read()))
            except Exception:
                continue
    return urls


__all__ = [
    "backfill_citations_from_responses",
    "queries_by_day_date",
    "queries_by_day_month",
]
