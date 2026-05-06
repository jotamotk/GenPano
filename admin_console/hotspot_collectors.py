"""Hotspot collectors for the Admin console (Module D-2.5).

This module is intentionally self-contained so the ``admin_console`` Docker
image — which does not ship the ``geo_tracker`` package — can run the
``POST /api/admin/hot-topics/collect`` endpoint without
``ModuleNotFoundError: No module named 'geo_tracker'``. Celery beat keeps
using ``geo_tracker.hotspots.pipeline`` (the worker container does ship that
package) for the browser-based collectors that need a logged-in account.

Sources implemented here (no browser, no login):

* ``baidu``       — 百度热搜 PC endpoint (returns title, summary, hot score, url)
* ``zhihu``       — 知乎热榜 desktop API (returns title, excerpt, hot text, url)
* ``weibo``       — 微博热搜 PC sidebar API (no login required for top-50)
* ``toutiao``     — 今日头条热榜 PC endpoint (covers ByteDance trends; serves as
                    an admin-side substitute for Douyin which now requires a
                    signed cookie that the browser collector in geo_tracker
                    handles separately)
* ``llm_search``  — Doubao 2 / Volcengine Ark prompted to enumerate trending
                    topics for the given industry. Replaces the previous
                    placeholder stub so admin can populate hotspots via LLM.

Each collector returns ``[]`` on failure (timeout, schema drift, anti-bot
block) so a single broken source never aborts a multi-source cycle. Errors
are surfaced to the API caller via the ``errors`` map in
``run_collection_cycle``'s return value.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

try:
    from .topic_plan import TopicPlanLLMError, load_doubao_config, strip_markdown_fence
except ImportError:  # pragma: no cover - flat-layout fallback (Docker image)
    from topic_plan import TopicPlanLLMError, load_doubao_config, strip_markdown_fence


# ─── Endpoint constants ──────────────────────────────────────────────────

BAIDU_API_URL = "https://top.baidu.com/api/board?platform=pc&tab=realtime"
ZHIHU_API_URL = (
    "https://api.zhihu.com/topstory/hot-list?"
    "limit=50&reverse_order=0&desktop=true"
)
WEIBO_API_URL = "https://weibo.com/ajax/side/hotSearch"
TOUTIAO_API_URL = (
    "https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc"
)

DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

ALLOWED_SOURCES = {"baidu", "zhihu", "weibo", "toutiao", "llm_search"}


@dataclass
class HotspotCandidate:
    title: str
    summary: str | None = None
    category: str | None = None
    source: str = "unknown"
    source_url: str | None = None
    raw_rank: int | None = None
    raw_metric: str | None = None
    industry: str | None = None
    extras: dict = field(default_factory=dict)


# ─── HTTP helpers ────────────────────────────────────────────────────────

def _http_get_json(url: str, *, timeout: int = 15, headers: dict | None = None) -> Any:
    import urllib.request

    base_headers = {
        "User-Agent": DESKTOP_UA,
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    if headers:
        base_headers.update(headers)
    req = urllib.request.Request(url, headers=base_headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - admin only
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


# ─── Baidu 热搜 (PC) ─────────────────────────────────────────────────────

def collect_baidu(*, limit: int = 30) -> list[HotspotCandidate]:
    """Pull 百度热搜 (实时榜) via the PC endpoint.

    Note: the mobile (``platform=wise``) endpoint nests the items one level
    deeper inside ``cards[0].content[0].content`` and strips ``desc`` /
    ``hotScore`` to ``None``. The PC endpoint keeps the full payload at
    ``cards[0].content`` which is what we want for admin review.
    """
    try:
        payload = _http_get_json(
            BAIDU_API_URL,
            headers={"Referer": "https://top.baidu.com/"},
        )
    except Exception as e:
        print(f"[hotspots.baidu] collect failed: {e}")
        return []

    cards = (payload.get("data") or {}).get("cards") or []
    if not cards:
        return []

    inner = cards[0].get("content") or []
    # Defensive: the wise/mobile shape (one wrapper dict whose own ``content``
    # holds the items) shows up occasionally on PC too, so handle both.
    if inner and isinstance(inner[0], dict) and "word" not in inner[0] \
            and isinstance(inner[0].get("content"), list):
        inner = inner[0]["content"]

    out: list[HotspotCandidate] = []
    for i, item in enumerate(inner[:limit]):
        if not isinstance(item, dict):
            continue
        title = (item.get("word") or item.get("query") or "").strip()
        if not title:
            continue
        out.append(
            HotspotCandidate(
                title=title,
                summary=(item.get("desc") or "").strip() or None,
                source="baidu",
                source_url=item.get("url") or item.get("rawUrl"),
                raw_rank=i + 1,
                raw_metric=(f"热度 {item.get('hotScore', '')}".strip() or None)
                if item.get("hotScore")
                else None,
            )
        )
    return out


# ─── 知乎热榜 ────────────────────────────────────────────────────────────

def _zhihu_web_url(api_url: str | None, item_id: Any) -> str | None:
    """Convert the API ``api.zhihu.com/questions/{id}`` URL into a user-facing
    ``www.zhihu.com/question/{id}`` link. Falls back to the raw URL or ``None``
    when nothing usable is available."""
    if item_id:
        return f"https://www.zhihu.com/question/{item_id}"
    if not api_url:
        return None
    m = re.search(r"/questions?/(\d+)", api_url)
    if m:
        return f"https://www.zhihu.com/question/{m.group(1)}"
    return api_url


def collect_zhihu(*, limit: int = 30) -> list[HotspotCandidate]:
    try:
        payload = _http_get_json(
            ZHIHU_API_URL,
            headers={"Referer": "https://www.zhihu.com/hot"},
        )
    except Exception as e:
        print(f"[hotspots.zhihu] collect failed: {e}")
        return []

    items = payload.get("data") or []
    out: list[HotspotCandidate] = []
    for i, item in enumerate(items[:limit]):
        if not isinstance(item, dict):
            continue
        target = item.get("target") or {}
        title = (target.get("title") or item.get("query") or "").strip()
        if not title:
            continue
        out.append(
            HotspotCandidate(
                title=title,
                summary=(target.get("excerpt") or "").strip() or None,
                source="zhihu",
                source_url=_zhihu_web_url(target.get("url"), target.get("id")),
                raw_rank=i + 1,
                raw_metric=(item.get("detail_text") or "").strip() or None,
            )
        )
    return out


# ─── 微博热搜 (PC sidebar) ──────────────────────────────────────────────

def collect_weibo(*, limit: int = 30) -> list[HotspotCandidate]:
    """Public PC sidebar endpoint. Returns 50 items — ranked, with hot value
    and a ``label_name`` flag (热 / 新 / 沸 / 爆). No login or visitor cookie
    required."""
    try:
        payload = _http_get_json(
            WEIBO_API_URL,
            headers={"Referer": "https://weibo.com/"},
        )
    except Exception as e:
        print(f"[hotspots.weibo] collect failed: {e}")
        return []

    items = (payload.get("data") or {}).get("realtime") or []
    out: list[HotspotCandidate] = []
    for i, item in enumerate(items[:limit]):
        if not isinstance(item, dict):
            continue
        title = (item.get("word") or item.get("note") or "").strip()
        if not title:
            continue
        # Weibo sometimes flags promoted items with ``is_ad`` / ``ad_id``.
        # Filter them out so admin doesn't see paid placements as "热点".
        if item.get("is_ad") or item.get("ad_id"):
            continue
        scheme = (item.get("word_scheme") or "").strip().strip("#")
        title_clean = scheme or title
        try:
            from urllib.parse import quote as _quote

            search_url = (
                "https://s.weibo.com/weibo?q="
                + _quote("#" + (scheme or title_clean) + "#")
            )
        except Exception:  # pragma: no cover - defensive
            search_url = None
        try:
            num = int(item.get("num") or 0)
        except (TypeError, ValueError):
            num = 0
        out.append(
            HotspotCandidate(
                title=title_clean[:240],
                summary=None,
                source="weibo",
                source_url=search_url,
                raw_rank=int(item.get("rank") or i) + 1,
                raw_metric=(f"{item.get('label_name') or ''} {num}".strip() or None)
                if (item.get("label_name") or num)
                else None,
            )
        )
    return out


# ─── Toutiao 热榜 (covers ByteDance / Douyin trends without browser) ─────

# Toutiao surfaces the ByteDance trending pool on its desktop site, which
# overlaps heavily with Douyin's 抖音热点 list. Using the public hot-board
# endpoint is the only way to cover that trend pool from a no-browser
# environment — the iesdouyin / aweme.snssdk APIs are 403-protected
# without a signed __ac_nonce cookie, and the dedicated DouyinHotsCollector
# (browser-use + camoufox) lives in the worker container, not admin_console.
TOUTIAO_CATEGORY_TO_INDUSTRY = {
    "tech": "数码科技",
    "digital": "数码科技",
    "internet": "互联网",
    "finance": "财经",
    "stock": "财经",
    "auto": "汽车",
    "estate": "房产",
    "real_estate": "房产",
    "education": "教育",
    "health": "健康医疗",
    "medical": "健康医疗",
    "travel": "旅游",
    "fashion": "时尚",
    "beauty": "美妆个护",
    "mom_kid": "母婴个护",
    "baby": "母婴个护",
    "food": "食品饮料",
    "sports": "体育",
    "entertainment": "娱乐",
    "movie": "影视",
    "tv": "影视",
    "game": "游戏",
    "military": "军事",
    "society": "社会",
    "politics": "时政",
    "world": "国际",
    "history": "历史",
    "culture": "文化",
    "agriculture": "三农",
}


def _toutiao_industry(categories: Any) -> str | None:
    if not isinstance(categories, list):
        return None
    for raw in categories:
        if not isinstance(raw, str):
            continue
        mapped = TOUTIAO_CATEGORY_TO_INDUSTRY.get(raw.strip().lower())
        if mapped:
            return mapped
    return None


def collect_toutiao(*, limit: int = 30) -> list[HotspotCandidate]:
    try:
        payload = _http_get_json(
            TOUTIAO_API_URL,
            headers={"Referer": "https://www.toutiao.com/"},
        )
    except Exception as e:
        print(f"[hotspots.toutiao] collect failed: {e}")
        return []

    items = payload.get("data") or []
    out: list[HotspotCandidate] = []
    for i, item in enumerate(items[:limit]):
        if not isinstance(item, dict):
            continue
        title = (item.get("Title") or item.get("QueryWord") or "").strip()
        if not title:
            continue
        try:
            hot = int(item.get("HotValue") or 0)
        except (TypeError, ValueError):
            hot = 0
        out.append(
            HotspotCandidate(
                title=title[:240],
                summary=(item.get("Abstract") or "").strip() or None,
                source="toutiao",
                source_url=(item.get("Url") or "").strip() or None,
                raw_rank=i + 1,
                raw_metric=(f"热度 {hot}" if hot else None),
                industry=_toutiao_industry(item.get("InterestCategory")),
                category=(item.get("LabelDesc") or item.get("Label") or None) or None,
            )
        )
    return out


# ─── LLM search (Doubao) ────────────────────────────────────────────────

def _build_llm_search_messages(industry: str | None, limit: int, brand_context: dict[str, Any] | None = None) -> list[dict]:
    industry_label = (industry or "").strip()
    brand_context = brand_context or {}
    brand_name = str(brand_context.get("name") or "").strip()
    scope_text = (
        f"行业：{industry_label}"
        if industry_label
        else "行业：通用消费 / 大众生活 / 数码 / 社会 (覆盖面尽量广)"
    )
    if brand_name:
        scope_text += (
            "\n"
            + json.dumps(
                {
                    "brand": brand_name,
                    "brand_aliases": brand_context.get("aliases") or [],
                    "target_market": brand_context.get("target_market") or "",
                    "brand_description": brand_context.get("description") or "",
                },
                ensure_ascii=False,
            )
        )
    schema = {
        "hotspots": [
            {
                "title": "...简洁的中文标题，来自真实社媒/搜索/新闻热点 (不超过 40 字)",
                "summary": "...一两句中文摘要，给 LLM 当上下文用",
                "category": "...如：舆论事件/政策/明星/产品发布/赛事/争议/榜单",
                "industry": "...该热点最贴合的中文行业标签 (优先使用上面给定的行业)",
                "source_url": "...如有可信链接则填，否则留空字符串",
                "raw_rank": 0,
            }
        ]
    }
    system = (
        "你是 GENPANO 的『热点雷达』助手。给定一个行业，你需要列举该行业下最近 7 天"
        "在中文互联网（微博 / 知乎 / 小红书 / 抖音 / 新闻媒体）正在讨论的热点话题。"
        "只返回严格 JSON，不要包含 markdown 代码块、解释或 ``` 围栏。"
        "要求：每个 hotspot 必须是真实存在或近期合理流行的话题，不要凭空捏造品牌活动或政策。"
        "若不确定，使用更宽泛的行业级话题，不要瞎编名字、价格、日期。"
    )
    user = (
        f"{scope_text}\n"
        f"请按热度从高到低输出最多 {limit} 条热点，每条都要写明 title / summary / category / industry。\n"
        "不要重复、不要拼装多个话题、不要把品牌名作为 title，不要写营销/CRM/私域口吻。\n"
        "title 应像普通用户在搜索框里会输入或在朋友圈讨论的样子。\n"
        "JSON Schema 示例:\n"
        + json.dumps(schema, ensure_ascii=False)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_llm_search_response(raw: str) -> list[dict[str, Any]]:
    """Parse Doubao response into hotspot dicts. Tolerant of code-fences and
    bare JSON arrays."""
    cleaned = strip_markdown_fence(raw or "")
    if not cleaned:
        return []
    try:
        parsed: Any = json.loads(cleaned)
    except Exception:
        try:
            from json_repair import repair_json  # type: ignore

            parsed = json.loads(repair_json(cleaned))
        except Exception:
            m = re.search(r"\{[\s\S]*\}", cleaned)
            if not m:
                return []
            try:
                parsed = json.loads(m.group(0))
            except Exception:
                return []

    if isinstance(parsed, list):
        items = parsed
    elif isinstance(parsed, dict):
        items = parsed.get("hotspots") or parsed.get("items") or parsed.get("data") or []
    else:
        return []

    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def collect_llm_search(
    *,
    industry: str | None = None,
    brand_context: dict[str, Any] | None = None,
    limit: int = 20,
    client_factory=None,
) -> list[HotspotCandidate]:
    """Ask Doubao for trending topics in ``industry`` and parse them into
    HotspotCandidate items. Returns ``[]`` if Doubao is not configured or the
    call fails — the pipeline must keep working when LLM is offline.

    ``client_factory`` is injected for unit tests; production code uses the
    OpenAI-compatible Volcengine Ark endpoint.
    """
    try:
        cfg = load_doubao_config()
    except TopicPlanLLMError as e:
        print(f"[hotspots.llm_search] doubao not configured: {e}")
        return []
    except Exception as e:  # pragma: no cover - defensive
        print(f"[hotspots.llm_search] config load failed: {e}")
        return []

    if not getattr(cfg, "api_key", None):
        return []

    if client_factory is None:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as e:  # pragma: no cover - environment dependent
            print(f"[hotspots.llm_search] openai client unavailable: {e}")
            return []

        def _default_factory(api_key, base_url):
            return OpenAI(api_key=api_key, base_url=base_url)

        client_factory = _default_factory

    try:
        client = client_factory(cfg.api_key, cfg.base_url)
    except Exception as e:
        print(f"[hotspots.llm_search] client init failed: {e}")
        return []

    messages = _build_llm_search_messages(industry, limit, brand_context=brand_context)

    try:
        response = client.chat.completions.create(
            model=cfg.model,
            messages=messages,
            temperature=0.2,
            timeout=60,
        )
    except Exception as e:
        print(f"[hotspots.llm_search] doubao call failed: {e}")
        return []

    try:
        content = response.choices[0].message.content or ""
    except Exception:
        content = ""

    raw_items = _parse_llm_search_response(content)
    out: list[HotspotCandidate] = []
    for i, item in enumerate(raw_items[:limit]):
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        try:
            rank = int(item.get("raw_rank") or (i + 1))
        except (TypeError, ValueError):
            rank = i + 1
        source_url = str(item.get("source_url") or "").strip() or None
        # Reject obvious placeholders like the legacy
        # "[LLM-search placeholder] X trending #1" or generic stub-bracketed
        # titles the LLM occasionally emits when it has nothing real.
        lower_title = title.lower()
        if (
            "placeholder" in lower_title
            or lower_title.startswith("[llm")
            or lower_title.startswith("[example")
            or (title.startswith("[") and title.endswith("]"))
        ):
            continue
        out.append(
            HotspotCandidate(
                title=title[:240],
                summary=(str(item.get("summary") or "").strip() or None),
                category=(str(item.get("category") or "").strip() or None),
                source="llm_search",
                source_url=source_url,
                raw_rank=rank,
                industry=(str(item.get("industry") or industry or "").strip() or None),
            )
        )
    return out


# ─── Pipeline ────────────────────────────────────────────────────────────

COLLECTORS = {
    "baidu": collect_baidu,
    "zhihu": collect_zhihu,
    "weibo": collect_weibo,
    "toutiao": collect_toutiao,
    "llm_search": collect_llm_search,
}


def _normalize_title(text: str) -> str:
    return "".join((text or "").split()).lower()


def _dedupe(items: Iterable[HotspotCandidate]) -> list[HotspotCandidate]:
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


def run_collection_cycle(
    *,
    sources: list[str] | None = None,
    industry_filter: str | None = None,
    brand_context: dict[str, Any] | None = None,
    per_source_limit: int = 30,
    get_db=None,
) -> dict:
    """Run the configured collectors and persist deduped drafts.

    Returns ``{"collected": int, "inserted": int, "by_source": {...},
    "errors": {...}}``. ``get_db`` is injected so the function stays
    importable in unit tests without a Flask app context.
    """
    requested = sources or list(COLLECTORS.keys())
    candidates: list[HotspotCandidate] = []
    by_source: dict[str, int] = {}
    errors: dict[str, str] = {}

    for name in requested:
        fn = COLLECTORS.get(name)
        if not fn:
            errors[name] = "unknown_source"
            continue
        try:
            if name == "llm_search":
                if brand_context is not None:
                    items = fn(industry=industry_filter, brand_context=brand_context, limit=per_source_limit)
                else:
                    items = fn(industry=industry_filter, limit=per_source_limit)
            else:
                items = fn(limit=per_source_limit)
            by_source[name] = len(items)
            for it in items:
                if industry_filter and it.industry and it.industry != industry_filter:
                    continue
                candidates.append(it)
        except Exception as e:
            errors[name] = str(e)[:200]
            by_source[name] = 0

    candidates = _dedupe(candidates)

    inserted = 0
    if candidates:
        if get_db is None:
            try:
                from .app import get_db as _get_db  # type: ignore
            except ImportError:
                from app import get_db as _get_db  # type: ignore
            get_db = _get_db
        try:
            conn = get_db()
        except Exception as e:
            errors["__persist__"] = f"get_db unavailable: {e}"
            return {
                "collected": len(candidates),
                "inserted": 0,
                "by_source": by_source,
                "errors": errors,
            }
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
                        (
                            c.title[:256],
                            c.summary,
                            c.category,
                            c.source,
                            c.source_url,
                            c.raw_rank,
                            c.raw_metric,
                            c.industry or industry_filter,
                            (brand_context or {}).get("id"),
                        ),
                    )
                    inserted += 1
            conn.commit()
        except Exception as e:
            errors["__persist__"] = str(e)[:200]
            try:
                conn.rollback()
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    return {
        "collected": len(candidates),
        "inserted": inserted,
        "by_source": by_source,
        "errors": errors,
    }
