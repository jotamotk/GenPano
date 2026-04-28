"""session_a1_baseline_8_tables_plus_purpose_default_drop

Revision ID: 15500b81322a
Revises: 55a628f2bb7d
Create Date: 2026-04-28 12:52:05.396407+00:00

A1' Step 1 baseline migration. Two concerns in one revision:

  (1) Eight new admin tables per ADMIN_PRD §4.1.4 / §4.3.7 / §4.4.8
      (round 8 决议版字段集, see CLAUDE.md 决策 #30.G):
        user_moderation_actions / user_activity_stats /
        kg_review_queue / alias_conflicts / brand_submissions /
        alerts / cost_daily / budget_config

  (2) T5 closure: drop the server_default='reset' carry-over from
      A0' baseline on admin_password_resets.purpose, per decision
      #28.G C3 NO SCHEMA DEFAULT (backfill-then-drop pattern).
      The column itself + CHECK constraint already shipped in
      A0' baseline 55a628f2bb7d (decision #30.F). This step
      removes the lingering default only.

FK policy: Only admin_users.id FKs are materialized — App-side
`users` and platform-layer `kg_*` tables don't exist yet
(Sessions 4a' / 1.5' deferred); their references are stored
as plain String(36) UUID columns and will gain FK constraints
in those sessions' migrations.

Cross-DB notes:
- UUID stored as String(36) (matches A0' baseline pattern).
- DateTime is naive (timezone=False) per analyzer.py convention.
- JSONB → sa.JSON(): JSONB on Postgres, TEXT on SQLite (portable).
- BETWEEN CHECK constraints work on both dialects.
- batch_alter_table is required for SQLite ALTER COLUMN; it is a
  no-op wrapper on Postgres so the same code runs everywhere.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15500b81322a'
down_revision: Union[str, Sequence[str], None] = '55a628f2bb7d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ------------------------------------------------------------------
    # 1. user_moderation_actions
    # ------------------------------------------------------------------
    op.create_table(
        'user_moderation_actions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('operator_id', sa.String(length=36), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.CheckConstraint(
            "action IN ('freeze', 'unfreeze', 'force_password_reset', 'soft_delete')",
            name=op.f('ck_user_moderation_actions_action_chk'),
        ),
        sa.ForeignKeyConstraint(
            ['operator_id'],
            ['admin_users.id'],
            name=op.f('fk_user_moderation_actions_operator_id_admin_users'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_user_moderation_actions')),
    )

    # ------------------------------------------------------------------
    # 2. user_activity_stats
    # ------------------------------------------------------------------
    op.create_table(
        'user_activity_stats',
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.Column(
            'login_count_30d',
            sa.Integer(),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column(
            'query_count_30d',
            sa.Integer(),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column('last_active_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('user_id', name=op.f('pk_user_activity_stats')),
    )

    # ------------------------------------------------------------------
    # 3. kg_review_queue
    # ------------------------------------------------------------------
    op.create_table(
        'kg_review_queue',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('target_type', sa.String(length=32), nullable=False),
        sa.Column('target_id', sa.String(length=36), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('submitted_by', sa.String(length=36), nullable=False),
        sa.Column(
            'submitted_at',
            sa.DateTime(),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column('reviewer_id', sa.String(length=36), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "target_type IN ('brand', 'product', 'category')",
            name=op.f('ck_kg_review_queue_target_type_chk'),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'merged')",
            name=op.f('ck_kg_review_queue_status_chk'),
        ),
        sa.ForeignKeyConstraint(
            ['submitted_by'],
            ['admin_users.id'],
            name=op.f('fk_kg_review_queue_submitted_by_admin_users'),
        ),
        sa.ForeignKeyConstraint(
            ['reviewer_id'],
            ['admin_users.id'],
            name=op.f('fk_kg_review_queue_reviewer_id_admin_users'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_kg_review_queue')),
    )

    # ------------------------------------------------------------------
    # 4. alias_conflicts
    # ------------------------------------------------------------------
    op.create_table(
        'alias_conflicts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('alias_value', sa.String(length=255), nullable=False),
        sa.Column('language', sa.String(length=16), nullable=False),
        sa.Column('candidate_ids', sa.JSON(), nullable=False),
        sa.Column('resolved_to_id', sa.String(length=36), nullable=True),
        sa.Column('resolved_admin_id', sa.String(length=36), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ['resolved_admin_id'],
            ['admin_users.id'],
            name=op.f('fk_alias_conflicts_resolved_admin_id_admin_users'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_alias_conflicts')),
    )

    # ------------------------------------------------------------------
    # 5. brand_submissions
    # ------------------------------------------------------------------
    op.create_table(
        'brand_submissions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('submitter_user_id', sa.String(length=36), nullable=False),
        sa.Column('brand_name_zh', sa.String(length=255), nullable=True),
        sa.Column('brand_name_en', sa.String(length=255), nullable=True),
        sa.Column('aliases', sa.JSON(), nullable=True),
        sa.Column('trust_score', sa.Numeric(5, 4), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column(
            'sla_started_at',
            sa.DateTime(),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_admin_id', sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name=op.f('ck_brand_submissions_status_chk'),
        ),
        sa.ForeignKeyConstraint(
            ['resolved_admin_id'],
            ['admin_users.id'],
            name=op.f('fk_brand_submissions_resolved_admin_id_admin_users'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_brand_submissions')),
    )

    # ------------------------------------------------------------------
    # 6. alerts
    # ------------------------------------------------------------------
    op.create_table(
        'alerts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('alert_type', sa.String(length=64), nullable=False),
        sa.Column('severity', sa.String(length=8), nullable=False),
        sa.Column('state', sa.String(length=16), nullable=False),
        sa.Column('module', sa.String(length=64), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column(
            'first_seen_at',
            sa.DateTime(),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column(
            'last_seen_at',
            sa.DateTime(),
            server_default=sa.text('(CURRENT_TIMESTAMP)'),
            nullable=False,
        ),
        sa.Column(
            'count',
            sa.Integer(),
            server_default=sa.text('1'),
            nullable=False,
        ),
        sa.Column('ack_admin_id', sa.String(length=36), nullable=True),
        sa.Column('ack_at', sa.DateTime(), nullable=True),
        sa.Column('resolved_admin_id', sa.String(length=36), nullable=True),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "severity IN ('P0', 'P1', 'P2')",
            name=op.f('ck_alerts_severity_chk'),
        ),
        sa.CheckConstraint(
            "state IN ('open', 'acknowledged', 'resolved')",
            name=op.f('ck_alerts_state_chk'),
        ),
        sa.ForeignKeyConstraint(
            ['ack_admin_id'],
            ['admin_users.id'],
            name=op.f('fk_alerts_ack_admin_id_admin_users'),
        ),
        sa.ForeignKeyConstraint(
            ['resolved_admin_id'],
            ['admin_users.id'],
            name=op.f('fk_alerts_resolved_admin_id_admin_users'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_alerts')),
    )

    # ------------------------------------------------------------------
    # 7. cost_daily
    # ------------------------------------------------------------------
    op.create_table(
        'cost_daily',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('engine_id', sa.String(length=32), nullable=False),
        sa.Column('category', sa.String(length=64), nullable=True),
        sa.Column('industry_id', sa.String(length=36), nullable=True),
        sa.Column('brand_id', sa.String(length=36), nullable=True),
        sa.Column(
            'amount_cny',
            sa.Numeric(14, 4),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column(
            'amount_usd',
            sa.Numeric(14, 4),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column(
            'token_count',
            sa.Integer(),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column(
            'query_count',
            sa.Integer(),
            server_default=sa.text('0'),
            nullable=False,
        ),
        sa.Column('aggregated_from', sa.DateTime(), nullable=False),
        sa.Column('aggregated_to', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_cost_daily')),
        sa.UniqueConstraint(
            'date',
            'engine_id',
            'industry_id',
            'brand_id',
            'category',
            name=op.f('uq_cost_daily_composite'),
        ),
    )

    # ------------------------------------------------------------------
    # 8. budget_config
    # ------------------------------------------------------------------
    op.create_table(
        'budget_config',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('scope', sa.String(length=16), nullable=False),
        sa.Column('scope_id', sa.String(length=36), nullable=True),
        sa.Column('monthly_budget_usd', sa.Numeric(14, 4), nullable=False),
        sa.Column(
            'warning_threshold_pct',
            sa.Integer(),
            server_default=sa.text('80'),
            nullable=False,
        ),
        sa.Column(
            'hard_threshold_pct',
            sa.Integer(),
            server_default=sa.text('100'),
            nullable=False,
        ),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_admin_id', sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "scope IN ('global', 'engine', 'industry', 'brand')",
            name=op.f('ck_budget_config_scope_chk'),
        ),
        sa.CheckConstraint(
            'warning_threshold_pct >= 0 AND warning_threshold_pct <= 100',
            name=op.f('ck_budget_config_warning_threshold_pct_chk'),
        ),
        sa.CheckConstraint(
            'hard_threshold_pct >= 0 AND hard_threshold_pct <= 200',
            name=op.f('ck_budget_config_hard_threshold_pct_chk'),
        ),
        sa.ForeignKeyConstraint(
            ['updated_admin_id'],
            ['admin_users.id'],
            name=op.f('fk_budget_config_updated_admin_id_admin_users'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_budget_config')),
    )

    # ------------------------------------------------------------------
    # T5 closure: DROP server_default on admin_password_resets.purpose
    # ------------------------------------------------------------------
    # column + CHECK ('reset','invitation') already shipped in A0' baseline
    # 55a628f2bb7d (decision #30.F). This drops the leftover default to
    # honor decision #28.G C3 NO SCHEMA DEFAULT (backfill-then-drop).
    # batch_alter_table is required for SQLite ALTER COLUMN; works on PG too.
    with op.batch_alter_table('admin_password_resets') as batch_op:
        batch_op.alter_column(
            'purpose',
            existing_type=sa.String(length=16),
            existing_nullable=False,
            server_default=None,
        )


def downgrade() -> None:
    """Downgrade schema."""
    # T5 reverse: restore server_default='reset' (matches A0' baseline)
    with op.batch_alter_table('admin_password_resets') as batch_op:
        batch_op.alter_column(
            'purpose',
            existing_type=sa.String(length=16),
            existing_nullable=False,
            server_default=sa.text("'reset'"),
        )

    # Drop tables in reverse dependency order
    op.drop_table('budget_config')
    op.drop_table('cost_daily')
    op.drop_table('alerts')
    op.drop_table('brand_submissions')
    op.drop_table('alias_conflicts')
    op.drop_table('kg_review_queue')
    op.drop_table('user_activity_stats')
    op.drop_table('user_moderation_actions')
