"""Phase M — Organizations + UserApiKeys.

Revision ID: 20260505_phase_m
Revises: 20260505_phase_n
Create Date: 2026-05-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260505_phase_m"
down_revision: str | Sequence[str] | None = "20260505_phase_n"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(64), unique=True, nullable=True),
        sa.Column("plan", sa.String(16), nullable=False, server_default="free"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "user_api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("org_id", sa.String(36), nullable=True),
        sa.Column("name", sa.String(64), nullable=True),
        sa.Column("hash", sa.String(128), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("scope", sa.JSON, nullable=True),
        sa.Column("last_used_at", sa.DateTime, nullable=True),
        sa.Column("usage_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rate_limit_per_minute", sa.Integer, nullable=False, server_default="60"),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime, nullable=True),
    )
    op.create_index("user_api_keys_user_idx", "user_api_keys", ["user_id"])


def downgrade() -> None:
    op.drop_index("user_api_keys_user_idx", table_name="user_api_keys")
    op.drop_table("user_api_keys")
    op.drop_table("organizations")
