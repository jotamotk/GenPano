"""user_auth_module

Revision ID: 20260429_user_auth
Revises: 55a628f2bb7d
Create Date: 2026-04-29 22:30:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260429_user_auth"
down_revision: Union[str, Sequence[str], None] = "55a628f2bb7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("company", sa.String(length=160), nullable=True),
        sa.Column("role", sa.String(length=16), server_default="free", nullable=False),
        sa.Column("provider", sa.String(length=24), server_default="email", nullable=False),
        sa.Column("google_id", sa.String(length=128), nullable=True),
        sa.Column("email_verified", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "newsletter_subscribed", sa.Boolean(), server_default=sa.true(), nullable=False
        ),
        sa.Column("locale", sa.String(length=8), server_default="zh-CN", nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("locale IN ('zh-CN', 'en-US')", name=op.f("ck_users_locale_chk")),
        sa.CheckConstraint(
            "provider IN ('email', 'google')", name=op.f("ck_users_provider_chk")
        ),
        sa.CheckConstraint("role IN ('free', 'paid')", name=op.f("ck_users_role_chk")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("google_id", name=op.f("uq_users_google_id")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)

    op.create_table(
        "user_auth_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_type", sa.String(length=24), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("email_snapshot", sa.String(length=255), nullable=True),
        sa.Column("meta", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False
        ),
        sa.CheckConstraint(
            "token_type IN ('verify_email', 'password_reset', 'oauth_setup')",
            name=op.f("ck_user_auth_tokens_token_type_chk"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_user_auth_tokens_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_auth_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_user_auth_tokens_token_hash")),
    )
    op.create_index(
        op.f("ix_user_auth_tokens_token_hash"),
        "user_auth_tokens",
        ["token_hash"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(op.f("ix_user_auth_tokens_token_hash"), table_name="user_auth_tokens")
    op.drop_table("user_auth_tokens")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
