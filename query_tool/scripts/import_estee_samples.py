"""Import Estée Lauder sample queries from estee-samples.json.

Builds the full hierarchy so downstream filtering works:
    brand (Estée Lauder) → topics (10) → prompts (100) → queries (1500)

Each row in `queryExecutions` → one `queries` row, linked via `prompt_id`.
`engineId` is mapped (deepseek-cn → deepseek). Topics/prompts are upserted by
(brand_id, text) / (topic_id, text) so re-runs don't duplicate.

Usage:
    python import_estee_samples.py [path/to/estee-samples.json] [--force]

`--force` wipes existing queries for the brand and re-inserts (topics/prompts
are kept and reused — safe because they're matched by text).
"""
import json
import os
import sys

import psycopg2
from psycopg2.extras import execute_batch

BRAND_NAME = "Estée Lauder"
BRAND_ALIASES = ["雅诗兰黛", "Estée Lauder", "Estee Lauder"]
BRAND_INDUSTRY = "美妆"

ENGINE_MAP = {
    "deepseek-cn": "deepseek",
    "deepseek": "deepseek",
    "chatgpt": "chatgpt",
    "doubao": "doubao",
    "gemini": "gemini",
}

DEFAULT_JSON = r"C:\Users\frank.wang\Documents\Claude\Projects\GENPANO\backend\estee-samples.json"


def parse_db_url(url: str):
    import re
    m = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", url)
    if not m:
        raise RuntimeError(f"cannot parse DATABASE_URL: {url}")
    return dict(user=m.group(1), password=m.group(2), host=m.group(3),
                port=m.group(4), dbname=m.group(5))


def resync_sequence(cur, table: str, col: str = "id") -> None:
    cur.execute(
        f"SELECT setval(pg_get_serial_sequence('{table}', '{col}'), "
        f"COALESCE((SELECT MAX({col}) FROM {table}), 0) + 1, false)"
    )


def upsert_brand(cur) -> int:
    cur.execute(
        "SELECT id FROM brands WHERE name = %s OR aliases::text ILIKE %s LIMIT 1",
        (BRAND_NAME, f"%{BRAND_NAME}%"),
    )
    row = cur.fetchone()
    if row:
        bid = row[0]
        cur.execute(
            "UPDATE brands SET aliases = %s::jsonb, industry = COALESCE(industry, %s) WHERE id = %s",
            (json.dumps(BRAND_ALIASES), BRAND_INDUSTRY, bid),
        )
        return bid

    resync_sequence(cur, "brands")
    cur.execute(
        """INSERT INTO brands (name, industry, aliases, target_market)
           VALUES (%s, %s, %s::jsonb, %s)
           RETURNING id""",
        (BRAND_NAME, BRAND_INDUSTRY, json.dumps(BRAND_ALIASES), "中国大陆"),
    )
    return cur.fetchone()[0]


def upsert_topics(cur, brand_id: int, topics):
    """Returns {json_topic_id: db_topic_id}."""
    mapping = {}
    for t in topics:
        text = (t.get("textZh") or "").strip()
        if not text:
            continue
        cur.execute(
            "SELECT id FROM topics WHERE brand_id = %s AND text = %s LIMIT 1",
            (brand_id, text),
        )
        row = cur.fetchone()
        if row:
            mapping[t["id"]] = row[0]
            continue
        resync_sequence(cur, "topics")
        cur.execute(
            """INSERT INTO topics (brand_id, text, category, generated_by, status)
               VALUES (%s, %s, %s, 'estee-import', 'active')
               RETURNING id""",
            (brand_id, text, t.get("dimension")),
        )
        mapping[t["id"]] = cur.fetchone()[0]
    return mapping


def upsert_prompts(cur, topic_id_map, prompts):
    """Returns {json_prompt_id: db_prompt_id}."""
    mapping = {}
    for p in prompts:
        topic_db_id = topic_id_map.get(p.get("topicId"))
        text = (p.get("textZh") or "").strip()
        if not topic_db_id or not text:
            continue
        cur.execute(
            "SELECT id FROM prompts WHERE topic_id = %s AND text = %s LIMIT 1",
            (topic_db_id, text),
        )
        row = cur.fetchone()
        if row:
            mapping[p["id"]] = row[0]
            continue
        resync_sequence(cur, "prompts")
        cur.execute(
            """INSERT INTO prompts (topic_id, text, intent, language)
               VALUES (%s, %s, %s, 'zh')
               RETURNING id""",
            (topic_db_id, text, p.get("intent")),
        )
        mapping[p["id"]] = cur.fetchone()[0]
    return mapping


