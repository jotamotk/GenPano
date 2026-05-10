"""Promote brand_mentions long-tail into the brands entity table.

Revision ID: 20260510_promote_mentions
Revises: 20260510_backfill_links
Create Date: 2026-05-10

The /v1/brands/search endpoint queries the `brands` entity table only.
On prod that table has ~21 rows (confirmed via the
brand-search-diagnostics workflow), but `brand_mentions.brand_name`
holds hundreds-to-thousands of brand strings extracted by the analyzer
from real LLM responses. Operators expect to search any of those, but
nothing has ever promoted them into the formal entity table — so the
search box returns empty for keywords like 雅诗兰黛.

This migration is the one-shot fix:

  Step 1 — pick distinct brand_name values that appear ≥ 3 times in
  brand_mentions and don't already match an existing brand row by
  name / name_zh / name_en (case-insensitive).

  Step 2 — INSERT them into `brands` with:
    - name      = the canonical brand_name string
    - name_zh   = brand_name if it contains Han characters, else NULL
    - name_en   = brand_name if it's ASCII-only, else NULL
    - source    = 'mention-promote' (lets operators filter / undo)
    - status    = 'active'

The 3-mention threshold filters typo / one-off LLM hallucinations.
Idempotent via NOT EXISTS.

SQLite (CI) is a no-op — the brands / brand_mentions tables don't
exist on the test bind.
"""

from collections.abc import Sequence
import logging

from alembic import op
from sqlalchemy import inspect

revision: str = "20260510_promote_mentions"
down_revision: str | Sequence[str] | None = "20260510_backfill_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")


def _table_exists(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def _columns(table: str) -> set[str]:
    if not _table_exists(table):
        return set()
    return {col["name"] for col in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    if not (_table_exists("brands") and _table_exists("brand_mentions")):
        return

    brand_cols = _columns("brands")
    mention_cols = _columns("brand_mentions")
    if "brand_name" not in mention_cols or "name" not in brand_cols:
        return

    has_name_zh = "name_zh" in brand_cols
    has_name_en = "name_en" in brand_cols
    has_source = "source" in brand_cols
    has_status = "status" in brand_cols
    has_created_at = "created_at" in brand_cols

    # Build the INSERT column list dynamically — production schema has all
    # columns but test/staging may lag.
    insert_cols = ["name"]
    insert_vals = ["bm.brand_name"]
    if has_name_zh:
        insert_cols.append("name_zh")
        insert_vals.append("CASE WHEN bm.brand_name ~ '[\\u4e00-\\u9fff]' THEN bm.brand_name ELSE NULL END")
    if has_name_en:
        insert_cols.append("name_en")
        insert_vals.append("CASE WHEN bm.brand_name ~ '^[\\x20-\\x7e]+$' THEN bm.brand_name ELSE NULL END")
    if has_source:
        insert_cols.append("source")
        insert_vals.append("'mention-promote'")
    if has_status:
        insert_cols.append("status")
        insert_vals.append("'active'")
    if has_created_at:
        insert_cols.append("created_at")
        insert_vals.append("NOW()")

    insert_sql = f"""
        INSERT INTO brands ({', '.join(insert_cols)})
        SELECT {', '.join(insert_vals)}
        FROM (
            SELECT bm.brand_name, COUNT(*) AS mentions
            FROM brand_mentions bm
            WHERE bm.brand_name IS NOT NULL
              AND LENGTH(TRIM(bm.brand_name)) >= 2
            GROUP BY bm.brand_name
            HAVING COUNT(*) >= 3
        ) AS bm
        WHERE NOT EXISTS (
            SELECT 1 FROM brands b
            WHERE LOWER(COALESCE(b.name, '')) = LOWER(bm.brand_name)
               OR LOWER(COALESCE(b.name_zh, '')) = LOWER(bm.brand_name)
               OR LOWER(COALESCE(b.name_en, '')) = LOWER(bm.brand_name)
        )
        RETURNING id
    """

    bind = op.get_bind()
    result = bind.exec_driver_sql(insert_sql)
    inserted = result.rowcount or 0
    log.info("promote_brand_mentions: inserted %d brand rows from brand_mentions long-tail", inserted)


def downgrade() -> None:
    """Remove only the rows we promoted (source='mention-promote').

    Safe because we tagged them at insert time. Manually-curated brands
    don't carry that source value and stay untouched.
    """
    if op.get_bind().dialect.name != "postgresql":
        return
    if not _table_exists("brands"):
        return
    if "source" not in _columns("brands"):
        return
    op.execute("DELETE FROM brands WHERE source = 'mention-promote'")
