# DATA_MODEL.md — GENPANO Backend Schema

> **Status**: GENPANO MVP target/reference schema (2026-04-30 code-first reset)
>
> **Scope**: This document specifies the planned database schema for MVP in PostgreSQL 15+.
> For development and CI, a SQLite adapter layer translates `JSONB` → `JSON`, `UUID` → `TEXT`, and handles dialect differences.
>
> **Authority**: Design reference for database initialization and API implementation. Current runtime truth is the checked-in migrations plus ORM/code in `geo_tracker/db/models.py`, `backend/app/models/**`, and live query paths. When this document conflicts with code, treat it as target/drift to resolve explicitly, not as proof that the running adapter is wrong.
>
> **Linked to**:
> - `PRD.md` — §4.0 (entities), §4.2 (Pipeline), §4.6 (KPI cards)
> - `ADMIN_PRD.md` + `_B_PIPELINE.md` + `_C_KG.md` — Admin-facing entities

---

## 0. Conventions

### Naming
- **Tables**: `snake_case`, plural (e.g., `users`, `ai_responses`, `kg_brands`)
- **Columns**: `snake_case`
- **Primary Keys**: UUID, auto-generated via `gen_random_uuid()`, column name `id`
- **Timestamps**: `created_at` (immutable) and `updated_at` (trigger-driven), both `TIMESTAMPTZ`
- **Foreign Keys**: Explicit `REFERENCES` with named constraints; `ON DELETE` behavior documented per section
- **Soft Deletes**: `deleted_at TIMESTAMPTZ` where needed; hard delete + audit log elsewhere
- **Indexes**: `idx_<table>_<columns_or_purpose>` (e.g., `idx_responses_engine_date`)
- **Materialized Views**: `mv_<purpose>` (e.g., `mv_heatmap_mention_agg`)

### Column Order
1. Primary Key
2. Foreign Keys
3. Natural key / Unique constraints
4. Data columns
5. Timestamps
6. JSONB / Status enums

### JSON Columns
- **Type**: `JSONB` in Postgres (with `GIN` index when queried; SQLite uses `JSON`)
- **Usage**: Reserved for variable shapes (filter rules, LLM results, diffs); scalar data in columns
- **Schema**: Document structure in comments or separate `.jsonschema` file if complex

### Enums
- **Method**: PostgreSQL `CREATE TYPE` or SQL `CHECK` constraints (SELECT from WHERE clause)
- **Cardinality**: Keep under 20 values; if > 20, consider lookup table
- **Extensibility**: Always reserve `unknown` / `other` for forward compatibility

---

## 1. Core Entities

### 1.1 users
```sql
CREATE TABLE users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email VARCHAR(255) NOT NULL UNIQUE,
  email_verified_at TIMESTAMPTZ,
  password_hash VARCHAR(255),
  name_zh VARCHAR(100),
  name_en VARCHAR(100),
  preferences JSONB DEFAULT '{}',  -- locale, timezone, notification_opts, etc.
  deletion_requested_at TIMESTAMPTZ,  -- DECISIONS §5: 30-day soft delete window
  deletion_confirmed_at TIMESTAMPTZ,  -- After 30 days, marked for hard delete
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$')
);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_deletion ON users(deletion_requested_at) WHERE deletion_requested_at IS NOT NULL;
```
**Why**: Core user identity, linked to projects, API keys, brand submissions, audit logs.
**Soft Delete**: deletion_requested_at triggers 30-day grace period; cron job at day 31 hard-deletes and cascades to projects/brands/responses.

### 1.2 projects
```sql
CREATE TABLE projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  industry_id UUID NOT NULL REFERENCES kg_industries(id) ON DELETE RESTRICT,
  primary_brand_id UUID NOT NULL REFERENCES kg_brands(id) ON DELETE RESTRICT,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  competitor_brand_ids UUID[] DEFAULT '{}',  -- Array of kg_brands.id; empty = none selected
  preferences JSONB DEFAULT '{}',  -- report_frequency, alert_settings, etc.
  status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'archived', 'deleted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(user_id, name),
  FOREIGN KEY (user_id, primary_brand_id) DEFERRABLE INITIALLY DEFERRED  -- Soft constraint for multi-tenant queries
);
CREATE INDEX idx_projects_user_industry ON projects(user_id, industry_id);
CREATE INDEX idx_projects_primary_brand ON projects(primary_brand_id);
```
**Why**: User-facing view layer. Project scopes all Dashboard / Topics / Drilldown queries. Filters platform-layer data via primary_brand_id + competitor_brand_ids.
**Cascade**: ON DELETE CASCADE for users; RESTRICT for brands (user cannot accidentally orphan a brand).

### 1.3 kg_industries
```sql
CREATE TABLE kg_industries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name_zh VARCHAR(100) NOT NULL,
  name_en VARCHAR(100) NOT NULL,
  slug VARCHAR(100) NOT NULL UNIQUE,
  description TEXT,
  parent_industry_id UUID REFERENCES kg_industries(id) ON DELETE SET NULL,  -- For industry hierarchies (Phase 2)
  status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'archived')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_industries_slug ON kg_industries(slug);
CREATE INDEX idx_industries_status ON kg_industries(status);
```
**Why**: Knowledge Graph root nodes. MVP covers 4 industries (beauty, luxury, food, fashion). Seed data mandatory.

### 1.4 kg_categories
```sql
CREATE TABLE kg_categories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  industry_id UUID NOT NULL REFERENCES kg_industries(id) ON DELETE CASCADE,
  parent_category_id UUID REFERENCES kg_categories(id) ON DELETE CASCADE,
  name_zh VARCHAR(255) NOT NULL,
  name_en VARCHAR(255) NOT NULL,
  level INT NOT NULL CHECK (level BETWEEN 1 AND 3),  -- 1=top, 2=mid, 3=leaf
  description TEXT,
  status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'archived')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(industry_id, parent_category_id, name_zh)
);
CREATE INDEX idx_categories_industry_level ON kg_categories(industry_id, level);
CREATE INDEX idx_categories_parent ON kg_categories(parent_category_id);
```
**Why**: Brand/Product categorization. 3-level tree per industry. Used by Planner to generate Topics.
**Cascade**: Deleting parent cascades all children.

### 1.5 kg_brands
```sql
CREATE TABLE kg_brands (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  industry_id UUID NOT NULL REFERENCES kg_industries(id) ON DELETE CASCADE,
  primary_name VARCHAR(255) NOT NULL,  -- E.g. "Estée Lauder" (English preferred, or primary market name)
  name_zh VARCHAR(255),
  name_en VARCHAR(255),
  aliases JSONB DEFAULT '[]',  -- Array of {value, language, type (abbreviation|regional|alternative)}; e.g. [{value: "EL", language: "en", type: "abbreviation"}]
  positioning VARCHAR(50),  -- E.g. "luxury", "mass-market", "premium"
  price_range VARCHAR(50),  -- E.g. "¥500-1000", "$100-200"
  parent_company_id UUID REFERENCES kg_brands(id) ON DELETE SET NULL,  -- For conglomerate relationships
  origin_country VARCHAR(100),
  status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'delisted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(industry_id, primary_name)
);
CREATE INDEX idx_brands_industry_status ON kg_brands(industry_id, status);
CREATE INDEX idx_brands_primary_name ON kg_brands(primary_name);
```
**Why**: Brand master nodes. Aliases modeled as JSONB array for flexible matching (exact, case-insensitive, abbreviations).
**Alias matching**: Phase 1 exact + alias exact; Phase 2 adds fuzzy (DECISIONS §8).

