"""repair legacy Query Pool schema drift

Revision ID: 20260507_qpool_repair
Revises: 20260506_drop_audit_operator_fk
Create Date: 2026-05-07

Existing Admin databases can already contain query_generation_* tables created
by admin_console before FastAPI owned Query Pool assembly. The consolidation
migration creates the final schema for fresh databases, but CREATE TABLE IF NOT
EXISTS does not patch pre-existing legacy tables. Add the LLM bookkeeping
columns that the FastAPI read/write paths now use.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260507_qpool_repair"
down_revision: str | Sequence[str] | None = "20260506_drop_audit_operator_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("ALTER TABLE query_generation_runs ADD COLUMN IF NOT EXISTS llm_model VARCHAR(128);")
    op.execute(
        "ALTER TABLE query_generation_runs ADD COLUMN IF NOT EXISTS "
        "llm_usage_json JSONB NOT NULL DEFAULT '{}'::jsonb;"
    )
    op.execute("ALTER TABLE query_generation_runs ADD COLUMN IF NOT EXISTS llm_error TEXT;")

    op.execute(
        "ALTER TABLE query_generation_candidates ADD COLUMN IF NOT EXISTS "
        "generation_method VARCHAR(32) NOT NULL DEFAULT 'llm';"
    )
    op.execute(
        "ALTER TABLE query_generation_candidates ADD COLUMN IF NOT EXISTS "
        "llm_model VARCHAR(128);"
    )
    op.execute(
        "ALTER TABLE query_generation_candidates ADD COLUMN IF NOT EXISTS "
        "llm_usage_json JSONB NOT NULL DEFAULT '{}'::jsonb;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_query_candidates_generation_method "
        "ON query_generation_candidates (generation_method);"
    )


def downgrade() -> None:
    """No-op: these columns are now part of the Admin Query Pool contract."""
    return
