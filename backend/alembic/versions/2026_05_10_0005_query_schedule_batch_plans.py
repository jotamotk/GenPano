"""Query schedule batch plans.

Revision ID: 20260510_schedule_batch_plans
Revises: 20260510_promote_mentions
Create Date: 2026-05-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260510_schedule_batch_plans"
down_revision: str | Sequence[str] | None = "20260510_promote_mentions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "ALTER TABLE query_schedules "
        "ADD COLUMN IF NOT EXISTS plan_kind VARCHAR(16) NOT NULL DEFAULT 'single';"
    )
    op.execute(
        "ALTER TABLE query_schedules "
        "ADD COLUMN IF NOT EXISTS target_llms_json JSONB NOT NULL DEFAULT '[]'::jsonb;"
    )
    op.execute(
        "ALTER TABLE query_schedules "
        "ADD COLUMN IF NOT EXISTS query_items_json JSONB NOT NULL DEFAULT '[]'::jsonb;"
    )
    op.execute(
        "ALTER TABLE query_schedules "
        "ADD COLUMN IF NOT EXISTS item_count INTEGER NOT NULL DEFAULT 1;"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_qs_plan_kind ON query_schedules (plan_kind);")


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS idx_qs_plan_kind;")
    op.execute("ALTER TABLE query_schedules DROP COLUMN IF EXISTS item_count;")
    op.execute("ALTER TABLE query_schedules DROP COLUMN IF EXISTS query_items_json;")
    op.execute("ALTER TABLE query_schedules DROP COLUMN IF EXISTS target_llms_json;")
    op.execute("ALTER TABLE query_schedules DROP COLUMN IF EXISTS plan_kind;")
