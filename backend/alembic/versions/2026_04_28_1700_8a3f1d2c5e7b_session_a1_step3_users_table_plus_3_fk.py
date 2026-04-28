"""session_a1_step3_users_table_plus_3_fk

Revision ID: 8a3f1d2c5e7b
Revises: 15500b81322a
Create Date: 2026-04-28 17:00:00.000000+00:00

A1' Step 3 — Path B Variant 2 (CLAUDE.md decision #30.H):

  (1) Promote `users` from upstream-stub idiom to a real table per
      DATA_MODEL §1.1: 11 columns + 2 indexes (idx_users_email,
      idx_users_deletion partial WHERE deletion_requested_at IS NOT NULL).

  (2) Materialize three deferred FKs introduced in Step 1 (15500b81322a):
        user_moderation_actions.user_id  -> users.id  ON DELETE CASCADE
        user_activity_stats.user_id      -> users.id  ON DELETE CASCADE
        brand_submissions.submitter_user_id -> users.id ON DELETE SET NULL
      The third column is also relaxed from NOT NULL to NULLABLE so the
      SET NULL semantics are reachable.

Cross-DB notes:
- batch_alter_table is required for SQLite ALTER COLUMN / add FK on an
  existing table; on Postgres it is a no-op wrapper so the same code
  runs everywhere.
- Email regex CHECK from DATA_MODEL §1.1 is enforced at the API layer
  (Pydantic v2 EmailStr) rather than at the DB level — Postgres `~*`
  has no SQLite analogue. Documented in app/models/user.py module
  docstring and the round 9 / round-10 deviation note in CLAUDE.md.
- DateTime is naive (timezone=False) per analyzer.py / admin.py
  convention. UTC is the application-level invariant.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8a3f1d2c5e7b"
down_revision: Union[str, Sequence[str], None] = "15500b81322a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ------------------------------------------------------------------
    # 1. Create users table (DATA_MODEL §1.1 — 11 columns)
    # ------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("name_zh", sa.String(length=100), nullable=True),
        sa.Column("name_en", sa.String(length=100), nullable=True),
        sa.Column("preferences", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("deletion_requested_at", sa.DateTime(), nullable=True),
        sa.Column("deletion_confirmed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
    )

    # ------------------------------------------------------------------
    # 2. Indexes — idx_users_email + partial idx_users_deletion
    # ------------------------------------------------------------------
    op.create_index(op.f("idx_users_email"), "users", ["email"], unique=False)
    op.create_index(
        "idx_users_deletion",
        "users",
        ["deletion_requested_at"],
        unique=False,
        postgresql_where=sa.text("deletion_requested_at IS NOT NULL"),
        sqlite_where=sa.text("deletion_requested_at IS NOT NULL"),
    )

    # ------------------------------------------------------------------
    # 3. Materialize FK on user_moderation_actions.user_id (CASCADE)
    # ------------------------------------------------------------------
    with op.batch_alter_table("user_moderation_actions") as batch_op:
        batch_op.create_foreign_key(
            "fk_user_moderation_actions_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # ------------------------------------------------------------------
    # 4. Materialize FK on user_activity_stats.user_id (CASCADE)
    # ------------------------------------------------------------------
    with op.batch_alter_table("user_activity_stats") as batch_op:
        batch_op.create_foreign_key(
            "fk_user_activity_stats_user_id_users",
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # ------------------------------------------------------------------
    # 5. Relax brand_submissions.submitter_user_id to nullable + FK SET NULL
    # ------------------------------------------------------------------
    with op.batch_alter_table("brand_submissions") as batch_op:
        batch_op.alter_column(
            "submitter_user_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch_op.create_foreign_key(
            "fk_brand_submissions_submitter_user_id_users",
            "users",
            ["submitter_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop FKs in reverse order, then revert nullable, then drop users.
    with op.batch_alter_table("brand_submissions") as batch_op:
        batch_op.drop_constraint(
            "fk_brand_submissions_submitter_user_id_users", type_="foreignkey"
        )
        batch_op.alter_column(
            "submitter_user_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )

    with op.batch_alter_table("user_activity_stats") as batch_op:
        batch_op.drop_constraint(
            "fk_user_activity_stats_user_id_users", type_="foreignkey"
        )

    with op.batch_alter_table("user_moderation_actions") as batch_op:
        batch_op.drop_constraint(
            "fk_user_moderation_actions_user_id_users", type_="foreignkey"
        )

    op.drop_index("idx_users_deletion", table_name="users")
    op.drop_index(op.f("idx_users_email"), table_name="users")
    op.drop_table("users")
