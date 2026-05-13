# App Analytics Product Entities Runbook

Issue: #523. Scope: Estee Lauder / 雅诗兰黛 product facts for App analytics.

## Target Slice

- Project: `95d43022-a5c8-5944-b6d6-34b29faa18b5`
- Canonical brand: `12`
- Source owner brand: `2`
- Default evidence window: `2026-04-24` through `2026-05-11`

## Safety Contract

- No product is created from a brand-only mention.
- Product facts are only emitted when scoped source text or existing analyzer facts explicitly contain a known Estee product alias, for example `Advanced Night Repair` or `小棕瓶`.
- The write path updates `brand_mentions.product_name` only on existing canonical brand `12` mention rows and upserts `product_score_daily` by `(brand_id, product_name, date, target_llm)`.
- Existing geo/topic/brand rollups are not rewritten.

## Read-Only Diagnostic

Generate the SQL:

```bash
python backend/scripts/app_product_entities_backfill.py diagnostic-sql \
  --brand-id 12 \
  --source-brand-ids 2 \
  --date-from 2026-04-24 \
  --date-to 2026-05-11
```

Run the emitted SQL in production with `psql -X -v ON_ERROR_STOP=1`. It starts `BEGIN TRANSACTION READ ONLY` and ends with `ROLLBACK`.

Counters to capture before approving writes:

- scoped response counts by `query_brand_id`
- matched Estee product alias counts
- existing non-empty `brand_mentions.product_name`
- existing `product_score_daily` rows for brand `12`

## Dry Run

```bash
python backend/scripts/app_product_entities_backfill.py run \
  --brand-id 12 \
  --source-brand-ids 2 \
  --date-from 2026-04-24 \
  --date-to 2026-05-11
```

The dry run prints JSON with `scanned_responses`, `evidence_responses`, `product_names`, `brand_mentions_updated`, and `product_score_rows_upserted` without committing.

## Write

Only run after AI Lead approval:

```bash
python backend/scripts/app_product_entities_backfill.py run \
  --brand-id 12 \
  --source-brand-ids 2 \
  --date-from 2026-04-24 \
  --date-to 2026-05-11 \
  --write
```

Expected post-run shape when evidence exists:

- `brand_mentions.product_name`: non-empty rows for canonical brand `12` where existing canonical mentions were product-specific.
- `product_score_daily`: one row per `(product_name, date, target_llm)` with non-zero `mention_count`.
- `/api/v1/projects/95d43022-a5c8-5944-b6d6-34b29faa18b5/products?brand_id=12`: product items become non-empty after deploy/backfill.
- `/products/relations`: remains empty unless separate explicit product-relation KG evidence exists; this runbook does not fabricate product-to-product edges.

## Rollback

Use the diagnostic output to identify rows created by the write window. Roll back by deleting only brand `12` `product_score_daily` rows for the emitted product names and dates, and clearing `brand_mentions.product_name` only for brand `12` rows whose previous value was empty and whose response id appeared in the dry-run/write evidence set.
