"""Add durable analyzer submit and batch tracking.

Revision ID: 20260513_analyzer_batches
Revises: 20260513_analyzer_v4
Create Date: 2026-05-13

Rollback note:
Downgrade drops only the API-created batch tracking tables and nullable
run handoff columns added here. Analyzer v4 fact tables from the prior
revision are left intact.
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "20260513_analyzer_batches"
down_revision: str | Sequence[str] | None = "20260513_analyzer_v4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    if not _table_exists("analyzer_runs"):
        return

    op.execute("ALTER TABLE analyzer_runs ADD COLUMN IF NOT EXISTS task_id VARCHAR(128);")
    op.execute("ALTER TABLE analyzer_runs ADD COLUMN IF NOT EXISTS batch_id VARCHAR(64);")
    op.execute("ALTER TABLE analyzer_runs ADD COLUMN IF NOT EXISTS batch_item_id INTEGER;")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analyzer_batches (
            batch_id VARCHAR(64) PRIMARY KEY,
            mode VARCHAR(32) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'queued',
            trigger_source VARCHAR(64),
            idempotency_key VARCHAR(128),
            dry_run_id VARCHAR(64) NOT NULL,
            request_json JSONB,
            preview_json JSONB,
            submitted_response_ids_json JSONB,
            skipped_counts_json JSONB,
            skipped_reasons_json JSONB,
            submitted_count INTEGER NOT NULL DEFAULT 0,
            skipped_count INTEGER NOT NULL DEFAULT 0,
            created_by VARCHAR(64),
            reason TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMP
        );
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analyzer_batch_items (
            id SERIAL PRIMARY KEY,
            batch_id VARCHAR(64) NOT NULL
                REFERENCES analyzer_batches(batch_id) ON DELETE CASCADE,
            response_id INTEGER REFERENCES llm_responses(id) ON DELETE CASCADE,
            query_id INTEGER,
            run_id INTEGER REFERENCES analyzer_runs(id) ON DELETE SET NULL,
            task_id VARCHAR(128),
            status VARCHAR(32) NOT NULL,
            skipped_reason VARCHAR(64),
            detail_json JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_analyzer_batch_item_response UNIQUE (batch_id, response_id)
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_analyzer_runs_task_id ON analyzer_runs (task_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_analyzer_runs_batch_id ON analyzer_runs (batch_id);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_analyzer_batches_status "
        "ON analyzer_batches (status, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_analyzer_batches_idempotency "
        "ON analyzer_batches (idempotency_key);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_analyzer_batch_items_batch "
        "ON analyzer_batch_items (batch_id, status);"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("DROP TABLE IF EXISTS analyzer_batch_items;")
    op.execute("DROP TABLE IF EXISTS analyzer_batches;")
    if _table_exists("analyzer_runs"):
        op.execute("ALTER TABLE analyzer_runs DROP COLUMN IF EXISTS batch_item_id;")
        op.execute("ALTER TABLE analyzer_runs DROP COLUMN IF EXISTS batch_id;")
        op.execute("ALTER TABLE analyzer_runs DROP COLUMN IF EXISTS task_id;")
