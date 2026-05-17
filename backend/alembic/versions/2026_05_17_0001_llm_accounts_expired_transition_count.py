"""Add ``expired_transition_count`` column to ``llm_accounts`` (Refs #963).

Audit pain point #2 (from /tmp/.../tasks/a5ea2f0732159e2a1.output): Doubao
accounts ricochet ``expired → re-login → active → expired`` forever because
the existing ``consecutive_fails`` counter is RESET to 0 every time the pool
transitions an account to ``status='expired'`` (see
``geo_tracker/pool/account_pool.py::AccountPool.report_failure``,
EXPIRED_ACCOUNT_REASONS branch). The ban gate
``consecutive_fails >= MAX_CONSECUTIVE_FAILS=3`` therefore never fires for
Doubao, whose primary failure mode IS ``doubao_not_logged_in`` (one of the
expired reasons). Each cycle burns a fresh SMS via the auto-register path
without ever producing a usable query result.

This migration adds ``expired_transition_count INTEGER NOT NULL DEFAULT 0`` so
the companion code change in ``account_pool.py`` can increment a separate
counter on every ``expired`` transition for the same account and permanently
ban (status='banned') accounts that ricochet 3+ times. ``save_cookies`` —
called when a re-login succeeds and writes back fresh cookies — resets the
counter to 0.

Schema change is purely additive:

  - All existing rows backfill to 0 (server_default='0').
  - The column is NOT NULL so the SQLAlchemy default + the
    ``report_failure`` increment can rely on integer arithmetic without a
    None check on read.
  - No CHECK constraint, no FK — minimal blast radius.

Revision ID: 20260517_expired_trans_count
Revises: 20260516_alert_snooze
Create Date: 2026-05-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260517_expired_trans_count"
down_revision: str | Sequence[str] | None = "20260516_alert_snooze"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def _column_exists(table: str, column: str) -> bool:
    insp = inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _table_exists("llm_accounts"):
        return
    if _column_exists("llm_accounts", "expired_transition_count"):
        return
    # Fail fast (5s) instead of hanging forever when a long-lived
    # worker/backend connection holds a conflicting lock on llm_accounts.
    # On Postgres lock_timeout is scoped to the current transaction and
    # auto-resets when the migration commits/rolls back, so we do not need
    # a RESET. The original single ``op.add_column(nullable=False,
    # server_default='0')`` triggered AccessExclusiveLock for the duration
    # of the full-table rewrite and silently waited 14-28 minutes on the
    # production deploys for PR #1102 (8bd1bed) and PR #1104 (e425f21).
    op.execute("SET lock_timeout = '5s'")
    # Step 1: add as nullable, no default — instant on PG 11+, lock held briefly.
    op.add_column(
        "llm_accounts",
        sa.Column("expired_transition_count", sa.Integer(), nullable=True),
    )
    # Step 2: backfill existing rows (~26 rows in prod verify dump
    # 2026-05-16T15:09:58Z; safe to do in one UPDATE).
    op.execute(
        "UPDATE llm_accounts "
        "SET expired_transition_count = 0 "
        "WHERE expired_transition_count IS NULL"
    )
    # Step 3: enforce NOT NULL + default for future inserts. Still takes an
    # AccessExclusiveLock but the table is small so it returns in <1s, well
    # under the 5s lock_timeout.
    op.alter_column(
        "llm_accounts",
        "expired_transition_count",
        nullable=False,
        server_default="0",
    )


def downgrade() -> None:
    if not _table_exists("llm_accounts"):
        return
    if _column_exists("llm_accounts", "expired_transition_count"):
        # Mirror the upgrade lock_timeout so a stuck connection cannot hang
        # the downgrade indefinitely either — column drop also acquires
        # AccessExclusiveLock on llm_accounts.
        op.execute("SET lock_timeout = '5s'")
        op.drop_column("llm_accounts", "expired_transition_count")