### 1.6 kg_products
```sql
CREATE TABLE kg_products (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES kg_brands(id) ON DELETE CASCADE,
  category_id UUID NOT NULL REFERENCES kg_categories(id) ON DELETE RESTRICT,
  primary_name VARCHAR(255) NOT NULL,
  name_zh VARCHAR(255),
  name_en VARCHAR(255),
  aliases JSONB DEFAULT '[]',  -- Same structure as kg_brands.aliases
  price_range VARCHAR(50),
  key_features JSONB DEFAULT '[]',  -- Array of feature strings
  launch_date DATE,
  status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'discontinued')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(brand_id, primary_name)
);
CREATE INDEX idx_products_brand_status ON kg_products(brand_id, status);
CREATE INDEX idx_products_category ON kg_products(category_id);
```
**Why**: Product nodes under brands. Linked to categories for dimension filtering. Aliases same structure as brands.

### 1.7 kg_brand_aliases
```sql
CREATE TABLE kg_brand_aliases (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES kg_brands(id) ON DELETE CASCADE,
  alias_value VARCHAR(255) NOT NULL,
  language VARCHAR(10) NOT NULL,  -- e.g. "en", "zh-CN", "ja-JP"
  type VARCHAR(50) NOT NULL CHECK (type IN ('abbreviation', 'regional', 'alternative', 'historical')),
  confidence DECIMAL(3, 2) DEFAULT 1.0,  -- 0.0–1.0; 1.0 for verified aliases
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(brand_id, alias_value, language)
);
CREATE INDEX idx_brand_aliases_value ON kg_brand_aliases(alias_value);
```
**Why**: Denormalized alias lookup table. Improves query performance for citation matching (DECISIONS §8: "Citation 归因表缺失").
**GIN Index (future)**: When adding full-text search, `CREATE INDEX idx_aliases_tsvector ON kg_brand_aliases USING GIN(to_tsvector('chinese', alias_value))`.

### 1.8 kg_brand_domains
```sql
CREATE TABLE kg_brand_domains (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES kg_brands(id) ON DELETE CASCADE,
  domain VARCHAR(255) NOT NULL,  -- eTLD+1 normalized, e.g. "esteelauder.com"
  type VARCHAR(50) DEFAULT 'official' CHECK (type IN ('official', 'regional', 'legacy', 'affiliate')),
  confidence DECIMAL(3, 2) DEFAULT 1.0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(brand_id, domain)
);
CREATE INDEX idx_brand_domains_domain ON kg_brand_domains(domain);
```
**Why**: Citation → Brand attribution. eTLD+1-normalized domains map to brands (DECISIONS §8). Used by citation extraction (PRD §4.2.6).
**Matching Rule**: Exact domain match (eTLD+1) = confidence 1.0; no fuzzy in MVP.

### 1.9 kg_mined_relations (2026-04-21 新增)

> **Why**: Knowledge Graph uses LLM initialization plus Response mining iteration. Candidate brand/product relations mined from Responses must accumulate confidence before promotion into `kg_brand_relations` / `kg_product_relations`.

```sql
CREATE TABLE kg_mined_relations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  -- 关系两端 (任一可为 brand 或 product; 同类型关系用 type 区分)
  source_type VARCHAR(20) NOT NULL CHECK (source_type IN ('brand', 'product', 'category')),
  source_id UUID NOT NULL,                            -- kg_brands.id / kg_products.id / kg_categories.id
  target_type VARCHAR(20) NOT NULL CHECK (target_type IN ('brand', 'product', 'category')),
  target_id UUID NOT NULL,
  
  -- 关系语义 (对齐 §1.6 kg_brand_relations / §1.7 kg_product_relations)
  relation_type VARCHAR(50) NOT NULL CHECK (relation_type IN (
    -- brand × brand
    'COMPETES_WITH', 'SAME_GROUP',
    -- product × product
    'SUBSTITUTES', 'PAIRS_WITH', 'UPGRADES_TO', 'BUDGET_ALT_OF',
    -- category × brand / product × category (扩展)
    'BELONGS_TO', 'REPRESENTS_CATEGORY'
  )),

  -- 置信度累积 (核心逻辑)
  evidence_count    INT NOT NULL DEFAULT 1,           -- 命中该关系的不同 Response 数量 (去重)
  confidence_score  DECIMAL(4, 3) NOT NULL DEFAULT 0.000,  -- 0.000 - 1.000, 累积公式见下
  first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_seen_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_evidence_response_id UUID REFERENCES ai_responses(id) ON DELETE SET NULL,

  -- 迁移状态 (是否已升迁到 kg_*_relations)
  promoted          BOOLEAN NOT NULL DEFAULT FALSE,
  promoted_at       TIMESTAMPTZ,
  promoted_to_table VARCHAR(50),                       -- 'kg_brand_relations' | 'kg_product_relations'

  -- 审核/否决
  admin_status      VARCHAR(20) NOT NULL DEFAULT 'auto' CHECK (admin_status IN ('auto', 'approved', 'rejected', 'manual_review')),
  admin_note        TEXT,

  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  UNIQUE(source_type, source_id, target_type, target_id, relation_type)
);
CREATE INDEX idx_mined_confidence        ON kg_mined_relations(confidence_score DESC) WHERE NOT promoted;
CREATE INDEX idx_mined_last_seen         ON kg_mined_relations(last_seen_at DESC);
CREATE INDEX idx_mined_source            ON kg_mined_relations(source_type, source_id);
CREATE INDEX idx_mined_pending_review    ON kg_mined_relations(admin_status) WHERE admin_status = 'manual_review';
```

**置信度累积公式** (Session 1.5 实现):

```
confidence_score = min(1.0, 1 - 0.85^evidence_count)
  → 1 次见: 0.150
  → 3 次见: 0.386
  → 5 次见: 0.556
  → 10 次见: 0.803
  → 20 次见: 0.961
```

**升迁规则**:

- `confidence_score >= 0.70` 且 `evidence_count >= 5`: 自动升迁到 `kg_brand_relations` / `kg_product_relations`, 置 `promoted=true`
- `confidence_score in [0.50, 0.70)` 且 `evidence_count >= 3`: 置 `admin_status='manual_review'`, 进 Admin A1 审核队列
- 其他: 持续累积, 不展示给用户

**Cross-ref**: Admin Session A1 (KG 审核) 必须暴露该表的 manual_review 队列; Session 1.5 (KG 构建) 的 Response 解析器在命中关系时 upsert 此表.

**测试**:
- L2 `kg-mined-relation-confidence.test.ts` — 11 个 evidence_count 边界值
- L2 `kg-mined-promotion.test.ts` — 升迁到 kg_brand_relations / manual_review / 保持的 3 条路径
- L1 Harness (Session 1.5 追加): kg 迁移不能绕过 `kg_mined_relations` 直写 `kg_brand_relations` — grep `INSERT INTO kg_brand_relations` 上下文必须有 `promoted_at` 或 admin-seed 注释

---

## 2. Pipeline Entities

> These tables record the flow: Topic → Prompt → Query → Response → Analysis
>
> **Code-first caveat**: This section is a future/target schema. The current running collector uses `queries`, `llm_responses`, `llm_accounts`, `profiles`, and related Python ORM models under `geo_tracker/db/models.py`; do not use `query_executions` / `attempts` / `ai_responses` alone to judge adapter compliance.

