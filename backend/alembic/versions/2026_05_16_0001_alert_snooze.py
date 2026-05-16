"""Add `snoozed_until` column + 'snoozed' status to alerts (PRD §4.8.7).

Closes [audit #1044 B3-3]. The audit found the alert lifecycle CHECK
constraint was hard-locked to ``('unread', 'read', 'ignored', 'resolved')``
with no snooze state. PRD §4.8.7 mandates a snoozed state with an
expiry (default 24h, presets 1h / 4h / 24h / 7d) so users can defer
non-urgent P1s without losing them to the terminal `ignored` state.

Schema changes (all additive, no data migration required):

  1. Add ``snoozed_until TIMESTAMP NULL`` to ``alerts``.
  2. Drop the existing ``ck_alerts_status`` CHECK constraint.
  3. Re-add it with ``'snoozed'`` included.

Why drop-and-recreate instead of using the prior constraint as-is:
SQLite cannot ALTER CHECK constraints in place, and Postgres needs an
explicit ``DROP CONSTRAINT`` + ``ADD CONSTRAINT`` cycle. We do both
explicitly so the migration is deterministic across dialects.

Revision ID: 20260516_alert_snooze
Revises: 20260514_doubao_unblock
Create Date: 2026-05-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260516_alert_snooze"
down_revision: str | Sequence[str] | None = "20260514_doubao_unblock"
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
    if not _table_exists("alerts"):
        return

    if not _column_exists("alerts", "snoozed_until"):
        op.add_column(
            "alerts",
            sa.Column("snoozed_until", sa.DateTime(), nullable=True),
        )

    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute(
            """
            ALTER TABLE alerts DROP CONSTRAINT IF EXISTS ck_alerts_status
            """
        )
        op.execute(
            """
            ALTER TABLE alerts
            ADD CONSTRAINT ck_alerts_status
            CHECK (status IN ('unread', 'read', 'ignored', 'resolved', 'snoozed'))
            """
        )
    elif dialect == "sqlite":
        # SQLite CANNOT ``ALTER TABLE DROP CONSTRAINT`` for inline CHECK
        # constraints, and alembic's batch_alter_table forces the project
        # MetaData naming convention onto the constraint name we pass to
        # `drop_constraint`, which double-prefixes to
        # `ck_alerts_ck_alerts_status` and fails to find the real
        # `ck_alerts_status` on disk. Sidestep both problems with a raw
        # table rebuild: copy data into a fresh table with the new CHECK,
        # then atomically replace the old one.
        bind = op.get_bind()
        bind.execute(sa.text("PRAGMA foreign_keys=OFF"))
        bind.execute(
            sa.text(
                """
                CREATE TABLE alerts__new (
                    id VARCHAR(36) NOT NULL,
                    project_id VARCHAR(36),
                    brand_id INTEGER,
                    source VARCHAR(32) NOT NULL,
                    source_ref_id VARCHAR(64),
                    severity VARCHAR(4) NOT NULL,
                    scope VARCHAR(16) DEFAULT 'user' NOT NULL,
                    title VARCHAR(512) NOT NULL,
                    body TEXT,
                    status VARCHAR(16) DEFAULT 'unread' NOT NULL,
                    triggered_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    read_at DATETIME,
                    read_by VARCHAR(36),
                    resolved_at DATETIME,
                    snoozed_until DATETIME,
                    assigned_to VARCHAR(36),
                    runbook_url TEXT,
                    CONSTRAINT pk_alerts PRIMARY KEY (id),
                    CONSTRAINT ck_alerts_severity CHECK (severity IN ('P0','P1','P2','P3')),
                    CONSTRAINT ck_alerts_scope CHECK (scope IN ('user','operator')),
                    CONSTRAINT ck_alerts_status CHECK (
                        status IN ('unread','read','ignored','resolved','snoozed')
                    ),
                    CONSTRAINT fk_alerts_project_id_projects FOREIGN KEY(project_id)
                        REFERENCES projects (id) ON DELETE CASCADE
                )
                """
            )
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO alerts__new (
                    id, project_id, brand_id, source, source_ref_id, severity,
                    scope, title, body, status, triggered_at, read_at, read_by,
                    resolved_at, snoozed_until, assigned_to, runbook_url
                )
                SELECT
                    id, project_id, brand_id, source, source_ref_id, severity,
                    scope, title, body, status, triggered_at, read_at, read_by,
                    resolved_at, snoozed_until, assigned_to, runbook_url
                FROM alerts
                """
            )
        )
        bind.execute(sa.text("DROP TABLE alerts"))
        bind.execute(sa.text("ALTER TABLE alerts__new RENAME TO alerts"))
        # Re-create indexes that lived on the old table.
        bind.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS alerts_scope_status_idx "
                "ON alerts (scope, status, triggered_at)"
            )
        )
        bind.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS alerts_project_idx ON alerts (project_id, triggered_at)"
            )
        )
        bind.execute(sa.text("PRAGMA foreign_keys=ON"))


