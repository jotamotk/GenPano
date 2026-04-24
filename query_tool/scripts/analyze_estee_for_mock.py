#!/usr/bin/env python3
"""Analyze Estée Lauder responses in DB and output a JS mock module.

Run inside the query-tool-preview container:
    docker exec -e ARK_API_KEY=... genpano-query-tool-preview-1 \
        python /app/scripts/analyze_estee_for_mock.py > real_estee.js

Requires env:
  DATABASE_URL  (already set in container)
  ARK_API_KEY   (Volcengine Ark / Doubao)

Options (env):
  BRAND_NAME    default "Estée Lauder"
  DEEP_LIMIT    how many responses to deep-analyze (default 10)
  ARK_MODEL     Ark endpoint id or model alias (default "doubao-seed-2-0-pro-260215",
                matching what worker/.env uses). LLM_MODEL kept as legacy alias.
  ARK_BASE_URL  default https://ark.cn-beijing.volces.com/api/v3
"""
import asyncio
import json
import os
import re
import sys
import traceback
from datetime import datetime

import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from openai import AsyncOpenAI
    import httpx
except Exception as e:
    print(f"ERROR: openai/httpx not installed: {e}", file=sys.stderr)
    sys.exit(2)

try:
    from json_repair import repair_json
except Exception:
    repair_json = None


BRAND_NAME = os.environ.get("BRAND_NAME", "Estée Lauder")
DEEP_LIMIT = int(os.environ.get("DEEP_LIMIT", "10"))
LLM_MODEL = (
    os.environ.get("ARK_MODEL")
    or os.environ.get("LLM_MODEL")
    or "doubao-seed-2-0-pro-260215"
)
LLM_BASE_URL = (
    os.environ.get("ARK_BASE_URL")
    or os.environ.get("LLM_BASE_URL")
    or "https://ark.cn-beijing.volces.com/api/v3"
)
ARK_API_KEY = os.environ.get("ARK_API_KEY", "")
DATABASE_URL = os.environ.get("DATABASE_URL")


ANALYSIS_SYSTEM = (
    "你是品牌GEO分析专家。任务：\n"
    "1. 从AI回答中提取所有被提及的品牌和产品\n"
    "2. 判断每个品牌的位置（首推/罗列/一般提及）和情感倾向\n"
    "3. 提取产品特性、卖点关键词\n"
    "4. 提取引用源（链接/来源标注）\n"
    "严格按JSON输出，不要添加任何解释。"
)

ANALYSIS_USER = """\
分析以下AI回答。

**目标品牌**: {target}
**Prompt**: {prompt}

**AI回答**:
{response}

请输出以下JSON（严格遵循字段名，不要省略字段）：
{{
  "brands": [
    {{
      "name": "品牌名（中文或原文，统一大小写）",
      "position": "first|listed|mentioned",
      "sentiment": "positive|neutral|negative",
      "sentimentScore": 0.7,
      "recommended": true
    }}
  ],
  "products": [
    {{
      "name": "产品名（具体 SKU 或系列，不含品牌前缀）",
      "brand": "所属品牌",
      "sentiment": "positive|neutral|negative",
      "keywords": ["核心卖点1", "核心卖点2", "核心卖点3"]
    }}
  ],
  "citations": [
    {{
      "index": 1,
      "url": "链接或来源",
      "title": "来源标题",
      "snippet": "AI引用的原文片段"
    }}
  ],
  "wordCount": 1234,
  "recommendationType": "ranking|comparison|recommendation|analysis"
}}

规则：
- brands 至少包含目标品牌（若未提及则为 negative/0 并写入 position=mentioned, recommended=false）
- products 仅在 AI 回答里明确写出产品名时出现
- citations 如果 AI 回答没有引用源，返回空数组
- wordCount 是 AI 回答的中文字符+英文词数估算（整数）
- recommendationType 根据回答主体风格判断
"""


def db():
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(2)
    return psycopg2.connect(DATABASE_URL)


def fetch_brand(conn, name):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT id, name FROM brands WHERE name = %s", (name,))
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT id, name FROM brands WHERE name ILIKE %s", (f"%{name}%",))
            row = cur.fetchone()
        return row


def fetch_graph(conn, brand_id):
    """Return list of dicts, one row per done query with response joined."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT
              t.id AS topic_id,
              t.text AS topic_text,
              t.category AS topic_category,
              pr.id AS prompt_id,
              pr.text AS prompt_text,
              q.id AS query_id,
              q.target_llm AS engine,
              q.status AS status,
              q.finished_at AS finished_at,
              q.started_at AS started_at,
              q.created_at AS created_at,
              q.query_text AS query_text,
              p.name AS profile_name,
              p.country_code AS profile_country,
              r.raw_text AS raw_text,
              r.citations_json AS citations_json,
              r.collected_at AS collected_at
            FROM queries q
            LEFT JOIN prompts pr ON q.prompt_id = pr.id
            LEFT JOIN topics t ON pr.topic_id = t.id
            LEFT JOIN profiles p ON q.profile_id = p.id
            LEFT JOIN llm_responses r ON r.query_id = q.id
            WHERE q.brand_id = %s
            ORDER BY t.id, pr.id, q.id
            """,
            (brand_id,),
        )
        return cur.fetchall()


