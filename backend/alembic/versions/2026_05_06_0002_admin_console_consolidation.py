"""admin_console schema consolidation — Alembic becomes single owner

Revision ID: 20260506_admin_consolidation
Revises: 20260506_topic_score_daily
Create Date: 2026-05-06

Phase 1 of admin_console → backend consolidation (option C). Until now,
`admin_console/app.py` ran ~13 `_ensure_*_tables()` startup functions that
issued `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE ADD COLUMN IF NOT EXISTS`
for every admin-owned table. Alembic later added some of these tables (Phase O
admin_audit_log, legacy_sql products/hot_topics/scheduler) which created
schema drift — admin_console's startup re-pasted legacy columns onto the new
Alembic tables, producing Frankenstein schemas where INSERTs violated
NOT NULL constraints (the production resource_type 500 storm on every audit
write).

This migration absorbs every remaining DDL action that admin_console used to
do at startup:

  Section B — admin_console-only tables (none in any prior Alembic migration):
    * user_moderation_actions
    * admin_login_attempts
    * topic_plan_runs            + 1 index
    * topic_candidates           + 3 indexes
    * prompt_generation_runs     + 1 index
    * prompt_candidates          + 3 indexes
    * query_generation_runs      + 1 index
    * query_generation_candidates + 4 indexes
    * segments                   + 2 indexes
    * profiles                   + 2 indexes
    * brand_generation_logs      + 1 index

  Section C — ALTER COLUMN on upstream tracker tables (guarded):
    queries / llm_responses / llm_accounts / brands / competitors / prompts /
    users — all wrapped in `_table_exists` so fresh CI/test DBs no-op.

  Section D — one-shot data normalization (lowercase status/target_llm/
  llm_name; cascade-delete queries whose engine is not in the approved list).

After this migration runs in production, the next admin_console deploy
removes every `_ensure_*_tables()` function and `_run_startup_migrations()`,
making Alembic the single schema owner. See the matching admin_console
diff for the deletions.

All operations are Postgres-specific and use raw `IF NOT EXISTS` guards so
re-running on already-migrated production DBs is a no-op. SQLite (CI / unit
tests) skips the body entirely — none of these tables are exercised by the
backend test suite, which uses sqlite+aiosqlite.
"""
from collections.abc import Sequence

from alembic import op
from sqlalchemy import inspect

revision: str = "20260506_admin_consolidation"
down_revision: str | Sequence[str] | None = "20260506_topic_score_daily"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(name: str) -> bool:
    """True iff `name` is a real table in the current bind.

    Used to guard ALTER TABLE / FK references against upstream Tracker-domain
    tables that exist in production but not in fresh CI/test databases.
    """
    return inspect(op.get_bind()).has_table(name)


