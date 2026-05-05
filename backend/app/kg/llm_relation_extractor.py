"""Phase K.5 follow-up — LLM-driven relation extractor.

Augments the deterministic regex extractor in `relation_extractor.py`
with a Doubao (Volcano Ark) call that handles paraphrasing and indirect
relation phrasing the regex patterns can't catch.

Design contract:
    - Same `extract_relations()` signature returning the same dict shape
      (`entity_kind / a_id / b_id / type / confidence / evidence`)
    - 24h Redis cache keyed by hash(text + brand_index) so repeated
      calls in the daily aggregator don't replay the LLM.
    - Falls back to the regex extractor on any LLM failure (no API key,
      timeout, parse error). The output is always valid — there's no
      None/raise-from-here path.

Usage:
    from app.kg.llm_relation_extractor import extract_relations_llm
    relations = await extract_relations_llm(text, brand_index=name_to_id)

The caller stages each result into `kg_relation_candidates` exactly the
same way as the regex extractor; the only difference is `source` should
be set to "llm_v1" by the caller for evidence audits.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from typing import Any

from app.kg.relation_extractor import extract_relations

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
你是关系抽取助手. 给定一段中文/英文文本和已知的品牌列表, 提取文本中
描述的品牌之间关系. 只输出 JSON 数组, 每条关系包含字段:
  a_name (品牌名, 必须在已知列表里)
  b_name (品牌名, 必须在已知列表里, 不等于 a_name)
  type   (枚举: COMPETES_WITH | SAME_GROUP | SUBSTITUTES | UPGRADES_TO | PAIRS_WITH)
  confidence (0.0-1.0)
  snippet (原文 50 字以内, 作为证据)

关系语义:
  COMPETES_WITH - 两品牌在同一类目竞争 (如 vs 比较 / 平替 / 选哪个)
  SAME_GROUP    - A 是 B 的子公司 / 旗下品牌 / B 收购了 A (a 是父, b 是子)
  SUBSTITUTES   - A 是 B 的平替 / 替代品 (a 替代 b)
  UPGRADES_TO   - 用户从 A 升级到 B (a 旧, b 新)
  PAIRS_WITH    - A 和 B 搭配使用 (双向)

不确定的关系不要输出. 如果文本里没有任何关系, 返回 [].
"""

USER_PROMPT_TEMPLATE = """\
已知品牌列表 (按出现频率): {brands}

文本:
{text}

请输出 JSON 数组。
"""


def _cache_key(text: str, brand_index: dict[str, int]) -> str:
    h = hashlib.sha256()
    h.update(text.encode("utf-8"))
    for name, bid in sorted(brand_index.items()):
        h.update(f"|{name}={bid}".encode())
    return f"kg:rel:llm:{h.hexdigest()[:32]}"


async def _redis_get(key: str) -> list[dict[str, Any]] | None:
    """Best-effort: read cached value, return None on any failure."""
    if os.environ.get("GENPANO_KG_LLM_NO_REDIS") == "1":
        return None
    try:
        from redis.asyncio import from_url

        url = os.environ.get("GENPANO_REDIS_URL") or os.environ.get(
            "REDIS_URL", "redis://localhost:6379/0"
        )
        client = from_url(  # type: ignore[no-untyped-call]
            url, encoding="utf-8", decode_responses=True
        )
        try:
            raw = await client.get(key)
            if raw is None:
                return None
            parsed: list[dict[str, Any]] = json.loads(raw)
            return parsed
        finally:
            await client.aclose()
    except Exception as exc:
        logger.debug("kg llm cache get failed: %s", exc)
        return None


async def _redis_set(key: str, value: list[dict[str, Any]], ttl_seconds: int = 86400) -> None:
    """Best-effort: write cached value."""
    if os.environ.get("GENPANO_KG_LLM_NO_REDIS") == "1":
        return
    try:
        from redis.asyncio import from_url

        url = os.environ.get("GENPANO_REDIS_URL") or os.environ.get(
            "REDIS_URL", "redis://localhost:6379/0"
        )
        client = from_url(  # type: ignore[no-untyped-call]
            url, encoding="utf-8", decode_responses=True
        )
        try:
            await client.set(key, json.dumps(value), ex=ttl_seconds)
        finally:
            await client.aclose()
    except Exception as exc:
        logger.debug("kg llm cache set failed: %s", exc)