def word_count(text):
    if not text:
        return 0
    cn = len(re.findall(r"[一-鿿]", text))
    en = len(re.findall(r"[A-Za-z]+", text))
    return cn + en


def fmt_time(t):
    if not t:
        return ""
    if isinstance(t, datetime):
        return t.strftime("%Y-%m-%d %H:%M")
    return str(t)


def short_date(t):
    if not t:
        return ""
    if isinstance(t, datetime):
        return t.strftime("%Y-%m-%d")
    return str(t)[:10]


def engine_label(raw):
    if not raw:
        return "未知"
    s = raw.lower()
    if "doubao" in s or "豆包" in s:
        return "doubao"
    if "deepseek" in s:
        return "deepseek"
    if "chatgpt" in s or "gpt" in s or "openai" in s:
        return "chatgpt"
    if "kimi" in s:
        return "kimi"
    if "gemini" in s:
        return "gemini"
    return s


async def deep_analyze(client, target, prompt, response):
    msgs = [
        {"role": "system", "content": ANALYSIS_SYSTEM},
        {
            "role": "user",
            "content": ANALYSIS_USER.format(target=target, prompt=prompt[:400], response=response[:8000]),
        },
    ]
    try:
        resp = await client.chat.completions.create(
            model=LLM_MODEL,
            messages=msgs,
            temperature=0.2,
            response_format={"type": "json_object"},
            timeout=90,
        )
        content = resp.choices[0].message.content or "{}"
    except Exception as e:
        print(f"  LLM call failed: {e}", file=sys.stderr)
        return None
    try:
        return json.loads(content)
    except Exception:
        if repair_json:
            try:
                return json.loads(repair_json(content))
            except Exception as e:
                print(f"  json_repair failed: {e}", file=sys.stderr)
                return None
        print("  json decode failed, no repair_json available", file=sys.stderr)
        return None


def fallback_analysis(target, raw):
    return {
        "brands": [
            {
                "name": target,
                "position": "mentioned",
                "sentiment": "neutral",
                "sentimentScore": 0.0,
                "recommended": False,
            }
        ],
        "products": [],
        "citations": [],
        "wordCount": word_count(raw or ""),
        "recommendationType": "analysis",
    }


def js_literal(obj, indent=2, level=0):
    """Serialize as a JS-friendly literal: JSON is valid JS. Keep as JSON."""
    return json.dumps(obj, ensure_ascii=False, indent=indent)