### 2.1 platform_topics
```sql
CREATE TABLE platform_topics (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID REFERENCES kg_brands(id) ON DELETE CASCADE,  -- NULL for category-level topics
  product_id UUID REFERENCES kg_products(id) ON DELETE CASCADE,  -- NULL for brand-level topics
  category_id UUID REFERENCES kg_categories(id) ON DELETE CASCADE,  -- NULL for brand/product-level
  dimension VARCHAR(50) NOT NULL CHECK (dimension IN ('品类', '品牌', '产品')),
  text_zh TEXT NOT NULL,
  text_en TEXT NOT NULL,
  intent VARCHAR(50) CHECK (intent IN ('informational', 'commercial', 'transactional', 'navigational')),
  status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'archived', 'deprecated')),
  confidence DECIMAL(3, 2),  -- Planner-assigned confidence (0.0–1.0)
  source VARCHAR(50) CHECK (source IN ('planner_generated', 'user_submitted', 'ai_discovered')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_topic_brand_status ON platform_topics(brand_id, status);
CREATE INDEX idx_topic_dimension ON platform_topics(dimension);
CREATE INDEX idx_topic_source ON platform_topics(source);
```
**Why**: Topics are search queries to be executed. Generated by Planner from KG + user submissions + AI discovery.
**Dimension**: Determines aggregation level (product-level details vs. brand-level trends).

### 2.2 platform_prompts
```sql
CREATE TABLE platform_prompts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  topic_id UUID NOT NULL REFERENCES platform_topics(id) ON DELETE CASCADE,
  intent VARCHAR(50) NOT NULL CHECK (intent IN ('informational', 'commercial', 'transactional', 'navigational')),
  text_zh TEXT NOT NULL,
  text_en TEXT NOT NULL,
  language VARCHAR(10) NOT NULL CHECK (language IN ('zh-CN', 'en-US')),
  status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'archived', 'deprecated')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(topic_id, intent, language)
);
CREATE INDEX idx_prompt_topic_intent ON platform_prompts(topic_id, intent);
```
**Why**: Intent + language variants of a Topic. One Topic → multiple Prompts (e.g., "小棕瓶" × {informational/commercial} × {Chinese/English}).
**Language routing**: SELECT appropriate Prompt based on ExecutableQuery.language.

### 2.3 query_executions
```sql
-- Renamed from platform_queries (DECISIONS §18)
CREATE TABLE query_executions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  prompt_id UUID NOT NULL REFERENCES platform_prompts(id) ON DELETE CASCADE,
  engine_id VARCHAR(50) NOT NULL CHECK (engine_id IN ('chatgpt', 'doubao', 'deepseek')),  -- Code-first MVP keys. Any CN/overseas split requires migration.
  profile_group_ids VARCHAR(255)[] DEFAULT '{}',  -- DECISIONS §3: plural, array of group IDs; [] = any group
  requires_login BOOLEAN DEFAULT FALSE,
  status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'queued', 'executing', 'completed', 'failed')),
  scheduled_for TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_query_engine_status ON query_executions(engine_id, status);
CREATE INDEX idx_query_scheduled ON query_executions(scheduled_for) WHERE status = 'pending';
```
**Why**: Execution intent. Scheduler dequeues pending queries, samples profile + account, routes to Adapter.
**profile_group_ids**: DECISIONS §3 (plural). Empty array [] = sample from any group; non-empty = constrain to those groups.

### 2.4 attempts
```sql
CREATE TABLE attempts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_execution_id UUID NOT NULL REFERENCES query_executions(id) ON DELETE CASCADE,
  attempt_number INT NOT NULL CHECK (attempt_number >= 1),
  status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'executing', 'success', 'partial', 'failed')),
  error_code VARCHAR(50),  -- Future standardized code; current runtime mostly stores failure reasons/exceptions.
  error_detail JSONB,
  account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
  proxy_id VARCHAR(255),  -- Proxy node ID from Ninja Clash
  browser_profile JSONB,  -- BrowserProfile snapshot (locale, timezone, UA, viewport, segmentGroup)
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  latency_ms INT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(query_execution_id, attempt_number)
);
CREATE INDEX idx_attempts_query ON attempts(query_execution_id);
CREATE INDEX idx_attempts_error ON attempts(error_code);
```
**Why**: Future retry tracking target. Current runtime keeps retry count on `queries.retry_count`.
**browser_profile**: Snapshot of sampled profile to ensure reproducibility (HAR replay with same seed).

### 2.5 ai_responses
```sql
CREATE TABLE ai_responses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_execution_id UUID NOT NULL REFERENCES query_executions(id) ON DELETE CASCADE,
  attempt_id UUID REFERENCES attempts(id) ON DELETE SET NULL,
  engine_id VARCHAR(50) NOT NULL,
  execution_mode VARCHAR(10) CHECK (execution_mode IN ('web', 'api')),
  status VARCHAR(50) DEFAULT 'success' CHECK (status IN ('success', 'partial', 'failed')),
  raw_text TEXT,  -- Full response body
  raw_html_url VARCHAR(500),  -- S3 path to snapshot
  har_url VARCHAR(500),  -- S3 path to HAR (HAR replay + CI回放 mandatory)
  screenshot_url VARCHAR(500),  -- S3 path to viewport screenshot
  
  -- DECISIONS §16: Sentiment (MVP rule-based, Phase 2 LLM-enhanced)
  sentiment DECIMAL(3, 2),  -- -1.0 to +1.0 (null if extraction failed)
  sentiment_source VARCHAR(50) DEFAULT 'rule' CHECK (sentiment_source IN ('rule', 'llm')),
  sentiment_confidence DECIMAL(3, 2),  -- 0.0–1.0
  
  -- Response denormalization for fast Drilldown queries (DECISIONS §E-P0-4)
  detected_brand_ids UUID[] DEFAULT '{}',  -- GIN-indexed array of kg_brands.id found in response
  detected_topic_ids UUID[] DEFAULT '{}',  -- GIN-indexed array of platform_topics.id related to response
  matched_aliases JSONB DEFAULT '{}',  -- Phase 2: {brand_id: [matched_alias_values]}; reserved for future
  
  latency_ms INT,
  response_started_at TIMESTAMPTZ,
  response_completed_at TIMESTAMPTZ,
  profile_snapshot JSONB NOT NULL,  -- BrowserProfile at execution time
  account_id_used UUID REFERENCES accounts(id) ON DELETE SET NULL,
  proxy_id_used VARCHAR(255),

  -- 2026-04-21 patch: 成本 / Token / 延迟分解 / 触发归因 (PRD §4.9.4 Cost spike alert)
  cost_usd          DECIMAL(8, 5),                        -- LLM API 成本 (美元), 5 位小数足够
  cost_cny          DECIMAL(8, 4),                        -- 同上, 火山引擎人民币计价
  token_count       JSONB,                                -- { input: n, output: n, total: n }, null 仅在 status=failed
  latency_breakdown JSONB,                                -- { queue_ms, adapter_ms, llm_ms, parse_ms, total_ms } — 比 latency_ms 更细分
  trigger_source    VARCHAR(20) NOT NULL DEFAULT 'scheduled'
                    CHECK (trigger_source IN ('scheduled', 'manual', 'retry', 'user_refresh', 'admin_replay')),

  -- 2026-04-22 patch (Session 1.2 双修正最终版, Decision #28.C3): 来源标签
  -- NO SCHEMA DEFAULT — Adapter / API fallback / Prisma create 三处必须显式 stamp,
  -- Historical target: Harness F4-1/F4-2/F4-3 would block missing stamps once this schema is implemented.
  response_source   VARCHAR(24) NOT NULL
                    CHECK (response_source IN ('web_ui', 'api_fallback', 'mock_proxy', 'cached_replay', 'admin_har_replay', 'harness_fixture')),
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(query_execution_id)  -- One response per query execution
);
CREATE INDEX idx_responses_engine_date ON ai_responses(engine_id, created_at DESC);
CREATE INDEX idx_responses_status ON ai_responses(status);
CREATE INDEX idx_response_brands_gin ON ai_responses USING GIN (detected_brand_ids);  -- For Drilldown: "responses mentioning brand X"
CREATE INDEX idx_response_topics_gin ON ai_responses USING GIN (detected_topic_ids);  -- For topic drilldown
CREATE INDEX idx_responses_trigger_source_date ON ai_responses(trigger_source, created_at DESC);  -- 成本归因看板用 (PRD §4.9.4)
CREATE INDEX idx_ai_responses_source_created ON ai_responses(response_source, created_at DESC);  -- Session 1.2: 按来源切片审计
```
**Why**: Response persistence. Stores raw text, URLs to artifacts, parsed data (sentiment, brands), and denormalization columns for fast queries.
**detected_brand_ids / detected_topic_ids**: GIN indexes enable fast "show me all responses mentioning Brand X" without full-text scan (PRD §4.6.1a-drilldown, DECISIONS §E-P0-4).
**profile_snapshot**: Immutable copy for audit + HAR replay reproducibility.
**cost_usd / cost_cny / token_count / latency_breakdown / trigger_source (2026-04-21)**: 4 个成本&性能字段 + 1 个触发归因字段, 用于 PRD §4.9.4 成本突增告警与 Admin §4.4 运营看板. `trigger_source` 区分定时任务产生的成本 vs 用户主动刷新的成本, 便于成本归因. **Adapter 层 AFTER hook 必须写入 cost_usd**, Harness `ai-response-cost-field-required` (Session 1 追加) 把空写入 PR block.

