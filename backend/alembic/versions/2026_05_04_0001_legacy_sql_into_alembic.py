"""legacy SQL migrations 002/003/004 into alembic SSOT (Phase R.2 / ADR-002)

Revision ID: 20260504_legacy_sql
Revises: 20260429_user_auth
Create Date: 2026-05-04

Brings the following 6 tables + 2 column ALTERs into the single Alembic head,
matching what `migrations/{002,003,004}*.sql` produced. All operations are
**idempotent** via raw `IF NOT EXISTS` guards so the existing production /
preview DB upgrades cleanly without touching pre-existing rows.

**Upstream-table guard**: the column ALTERs and FK references depend on
upstream Tracker-domain tables (`brands`, `topics`, `prompts`, `queries`)
which exist in production (created pre-alembic) but NOT in fresh CI/test
databases. Each block checks via SQLAlchemy Inspector whether the upstream
table exists; if not (fresh DB), the block is a no-op. This keeps `alembic
upgrade head` working on both production and CI.

Tables (CREATE IF NOT EXISTS, with upstream-table guard where FK exists):
  - account_profile_map (002, no upstream FK)
  - scheduler_config + 1 seed row (002)
  - scheduler_runs (002)
  - query_schedules (002)
  - products (003, FK→brands — guarded)
  - hot_topics (004, FK→brands — guarded)

Column ALTERs (ADD COLUMN IF NOT EXISTS, all guarded):
  - queries.schedule_id (002)
  - topics.product_id (003)
  - prompts.hotspot_id (004)

Indexes are created IF NOT EXISTS.

`downgrade()` is a **no-op** — these tables predate alembic in production and
removing them would destroy operational data. Schema rollback for these
specific tables must be done manually with explicit DBA approval.

See ADR-002 in `docs/ADR/002-schema-ssot-single-alembic.md`.
"""
from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "20260504_legacy_sql"
down_revision: str | Sequence[str] | None = "20260429_user_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(name: str) -> bool:
    """True iff `name` is a real table in the current DB.

    Used to guard ALTER TABLE / FK references against upstream Tracker-domain
    tables that exist in production but not in fresh CI/test databases.
    """
    bind = op.get_bind()
    return inspect(bind).has_table(name)


