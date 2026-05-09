"""chart_data_support — kg_brands.positioning + supporting indexes.

Revision ID: 20260509_chart_data_support
Revises: 20260507_llm_accts_repair
Create Date: 2026-05-09

Adds the minimum schema needed by the new chart endpoints:

* `kg_brands.positioning` (VARCHAR(32) NULL) — used by `IndustrySegmentRanking`
  to bucket brands into the 3 marketed segments (`luxury_intl` / `mass_premium`
  / `niche_emerging`). Existing rows stay NULL; admin / KG-pipeline backfills
  per brand. Service falls back to `niche_emerging` when NULL.
* `idx_topic_score_daily_brand_date` (already exists; no-op guard).
* `idx_brand_mentions_brand_created` — speeds up position-distribution +
  mention-samples queries.

Idempotent on Postgres via IF NOT EXISTS guards. Downgrade drops the column
and the index.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260509_chart_data_supp"
down_revision: str | Sequence[str] | None = "20260507_llm_accts_repair"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE kg_brands ADD COLUMN IF NOT EXISTS positioning VARCHAR(32)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_kg_brands_positioning "
        "ON kg_brands (positioning) WHERE positioning IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_brand_mentions_brand_created "
        "ON brand_mentions (brand_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_brand_mentions_brand_created")
    op.execute("DROP INDEX IF EXISTS idx_kg_brands_positioning")
    op.execute("ALTER TABLE kg_brands DROP COLUMN IF EXISTS positioning")