async def _call_doubao(text: str, brand_index: dict[str, int]) -> list[dict[str, Any]] | None:
    """Returns parsed LLM output or None on any failure."""
    if os.environ.get("GENPANO_KG_LLM_DISABLED") == "1":
        return None
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        return None
    try:
        import httpx
        from openai import AsyncOpenAI  # type: ignore[import-not-found]

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=os.environ.get("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
            timeout=60.0,
            max_retries=1,
            http_client=httpx.AsyncClient(trust_env=False),
        )
        resp = await client.chat.completions.create(
            model=os.environ.get("ARK_MODEL", "doubao-pro-32k"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": USER_PROMPT_TEMPLATE.format(
                        brands=", ".join(sorted(brand_index.keys())),
                        text=text[:8000],  # bound payload
                    ),
                },
            ],
            temperature=0.0,
        )
        content = (resp.choices[0].message.content or "").strip()
        # Strip ```json fences if the model adds them
        if content.startswith("```"):
            content = content.split("```", 2)[1].lstrip("json").lstrip()
            if content.endswith("```"):
                content = content[:-3]
        parsed = json.loads(content)
        if not isinstance(parsed, list):
            return None
        return parsed
    except Exception as exc:
        logger.info("kg llm call failed; falling back to regex extractor: %s", exc)
        return None


def _normalize_llm_output(
    raw: list[dict[str, Any]],
    *,
    brand_index: dict[str, int],
    entity_kind: str,
    source_id: str | None,
) -> list[dict[str, Any]]:
    """Convert LLM output to the canonical extract_relations() shape."""
    name_to_id = {name.lower(): bid for name, bid in brand_index.items()}
    valid_types = {"COMPETES_WITH", "SAME_GROUP", "SUBSTITUTES", "UPGRADES_TO", "PAIRS_WITH"}
    symmetric = {"COMPETES_WITH", "PAIRS_WITH"}

    out: list[dict[str, Any]] = []
    for item in raw:
        try:
            a_name = str(item.get("a_name", "")).strip()
            b_name = str(item.get("b_name", "")).strip()
            rel_type = str(item.get("type", "")).strip().upper()
            conf = float(item.get("confidence", 0.0))
            snippet = str(item.get("snippet", ""))
        except Exception:
            continue
        if rel_type not in valid_types:
            continue
        a_id = name_to_id.get(a_name.lower())
        b_id = name_to_id.get(b_name.lower())
        if a_id is None or b_id is None or a_id == b_id:
            continue
        # Normalize symmetric edges so dedup works downstream
        if rel_type in symmetric:
            lo, hi = sorted([a_id, b_id])
            a_id, b_id = lo, hi
        ev: dict[str, Any] = {
            "text_snippet": snippet,
            "pattern_type": rel_type,
            "matched": f"{a_name} - {b_name}",
            "extractor": "llm_v1",
        }
        if source_id is not None:
            ev["source_id"] = source_id
        out.append(
            {
                "entity_kind": entity_kind,
                "a_id": a_id,
                "b_id": b_id,
                "type": rel_type,
                "confidence": max(0.0, min(1.0, conf)),
                "evidence": ev,
            }
        )
    return out


async def extract_relations_llm(
    text: str,
    *,
    brand_index: dict[str, int],
    entity_kind: str = "brand",
    source_id: str | None = None,
) -> list[dict[str, Any]]:
    """LLM relation extractor with 24h Redis cache + regex fallback.

    Args mirror the regex `extract_relations()` so callers can swap freely.
    """
    if not text or not brand_index:
        return []

    cache_key = _cache_key(text, brand_index)
    cached = await _redis_get(cache_key)
    if cached is not None:
        return _normalize_llm_output(
            cached,
            brand_index=brand_index,
            entity_kind=entity_kind,
            source_id=source_id,
        )

    raw = await _call_doubao(text, brand_index)
    if raw is None:
        # Fallback: synchronous regex extractor wrapped in to_thread to keep
        # the awaitable contract.
        return await asyncio.to_thread(
            extract_relations,
            text,
            brand_index=brand_index,
            entity_kind=entity_kind,
            source_id=source_id,
        )

    # Persist raw LLM output so the cache hit path doesn't have to re-call the LLM.
    await _redis_set(cache_key, raw)
    return _normalize_llm_output(
        raw,
        brand_index=brand_index,
        entity_kind=entity_kind,
        source_id=source_id,
    )