async def main():
    if not ARK_API_KEY:
        print("ERROR: ARK_API_KEY not set", file=sys.stderr)
        sys.exit(2)

    conn = db()
    try:
        brand = fetch_brand(conn, BRAND_NAME)
        if not brand:
            print(f"ERROR: brand {BRAND_NAME!r} not found", file=sys.stderr)
            sys.exit(2)
        print(f"Brand: {brand['name']} (id={brand['id']})", file=sys.stderr)
        rows = fetch_graph(conn, brand["id"])
    finally:
        conn.close()

    done_with_response = [
        r for r in rows if (r["status"] or "").lower() == "done" and r["raw_text"]
    ]
    print(f"Rows: total={len(rows)}, done-with-response={len(done_with_response)}", file=sys.stderr)
    if not done_with_response:
        print("ERROR: no done queries with responses", file=sys.stderr)
        sys.exit(1)

    # Group by topic / prompt for aggregation.
    by_topic = {}
    by_prompt = {}
    for r in rows:
        tid = r["topic_id"]
        if tid is None:
            continue
        t = by_topic.setdefault(
            tid,
            {
                "id": tid,
                "text": r["topic_text"],
                "category": r["topic_category"] or "未分类",
                "prompts": set(),
                "queries": 0,
                "responses": 0,
                "last_collected": None,
            },
        )
        if r["prompt_id"] is not None:
            t["prompts"].add(r["prompt_id"])
        t["queries"] += 1
        if r["raw_text"]:
            t["responses"] += 1
        ts = r["collected_at"] or r["finished_at"] or r["started_at"]
        if ts and (t["last_collected"] is None or ts > t["last_collected"]):
            t["last_collected"] = ts

        pid = r["prompt_id"]
        if pid is None:
            continue
        p = by_prompt.setdefault(
            pid,
            {
                "id": pid,
                "text": r["prompt_text"],
                "topic_id": tid,
                "queries": 0,
                "coverage_done": 0,
            },
        )
        p["queries"] += 1
        if r["raw_text"]:
            p["coverage_done"] += 1

    # Choose deep-analysis sample: longest raw_text, diversified across prompts.
    done_with_response.sort(key=lambda r: len(r["raw_text"] or ""), reverse=True)
    chosen = []
    seen_prompts = set()
    for r in done_with_response:
        if r["prompt_id"] in seen_prompts:
            continue
        chosen.append(r)
        seen_prompts.add(r["prompt_id"])
        if len(chosen) >= DEEP_LIMIT:
            break
    # Fill remainder with next-longest even if prompt already covered.
    for r in done_with_response:
        if len(chosen) >= DEEP_LIMIT:
            break
        if r in chosen:
            continue
        chosen.append(r)

    print(f"Deep-analyzing {len(chosen)} of {len(done_with_response)} responses", file=sys.stderr)

    http_client = httpx.AsyncClient(trust_env=False, timeout=120)
    client = AsyncOpenAI(api_key=ARK_API_KEY, base_url=LLM_BASE_URL, http_client=http_client)

    deep_by_prompt = {}
    deep_by_query = {}
    try:
        for i, r in enumerate(chosen, 1):
            print(f"  [{i}/{len(chosen)}] query_id={r['query_id']} len={len(r['raw_text'])}", file=sys.stderr)
            result = await deep_analyze(client, BRAND_NAME, r["prompt_text"] or "", r["raw_text"])
            if result is None:
                result = fallback_analysis(BRAND_NAME, r["raw_text"])
            # Ensure wordCount is sane.
            if not result.get("wordCount"):
                result["wordCount"] = word_count(r["raw_text"])
            deep_by_query[r["query_id"]] = result
            deep_by_prompt.setdefault(r["prompt_id"], result)
    finally:
        await http_client.aclose()

    # Build mock-shaped dicts.
    topics_real = []
    for t in sorted(by_topic.values(), key=lambda x: x["id"]):
        topics_real.append(
            {
                "id": f"real-topic-{t['id']}",
                "name": t["text"] or f"topic-{t['id']}",
                "dimension": t["category"] or "行业",
                "brand": BRAND_NAME,
                "source": "真实执行",
                "promptCount": len(t["prompts"]),
                "queryCount": t["queries"],
                "responseCount": t["responses"],
                "lastCollected": short_date(t["last_collected"]),
                "status": "active",
                "priority": "high",
            }
        )

    prompts_real = {}
    for p in sorted(by_prompt.values(), key=lambda x: x["id"]):
        key = f"real-topic-{p['topic_id']}"
        prompts_real.setdefault(key, []).append(
            {
                "id": f"real-prompt-{p['id']}",
                "text": p["text"] or f"prompt-{p['id']}",
                "intent": "对比推荐",
                "queryCount": p["queries"],
                "coverage": f"{p['coverage_done']}/{p['queries']}",
            }
        )

    queries_real = {}
    responses_real = {}
    for r in rows:
        if r["prompt_id"] is None:
            continue
        pid_key = f"real-prompt-{r['prompt_id']}"
        qid_key = f"real-query-{r['query_id']}"
        engine = engine_label(r["engine"])
        profile = r["profile_name"] or (r["profile_country"] or "默认")
        status_norm = (r["status"] or "pending").lower()
        analysis = deep_by_query.get(r["query_id"]) or deep_by_prompt.get(r["prompt_id"]) or (
            fallback_analysis(BRAND_NAME, r["raw_text"] or "") if r["raw_text"] else None
        )
        brand_mentions = 0
        if analysis:
            brand_mentions = sum(1 for b in analysis.get("brands", []) if b.get("name"))
        queries_real.setdefault(pid_key, []).append(
            {
                "id": qid_key,
                "engine": engine,
                "profile": profile,
                "time": fmt_time(r["finished_at"] or r["started_at"] or r["created_at"]),
                "status": "completed" if status_norm == "done" else status_norm,
                "brandMentions": brand_mentions,
            }
        )
        if r["raw_text"] and analysis:
            responses_real[qid_key] = {
                "id": qid_key,
                "engine": engine,
                "profile": profile,
                "prompt": r["prompt_text"] or "",
                "time": fmt_time(r["finished_at"] or r["started_at"] or r["created_at"]),
                "rawText": r["raw_text"],
                "analysis": analysis,
            }

    # Emit JS module.
    out = sys.stdout
    out.write("// Auto-generated from real Estée Lauder queries. Do not edit by hand.\n")
    out.write(f"// Generated at {datetime.utcnow().isoformat()}Z\n\n")
    out.write("export const TOPICS_REAL = ")
    out.write(js_literal(topics_real))
    out.write(";\n\n")
    out.write("export const PROMPTS_REAL = ")
    out.write(js_literal(prompts_real))
    out.write(";\n\n")
    out.write("export const QUERIES_REAL = ")
    out.write(js_literal(queries_real))
    out.write(";\n\n")
    out.write("export const RESPONSES_REAL = ")
    out.write(js_literal(responses_real))
    out.write(";\n")
    out.flush()

    print(
        f"Done. topics={len(topics_real)} prompts={sum(len(v) for v in prompts_real.values())} "
        f"queries={sum(len(v) for v in queries_real.values())} responses={len(responses_real)}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
