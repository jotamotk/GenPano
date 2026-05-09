"""brand_context_snapshots for Topic/Prompt/Query context reuse.

Revision ID: 20260510_brand_context
Revises: 20260509_chart_data_supp
Create Date: 2026-05-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260510_brand_context"
down_revision: str | Sequence[str] | None = "20260509_chart_data_supp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS brand_context_snapshots (
            id VARCHAR(36) PRIMARY KEY,
            brand_id INTEGER NOT NULL,
            version VARCHAR(64) NOT NULL UNIQUE,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_notes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            search_as_of TIMESTAMP,
            expires_at TIMESTAMP,
            status VARCHAR(16) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','expired','archived')),
            created_from_run_id VARCHAR(36),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_brand_context_snapshots_brand_status "
        "ON brand_context_snapshots (brand_id, status, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_brand_context_snapshots_version "
        "ON brand_context_snapshots (version);"
    )

    op.execute(
        "ALTER TABLE topic_candidates ADD COLUMN IF NOT EXISTS "
        "brand_context_version VARCHAR(64);"
    )
    op.execute(
        "ALTER TABLE topic_candidates ADD COLUMN IF NOT EXISTS context_refs_json JSONB;"
    )
    op.execute("ALTER TABLE topic_candidates ADD COLUMN IF NOT EXISTS topic_axis VARCHAR(64);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_topic_candidates_brand_context "
        "ON topic_candidates (brand_context_version);"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS idx_topic_candidates_brand_context;")
    op.execute("ALTER TABLE topic_candidates DROP COLUMN IF EXISTS topic_axis;")
    op.execute("ALTER TABLE topic_candidates DROP COLUMN IF EXISTS context_refs_json;")
    op.execute("ALTER TABLE topic_candidates DROP COLUMN IF EXISTS brand_context_version;")
    op.execute("DROP INDEX IF EXISTS idx_brand_context_snapshots_version;")
    op.execute("DROP INDEX IF EXISTS idx_brand_context_snapshots_brand_status;")
    op.execute("DROP TABLE IF EXISTS brand_context_snapshots;")