**Migration 注意 (Session 1 实施)**: 现有数据若已有 `latency_ms` 单字段, 不删除, 与 `latency_breakdown.total_ms` 保持冗余 (latency_ms 为主, latency_breakdown 是细分); 历史 Response 的成本字段保持 NULL, 仅新写入强制. 历史 trigger_source 一次性 backfill 为 'scheduled' (因 MVP 前已无手动触发渠道).

**response_source (future target)**: 6 值枚举 (`web_ui` / `api_fallback` / `mock_proxy` / `cached_replay` / `admin_har_replay` / `harness_fixture`) 标记每条 Response 的来源路径。当前 Python runtime 的 `llm_responses` 没有此字段；实施前需要先设计从当前表到目标表/字段的迁移和 backfill 策略。

### 2.6 ai_response_citations
```sql
-- Replaces inline ParsedCitation array in ai_responses (DECISIONS §E-P0-2)
CREATE TABLE ai_response_citations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  response_id UUID NOT NULL REFERENCES ai_responses(id) ON DELETE CASCADE,
  url VARCHAR(500) NOT NULL,
  domain VARCHAR(255) NOT NULL,  -- eTLD+1 normalized
  brand_id UUID REFERENCES kg_brands(id) ON DELETE SET NULL,  -- NULL if unmatched
  confidence DECIMAL(3, 2) NOT NULL,  -- 1.0 = exact domain match, 0.9 = alias match, 0.0 = unmatched
  extraction_method VARCHAR(50) NOT NULL CHECK (extraction_method IN ('footnote', 'reference_card', 'citation_tooltip', 'inline_link', 'api_structured', 'hover_card', 'unknown')),  -- DECISIONS §17
  position_in_response INT,  -- Citation order (1-based)
  anchor_text VARCHAR(255),  -- Link text if available
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_citation_response_brand ON ai_response_citations(response_id, brand_id);
CREATE INDEX idx_citation_domain ON ai_response_citations(domain);
```
**Why**: Citation → Brand attribution. eTLD+1 domain match (confidence 1.0) + alias match (0.9) + unmatched (0.0 with NULL brand_id).
**extraction_method**: Enum per DECISIONS §17, 7 values (added api_structured, hover_card, unknown for Phase 2 engine support).
**KPI metric**: `citation_share = COUNT(citations with brand_id NOT NULL) / COUNT(all citations)` for Dashboard (PRD §4.6).

### 2.7 brand_mentions
```sql
CREATE TABLE brand_mentions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  response_id UUID NOT NULL REFERENCES ai_responses(id) ON DELETE CASCADE,
  brand_id UUID NOT NULL REFERENCES kg_brands(id) ON DELETE CASCADE,
  engine_id VARCHAR(50),
  position_in_text INT,  -- Mention order within response
  context_snippet TEXT,  -- 50-char context around mention
  sentiment DECIMAL(3, 2),  -- Inherited from ai_responses.sentiment or parsed
  mentioned_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_mention_brand_date ON brand_mentions(brand_id, created_at DESC);
CREATE INDEX idx_mention_engine_date ON brand_mentions(engine_id, created_at DESC);
```
**Why**: Extracted brand mentions from response raw_text. Used for heatmap aggregation (DECISIONS §E-P0-3).
**sentiment**: Can differ per mention (Phase 2 fine-grained analysis); MVP uses response-level sentiment.

### 2.8 product_mentions
```sql
CREATE TABLE product_mentions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  response_id UUID NOT NULL REFERENCES ai_responses(id) ON DELETE CASCADE,
  product_id UUID NOT NULL REFERENCES kg_products(id) ON DELETE CASCADE,
  brand_id UUID NOT NULL REFERENCES kg_brands(id) ON DELETE CASCADE,  -- Denormalized for easier aggregation
  engine_id VARCHAR(50),
  position_in_text INT,
  context_snippet TEXT,
  sentiment DECIMAL(3, 2),
  mentioned_at TIMESTAMPTZ DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_product_mention_date ON product_mentions(product_id, created_at DESC);
CREATE INDEX idx_product_mention_brand ON product_mentions(brand_id, created_at DESC);
```
**Why**: Product-level mention tracking. Parallel to brand_mentions for product-focused analytics.

---

## 3. Profile & Account Pool

