"""Phase RP — ReportSchedule + ReportShareToken.

Revision ID: 20260505_phase_rp
Revises: 20260505_phase_d
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260505_phase_rp"
down_revision: str | Sequence[str] | None = "20260505_phase_d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "report_schedules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("report_type", sa.String(32), nullable=False),
        sa.Column("cron", sa.String(64), nullable=False),
        sa.Column("recipients", sa.JSON, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("next_run_at", sa.DateTime, nullable=True),
        sa.Column("last_run_at", sa.DateTime, nullable=True),
        sa.Column("last_run_id", sa.String(36), nullable=True),
        sa.Column("locale", sa.String(8), nullable=False, server_default="zh-CN"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "report_schedules_next_run_idx",
        "report_schedules",
        ["next_run_at", "enabled"],
    )

    op.create_table(
        "report_share_tokens",
        sa.Column("token", sa.String(64), primary_key=True),
        sa.Column("report_id", sa.String(36), nullable=False),
        sa.Column("expires_at", sa.DateTime, nullable=False),
        sa.Column("view_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("report_share_tokens")
    op.drop_index("report_schedules_next_run_idx", table_name="report_schedules")
    op.drop_table("report_schedules")
