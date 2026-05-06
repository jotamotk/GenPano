"""Run multiple collectors and persist a deduped batch as draft hot_topics.

Designed to be called both from a Beat schedule (collect on a cron) and from
the admin UI (`POST /api/admin/hot-topics/collect`).
"""
from __future__ import annotations

import os

from .base import HotspotCandidate
from .baidu import BaiduHotsCollector
from .zhihu import ZhihuHotsCollector
from .llm_search import LLMSearchCollector

COLLECTOR_REGISTRY: dict[str, type] = {
    "baidu": BaiduHotsCollector,
    "zhihu": ZhihuHotsCollector,
    "llm_search": LLMSearchCollector,
}

# Module D-B: browser-use collectors. They import camoufox + the agent
# stack lazily (inside .collect()), so import here is safe even on web-only
# deploys; the actual browser launch is gated on
# HOTSPOT_BROWSER_COLLECTORS=1 (see browser.browser_collectors_enabled).
try:
    from .weibo import WeiboHotsCollector
    from .douyin import DouyinHotsCollector
    from .xiaohongshu import XHSHotsCollector
    COLLECTOR_REGISTRY["weibo"] = WeiboHotsCollector
    COLLECTOR_REGISTRY["douyin"] = DouyinHotsCollector
    COLLECTOR_REGISTRY["xhs"] = XHSHotsCollector
except Exception as _e:
    print(f"[hotspots] browser collectors unavailable: {_e}")


def _normalize_title(text: str) -> str:
    return "".join((text or "").split()).lower()


def _dedupe(items: list[HotspotCandidate]) -> list[HotspotCandidate]:
    seen: set[str] = set()
    out: list[HotspotCandidate] = []
    for item in items:
        key = _normalize_title(item.title)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _existing_titles(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT title FROM hot_topics "
            "WHERE status IN ('draft', 'active') "
            "  AND effective_until > NOW()"
        )
        return {_normalize_title(r[0]) for r in cur.fetchall()}


def run_collection_cycle(*,
                         sources: list[str] | None = None,
                         industry_filter: str | None = None,
                         brand_context: dict | None = None,
                         brand_id: int | None = None,
                         per_source_limit: int = 30) -> dict:
    """Return ``{collected: int, inserted: int, by_source: {...}, errors: {...}}``."""
    sources = sources or list(COLLECTOR_REGISTRY.keys())
    candidates: list[HotspotCandidate] = []
    by_source: dict[str, int] = {}
    errors: dict[str, str] = {}

    for name in sources:
        cls = COLLECTOR_REGISTRY.get(name)
        if not cls:
            errors[name] = "unknown_source"
            continue
        try:
            if name == "llm_search":
                items = cls(industry=industry_filter).collect(limit=per_source_limit)
            else:
                items = cls().collect(limit=per_source_limit)
            by_source[name] = len(items)
            for it in items:
                if industry_filter and it.industry and it.industry != industry_filter:
                    continue
                candidates.append(it)
        except Exception as e:
            errors[name] = str(e)[:200]
            by_source[name] = 0

    candidates = _dedupe(candidates)

    # Persist as drafts. Skip duplicates against the existing draft+active set.
    inserted = 0
    if candidates:
        try:
            from admin_console.app import get_db
        except Exception as e:
            errors["__persist__"] = f"admin_console.app.get_db unavailable: {e}"
            return {
                "collected": len(candidates),
                "inserted": 0,
                "by_source": by_source,
                "errors": errors,
            }
        conn = get_db()
        linked_brand_id = brand_id or (brand_context or {}).get("id")
        try:
            existing = _existing_titles(conn)
            with conn.cursor() as cur:
                for c in candidates:
                    if _normalize_title(c.title) in existing:
                        continue
                    cur.execute(
                        """
                        INSERT INTO hot_topics
                            (title, summary, category, source, source_url,
                             raw_rank, raw_metric, industry, brand_id, status,
                             effective_from, effective_until)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'draft',
                                NOW(), NOW() + INTERVAL '14 days')
                        """,
                        (c.title[:256], c.summary, c.category, c.source,
                         c.source_url, c.raw_rank, c.raw_metric,
                         c.industry or industry_filter, linked_brand_id),
                    )
                    inserted += 1
            conn.commit()
        except Exception as e:
            errors["__persist__"] = str(e)[:200]
            conn.rollback()
        finally:
            conn.close()

    return {
        "collected": len(candidates),
        "inserted": inserted,
        "by_source": by_source,
        "errors": errors,
    }


def archive_expired_hotspots() -> int:
    """Module D-5 daily task. Returns the count of newly-expired rows."""
    try:
        from admin_console.app import get_db
    except Exception:
        return 0
    conn = get_db()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE hot_topics SET status = 'expired', updated_at = NOW() "
                "WHERE status = 'active' AND effective_until <= NOW()"
            )
            n = cur.rowcount
        conn.commit()
        return n
    finally:
        conn.close()


if __name__ == "__main__":
    # CLI: python -m geo_tracker.hotspots.pipeline [--sources baidu,zhihu] [--industry 母婴个护]
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", default=os.getenv("HOTSPOT_SOURCES", "baidu,zhihu"))
    parser.add_argument("--industry", default=None)
    parser.add_argument("--archive-expired", action="store_true")
    args = parser.parse_args()
    if args.archive_expired:
        print(f"archived {archive_expired_hotspots()} expired hotspots")
    else:
        srcs = [s.strip() for s in args.sources.split(",") if s.strip()]
        result = run_collection_cycle(sources=srcs, industry_filter=args.industry)
        print(result)