def downgrade() -> None:
    if not _table_exists("alerts"):
        return

    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        op.execute("UPDATE alerts SET status='unread' WHERE status='snoozed'")
        op.execute("ALTER TABLE alerts DROP CONSTRAINT IF EXISTS ck_alerts_status")
        op.execute(
            """
            ALTER TABLE alerts
            ADD CONSTRAINT ck_alerts_status
            CHECK (status IN ('unread', 'read', 'ignored', 'resolved'))
            """
        )
        if _column_exists("alerts", "snoozed_until"):
            op.drop_column("alerts", "snoozed_until")
    elif dialect == "sqlite":
        # Mirror the upgrade rebuild for the downgrade path: rewind data
        # into a table with the old CHECK + without `snoozed_until`.
        bind = op.get_bind()
        bind.execute(sa.text("UPDATE alerts SET status='unread' WHERE status='snoozed'"))
        bind.execute(sa.text("PRAGMA foreign_keys=OFF"))
        bind.execute(
            sa.text(
                """
                CREATE TABLE alerts__old (
                    id VARCHAR(36) NOT NULL,
                    project_id VARCHAR(36),
                    brand_id INTEGER,
                    source VARCHAR(32) NOT NULL,
                    source_ref_id VARCHAR(64),
                    severity VARCHAR(4) NOT NULL,
                    scope VARCHAR(16) DEFAULT 'user' NOT NULL,
                    title VARCHAR(512) NOT NULL,
                    body TEXT,
                    status VARCHAR(16) DEFAULT 'unread' NOT NULL,
                    triggered_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    read_at DATETIME,
                    read_by VARCHAR(36),
                    resolved_at DATETIME,
                    assigned_to VARCHAR(36),
                    runbook_url TEXT,
                    CONSTRAINT pk_alerts PRIMARY KEY (id),
                    CONSTRAINT ck_alerts_severity CHECK (severity IN ('P0','P1','P2','P3')),
                    CONSTRAINT ck_alerts_scope CHECK (scope IN ('user','operator')),
                    CONSTRAINT ck_alerts_status CHECK (
                        status IN ('unread','read','ignored','resolved')
                    ),
                    CONSTRAINT fk_alerts_project_id_projects FOREIGN KEY(project_id)
                        REFERENCES projects (id) ON DELETE CASCADE
                )
                """
            )
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO alerts__old (
                    id, project_id, brand_id, source, source_ref_id, severity,
                    scope, title, body, status, triggered_at, read_at, read_by,
                    resolved_at, assigned_to, runbook_url
                )
                SELECT
                    id, project_id, brand_id, source, source_ref_id, severity,
                    scope, title, body, status, triggered_at, read_at, read_by,
                    resolved_at, assigned_to, runbook_url
                FROM alerts
                """
            )
        )
        bind.execute(sa.text("DROP TABLE alerts"))
        bind.execute(sa.text("ALTER TABLE alerts__old RENAME TO alerts"))
        bind.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS alerts_scope_status_idx "
                "ON alerts (scope, status, triggered_at)"
            )
        )
        bind.execute(
            sa.text(
                "CREATE INDEX IF NOT EXISTS alerts_project_idx ON alerts (project_id, triggered_at)"
            )
        )
        bind.execute(sa.text("PRAGMA foreign_keys=ON"))