### 3.1 profile_groups
```sql
CREATE TABLE profile_groups (
  id VARCHAR(100) PRIMARY KEY,  -- e.g. 'beauty_daily', 'luxury_collector', 'baseline'
  name_zh VARCHAR(100) NOT NULL,
  name_en VARCHAR(100) NOT NULL,
  description TEXT,
  filter_rules JSONB DEFAULT '{}',  -- e.g. {locale: ['zh-CN'], platforms: ['Win32', 'MacIntel']}
  is_default BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
**Why**: DECISIONS §10: Persist profile groups to DB for Admin control. Seed 6 baseline groups (beauty_daily, luxury_collector, etc.).
**segment_group alignment**: Used to bind accounts (accounts.segment_group) and profiles (BrowserProfile.segmentGroup).

### 3.2 browser_profiles
```sql
CREATE TABLE browser_profiles (
  id VARCHAR(100) PRIMARY KEY,  -- e.g. 'pg_beauty_daily_zh_win' (deterministic, not UUID)
  profile_group_id VARCHAR(100) NOT NULL REFERENCES profile_groups(id) ON DELETE CASCADE,
  instance_id VARCHAR(100) NOT NULL UNIQUE,  -- DECISIONS §14: Renamed from profileId; unique stable ID
  locale VARCHAR(20) NOT NULL,  -- e.g. 'zh-CN', 'en-US', 'ja-JP'
  timezone VARCHAR(50) NOT NULL,  -- e.g. 'Asia/Shanghai', 'America/New_York'
  viewport_width INT NOT NULL,  -- 1920, 1536, 1366
  viewport_height INT NOT NULL,  -- 1080, 864, 768
  user_agent TEXT NOT NULL,
  platform VARCHAR(50) NOT NULL CHECK (platform IN ('Win32', 'MacIntel', 'Linux x86_64')),
  languages VARCHAR(20)[] NOT NULL,  -- e.g. ['zh-CN', 'zh', 'en']
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(profile_group_id, locale, platform)
);
CREATE INDEX idx_browser_profiles_group ON browser_profiles(profile_group_id);
```
**Why**: DECISIONS §10: Sampler deterministically picks a profile per (group, seed). Seed data: 6 groups × 3–4 profiles/group = 18–24 profiles.
**instance_id**: Renamed from profileId (DECISIONS §14) to avoid confusion with profile_group. Used for reproducibility (same seed → same instance).

### 3.3 accounts
```sql
CREATE TABLE accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  engine_id VARCHAR(50) NOT NULL CHECK (engine_id IN ('chatgpt', 'doubao', 'deepseek')),  -- Code-first MVP keys.
  username_masked VARCHAR(100),  -- e.g. 'm***@gmail.com' (never store plain username in logs)
  encrypted_cookies BYTEA,  -- AES-256-GCM, KMS key management
  segment_group VARCHAR(100) REFERENCES profile_groups(id) ON DELETE SET NULL,  -- DECISIONS §3.3: accounts bound to segment groups
  status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'cooldown', 'frozen', 'banned', 'pending_register')),
  cooldown_until TIMESTAMPTZ,  -- Cooldown duration target; current runtime policy is in account_pool.py.
  consecutive_failures INT DEFAULT 0,
  last_used_at TIMESTAMPTZ,
  last_health_check_at TIMESTAMPTZ,
  registered_at TIMESTAMPTZ,
  created_by VARCHAR(50) DEFAULT 'manual' CHECK (created_by IN ('auto_register', 'admin_manual')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_accounts_engine_status ON accounts(engine_id, status, segment_group);
CREATE INDEX idx_accounts_active ON accounts(engine_id, status, last_used_at) WHERE status = 'active';
```
**Why**: Account pool target model. Current runtime status machine is `active` / `cooldown` / `banned` in `geo_tracker/db/models.py`.
**segment_group binding**: DECISIONS §3.3: Scheduler matches Query.profileGroupIds to Account.segment_group to avoid profile pollution.
**encrypted_cookies**: AES-256-GCM with KMS; never log plain value.

### 3.4 account_states (Audit/History)
```sql
CREATE TABLE account_states (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  old_status VARCHAR(50),
  new_status VARCHAR(50) NOT NULL,
  error_code VARCHAR(50),  -- If transition due to error
  reason TEXT,
  admin_operator_id UUID REFERENCES admin_users(id) ON DELETE SET NULL,  -- If manual override
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_account_states_account ON account_states(account_id, created_at DESC);
```
**Why**: Audit trail for account lifecycle (ACTIVE → COOLDOWN → FROZEN). Supports Admin drilldown on "why was this account frozen?".

---

## 4. Metrics / Rollups

### 4.1 metric_snapshots
```sql
-- DECISIONS §E-P0-1: Complete MVP schema (was missing before)
CREATE TABLE metric_snapshots (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_id UUID NOT NULL REFERENCES kg_brands(id) ON DELETE CASCADE,
  project_id UUID REFERENCES projects(id) ON DELETE SET NULL,  -- NULL for platform-level (all users) snapshots
  engine_id VARCHAR(50),  -- NULL = all engines aggregated
  profile_group_id VARCHAR(100),  -- NULL = all profiles; referenced from profile_groups
  
  period_start TIMESTAMPTZ NOT NULL,
  period_end TIMESTAMPTZ NOT NULL,
  period_unit VARCHAR(20) DEFAULT 'day' CHECK (period_unit IN ('hour', 'day', 'week')),
  
  mention_count INT DEFAULT 0,
  mention_rate DECIMAL(5, 3),  -- 0.0–1.0 (mentions / total responses for brand in period)
  sentiment_score DECIMAL(3, 2),  -- -1.0 to +1.0 (avg sentiment of mentions)
  ranking INT,  -- Position in leaderboard for period (1-based)
  sov DECIMAL(5, 3),  -- Share of Voice: brand mentions / (brand mentions + competitor mentions)
  citation_share DECIMAL(5, 3),  -- Citations attributed to brand / total citations
  sample_count INT,  -- Number of responses analyzed in period
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  
  UNIQUE(brand_id, project_id, engine_id, profile_group_id, period_start, period_unit)
);
CREATE INDEX idx_ms_brand_period ON metric_snapshots(brand_id, period_start, period_end);
CREATE INDEX idx_ms_project_period ON metric_snapshots(project_id, period_start, period_end);
CREATE INDEX idx_ms_engine_period ON metric_snapshots(engine_id, period_start);
```
**Why**: Pre-computed KPI snapshots for Dashboard 5-card display (mention_rate, sentiment_score, ranking, sov, citation_share).
**Update frequency**: Batch job 02:00 UTC (daily) for yesterday's full day + hourly cache for today's partial data.
**Query pattern**: KPI card: `SELECT * FROM metric_snapshots WHERE brand_id = ? AND period_start >= NOW() - INTERVAL '7 days' AND period_unit = 'day'`.

### 4.2 mv_heatmap_mention_agg (Materialized View)
```sql
-- DECISIONS §7, §E-P0-3: Heatmap aggregation without ClickHouse
CREATE MATERIALIZED VIEW mv_heatmap_mention_agg AS
SELECT
  topic_id,
  brand_id,
  engine_id,
  DATE(bm.created_at) AS mention_date,
  COUNT(*) AS mention_count,
  AVG(bm.sentiment) AS avg_sentiment,
  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY bm.sentiment) AS median_sentiment
FROM brand_mentions bm
WHERE bm.created_at > NOW() - INTERVAL '90 days'  -- 3-month rolling window
GROUP BY topic_id, brand_id, engine_id, DATE(bm.created_at);

CREATE INDEX idx_heatmap_topic_date ON mv_heatmap_mention_agg(topic_id, mention_date DESC);
CREATE INDEX idx_heatmap_brand_date ON mv_heatmap_mention_agg(brand_id, mention_date DESC);
CREATE INDEX idx_heatmap_engine_date ON mv_heatmap_mention_agg(engine_id, mention_date DESC);

-- Refresh strategy: REFRESH MATERIALIZED VIEW CONCURRENTLY every 1 hour (can run while view is being queried)
-- App-level scheduler or pg_cron: SELECT cron.schedule('refresh-heatmap', '0 * * * *', 'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_heatmap_mention_agg');
```
**Why**: 50×10 Heatmap (50 topics × 10 brands) requires < 2s response. Raw aggregation over million-row brand_mentions table times out. Materialized view with hourly refresh balances freshness + performance.
**Query pattern**: Heatmap cell (topic_id, brand_id, date): `SELECT mention_count, avg_sentiment FROM mv_heatmap_mention_agg WHERE topic_id = ? AND brand_id = ? AND mention_date = ?`.

### 4.3 mv_brand_rankings (Materialized View)
```sql
-- DECISIONS §E-P1-2: Brand ranking by mention count per day/engine
CREATE MATERIALIZED VIEW mv_brand_rankings AS
SELECT
  project_id,
  DATE(bm.created_at) AS mention_date,
  engine_id,
  brand_id,
  COUNT(*) AS mention_count,
  ROW_NUMBER() OVER (
    PARTITION BY project_id, DATE(bm.created_at), engine_id
    ORDER BY COUNT(*) DESC
  ) AS ranking
FROM brand_mentions bm
JOIN projects p ON p.primary_brand_id = bm.brand_id OR bm.brand_id = ANY(p.competitor_brand_ids)
WHERE bm.created_at > NOW() - INTERVAL '90 days'
GROUP BY project_id, DATE(bm.created_at), engine_id, brand_id;

CREATE INDEX idx_brand_rankings_project_date ON mv_brand_rankings(project_id, mention_date DESC);
```
**Why**: Dashboard brand card shows "Ranking #4" badge (PRD §4.6). Materialized view avoids re-computing ROW_NUMBER() every page load.
**Refresh**: Same 1-hour schedule as heatmap.

### 4.4 brand_mention_daily_agg (Base for MVs)
```sql
-- Materialized view aggregating daily brand mention stats (basis for rankings/heatmaps)
CREATE MATERIALIZED VIEW brand_mention_daily_agg AS
SELECT
  brand_id,
  engine_id,
  DATE(bm.created_at) AS mention_date,
  COUNT(*) AS mention_count,
  COUNT(*) FILTER (WHERE bm.sentiment > 0.2) AS positive_mentions,
  COUNT(*) FILTER (WHERE bm.sentiment < -0.2) AS negative_mentions,
  AVG(bm.sentiment) AS avg_sentiment
FROM brand_mentions bm
WHERE bm.created_at > NOW() - INTERVAL '90 days'
GROUP BY brand_id, engine_id, DATE(bm.created_at);

CREATE INDEX idx_brand_mention_daily_brand_date ON brand_mention_daily_agg(brand_id, mention_date DESC);
```
**Why**: Base aggregation for mv_brand_rankings. Separates daily stats from topic-brand heatmap.

---

## 5. Admin / Audit / Cost

### 5.1 audit_logs
```sql
CREATE TABLE audit_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  operator_id UUID REFERENCES admin_users(id) ON DELETE SET NULL,
  action VARCHAR(50) NOT NULL,  -- 'approve_brand', 'freeze_account', 'adjust_budget', 'export_users', etc.
  target_type VARCHAR(50),  -- 'brand', 'account', 'user', 'project', etc.
  target_id VARCHAR(255),
  diff_json JSONB,  -- Before/after snapshot (only for mutations)
  reason TEXT,  -- Why was this action taken?
  ip_address VARCHAR(50),
  user_agent TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_operator ON audit_logs(operator_id, created_at DESC);
CREATE INDEX idx_audit_target ON audit_logs(target_type, target_id, created_at DESC);
```
**Why**: ADMIN_PRD §1.3 "一切特权操作留痕". Comprehensive audit trail for Admin actions.
**Query pattern**: Admin drilling down on "who approved this brand?": `SELECT * FROM audit_logs WHERE target_type = 'brand' AND target_id = ? ORDER BY created_at DESC`.

### 5.2 cost_events
```sql
-- DECISIONS §13: Unified cost tracking with budget_scope enum
CREATE TABLE cost_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  date DATE NOT NULL,
  budget_scope VARCHAR(50) NOT NULL CHECK (budget_scope IN ('pipeline', 'kg')),  -- Pipeline vs KG LLM
  cost_category VARCHAR(50),  -- 'llm_api', 'proxy_traffic', 'sms_code', 'storage', etc.
  engine_id VARCHAR(50),  -- Nullable for non-engine costs
  amount DECIMAL(10, 4) NOT NULL,  -- Cost in USD
  currency VARCHAR(3) DEFAULT 'USD',
  metadata JSONB DEFAULT '{}',  -- e.g. {query_count: 1000, token_count: 50000}
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_cost_date_scope ON cost_events(date, budget_scope);
CREATE INDEX idx_cost_engine ON cost_events(engine_id, date);
```
**Why**: DECISIONS §13 (KG 预算与 Pipeline 预算分开但统一上报). Admin A4 cost dashboard aggregates by scope.
**Daily budget check**: Cron job: `SELECT SUM(amount) FROM cost_events WHERE date = TODAY AND budget_scope = 'pipeline' GROUP BY budget_scope HAVING SUM(amount) > DAILY_BUDGET_LIMIT` → stop scheduler if exceeded.

### 5.3 brand_submissions
```sql
-- DECISIONS §9, §E-P1-5: User-submitted brands await verification
CREATE TABLE brand_submissions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  industry_id UUID NOT NULL REFERENCES kg_industries(id) ON DELETE RESTRICT,
  brand_name_zh TEXT NOT NULL,
  brand_name_en TEXT,
  status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'verified', 'approved', 'rejected', 'merged')),
  
  -- LLM verification result (Phase 1: automatic screening; Phase 2: human review)
  llm_verification_result JSONB,  -- {verified: true/false, confidence: 0.0–1.0, reason: "..."}
  
  -- Admin approval
  admin_operator_id UUID REFERENCES admin_users(id) ON DELETE SET NULL,
  rejection_reason TEXT,  -- If status = 'rejected'
  merged_into_brand_id UUID REFERENCES kg_brands(id) ON DELETE SET NULL,  -- If status = 'merged'
  
  approved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_submissions_status ON brand_submissions(status);
