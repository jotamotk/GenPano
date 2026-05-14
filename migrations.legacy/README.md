# Legacy SQL Migrations (Archived)

> **Status**: Archived 2026-05-04 — see [ADR-002](../docs/ADR/002-schema-ssot-single-alembic.md)
> **Do not add new SQL files here.** All future schema changes go through
> `backend/alembic/versions/`.

## What's here

These 4 SQL files are the historical schema migrations that ran in the deployed environment
before Alembic was set up:

| File | Date | Tables / Columns | Now in Alembic |
| --- | --- | --- | --- |
| `001_analyzer_tables.sql` | 2026-04-09 | brand_mentions, sentiment_drivers, citation_sources, response_analyses, product_feature_mentions, geo_score_daily, industry_benchmark_daily, product_score_daily | `2026_04_27_0231_cdfdaab4088e_baseline.py` |
| `002_scheduler_and_binding_tables.sql` | 2026-05-03 | account_profile_map, scheduler_config, scheduler_runs, query_schedules + queries.schedule_id ALTER | `2026_05_04_0001_legacy_sql_into_alembic.py` |
| `003_products.sql` | — | products + topics.product_id ALTER | `2026_05_04_0001_legacy_sql_into_alembic.py` |
| `004_hot_topics.sql` | — | hot_topics + prompts.hotspot_id ALTER | `2026_05_04_0001_legacy_sql_into_alembic.py` |

## Why archived (not deleted)

- **Reference**: original SQL is more readable than alembic op.execute() raw strings
- **Rollback safety net**: if Phase R.2 alembic absorption has a bug, can compare with original
- **Audit trail**: shows historical schema evolution before SSOT was enforced

## How to add new schema

```bash
# Old way (DEPRECATED):
# echo "CREATE TABLE ..." > migrations/005_xxx.sql

# New way (SINGLE source of truth):
cd backend
uv run alembic revision --autogenerate -m "add X table for feature Y"
# Edit the generated file in backend/alembic/versions/
uv run alembic upgrade head    # apply locally
git add backend/alembic/versions/<new_file>
```

## CI guard

`backend/tests/test_legacy_sql_archived.py` (Phase R.5) will assert:
- `migrations.legacy/` exists with 4 files
- No new `.sql` files added to `migrations.legacy/` after 2026-05-04
- `migrations/` directory does not exist at repo root

## Removal date (tentative)

After 2026-Q4 (~6 months of stability with Alembic SSOT), these files may be
fully deleted. Until then, keep as historical reference.
