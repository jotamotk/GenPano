"""Import Estée Lauder sample queries from estee-samples.json into the queries table.

Reads the JSON file's `queryExecutions` array (1500 rows, 500 prompts × 3 engines),
maps `engineId` → `target_llm` (deepseek-cn → deepseek), and bulk-inserts into
`queries` linked to an upserted Estée Lauder brand row.

Usage:
    python import_estee_samples.py [path/to/estee-samples.json] [--force]

Defaults to the checked-in prototype path on Frank's laptop; override with an arg
when running on the server. `--force` re-inserts even if queries already exist
for the brand (otherwise the script exits idempotently).
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

    cur.execute(
        """INSERT INTO brands (name, industry, aliases, target_market)
           VALUES (%s, %s, %s::jsonb, %s)
           RETURNING id""",
        (BRAND_NAME, BRAND_INDUSTRY, json.dumps(BRAND_ALIASES), "中国大陆"),
    )
    return cur.fetchone()[0]


def load_executions(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    execs = data.get("queryExecutions") or []
    rows = []
    skipped = 0
    for e in execs:
        engine = ENGINE_MAP.get(str(e.get("engineId", "")).lower())
        text = (e.get("textZh") or "").strip()
        if not engine or not text:
            skipped += 1
            continue
        rows.append((engine, text))
    return rows, skipped


def main():
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    json_path = args[0] if args else DEFAULT_JSON

    if not os.path.exists(json_path):
        print(f"[err] JSON not found: {json_path}", file=sys.stderr)
        sys.exit(1)

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
                print(f"[skip] {existing} queries already exist for brand {brand_id}; use --force to re-insert")
                conn.rollback()
                return

            rows, skipped = load_executions(json_path)
            print(f"[info] parsed {len(rows)} executions ({skipped} skipped)")

            execute_batch(
                cur,
                """INSERT INTO queries (target_llm, query_text, brand_id, status, created_at, queued_at)
                   VALUES (%s, %s, %s, 'pending', NOW(), NOW())""",
                [(engine, text, brand_id) for engine, text in rows],
                page_size=200,
            )
            inserted = cur.rowcount
            conn.commit()
            print(f"[done] inserted {inserted} queries for brand {brand_id}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