CREATE INDEX idx_submissions_user ON brand_submissions(user_id, created_at DESC);
```
**Why**: PRD §4.1.2 user brand submission. Status machine: pending → verified → {approved/rejected/merged}.
**Approve hook**: DECISIONS §9 Outbox pattern: approval writes to `brand_bootstrap_jobs` table; 5-min Planner worker picks up and does first-day scrape.

### 5.4 brand_discovery_logs
```sql
-- DECISIONS §E-P1-5: LLM-discovered brands (from Response analysis)
CREATE TABLE brand_discovery_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_response_id UUID REFERENCES ai_responses(id) ON DELETE CASCADE,
  discovered_brand_name TEXT NOT NULL,
  confidence DECIMAL(3, 2) NOT NULL,  -- 0.0–1.0; < 0.6 → candidate status (DECISIONS §E-P1-5)
  llm_context JSONB,  -- Context snippet from response + LLM reasoning
  status VARCHAR(50) DEFAULT 'candidate' CHECK (status IN ('candidate', 'verified', 'approved', 'rejected')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_discovery_status ON brand_discovery_logs(status);
CREATE INDEX idx_discovery_confidence ON brand_discovery_logs(confidence) WHERE confidence >= 0.6;
```
**Why**: ADMIN_PRD §4.3.2 Brand Audit: LLM auto-discovers new brands from Responses. Low confidence (< 0.6) held as "candidate" for human review.

### 5.5 brand_bootstrap_jobs (Outbox Pattern)
```sql
-- DECISIONS §9: Outbox pattern for brand approval → first-day scrape
CREATE TABLE brand_bootstrap_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brand_submission_id UUID REFERENCES brand_submissions(id) ON DELETE CASCADE,
  status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
  error_message TEXT,
  attempts INT DEFAULT 0,
  max_attempts INT DEFAULT 3,
  next_retry_at TIMESTAMPTZ,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_bootstrap_status_retry ON brand_bootstrap_jobs(status, next_retry_at) WHERE status IN ('pending', 'failed');
```
**Why**: Decouple Admin approve action from expensive first-scrape. Planner 5-min cron worker picks up pending jobs, generates Topics + Prompts, executes first-day Query batch.
**Idempotency**: Job ID ensures "approve same brand twice" doesn't double-scrape.

### 5.6 parse_failures
```sql
-- DECISIONS §12: Parse failures (PARSER_FAIL analyzer queue, not Tracker retry)
CREATE TABLE parse_failures (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  response_id UUID NOT NULL REFERENCES ai_responses(id) ON DELETE CASCADE,
  engine_id VARCHAR(50),
  selector VARCHAR(500),  -- DOM selector that failed
  expected_element_desc TEXT,  -- e.g. "chat-output div"
  har_snapshot_url VARCHAR(500),  -- S3 path to HAR for manual debugging
  status VARCHAR(50) DEFAULT 'open' CHECK (status IN ('open', 'investigating', 'fixed', 'dismissed')),
  notes TEXT,  -- Operator notes
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_parse_failures_engine ON parse_failures(engine_id, status);
```
**Why**: DECISIONS §12 (PARSER_FAIL 归属): Parse failures are structural (DOM changed), not transient. Stored in separate queue for Analyzer manual review (not auto-retry via Tracker).

---

## 6. Scheduling / Jobs

### 6.1 export_jobs [Phase 2]
```sql
-- Skeleton for CSV/PDF async export (Phase 2; MVP: 1000-row sync download only)
CREATE TABLE export_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
  export_type VARCHAR(50) CHECK (export_type IN ('csv_responses', 'csv_metrics', 'pdf_report')),
  status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
  file_url VARCHAR(500),  -- S3 path when completed
  error_message TEXT,
  row_count INT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT export_max_rows CHECK (row_count <= 1000000)  -- MVP limit: 1M rows
);
```
**Why**: Placeholder for Phase 2. MVP: 1000-row sync download with "use API for larger exports" message.

### 6.2 report_schedules [Phase 2]
```sql
-- Placeholder for recurring reports (Phase 2; MVP: "Export Now" button only)
CREATE TABLE report_schedules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  frequency VARCHAR(50) CHECK (frequency IN ('daily', 'weekly', 'monthly')),
  recipients VARCHAR(255)[],  -- Email array
  format VARCHAR(50) CHECK (format IN ('pdf', 'csv', 'html')),
  template_id VARCHAR(100),
  status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'paused', 'deleted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(project_id, frequency)
);
```
**Why**: Phase 2 only. MVP: Manual "Export PDF" button on Dashboard (PRD §4.6.1a-C.2.2e).

---

## 7. Indices Summary

| Purpose | Table | Indices | Query Pattern |
|---------|-------|---------|---------------|
| **Heatmap** | mv_heatmap_mention_agg | (topic_id, mention_date), (brand_id, mention_date), (engine_id, mention_date) | `SELECT * WHERE topic_id = ? AND mention_date = ?` (50 cells × 10 brands, each < 5ms) |
| **KPI Card** | metric_snapshots | (brand_id, period_start, period_end), (project_id, period_start) | `SELECT * WHERE brand_id = ? AND period_start >= NOW() - 7d` (Dashboard 5-card refresh) |
| **Drilldown** | ai_responses + GIN | GIN(detected_brand_ids), GIN(detected_topic_ids) | `WHERE detected_brand_ids @> ARRAY[?]` (no sequential scan for large Response table) |
| **Account Dispatch** | accounts | (engine_id, status, segment_group), (engine_id, status, last_used_at) WHERE status='ACTIVE' | `SELECT FOR UPDATE ... WHERE engine_id = ? AND status = 'ACTIVE' AND segment_group = ? ORDER BY last_used_at` (Scheduler SELECT FOR UPDATE) |
| **Citation Attribution** | ai_response_citations | (response_id, brand_id), (domain) | `SELECT SUM(1) WHERE brand_id NOT NULL` (citation_share KPI) |
| **Admin Audit** | audit_logs | (operator_id, created_at DESC), (target_type, target_id, created_at DESC) | `SELECT * WHERE target_type = 'brand' AND target_id = ? ORDER BY created_at DESC` |

---

## 8. Materialized Views & Refresh Strategy

### 8.1 mv_heatmap_mention_agg
- **Purpose**: 50×10 brand-topic heatmap < 2s response
- **Refresh**: Every 1 hour via `REFRESH MATERIALIZED VIEW CONCURRENTLY`
- **Implementation**:
  - **Option A (Recommended for MVP)**: pg_cron (PostgreSQL 12+): `SELECT cron.schedule('refresh_heatmap', '0 * * * *', 'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_heatmap_mention_agg');`
  - **Option B (App-level)**: Node.js Cron job (node-cron) every hour, calls `SELECT refresh_heatmap();` stored procedure
  - **Option C (SQLite dev)**: Omit materialized views in dev; pre-compute in-memory cache on app startup + refresh every 5 min for testing

### 8.2 mv_brand_rankings
- **Purpose**: Dashboard brand card ranking badge ("Ranking #4")
- **Refresh**: Same 1-hour schedule (combined with heatmap refresh)
- **Query pattern**: `SELECT ranking FROM mv_brand_rankings WHERE project_id = ? AND mention_date = ? AND engine_id = ?`

### 8.3 brand_mention_daily_agg
- **Purpose**: Base aggregation for all daily metrics
- **Refresh**: 1-hour schedule (foundation for rankings + heatmap)

### Implementation Note for SQLite (Dev)
SQLite does not support materialized views natively. For development:
1. Create tables `heatmap_mention_agg`, `brand_mention_daily_agg` as regular tables
2. Batch job (every 5 min in tests) re-computes:
   ```sql
   DELETE FROM heatmap_mention_agg WHERE mention_date < date('now', '-90 days');
   INSERT INTO heatmap_mention_agg 
   SELECT topic_id, brand_id, engine_id, DATE(created_at), COUNT(*), AVG(sentiment), ...
   FROM brand_mentions
   WHERE created_at > datetime('now', '-90 days')
   GROUP BY ...;
   ```

---

## 9. Migration Order & Seed Data Instructions

### 9.1 Execution Order (Session 2)

**Phase 1: Core Entities** (0–10 min)
1. `kg_industries` (seed 4 industries)
2. `kg_categories` (seed 3-level category tree per industry)
3. `kg_brands` (seed 20–50 brands per industry)
4. `kg_products` (seed 5–15 products per brand)
5. `kg_brand_aliases`, `kg_brand_domains` (seed from brands/products)

**Phase 2: Users & Projects** (10–15 min)
6. `users` (test user)
7. `projects` (test project with primary_brand_id + competitor list)
8. `profile_groups` (seed 6 groups: baseline, beauty_daily, luxury_collector, …)
9. `browser_profiles` (seed 18–24 profiles: 6 groups × 3–4 profiles/group)
10. `accounts` (seed 3 test accounts per engine: chatgpt, doubao, deepseek — MVP 3 家, code-first keys)

**Phase 3: Pipeline** (15–25 min)
11. `platform_topics` (seed 100–200 topics from KG)
12. `platform_prompts` (seed × 2 intents × 2 languages)
13. `query_executions` (seed 500–1000 pending/completed queries)
14. `attempts` (seed 1–3 per query for testing retry logic)
15. `ai_responses` (seed 500–1000 with mock sentiment + detected_brand_ids)
16. `ai_response_citations` (seed 3–5 per response)
17. `brand_mentions`, `product_mentions` (extracted from responses)

**Phase 4: Metrics & Rollups** (25–35 min)
18. `metric_snapshots` (pre-compute for Dashboard 7-day window)
19. `mv_heatmap_mention_agg` (populate + create indexes)
20. `mv_brand_rankings` (populate)
21. `brand_mention_daily_agg` (populate)

**Phase 5: Admin / Audit** (35–40 min)
22. `admin_users` (Frank super_admin + roles enum placeholder)
23. `audit_logs` (sample entries)
24. `cost_events` (sample daily costs)
25. `brand_submissions`, `brand_discovery_logs`, `brand_bootstrap_jobs`, `parse_failures` (empty, ready for Phase 1 data)
26. `account_states` (sample account transitions)

### 9.2 Seed Data Source
- **Location**: `PRD_TEST_DATA_V1.md` (already exists with 128K Attempts / 1560 Topics)
- **Injection**: `npm run seed:admin` (Session A2 Prompt responsibility)
- **SQLite Dev**: `prisma migrate dev` + seed script in `prisma/seed.ts`

### 9.3 Sample Quantities (MVP)
- Industries: 4
- Categories per industry: 8–12 (3 levels)
- Brands per industry: 20–30
- Products per brand: 5–10
- Topics: 500–1000
- Profiles: 18–24 (6 groups × 3–4)
- Accounts: 9 (3 per engine × 3 engines)
- Query executions: 5000–10000 (for realistic Heatmap / KPI testing)
- Responses: 4000–8000 (80–90% success rate)

---

## 10. FK / Cascade Policy Summary

| From Table | To Table | Cardinality | ON DELETE | Rationale |
|-----------|----------|-------------|-----------|-----------|
| projects | users | N:1 | CASCADE | User deletion cascades projects (user data cleanup) |
| projects | kg_brands | N:1 (primary) | RESTRICT | Prevent orphaning; Admin deletes brands manually |
| kg_categories | kg_industries | N:1 | CASCADE | Industry deletion cascades categories (cleanup) |
| kg_brands | kg_industries | N:1 | CASCADE | Ditto |
| kg_products | kg_brands | N:1 | CASCADE | Brand deletion cascades products |
| kg_brand_aliases | kg_brands | N:1 | CASCADE | Alias is attribute of brand |
| kg_brand_domains | kg_brands | N:1 | CASCADE | Domain is attribute of brand |
| query_executions | platform_prompts | N:1 | CASCADE | Prompt deletion cascades queries (inactive prompts) |
| ai_responses | query_executions | 1:1 | CASCADE | Query cascades response (no orphan responses) |
| attempts | query_executions | N:1 | CASCADE | Query cascades attempts |
| attempts | accounts | N:1 | SET NULL | Account deletion doesn't cascade responses (preserve audit trail) |
| brand_mentions | ai_responses | N:1 | CASCADE | Response deletion cascades mentions |
| brand_mentions | kg_brands | N:1 | CASCADE | Brand deletion cascades mentions (cleanup) |
| product_mentions | ai_responses | N:1 | CASCADE | Ditto |
| product_mentions | kg_products | N:1 | CASCADE | Ditto |
| ai_response_citations | ai_responses | N:1 | CASCADE | Response deletion cascades citations |
| ai_response_citations | kg_brands | N:1 | SET NULL | Brand deletion nullifies citation attribution (preserve response) |
| metric_snapshots | kg_brands | N:1 | CASCADE | Brand deletion cascades snapshots |
| metric_snapshots | projects | N:1 | SET NULL | Project deletion doesn't cascade (snapshot is platform-level snapshot) |
| brand_submissions | users | N:1 | CASCADE | User deletion cascades submissions |
| brand_discovery_logs | ai_responses | N:1 | CASCADE | Response deletion cascades discovery logs |
| account_states | accounts | N:1 | CASCADE | Account deletion cascades state history |
| audit_logs | admin_users | N:1 | SET NULL | Admin deletion preserves audit trail (logs operator_id = NULL) |

**Cascading Deletes to Avoid**:
- `ai_responses → accounts` (SET NULL): Preserve response audit trail even if account is deleted
- `metric_snapshots → projects` (SET NULL): Platform-level snapshots persist even after user deletes project

---

## 11. Query Pattern Reference (Design Verification)

| Feature | Table(s) | Query Pattern | Expected Latency |
|---------|----------|---------------|------------------|
| **Heatmap Grid** | mv_heatmap_mention_agg | `SELECT * FROM mv_heatmap_mention_agg WHERE topic_id IN (1..50) AND mention_date >= ? AND mention_date <= ?` | < 2s (50 cells) |
| **KPI Card Refresh** | metric_snapshots | `SELECT mention_rate, sentiment_score, ranking, sov, citation_share FROM metric_snapshots WHERE brand_id = ? AND period_start >= NOW() - 7d` | < 100ms |
| **Drilldown Responses** | ai_responses (GIN) | `SELECT * FROM ai_responses WHERE detected_brand_ids @> ARRAY[brand_id] AND detected_topic_ids @> ARRAY[topic_id] LIMIT 100` | < 500ms (no seq scan) |
| **Citation Attribution** | ai_response_citations | `SELECT COUNT(*) FILTER (WHERE brand_id NOT NULL) / COUNT(*) FROM ai_response_citations WHERE response_id = ?` | < 10ms |
| **Account Scheduler** | accounts | `BEGIN; SELECT id FROM accounts WHERE engine_id = ? AND status = 'ACTIVE' AND segment_group = ? AND last_used_at < NOW() - 30s ORDER BY last_used_at ASC NULLS FIRST LIMIT 1 FOR UPDATE SKIP LOCKED;` | < 50ms (index scan + row lock) |
| **Admin Audit Trail** | audit_logs | `SELECT * FROM audit_logs WHERE target_type = 'brand' AND target_id = ? ORDER BY created_at DESC LIMIT 50` | < 100ms |
| **Brand Rankings MV** | mv_brand_rankings | `SELECT ranking FROM mv_brand_rankings WHERE project_id = ? AND mention_date = TODAY AND engine_id = ? AND brand_id = ?` | < 10ms |

---

## Appendix: SQLite Dialect Adaptations

For development/CI, the following PostgreSQL features map to SQLite equivalents:

| PostgreSQL | SQLite Equivalent | Adapter Behavior |
|-----------|------------------|-----------------|
| `UUID` type | `TEXT` | Store UUIDs as TEXT; auto-generate with `uuid4()` in Prisma/ORM |
| `JSONB` | `JSON` | SQLite JSON1 extension; queries use `json_extract()` |
| `TIMESTAMPTZ` | `DATETIME` | Store as ISO 8601; app handles timezone conversions |
| `gen_random_uuid()` | `uuid4()` (SQLite extension) | Requires loading `uuid` module |
| Materialized Views | Regular tables + triggers | Pre-compute in app at startup; refresh every 5 min for tests |
| `CREATE TYPE enum` | `CHECK` constraints | Use `CHECK (status IN ('...'))` in SQLite DDL |
| `GIN` indexes | No equivalent | Full-text search via `json_extract()` in WHERE clause (slower but acceptable for test scale) |
| `CONCURRENTLY` | Not supported | Omit; SQLite refreshes are blocking but instant at test scale |
| `DISTINCT ON` | `DISTINCT` workaround | Use subquery with `ROW_NUMBER()` or application-layer deduping |
| `ARRAY[]` type | `JSON array` or comma-separated TEXT | Store as JSON array in SQLite; Prisma auto-handles marshaling |

**Prisma ORM**: Use Prisma's `@db.Json` type annotation for JSONB columns; Prisma auto-translates to native dialect. No manual SQL needed for dialect differences in application code.

---

**End of DATA_MODEL.md**
