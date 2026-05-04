-- Module D-1: Hotspots / current events for piggyback prompts
--
-- Insertion layer is Prompt — Hotspots are short-lived (≈ 14 day window) and
-- the same evergreen Topic ("代购真伪辨别") may grow new Prompts during a hot
-- event ("辛巴事件后代购还能信吗") without disturbing the Topic library.
--
-- Lifecycle: draft (pending review) → active → expired (auto-archived past
-- effective_until). Sources: admin-typed (status=active immediately) +
-- collector-collected (status=draft, awaits review).

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

CREATE INDEX IF NOT EXISTS idx_hot_topics_active   ON hot_topics (status, effective_until);
CREATE INDEX IF NOT EXISTS idx_hot_topics_industry ON hot_topics (industry);
CREATE INDEX IF NOT EXISTS idx_hot_topics_brand    ON hot_topics (brand_id);
CREATE INDEX IF NOT EXISTS idx_hot_topics_source   ON hot_topics (source, status);

-- Primary insertion point on Prompt — generated prompts that piggyback on a
-- hotspot stamp this FK so we can trace impact.
ALTER TABLE prompts ADD COLUMN IF NOT EXISTS hotspot_id INTEGER;
CREATE INDEX IF NOT EXISTS idx_prompts_hotspot ON prompts (hotspot_id);
