"""repair legacy llm_accounts schema drift

Revision ID: 20260507_llm_accts_repair
Revises: 20260507_qpool_repair
Create Date: 2026-05-07

Companion to ``20260507_qpool_repair`` — same bug class, different table.
Existing operator databases already have ``llm_accounts`` (it predates the
FastAPI port and is NOT in genpano_models). Phase 7 slice 7b moves cookie
import / status / reset / delete / auto_login into FastAPI; the new code
SELECTs and UPDATEs the same column set admin_console used, but if any of
those columns are missing on a legacy DB the SPA gets a 500.

This migration is a defense-in-depth safety net: ``ALTER TABLE … ADD COLUMN
IF NOT EXISTS`` for every column the ``app.admin.accounts`` package touches.
Idempotent on healthy DBs, repairs broken ones, no-op on sqlite tests.

Note on revision IDs: the alembic ``alembic_version`` column is VARCHAR(32),
so revision strings must fit ≤32 chars (PR #370 made the same fix to the
query_pool repair migration).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260507_llm_accts_repair"
down_revision: str | Sequence[str] | None = "20260507_qpool_repair"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(name: str) -> bool:
    """Postgres-only existence probe (sqlite test path returns False)."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    row = bind.exec_driver_sql(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s LIMIT 1",
        (name,),
    ).first()
    return row is not None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    if not _table_exists("llm_accounts"):
        # Fresh DB without llm_accounts (the table is upstream-only and not
        # in genpano_models); nothing to repair. Slice 7b's ``_table_exists``
        # guard returns 503 ``llm_accounts_unavailable`` cleanly in this case.
        return

    # Identity / lookup keys.
    op.execute("ALTER TABLE llm_accounts ADD COLUMN IF NOT EXISTS llm_name VARCHAR(64);")
    op.execute("ALTER TABLE llm_accounts ADD COLUMN IF NOT EXISTS phone_number VARCHAR(128);")
    op.execute("ALTER TABLE llm_accounts ADD COLUMN IF NOT EXISTS email VARCHAR(256);")
    op.execute(
        "ALTER TABLE llm_accounts ADD COLUMN IF NOT EXISTS "
        "password_encrypted TEXT NOT NULL DEFAULT '';"
    )

    # Cookie blob + freshness timestamp (cookies_updated_at also handled by
    # the consolidation migration; repeating here is idempotent and lets this
    # migration stand alone for hotfix replays).
    op.execute("ALTER TABLE llm_accounts ADD COLUMN IF NOT EXISTS cookies_json TEXT;")
    op.execute("ALTER TABLE llm_accounts ADD COLUMN IF NOT EXISTS cookies_updated_at TIMESTAMP;")

    # Status / scheduler bookkeeping.
    op.execute(
        "ALTER TABLE llm_accounts ADD COLUMN IF NOT EXISTS "
        "status VARCHAR(32) NOT NULL DEFAULT 'active';"
    )
    op.execute(
        "ALTER TABLE llm_accounts ADD COLUMN IF NOT EXISTS "
        "consecutive_fails INTEGER NOT NULL DEFAULT 0;"
    )
    op.execute(
        "ALTER TABLE llm_accounts ADD COLUMN IF NOT EXISTS "
        "query_count_today INTEGER NOT NULL DEFAULT 0;"
    )
    op.execute(
        "ALTER TABLE llm_accounts ADD COLUMN IF NOT EXISTS daily_limit INTEGER NOT NULL DEFAULT 20;"
    )
    op.execute("ALTER TABLE llm_accounts ADD COLUMN IF NOT EXISTS cooldown_until TIMESTAMP;")
    op.execute(
        "ALTER TABLE llm_accounts ADD COLUMN IF NOT EXISTS "
        "created_at TIMESTAMP NOT NULL DEFAULT NOW();"
    )

    # Match admin_console's ordering / lookup index (fetch_accounts ORDERs by
    # ``llm_name, id``; the upsert key is ``(llm_name, phone_number)``).
    op.execute("CREATE INDEX IF NOT EXISTS idx_llm_accounts_llm_name ON llm_accounts (llm_name);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_llm_accounts_llm_name_phone "
        "ON llm_accounts (llm_name, phone_number);"
    )


def downgrade() -> None:
    """No-op: these columns are part of the Admin Accounts contract."""
    return
