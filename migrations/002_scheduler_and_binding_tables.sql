-- Migration: Scheduler config + Account↔Profile binding (M:N)
-- Date: 2026-05-03
-- PR: claude/genpano-scheduling-tracking-9emvp
--
-- Scope:
--   1. account_profile_map: many-to-many between llm_accounts and profiles,
--      with per-binding daily_quota and conflict_acknowledged flag.
--   2. scheduler_config: single-row global scheduling policy.
--   3. scheduler_runs: append-only run history (one row per dispatch).
--
-- Compatibility:
--   - profiles.id is VARCHAR(64) ('pf_xxxx') in the live admin_console
--     schema; we use VARCHAR(64) here.
--   - llm_accounts.profile_id (legacy 1:1) is preserved as the "primary"
--     profile and used as a fallback when no binding rows exist.

-- ═══════════════════════════════════════════════════════════════════════════
-- 1. account_profile_map
-- ═══════════════════════════════════════════════════════════════════════════
-- account_id is NOT a FK on purpose: admin_console often connects as a
-- less-privileged role that lacks REFERENCES on the worker-owned
-- llm_accounts table. App-level cleanup handles cascading deletes.
CREATE TABLE IF NOT EXISTS account_profile_map (
    id                    SERIAL PRIMARY KEY,
    account_id            INTEGER NOT NULL,
    profile_id            VARCHAR(64) NOT NULL,
    daily_quota           INTEGER NOT NULL DEFAULT 1 CHECK (daily_quota >= 0),
    conflict_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    created_at            TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_apm_account_profile UNIQUE (account_id, profile_id)
);
CREATE INDEX IF NOT EXISTS idx_apm_account ON account_profile_map (account_id);
CREATE INDEX IF NOT EXISTS idx_apm_profile ON account_profile_map (profile_id);

-- ═══════════════════════════════════════════════════════════════════════════
-- 2. scheduler_config (single row)
-- ═══════════════════════════════════════════════════════════════════════════
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
ALTER TABLE scheduler_config ADD COLUMN IF NOT EXISTS engine_caps JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Seed exactly one row if empty (the "global" config).
INSERT INTO scheduler_config (mode, daily_time, timezone, retry_max, paused_engines)
SELECT 'auto', '09:00', 'Asia/Shanghai', 3, '[]'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM scheduler_config);

-- ═══════════════════════════════════════════════════════════════════════════
-- 3. scheduler_runs
-- ═══════════════════════════════════════════════════════════════════════════
CREATE TABLE IF NOT EXISTS scheduler_runs (
    id              SERIAL PRIMARY KEY,
    started_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMP,
    mode            VARCHAR(16),
    target_total    INTEGER NOT NULL DEFAULT 0,
    queries_created INTEGER NOT NULL DEFAULT 0,
    note            TEXT
);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_started
    ON scheduler_runs (started_at DESC);

-- ═══════════════════════════════════════════════════════════════════════════
-- 4. query_schedules — recurring query plans
-- ═══════════════════════════════════════════════════════════════════════════
-- Each row defines a recurring query: same query_text + (LLM, profile)
-- pair, fired every cadence_days. The dispatcher consumes rows whose
-- next_run_at <= now(), creates a row in `queries`, then advances
-- next_run_at. A `queries.schedule_id` FK lets attempts trace back to
-- their plan so the timeline can be reconstructed.
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
CREATE INDEX IF NOT EXISTS idx_qs_next_run
    ON query_schedules (enabled, next_run_at);

-- queries.schedule_id (additive, no FK to keep migration cheap on big tables)
ALTER TABLE queries ADD COLUMN IF NOT EXISTS schedule_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_queries_schedule
    ON queries (schedule_id);
