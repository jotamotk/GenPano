"""Phase E — Exports + Brand Submissions + Industry Pricing.

Revision ID: 20260505_phase_e
Revises: 20260504_phase0_app
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260505_phase_e"
down_revision: str | Sequence[str] | None = "20260504_phase0_app"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "export_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(36),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("export_type", sa.String(32), nullable=False),
        sa.Column("scope", sa.JSON, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("output_url", sa.Text, nullable=True),
        sa.Column("row_count", sa.Integer, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')",
            name=op.f("ck_export_jobs_status"),
        ),
    )
    op.create_index("export_jobs_user_idx", "export_jobs", ["user_id", "created_at"])

    op.create_table(
        "brand_submissions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("org_id", sa.String(36), nullable=True),
        sa.Column("proposed_name", sa.String(256), nullable=False),
        sa.Column("proposed_industry_id", sa.Integer, nullable=True),
        sa.Column("proposed_aliases", sa.JSON, nullable=True),
        sa.Column("proposed_official_domains", sa.JSON, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("source_url", sa.Text, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("reviewer_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime, nullable=True),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("resulting_brand_id", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'duplicate')",
            name=op.f("ck_brand_submissions_status"),
        ),
    )
    op.create_index(
        "brand_submissions_status_idx",
        "brand_submissions",
        ["status", "created_at"],
    )

    op.create_table(
        "industry_pricing_params",
        sa.Column("industry_id", sa.Integer, primary_key=True),
        sa.Column("tier1_unit_price_cny", sa.Numeric(10, 2), nullable=True),
        sa.Column("tier2_unit_price_cny", sa.Numeric(10, 2), nullable=True),
        sa.Column("tier3_unit_price_cny", sa.Numeric(10, 2), nullable=True),
        sa.Column("tier4_unit_price_cny", sa.Numeric(10, 2), nullable=True),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("industry_pricing_params")
    op.drop_index("brand_submissions_status_idx", table_name="brand_submissions")
    op.drop_table("brand_submissions")
    op.drop_index("export_jobs_user_idx", table_name="export_jobs")
    op.drop_table("export_jobs")