def _columns(table: str) -> set[str]:
    """Return the set of column names for `table`, or empty if missing.

    Used by Section D data normalization where the upstream `queries` /
    `llm_accounts` tables may exist as schema stubs (created out-of-band)
    without all the columns the legacy admin_console expected.
    """
    if not _table_exists(table):
        return set()
    return {col["name"] for col in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:  # noqa: PLR0915
    if op.get_bind().dialect.name != "postgresql":
        # SQLite CI / unit tests: none of these tables are reachable from the
        # FastAPI backend test suite, so the migration is a no-op.
        return

    # ------------------------------------------------------------------
    # Section B-1 — admin: user moderation + login attempts
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_moderation_actions (
            id VARCHAR(36) PRIMARY KEY,
            user_id VARCHAR(36) NOT NULL,
            operator_id VARCHAR(36),
            action VARCHAR(32) NOT NULL
                CHECK (action IN ('freeze','unfreeze','force_password_reset','soft_delete')),
            reason TEXT,
            expires_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_moderation_user_created "
        "ON user_moderation_actions (user_id, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_moderation_action_created "
        "ON user_moderation_actions (action, created_at DESC);"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS admin_login_attempts (
            id VARCHAR(36) PRIMARY KEY,
            email VARCHAR(255) NOT NULL,
            ip_address VARCHAR(45),
            success BOOLEAN NOT NULL,
            failure_code VARCHAR(32),
            user_agent VARCHAR(512),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    op.execute(
        "ALTER TABLE admin_login_attempts ADD COLUMN IF NOT EXISTS user_agent VARCHAR(512);"
    )

    # ------------------------------------------------------------------
    # Section B-2 — Topic Plan
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS topic_plan_runs (
            id VARCHAR(36) PRIMARY KEY,
            admin_id VARCHAR(36),
            industry_id VARCHAR(128),
            category_id VARCHAR(128),
            brand_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            status VARCHAR(16) NOT NULL DEFAULT 'running'
                CHECK (status IN ('running','completed','failed','cancelled')),
            request_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            coverage_snapshot JSONB,
            llm_model VARCHAR(128),
            llm_usage_json JSONB,
            llm_error TEXT,
            candidates_generated INTEGER NOT NULL DEFAULT 0,
            metrics_json JSONB,
            started_at TIMESTAMP NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("ALTER TABLE topic_plan_runs ADD COLUMN IF NOT EXISTS metrics_json JSONB;")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_topic_plan_runs_created "
        "ON topic_plan_runs (created_at DESC);"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS topic_candidates (
            id VARCHAR(36) PRIMARY KEY,
            run_id VARCHAR(36) REFERENCES topic_plan_runs(id),
            brand_id INTEGER,
            brand_name VARCHAR(256) NOT NULL,
            title VARCHAR(256) NOT NULL,
            dimension VARCHAR(32) NOT NULL,
            reason TEXT,
            confidence FLOAT,
            coverage_gap VARCHAR(256),
            normalized_title VARCHAR(256) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','approved','rejected')),
            reviewed_by VARCHAR(36),
            reviewed_at TIMESTAMP,
            review_reason TEXT,
            approved_topic_id INTEGER,
            product_id INTEGER,
            product_name VARCHAR(256),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("ALTER TABLE topic_candidates ADD COLUMN IF NOT EXISTS product_id INTEGER;")
    op.execute("ALTER TABLE topic_candidates ADD COLUMN IF NOT EXISTS product_name VARCHAR(256);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_topic_candidates_status_created "
        "ON topic_candidates (status, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_topic_candidates_brand_status "
        "ON topic_candidates (brand_id, status);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_topic_candidates_run ON topic_candidates (run_id);"
    )

    # ------------------------------------------------------------------
    # Section B-3 — Prompt Matrix
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS prompt_generation_runs (
            id VARCHAR(36) PRIMARY KEY,
            admin_id VARCHAR(36),
            status VARCHAR(16) NOT NULL DEFAULT 'running'
                CHECK (status IN ('running','completed','failed','cancelled')),
            request_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            selected_topic_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            estimated_prompts INTEGER NOT NULL DEFAULT 0,
            candidates_generated INTEGER NOT NULL DEFAULT 0,
            llm_model VARCHAR(128),
            llm_usage_json JSONB,
            llm_error TEXT,
            metrics_json JSONB,
            started_at TIMESTAMP NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("ALTER TABLE prompt_generation_runs ADD COLUMN IF NOT EXISTS metrics_json JSONB;")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_prompt_generation_runs_created "
        "ON prompt_generation_runs (created_at DESC);"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS prompt_candidates (
            id VARCHAR(36) PRIMARY KEY,
            run_id VARCHAR(36) REFERENCES prompt_generation_runs(id),
            topic_id INTEGER NOT NULL,
            topic_text TEXT,
            brand_id INTEGER,
            brand_name VARCHAR(256),
            dimension VARCHAR(32),
            intent VARCHAR(32) NOT NULL,
            language VARCHAR(16) NOT NULL,
            template_strategy VARCHAR(64),
            template_version VARCHAR(64),
            text TEXT NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','approved','rejected')),
            confidence FLOAT,
            reason TEXT,
            duplicate_of VARCHAR(64),
            tags JSONB NOT NULL DEFAULT '{}'::jsonb,
            reviewed_by VARCHAR(36),
            reviewed_at TIMESTAMP,
            review_reason TEXT,
            approved_prompt_id INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_prompt_candidates_status_created "
        "ON prompt_candidates (status, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_prompt_candidates_topic_status "
        "ON prompt_candidates (topic_id, status);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_prompt_candidates_run ON prompt_candidates (run_id);"
    )

    # ------------------------------------------------------------------
    # Section B-4 — Query Pool
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS query_generation_runs (
            id VARCHAR(36) PRIMARY KEY,
            admin_id VARCHAR(36),
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','running','completed','failed','cancelled')),
            request_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            prompt_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            segment_ids_selected JSONB NOT NULL DEFAULT '[]'::jsonb,
            profiles_per_prompt INTEGER NOT NULL DEFAULT 3,
            desired_engine_policy VARCHAR(64) NOT NULL DEFAULT 'inherit',
            engine_panel_id VARCHAR(128),
            max_candidates INTEGER NOT NULL DEFAULT 12000,
            overflow_policy VARCHAR(32) NOT NULL DEFAULT 'split',
            candidates_estimated INTEGER NOT NULL DEFAULT 0,
            candidates_assembled INTEGER NOT NULL DEFAULT 0,
            estimated_cost NUMERIC,
            preflight_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            llm_model VARCHAR(128),
            llm_usage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            llm_error TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("ALTER TABLE query_generation_runs ADD COLUMN IF NOT EXISTS llm_model VARCHAR(128);")
    op.execute(
        "ALTER TABLE query_generation_runs ADD COLUMN IF NOT EXISTS "
        "llm_usage_json JSONB NOT NULL DEFAULT '{}'::jsonb;"
    )
    op.execute("ALTER TABLE query_generation_runs ADD COLUMN IF NOT EXISTS llm_error TEXT;")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_query_generation_runs_created "
        "ON query_generation_runs (created_at DESC);"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS query_generation_candidates (
            id VARCHAR(36) PRIMARY KEY,
            run_id VARCHAR(36) NOT NULL REFERENCES query_generation_runs(id),
            candidate_seq BIGINT NOT NULL,
            prompt_id VARCHAR(64) NOT NULL,
            segment_id VARCHAR(64),
            profile_id VARCHAR(64),
            rendered_query TEXT NOT NULL,
            render_hash VARCHAR(128) NOT NULL,
            generation_method VARCHAR(32) NOT NULL DEFAULT 'llm',
            llm_model VARCHAR(128),
            llm_usage_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            candidate_status VARCHAR(16) NOT NULL DEFAULT 'candidate'
                CHECK (candidate_status IN ('candidate','review','ready')),
            scheduler_intake_batch_id VARCHAR(64),
            reviewed_by VARCHAR(36),
            reviewed_at TIMESTAMP,
            review_reason TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_query_candidates_run_seq UNIQUE (run_id, candidate_seq)
        );
    """)
    op.execute(
        "ALTER TABLE query_generation_candidates ADD COLUMN IF NOT EXISTS "
        "generation_method VARCHAR(32) NOT NULL DEFAULT 'llm';"
    )
    op.execute(
        "ALTER TABLE query_generation_candidates ADD COLUMN IF NOT EXISTS "
        "llm_model VARCHAR(128);"
    )
    op.execute(
        "ALTER TABLE query_generation_candidates ADD COLUMN IF NOT EXISTS "
        "llm_usage_json JSONB NOT NULL DEFAULT '{}'::jsonb;"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_query_candidates_run_seq "
        "ON query_generation_candidates (run_id, candidate_seq);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_query_candidates_run_status_seq "
        "ON query_generation_candidates (run_id, candidate_status, candidate_seq);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_query_candidates_run_segment_profile_seq "
        "ON query_generation_candidates (run_id, segment_id, profile_id, candidate_seq);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_query_candidates_generation_method "
        "ON query_generation_candidates (generation_method);"
    )

    # ------------------------------------------------------------------
    # Section B-5 — Segments + Profiles
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS segments (
            id VARCHAR(64) PRIMARY KEY,
            code VARCHAR(64) UNIQUE,
            brand_id VARCHAR(128),
            brand_name TEXT,
            name TEXT NOT NULL,
            industry_id VARCHAR(128),
            industry TEXT,
            status VARCHAR(16) NOT NULL DEFAULT 'draft',
            weight NUMERIC NOT NULL DEFAULT 0,
            age_range TEXT,
            income TEXT,
            regions TEXT,
            sampling_rate TEXT,
            note TEXT,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TIMESTAMP,
            created_by VARCHAR(36),
            updated_by VARCHAR(36),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_segments_status_industry "
        "ON segments (status, industry_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_segments_deleted_updated "
        "ON segments (is_deleted, updated_at DESC);"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id VARCHAR(64) PRIMARY KEY,
            segment_id VARCHAR(64),
            code VARCHAR(64),
            brand_id VARCHAR(128),
            brand_name TEXT,
            name TEXT NOT NULL,
            demographic TEXT,
            need TEXT,
            weight NUMERIC NOT NULL DEFAULT 1,
            status VARCHAR(16) NOT NULL DEFAULT 'draft',
            persona_json JSONB,
            is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            deleted_at TIMESTAMP,
            created_by VARCHAR(36),
            updated_by VARCHAR(36),
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_profiles_segment_status "
        "ON profiles (segment_id, status);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_profiles_deleted_updated "
        "ON profiles (is_deleted, updated_at DESC);"
    )

    # ------------------------------------------------------------------
    # Section B-6 — Brand generation logs
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE IF NOT EXISTS brand_generation_logs (
            id VARCHAR(36) PRIMARY KEY,
            industry VARCHAR(128),
            seed_brands JSONB,
            llm_model VARCHAR(128),
            prompt_used TEXT,
            input_params JSONB NOT NULL DEFAULT '{}'::jsonb,
            output_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            brands_generated INTEGER NOT NULL DEFAULT 0,
            brands_imported INTEGER NOT NULL DEFAULT 0,
            tokens_used INTEGER,
            estimated_cost NUMERIC,
            created_by VARCHAR(36),
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_brand_generation_logs_created_at "
        "ON brand_generation_logs (created_at DESC);"
    )

    # ------------------------------------------------------------------
    # Section C — ALTERs on upstream / promoted tables (guarded)
    # ------------------------------------------------------------------
    if _table_exists("llm_responses"):
        op.execute("ALTER TABLE llm_responses ADD COLUMN IF NOT EXISTS citations_json JSONB;")
        op.execute("ALTER TABLE llm_responses ADD COLUMN IF NOT EXISTS response_html TEXT;")
        op.execute(
            "ALTER TABLE llm_responses ADD COLUMN IF NOT EXISTS "
            "analysis_status VARCHAR(16) NOT NULL DEFAULT 'pending';"
        )
        op.execute("ALTER TABLE llm_responses ADD COLUMN IF NOT EXISTS analyzed_at TIMESTAMP;")

    if _table_exists("llm_accounts"):
        op.execute("ALTER TABLE llm_accounts ADD COLUMN IF NOT EXISTS cookies_updated_at TIMESTAMP;")

    if _table_exists("queries"):
        op.execute("ALTER TABLE queries ADD COLUMN IF NOT EXISTS account_id INTEGER;")
        op.execute("ALTER TABLE queries ADD COLUMN IF NOT EXISTS queued_at TIMESTAMP;")
        op.execute("ALTER TABLE queries ADD COLUMN IF NOT EXISTS started_at TIMESTAMP;")
        op.execute("ALTER TABLE queries ADD COLUMN IF NOT EXISTS finished_at TIMESTAMP;")
        op.execute("ALTER TABLE queries ADD COLUMN IF NOT EXISTS latency_ms INTEGER;")
        op.execute("ALTER TABLE queries ADD COLUMN IF NOT EXISTS retry_reason VARCHAR(256);")

    if _table_exists("brands"):
        op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS aliases JSONB;")
        # Brand management columns (admin/_ensure_brand_management_tables).
        op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS name_zh VARCHAR(256);")
        op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS name_en VARCHAR(256);")
        op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS official_domains JSONB;")
        op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS group_id VARCHAR(128);")
        op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS positioning TEXT;")
        op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS headquarters VARCHAR(256);")
        op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS founded_year INTEGER;")
        op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS tags JSONB;")
        op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS status VARCHAR(32);")
        op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS source VARCHAR(64);")
        op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();")
        op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();")
        op.execute("ALTER TABLE brands ADD COLUMN IF NOT EXISTS created_by VARCHAR(36);")

    if _table_exists("competitors"):
        op.execute("ALTER TABLE competitors ADD COLUMN IF NOT EXISTS aliases JSONB;")

    if _table_exists("prompts"):
        op.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS tags JSONB;")
        op.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS intent VARCHAR(32);")
        op.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS language VARCHAR(16);")
        op.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS template_strategy VARCHAR(64);")
        op.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS template_version VARCHAR(64);")
        op.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS status VARCHAR(16);")
        op.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS generated_by VARCHAR(36);")
        op.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();")
        op.execute("ALTER TABLE prompts ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();")

    if _table_exists("users"):
        # admin_console used to add deletion_* columns; users is now a real
        # backend table (promoted from upstream stub) so this ALTER is safe
        # whenever the table exists.
        op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS deletion_requested_at TIMESTAMP;")
        op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS deletion_confirmed_at TIMESTAMP;")

    # ------------------------------------------------------------------
    # Section D — One-shot data normalization (was admin_console
    # `_normalize_query_data` running on every restart).
    #
    # Lowercase enum-ish columns and cascade-delete legacy queries whose
    # engine is not in the approved 4-engine panel. Idempotent. All blocks
    # guard upstream tables individually.
    # ------------------------------------------------------------------
    queries_cols = _columns("queries")
    if "status" in queries_cols:
        op.execute(
            "UPDATE queries SET status = LOWER(status) "
            "WHERE status IS DISTINCT FROM LOWER(status);"
        )
    if "target_llm" in queries_cols:
        op.execute(
            "UPDATE queries SET target_llm = LOWER(target_llm) "
            "WHERE target_llm IS DISTINCT FROM LOWER(target_llm);"
        )

    if "llm_name" in _columns("llm_accounts"):
        op.execute(
            "UPDATE llm_accounts SET llm_name = LOWER(llm_name) "
            "WHERE llm_name IS DISTINCT FROM LOWER(llm_name);"
        )

    # Cascade-delete: queries whose engine is outside the 4-engine panel,
    # plus their downstream rows. Skipped on any DB missing the upstream
    # tables (CI / test).
    cascade_safe = (
        all(
            _table_exists(t)
            for t in (
                "queries",
                "llm_responses",
                "brand_mentions",
                "response_analyses",
                "sentiment_drivers",
                "citation_sources",
                "product_feature_mentions",
            )
        )
        and "target_llm" in queries_cols
        and "query_id" in _columns("llm_responses")
    )
    if cascade_safe:
        op.execute("""
            DO $$
            BEGIN
                CREATE TEMP TABLE _bad_q ON COMMIT DROP AS
                  SELECT id FROM queries
                  WHERE LOWER(COALESCE(target_llm, ''))
                        NOT IN ('chatgpt','doubao','deepseek','gemini');
                CREATE TEMP TABLE _bad_r ON COMMIT DROP AS
                  SELECT id FROM llm_responses WHERE query_id IN (SELECT id FROM _bad_q);

                DELETE FROM product_feature_mentions
                  WHERE analysis_id IN (
                      SELECT id FROM response_analyses
                      WHERE response_id IN (SELECT id FROM _bad_r));
                DELETE FROM sentiment_drivers WHERE response_id IN (SELECT id FROM _bad_r);
                DELETE FROM citation_sources WHERE response_id IN (SELECT id FROM _bad_r);
                DELETE FROM response_analyses WHERE response_id IN (SELECT id FROM _bad_r);
                DELETE FROM brand_mentions WHERE response_id IN (SELECT id FROM _bad_r);
                DELETE FROM llm_responses WHERE query_id IN (SELECT id FROM _bad_q);
                DELETE FROM queries WHERE id IN (SELECT id FROM _bad_q);
            END
            $$;
        """)


def downgrade() -> None:
    """No-op.

    Like `legacy_sql_into_alembic.py`, these tables hold operational data and
    rolling them back would destroy state. Manual DBA action is required if a
    rollback is genuinely needed.
    """
    return
