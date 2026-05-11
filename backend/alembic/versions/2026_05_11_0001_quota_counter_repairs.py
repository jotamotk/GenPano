"""Add quota counter repair ledger.

Revision ID: 20260511_quota_repairs
Revises: 20260510_merge_mentions_schedule
Create Date: 2026-05-11
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "20260511_quota_repairs"
down_revision: str | Sequence[str] | None = "20260510_merge_mentions_schedule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    if not (_table_exists("queries") and _table_exists("llm_accounts")):
        return

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS quota_counter_repairs (
            id SERIAL PRIMARY KEY,
            query_id INTEGER NOT NULL REFERENCES queries(id) ON DELETE CASCADE,
            account_id INTEGER NOT NULL REFERENCES llm_accounts(id),
            engine VARCHAR(64) NOT NULL,
            reason VARCHAR(256) NOT NULL,
            delta INTEGER NOT NULL DEFAULT 1,
            service_day_start TIMESTAMP NOT NULL,
            service_day_end TIMESTAMP NOT NULL,
            approval_ref TEXT NOT NULL,
            repaired_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "uq_quota_counter_repairs_query_id ON quota_counter_repairs (query_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_quota_counter_repairs_account "
        "ON quota_counter_repairs (account_id, repaired_at);"
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TABLE IF EXISTS quota_counter_repairs;")
