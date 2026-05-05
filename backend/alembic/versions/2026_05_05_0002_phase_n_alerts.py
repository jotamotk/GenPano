"""Phase N — Alerts + AlertRules + UserNotificationPreferences.

Revision ID: 20260505_phase_n
Revises: 20260504_phase0_app
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260505_phase_n"
down_revision: str | Sequence[str] | None = "20260505_phase_e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "alerts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("brand_id", sa.Integer, nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_ref_id", sa.String(64), nullable=True),
        sa.Column("severity", sa.String(4), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False, server_default="user"),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="unread"),
        sa.Column("triggered_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("read_at", sa.DateTime, nullable=True),
        sa.Column("read_by", sa.String(36), nullable=True),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("assigned_to", sa.String(36), nullable=True),
        sa.Column("runbook_url", sa.Text, nullable=True),
        sa.CheckConstraint(
            "severity IN ('P0', 'P1', 'P2', 'P3')", name=op.f("ck_alerts_severity")
        ),
        sa.CheckConstraint("scope IN ('user', 'operator')", name=op.f("ck_alerts_scope")),
        sa.CheckConstraint(
            "status IN ('unread', 'read', 'ignored', 'resolved')",
            name=op.f("ck_alerts_status"),
        ),
    )
    op.create_index(
        "alerts_scope_status_idx", "alerts", ["scope", "status", "triggered_at"]
    )
    op.create_index("alerts_project_idx", "alerts", ["project_id", "triggered_at"])

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("rule_type", sa.String(32), nullable=False),
        sa.Column("conditions", sa.JSON, nullable=True),
        sa.Column("channels", sa.JSON, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "user_notification_preferences",
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("p0p1_alerts", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("weekly_report", sa.Boolean, nullable=False, server_default="1"),
        sa.Column("competitor_alert", sa.Boolean, nullable=False, server_default="0"),
        sa.Column("email_locale", sa.String(8), nullable=False, server_default="zh-CN"),
        sa.Column("quiet_hours", sa.JSON, nullable=True),
        sa.Column("channels", sa.JSON, nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("user_notification_preferences")
    op.drop_table("alert_rules")
    op.drop_index("alerts_project_idx", table_name="alerts")
    op.drop_index("alerts_scope_status_idx", table_name="alerts")
    op.drop_table("alerts")
