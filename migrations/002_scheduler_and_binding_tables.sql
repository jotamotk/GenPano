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
CREATE TABLE IF NOT EXISTS account_profile_map (
    id                    SERIAL PRIMARY KEY,
    account_id            INTEGER NOT NULL REFERENCES llm_accounts(id) ON DELETE CASCADE,
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
    retry_max       INTEGER      NOT NULL DEFAULT 3 CHECK (retry_max >= 0),
    paused_engines  JSONB        NOT NULL DEFAULT '[]'::jsonb,
    updated_at      TIMESTAMP    NOT NULL DEFAULT NOW()
);

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
