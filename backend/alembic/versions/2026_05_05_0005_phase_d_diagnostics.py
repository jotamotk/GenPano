"""Phase D — Diagnostics table.

Revision ID: 20260505_phase_d
Revises: 20260505_phase_k
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260505_phase_d"
down_revision: str | Sequence[str] | None = "20260505_phase_k"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "diagnostics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("brand_id", sa.Integer, nullable=True),
        sa.Column("product_id", sa.Integer, nullable=True),
        sa.Column("industry_id", sa.Integer, nullable=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(4), nullable=False),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("engine", sa.String(32), nullable=True),
        sa.Column("focus_area", sa.String(256), nullable=True),
        sa.Column("direction", sa.Text, nullable=True),
        sa.Column("reader_hints", sa.JSON, nullable=True),
        sa.Column("decision_prompt", sa.Text, nullable=True),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("causal_chain", sa.JSON, nullable=True),
        sa.Column("industry_benchmark", sa.JSON, nullable=True),
        sa.Column("time_series", sa.JSON, nullable=True),
        sa.Column("anchor_questions", sa.JSON, nullable=True),
        sa.Column("if_untreated", sa.Text, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("detected_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("acknowledged_at", sa.DateTime, nullable=True),
        sa.Column("acknowledged_by", sa.String(36), nullable=True),
        sa.Column("resolved_at", sa.DateTime, nullable=True),
        sa.Column("resolved_by", sa.String(36), nullable=True),
        sa.Column("rule_id", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.String(16), nullable=True),
        sa.Column("alert_id", sa.String(36), nullable=True),
        sa.CheckConstraint(
            "severity IN ('P0', 'P1', 'P2', 'P3')", name=op.f("ck_diagnostics_severity")
        ),
        sa.CheckConstraint(
            "type IN ('brand', 'product', 'industry')", name=op.f("ck_diagnostics_type")
        ),
        sa.CheckConstraint(
            "status IN ('open', 'acknowledged', 'ignored', 'resolved')",
            name=op.f("ck_diagnostics_status"),
        ),
    )
    op.create_index(
        "diagnostics_project_status_idx",
        "diagnostics",
        ["project_id", "severity", "status", "detected_at"],
    )
    op.create_index(
        "diagnostics_rule_idx",
        "diagnostics",
        ["rule_id", "detected_at"],
    )


def downgrade() -> None:
    op.drop_index("diagnostics_rule_idx", table_name="diagnostics")
    op.drop_index("diagnostics_project_status_idx", table_name="diagnostics")
    op.drop_table("diagnostics")
