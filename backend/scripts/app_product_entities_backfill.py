"""Issue #523 product entity diagnostics and backfill runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.pipeline.app_product_entities import (  # noqa: E402
    ESTEE_LAUDER_PRODUCT_ALIASES,
    ProductEntityBackfillConfig,
    backfill_product_entities,
)


def _csv_ints(value: str) -> tuple[int, ...]:
    if not value.strip():
        return ()
    return tuple(int(part.strip()) for part in value.split(",") if part.strip())


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")


def build_diagnostic_sql(
    *,
    canonical_brand_id: int,
    source_brand_ids: tuple[int, ...],
    date_from: str,
    date_to: str,
) -> str:
    brand_ids = ",".join(str(value) for value in (canonical_brand_id, *source_brand_ids))
    if not brand_ids:
        brand_ids = str(canonical_brand_id)
    alias_selects: list[str] = []
    for product_name, aliases in ESTEE_LAUDER_PRODUCT_ALIASES.items():
        terms = (product_name, *aliases)
        conditions = [
            "(COALESCE(r.raw_text, '') || ' ' || COALESCE(q.query_text, '') || ' ' "
            "|| COALESCE(p.text, '') || ' ' || COALESCE(bm.context_snippet, '')) "
            f"ILIKE '%{_sql_literal(term)}%'"
            for term in terms
        ]
        alias_selects.append(
            "SELECT "
            f"'{_sql_literal(product_name)}'::text AS product_name, "
            "COUNT(DISTINCT sr.response_id) FILTER (WHERE "
            + " OR ".join(conditions)
            + ") AS matched_responses "
            "FROM scoped_responses sr "
            "JOIN llm_responses r ON r.id = sr.response_id "
            "JOIN queries q ON q.id = r.query_id "
            "LEFT JOIN prompts p ON p.id = COALESCE(r.prompt_id, q.prompt_id) "
            "LEFT JOIN brand_mentions bm ON bm.response_id = r.id"
        )
    product_alias_sql = "\nUNION ALL\n".join(alias_selects)
    return f"""
\\set ON_ERROR_STOP on
BEGIN TRANSACTION READ ONLY;

\\echo '--- issue 523 product entity diagnostic context ---'
SELECT
  NOW() AS captured_at,
  {canonical_brand_id}::int AS canonical_brand_id,
  ARRAY[{','.join(str(v) for v in source_brand_ids)}]::int[] AS source_brand_ids,
  '{date_from}'::date AS date_from,
  '{date_to}'::date AS date_to;

\\echo '--- scoped response and product evidence counters ---'
WITH scoped_responses AS (
  SELECT
    r.id AS response_id,
    COALESCE(r.collected_at, q.finished_at, q.created_at)::date AS response_date,
    q.brand_id AS query_brand_id,
    r.analysis_status
  FROM llm_responses r
  JOIN queries q ON q.id = r.query_id
  WHERE q.brand_id IN ({brand_ids})
    AND COALESCE(r.collected_at, q.finished_at, q.created_at)::date
        BETWEEN '{date_from}'::date AND '{date_to}'::date
)
SELECT
  response_date,
  query_brand_id,
  COUNT(*) AS responses,
  COUNT(*) FILTER (WHERE analysis_status = 'done') AS done_responses
FROM scoped_responses
GROUP BY response_date, query_brand_id
ORDER BY response_date, query_brand_id;

\\echo '--- matched Estee product aliases in scoped response text ---'
WITH scoped_responses AS (
  SELECT r.id AS response_id
  FROM llm_responses r
  JOIN queries q ON q.id = r.query_id
  WHERE q.brand_id IN ({brand_ids})
    AND COALESCE(r.collected_at, q.finished_at, q.created_at)::date
        BETWEEN '{date_from}'::date AND '{date_to}'::date
)
{product_alias_sql}
ORDER BY matched_responses DESC, product_name;

\\echo '--- existing product facts before write ---'
SELECT
  'brand_mentions.product_name' AS source,
  bm.brand_id,
  COALESCE(NULLIF(bm.product_name, ''), '<empty>') AS product_name,
  COUNT(*) AS rows,
  COUNT(DISTINCT bm.response_id) AS responses
FROM brand_mentions bm
JOIN llm_responses r ON r.id = bm.response_id
JOIN queries q ON q.id = r.query_id
WHERE (bm.brand_id = {canonical_brand_id} OR q.brand_id IN ({brand_ids}))
  AND COALESCE(r.collected_at, q.finished_at, q.created_at)::date
      BETWEEN '{date_from}'::date AND '{date_to}'::date
GROUP BY bm.brand_id, COALESCE(NULLIF(bm.product_name, ''), '<empty>')
ORDER BY rows DESC, product_name
LIMIT 50;

SELECT
  'product_score_daily' AS source,
  brand_id,
  product_name,
  COUNT(*) AS rows,
  COALESCE(SUM(total_queries), 0)::bigint AS denominator_count,
  COALESCE(SUM(mention_count), 0)::bigint AS mention_count
FROM product_score_daily
WHERE brand_id = {canonical_brand_id}
  AND date::date BETWEEN '{date_from}'::date AND '{date_to}'::date
GROUP BY brand_id, product_name
ORDER BY mention_count DESC, product_name
LIMIT 50;

ROLLBACK;
""".strip()


async def _run(args: argparse.Namespace) -> None:
    from app.db.session import AsyncSessionLocal

    config = ProductEntityBackfillConfig(
        canonical_brand_id=args.brand_id,
        source_brand_ids=_csv_ints(args.source_brand_ids),
        date_from=_parse_date(args.date_from),
        date_to=_parse_date(args.date_to),
    )
    async with AsyncSessionLocal() as session:
        result = await backfill_product_entities(session, config=config, dry_run=not args.write)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    diag = sub.add_parser("diagnostic-sql", help="Emit read-only product evidence SQL")
    diag.add_argument("--brand-id", type=int, default=12)
    diag.add_argument("--source-brand-ids", default="2")
    diag.add_argument("--date-from", default="2026-04-24")
    diag.add_argument("--date-to", default="2026-05-11")

    run = sub.add_parser("run", help="Run dry-run or write backfill against DATABASE_URL")
    run.add_argument("--brand-id", type=int, default=12)
    run.add_argument("--source-brand-ids", default="2")
    run.add_argument("--date-from", default="2026-04-24")
    run.add_argument("--date-to", default="2026-05-11")
    run.add_argument("--write", action="store_true", help="Persist updates; omitted means dry-run")

    args = parser.parse_args()
    if args.command == "diagnostic-sql":
        print(
            build_diagnostic_sql(
                canonical_brand_id=args.brand_id,
                source_brand_ids=_csv_ints(args.source_brand_ids),
                date_from=args.date_from,
                date_to=args.date_to,
            )
        )
        return
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
