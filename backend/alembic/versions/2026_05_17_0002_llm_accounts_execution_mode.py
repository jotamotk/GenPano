"""Add ``execution_mode`` + ``vm_id`` columns to ``llm_accounts`` (Refs Epic #1110 / Issue #1114).

Phase 1 of the VM-per-account architecture (Epic #1110). The legacy production
behavior is "local launch + cookie injection per query" (``LocalLaunchConnector``
from PR #1120 / Issue #1113). Issue #1114 adds a second connector
(``RemoteCDPConnector``) that connects via CDP to a dedicated VM holding a
persistent logged-in browser for a single account. Each ``llm_accounts`` row
needs to declare which model it follows so the ``select_executor`` router can
pick the right ``BrowserConnector`` at query-dispatch time.

Schema change is **purely additive** + a CHECK constraint:

  - ``execution_mode TEXT NOT NULL DEFAULT 'local_cookie'`` — every existing
    row backfills to ``local_cookie``, so production behavior is unchanged.
    The router treats ``'vm_session'`` as opt-in and gated by the
    ``VM_EXECUTOR_ENABLED`` feature flag (default off).
  - ``vm_id TEXT NULL`` — references the VM record managed by the registry
    (see ``geo_tracker.agent.executors.registry.VmRegistry`` and the watchdog
    from Issue #1115). ``NULL`` for ``local_cookie`` rows.
  - ``chk_exec_mode_cookies`` CHECK ``(execution_mode = 'local_cookie' OR
    cookies_json IS NULL)`` — defends against the R2.5 "self-cloning device"
    failure: a ``vm_session`` row carrying ``cookies_json`` would let the
    local connector and the remote CDP path both attempt to drive the same
    account from different browsers, which Doubao/ChatGPT will treat as a
    session theft and ban. By making the constraint reject any ``vm_session``
    row that still has cookies, we make the failure surface at write time
    rather than as a production ban storm.

Revision ID: 20260517_exec_mode
Revises: 20260517_expired_trans_count
Create Date: 2026-05-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260517_exec_mode"
down_revision: str | Sequence[str] | None = "20260517_expired_trans_count"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CHECK_NAME = "chk_exec_mode_cookies"
CHECK_SQL = "(execution_mode = 'local_cookie' OR cookies_json IS NULL)"


def _table_exists(name: str) -> bool:
    return inspect(op.get_bind()).has_table(name)


def _column_exists(table: str, column: str) -> bool:
    insp = inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def _constraint_exists(table: str, name: str) -> bool:
    insp = inspect(op.get_bind())
    if not insp.has_table(table):
        return False
    try:
        constraints = insp.get_check_constraints(table)
    except NotImplementedError:
        # SQLite dialect under some SQLAlchemy versions does not implement
        # get_check_constraints; the downgrade path inspects the table SQL
        # instead, but for upgrade idempotency we just assume not-present.
        return False
    return any(c.get("name") == name for c in constraints)


def upgrade() -> None:
    if not _table_exists("llm_accounts"):
        return

    # Mirrors the lock_timeout discipline established by the sibling
    # ``2026_05_17_0001_llm_accounts_expired_transition_count.py`` migration:
    # fail fast instead of waiting indefinitely when a long-lived worker
    # connection holds AccessExclusiveLock on llm_accounts. On Postgres
    # lock_timeout is scoped to the current transaction so the alembic
    # commit/rollback resets it automatically.
    is_postgres = op.get_bind().dialect.name == "postgresql"
    if is_postgres:
        op.execute("SET lock_timeout = '5s'")

    if not _column_exists("llm_accounts", "execution_mode"):
        # Add as NOT NULL with DEFAULT in one step. The default backfills
        # every existing row to 'local_cookie' so production behavior is
        # preserved (the router only switches to the VM path when the flag
        # is enabled AND the row is explicitly 'vm_session').
        op.add_column(
            "llm_accounts",
            sa.Column(
                "execution_mode",
                sa.Text(),
                nullable=False,
                server_default="local_cookie",
            ),
        )

    if not _column_exists("llm_accounts", "vm_id"):
        op.add_column(
            "llm_accounts",
            sa.Column("vm_id", sa.Text(), nullable=True),
        )

    if not _constraint_exists("llm_accounts", CHECK_NAME):
        # SQLite does not support ALTER TABLE ADD CONSTRAINT, so the
        # CHECK is only created on Postgres. SQLite is the test-only
        # driver (production runs Postgres exclusively); the static
        # ORM-level model still expresses the invariant, and the
        # ``test_account_pool_vm_session.py`` suite confirms the Python
        # branches do the right thing without relying on a DB-level
        # rejection. If a future test path needs the constraint on
        # SQLite, swap this to ``with op.batch_alter_table('llm_accounts')
        # as batch_op: batch_op.create_check_constraint(...)``, which
        # forces SQLite into the copy-and-move recreate path.
        if is_postgres:
            op.create_check_constraint(
                CHECK_NAME,
                "llm_accounts",
                CHECK_SQL,
            )


def downgrade() -> None:
    if not _table_exists("llm_accounts"):
        return

    is_postgres = op.get_bind().dialect.name == "postgresql"
    if is_postgres:
        op.execute("SET lock_timeout = '5s'")

    if is_postgres and _constraint_exists("llm_accounts", CHECK_NAME):
        op.drop_constraint(CHECK_NAME, "llm_accounts", type_="check")

    if _column_exists("llm_accounts", "vm_id"):
        op.drop_column("llm_accounts", "vm_id")

    if _column_exists("llm_accounts", "execution_mode"):
        op.drop_column("llm_accounts", "execution_mode")
