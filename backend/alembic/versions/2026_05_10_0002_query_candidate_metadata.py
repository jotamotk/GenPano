"""Persist Query Pool inherited prompt/context metadata.

Revision ID: 20260510_query_metadata
Revises: 20260510_brand_context
Create Date: 2026-05-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260510_query_metadata"
down_revision: str | Sequence[str] | None = "20260510_brand_context"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        "ALTER TABLE query_generation_candidates ADD COLUMN IF NOT EXISTS "
        "metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_query_candidates_metadata_scope "
        "ON query_generation_candidates ((metadata_json->>'prompt_scope'));"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_query_candidates_metadata_context "
        "ON query_generation_candidates ((metadata_json->>'brand_context_version'));"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS idx_query_candidates_metadata_context;")
    op.execute("DROP INDEX IF EXISTS idx_query_candidates_metadata_scope;")
    op.execute("ALTER TABLE query_generation_candidates DROP COLUMN IF EXISTS metadata_json;")
