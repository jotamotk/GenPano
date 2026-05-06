"""drop admin_audit_log.operator_id → users(id) FK

Revision ID: 20260506_drop_audit_operator_fk
Revises: 20260506_admin_users
Create Date: 2026-05-06

Phase O originally declared a FOREIGN KEY from
``admin_audit_log.operator_id`` to ``users.id`` on the assumption that the
operator is always a regular product user with role='paid'. That assumption
is wrong: ``admin_console`` writes audit rows with ``operator_id`` taken
from ``admin_users.id`` — a separate identity table. ``admin_users`` rows
do NOT live in ``users``, so every audit-emitting admin operation done
through the legacy Flask path violates the FK with::

    insert or update on table "admin_audit_log" violates foreign key
    constraint "fk_admin_audit_log_operator_id_users"
    DETAIL: Key (operator_id)=(<admin_users.id>) is not present in
    table "users".

Drop the FK so both identity systems can coexist while we incrementally
migrate routes off admin_console (Phase 3-X). The column itself stays
``VARCHAR(36) NOT NULL`` — readers must consult either ``admin_users``
or ``users`` depending on context.

Sibling FK on ``comms_announcements.created_by`` (also pointed at
``users.id``) is left in place — that table is only written by the
backend's new admin routes, where the operator IS a regular user.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260506_drop_audit_operator_fk"
down_revision: str | Sequence[str] | None = "20260506_admin_users"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        # SQLite tests use fresh DBs reflected from current ORM metadata
        # (which we'll drop the FK from too); nothing to do here.
        return
    # Idempotent — IF EXISTS so re-running on a DB that's already had the
    # constraint removed (or never had it) is a no-op.
    op.execute(
        "ALTER TABLE admin_audit_log "
        "DROP CONSTRAINT IF EXISTS fk_admin_audit_log_operator_id_users;"
    )


def downgrade() -> None:
    """Re-adding the FK would re-introduce the production 500 storm — no-op."""
    return
