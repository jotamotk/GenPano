"""Merge brand mention promotion and schedule batch plan heads.

Revision ID: 20260510_merge_mentions_schedule
Revises: 20260510_promote_mentions, 20260510_schedule_batch_plans
Create Date: 2026-05-10
"""

from collections.abc import Sequence

revision: str = "20260510_merge_mentions_schedule"
down_revision: str | Sequence[str] | None = (
    "20260510_promote_mentions",
    "20260510_schedule_batch_plans",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