def load_executions(execs, prompt_id_map):
    rows = []
    skipped = 0
    for e in execs:
        engine = ENGINE_MAP.get(str(e.get("engineId", "")).lower())
        text = (e.get("textZh") or "").strip()
        prompt_db_id = prompt_id_map.get(e.get("promptId"))
        if not engine or not text or not prompt_db_id:
            skipped += 1
            continue
        rows.append((engine, text, prompt_db_id))
    return rows, skipped


def wipe_brand_queries(cur, brand_id: int) -> int:
    """Cascade delete queries for a brand. All 1500 are pending with no
    downstream response data, but we still walk the FK chain for safety."""
    cur.execute(
        "CREATE TEMP TABLE _qids ON COMMIT DROP AS "
        "SELECT id FROM queries WHERE brand_id = %s",
        (brand_id,),
    )
    cur.execute("SELECT COUNT(*) FROM _qids")
    n = cur.fetchone()[0]
    if n == 0:
        return 0
    # Cascade order mirrors app.py:_normalize_query_data. Note:
    # product_feature_mentions links via analysis_id → response_analyses → llm_responses,
    # NOT directly to llm_responses.
    for sql in [
        "DELETE FROM product_feature_mentions WHERE analysis_id IN "
        "(SELECT id FROM response_analyses WHERE response_id IN "
        "(SELECT id FROM llm_responses WHERE query_id IN (SELECT id FROM _qids)))",
        "DELETE FROM sentiment_drivers WHERE response_id IN "
        "(SELECT id FROM llm_responses WHERE query_id IN (SELECT id FROM _qids))",
        "DELETE FROM citation_sources WHERE response_id IN "
        "(SELECT id FROM llm_responses WHERE query_id IN (SELECT id FROM _qids))",
        "DELETE FROM response_analyses WHERE response_id IN "
        "(SELECT id FROM llm_responses WHERE query_id IN (SELECT id FROM _qids))",
        "DELETE FROM brand_mentions WHERE response_id IN "
        "(SELECT id FROM llm_responses WHERE query_id IN (SELECT id FROM _qids))",
        "DELETE FROM llm_responses WHERE query_id IN (SELECT id FROM _qids)",
        "DELETE FROM queries WHERE id IN (SELECT id FROM _qids)",
    ]:
        cur.execute(sql)
    return n


def main():
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    json_path = args[0] if args else DEFAULT_JSON

    if not os.path.exists(json_path):
        print(f"[err] JSON not found: {json_path}", file=sys.stderr)
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    topics = data.get("topics") or []
    prompts = data.get("prompts") or []
    execs = data.get("queryExecutions") or []
    print(f"[info] JSON: {len(topics)} topics, {len(prompts)} prompts, {len(execs)} executions")

    db_url = os.getenv("DATABASE_URL", "postgresql://genpano:genpano2026@localhost:5432/genpano")
    conn = psycopg2.connect(**parse_db_url(db_url))
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            brand_id = upsert_brand(cur)
            print(f"[ok] Estée Lauder brand_id = {brand_id}")

            cur.execute("SELECT COUNT(*) FROM queries WHERE brand_id = %s", (brand_id,))
            existing = cur.fetchone()[0]
            if existing and not force:
                print(f"[skip] {existing} queries already exist for brand {brand_id}; use --force to wipe + re-insert")
                conn.rollback()
                return
            if existing and force:
                wiped = wipe_brand_queries(cur, brand_id)
                print(f"[wipe] removed {wiped} existing queries for brand {brand_id}")

            topic_id_map = upsert_topics(cur, brand_id, topics)
            print(f"[ok] upserted {len(topic_id_map)} topics")

            prompt_id_map = upsert_prompts(cur, topic_id_map, prompts)
            print(f"[ok] upserted {len(prompt_id_map)} prompts")

            rows, skipped = load_executions(execs, prompt_id_map)
            print(f"[info] queued {len(rows)} queries ({skipped} skipped)")

            resync_sequence(cur, "queries")
            execute_batch(
                cur,
                """INSERT INTO queries (target_llm, query_text, brand_id, prompt_id, status, created_at, queued_at)
                   VALUES (%s, %s, %s, %s, 'pending', NOW(), NOW())""",
                [(engine, text, brand_id, prompt_id) for engine, text, prompt_id in rows],
                page_size=200,
            )
            conn.commit()
            print(f"[done] inserted {len(rows)} queries for brand {brand_id}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
