"""admin_users — admin operator account table

Revision ID: 20260506_admin_users
Revises: 20260506_admin_consolidation
Create Date: 2026-05-06

Phase 2 of admin_console → backend consolidation. The previous Alembic
revision (admin_console_consolidation) absorbed every other admin_console
DDL but missed `admin_users` itself, which was historically created only by
``admin_console/scripts/admin_reset_password.py`` via raw psycopg2.

This revision formalises ``admin_users`` in Alembic so:
- fresh CI / DR Postgres databases auto-create the table on
  ``alembic upgrade head``;
- production hosts no-op (``CREATE TABLE IF NOT EXISTS``);
- the new FastAPI admin auth router can write through SQLAlchemy ORM
  against the same table.

SQLite test DBs skip the body — the FastAPI test suite never exercises
admin_users (admin auth in tests uses User-side mocking).
"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260506_admin_users"
down_revision: str | Sequence[str] | None = "20260506_admin_consolidation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""
        CREATE TABLE IF NOT EXISTS admin_users (
            id VARCHAR(36) PRIMARY KEY,
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(32) NOT NULL DEFAULT 'super_admin',
            status VARCHAR(32) NOT NULL DEFAULT 'active',
            force_password_change_at TIMESTAMP,
            last_password_at TIMESTAMP,
            last_login_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP
        );
    """)


def downgrade() -> None:
    """No-op — admin_users contains operator accounts whose loss would lock
    everyone out. Rollback requires explicit DBA action."""
    return