def upgrade() -> None:
    """Upgrade schema — idempotent absorb of legacy 002/003/004 SQL."""

    is_postgres = op.get_bind().dialect.name == "postgresql"

    # ───────────────────────────────────────────────────────────────────
    # All operations below are PostgreSQL-specific (use JSONB, NOW(),
    # IF NOT EXISTS DDL, INTERVAL). On SQLite (CI), we skip the entire
    # migration body — these tables are Tracker-domain and never exist
    # on a fresh test DB anyway.
    # ───────────────────────────────────────────────────────────────────
    if not is_postgres:
        return

    # ───────────────────────────────────────────────────────────────────
    # 002: account_profile_map (no upstream FK, always safe)
    # ───────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS account_profile_map (
            id                    SERIAL PRIMARY KEY,
            account_id            INTEGER NOT NULL,
            profile_id            VARCHAR(64) NOT NULL,
            daily_quota           INTEGER NOT NULL DEFAULT 1 CHECK (daily_quota >= 0),
            conflict_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
            created_at            TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_apm_account_profile UNIQUE (account_id, profile_id)
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_apm_account ON account_profile_map (account_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_apm_profile ON account_profile_map (profile_id);")

    # ───────────────────────────────────────────────────────────────────
    # 002: scheduler_config (single-row seeded global policy)
    # ───────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduler_config (
            id              SERIAL PRIMARY KEY,
            mode            VARCHAR(16)  NOT NULL DEFAULT 'auto'
                            CHECK (mode IN ('auto', 'manual', 'paused')),
            daily_time      VARCHAR(8)   NOT NULL DEFAULT '09:00',
            timezone        VARCHAR(64)  NOT NULL DEFAULT 'Asia/Shanghai',
            temp_global_cap INTEGER,
            engine_caps     JSONB        NOT NULL DEFAULT '{}'::jsonb,
            retry_max       INTEGER      NOT NULL DEFAULT 3 CHECK (retry_max >= 0),
            paused_engines  JSONB        NOT NULL DEFAULT '[]'::jsonb,
            updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
        );
    """)
    op.execute(
        "ALTER TABLE scheduler_config ADD COLUMN IF NOT EXISTS engine_caps "
        "JSONB NOT NULL DEFAULT '{}'::jsonb;"
    )
    op.execute("""
        INSERT INTO scheduler_config (mode, daily_time, timezone, retry_max, paused_engines)
        SELECT 'auto', '09:00', 'Asia/Shanghai', 3, '[]'::jsonb
        WHERE NOT EXISTS (SELECT 1 FROM scheduler_config);
    """)

    # ───────────────────────────────────────────────────────────────────
    # 002: scheduler_runs (no upstream FK)
    # ───────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS scheduler_runs (
            id              SERIAL PRIMARY KEY,
            started_at      TIMESTAMP NOT NULL DEFAULT NOW(),
            finished_at     TIMESTAMP,
            mode            VARCHAR(16),
            target_total    INTEGER NOT NULL DEFAULT 0,
            queries_created INTEGER NOT NULL DEFAULT 0,
            note            TEXT
        );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_scheduler_runs_started "
        "ON scheduler_runs (started_at DESC);"
    )

    # ───────────────────────────────────────────────────────────────────
    # 002: query_schedules (no upstream FK; queries.schedule_id ALTER guarded)
    # ───────────────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS query_schedules (
            id            SERIAL PRIMARY KEY,
            query_text    TEXT       NOT NULL,
            profile_id    VARCHAR(64),
            target_llm    VARCHAR(32) NOT NULL,
            cadence_days  INTEGER    NOT NULL DEFAULT 1 CHECK (cadence_days >= 1),
            next_run_at   TIMESTAMP  NOT NULL DEFAULT NOW(),
            last_run_at   TIMESTAMP,
            enabled       BOOLEAN    NOT NULL DEFAULT TRUE,
            note          TEXT,
            brand_id      INTEGER,
            prompt_id     INTEGER,
            created_at    TIMESTAMP  NOT NULL DEFAULT NOW(),
            updated_at    TIMESTAMP  NOT NULL DEFAULT NOW()
        );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_qs_next_run "
        "ON query_schedules (enabled, next_run_at);"
    )

    # queries.schedule_id additive — only if `queries` table exists
    # (Tracker-domain table; absent on fresh CI DB, present in production)
    if _table_exists("queries"):
        op.execute("ALTER TABLE queries ADD COLUMN IF NOT EXISTS schedule_id INTEGER;")
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_queries_schedule ON queries (schedule_id);"
        )

    # ───────────────────────────────────────────────────────────────────
    # 003: products (FK→brands — guarded) + topics.product_id ALTER (guarded)
    # ───────────────────────────────────────────────────────────────────
    if _table_exists("brands"):
        op.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id            SERIAL PRIMARY KEY,
                brand_id      INTEGER NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
                name          VARCHAR(256) NOT NULL,
                sku           VARCHAR(128),
                category      VARCHAR(128),
                description   TEXT,
                aliases       JSONB,
                status        VARCHAR(16) NOT NULL DEFAULT 'active'
                               CHECK (status IN ('active', 'archived')),
                created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at    TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        op.execute("CREATE INDEX IF NOT EXISTS idx_products_brand ON products (brand_id);")
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_products_status_brand "
            "ON products (status, brand_id);"
        )
        op.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_products_brand_name "
            "ON products (brand_id, name);"
        )

    if _table_exists("topics"):
        op.execute("ALTER TABLE topics ADD COLUMN IF NOT EXISTS product_id INTEGER;")
        op.execute("CREATE INDEX IF NOT EXISTS idx_topics_product ON topics (product_id);")

    # ───────────────────────────────────────────────────────────────────
    # 004: hot_topics (FK→brands — guarded) + prompts.hotspot_id ALTER (guarded)
    # ───────────────────────────────────────────────────────────────────
    if _table_exists("brands"):
        op.execute("""
            CREATE TABLE IF NOT EXISTS hot_topics (
                id              SERIAL PRIMARY KEY,
                title           VARCHAR(256) NOT NULL,
                summary         TEXT,
                category        VARCHAR(64),
                source          VARCHAR(64) NOT NULL DEFAULT 'manual',
                source_url      TEXT,
                raw_rank        INTEGER,
                raw_metric      VARCHAR(128),
                industry        VARCHAR(128),
                brand_id        INTEGER REFERENCES brands(id) ON DELETE SET NULL,
                effective_from  TIMESTAMP NOT NULL DEFAULT NOW(),
                effective_until TIMESTAMP NOT NULL DEFAULT NOW() + INTERVAL '14 days',
                status          VARCHAR(16) NOT NULL DEFAULT 'active'
                                   CHECK (status IN ('draft', 'active', 'expired', 'rejected')),
                created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_hot_topics_active "
            "ON hot_topics (status, effective_until);"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_hot_topics_industry ON hot_topics (industry);"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_hot_topics_brand ON hot_topics (brand_id);"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_hot_topics_source ON hot_topics (source, status);"
        )

    if _table_exists("prompts"):
        op.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS hotspot_id INTEGER;")
        op.execute("CREATE INDEX IF NOT EXISTS idx_prompts_hotspot ON prompts (hotspot_id);")


def downgrade() -> None:
    """No-op: these tables predate alembic in production. Removing them via
    automated downgrade would destroy operational data. Manual rollback only,
    with explicit DBA approval. See ADR-002."""
