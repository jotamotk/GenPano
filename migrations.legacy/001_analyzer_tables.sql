-- Migration: Add GEN Analyzer data layer tables and columns
-- Date: 2026-04-09
-- PR: #104

-- ═══════════════════════════════════════════════════════════════════════════════
-- 1. Add new columns to existing tables
-- ═══════════════════════════════════════════════════════════════════════════════

-- LLMResponse: analysis tracking
ALTER TABLE llm_responses
    ADD COLUMN IF NOT EXISTS analysis_status VARCHAR(16) DEFAULT 'pending';
ALTER TABLE llm_responses
    ADD COLUMN IF NOT EXISTS analyzed_at TIMESTAMP;

-- Brand: aliases for multi-name matching
ALTER TABLE brands
    ADD COLUMN IF NOT EXISTS aliases JSONB;

-- Competitor: aliases for multi-name matching
ALTER TABLE competitors
    ADD COLUMN IF NOT EXISTS aliases JSONB;

-- Prompt: tags for query format/context classification
ALTER TABLE prompts
    ADD COLUMN IF NOT EXISTS tags JSONB;

-- ═══════════════════════════════════════════════════════════════════════════════
-- 2. Create new analysis tables
-- ═══════════════════════════════════════════════════════════════════════════════

-- BrandMention: per-response per-brand mention record
CREATE TABLE IF NOT EXISTS brand_mentions (
    id SERIAL PRIMARY KEY,
    response_id INTEGER NOT NULL REFERENCES llm_responses(id),
    brand_id INTEGER REFERENCES brands(id),
    brand_name VARCHAR(256) NOT NULL,
    product_name VARCHAR(256),
    is_target BOOLEAN DEFAULT FALSE,
    position_type VARCHAR(32),
    position_rank INTEGER,
    detail_level VARCHAR(16),
    sentiment VARCHAR(16),
    sentiment_score FLOAT,
    context_snippet TEXT,
    mention_count INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT uq_mention_response_brand UNIQUE (response_id, brand_name)
);

-- SentimentDriver: what drives positive/negative sentiment for a brand mention
CREATE TABLE IF NOT EXISTS sentiment_drivers (
    id SERIAL PRIMARY KEY,
    mention_id INTEGER NOT NULL REFERENCES brand_mentions(id),
    response_id INTEGER NOT NULL REFERENCES llm_responses(id),
    brand_name VARCHAR(256) NOT NULL,
    driver_text VARCHAR(512) NOT NULL,
    polarity VARCHAR(8) NOT NULL,
    category VARCHAR(64),
    strength FLOAT DEFAULT 0.5,
    source_quote TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- CitationSource: citation URL mapping and classification
CREATE TABLE IF NOT EXISTS citation_sources (
    id SERIAL PRIMARY KEY,
    response_id INTEGER NOT NULL REFERENCES llm_responses(id),
    mention_id INTEGER REFERENCES brand_mentions(id),
    url VARCHAR(2048) NOT NULL,
    domain VARCHAR(256),
    title VARCHAR(512),
    citation_index INTEGER,
    source_type VARCHAR(32),
    created_at TIMESTAMP DEFAULT NOW()
);

-- ResponseAnalysis: per-response analysis summary + GEO sub-scores
CREATE TABLE IF NOT EXISTS response_analyses (
    id SERIAL PRIMARY KEY,
    response_id INTEGER UNIQUE REFERENCES llm_responses(id),
    dimension_industry VARCHAR(128),
    dimension_company VARCHAR(128),
    dimension_product VARCHAR(128),
    dimension_category VARCHAR(128),
    total_brands_mentioned INTEGER DEFAULT 0,
    target_brand_mentioned BOOLEAN DEFAULT FALSE,
    target_brand_position VARCHAR(32),
    target_brand_rank INTEGER,
    target_brand_sentiment VARCHAR(16),
    target_brand_detail VARCHAR(16),
    visibility_score FLOAT DEFAULT 0.0,
    sentiment_score FLOAT DEFAULT 0.0,
    sov_score FLOAT DEFAULT 0.0,
    citation_score FLOAT DEFAULT 0.0,
    geo_score FLOAT DEFAULT 0.0,
    analyzed_at TIMESTAMP DEFAULT NOW(),
    analyzer_model VARCHAR(64),
    raw_analysis_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ProductFeatureMention: product feature/scenario/price details per analysis
CREATE TABLE IF NOT EXISTS product_feature_mentions (
    id SERIAL PRIMARY KEY,
    analysis_id INTEGER NOT NULL REFERENCES response_analyses(id),
    brand_name VARCHAR(256) NOT NULL,
    product_name VARCHAR(256) NOT NULL,
    feature_name VARCHAR(128) NOT NULL,
    feature_sentiment VARCHAR(16),
    context_snippet TEXT,
    scenario VARCHAR(128),
    price_positioning VARCHAR(32),
    created_at TIMESTAMP DEFAULT NOW()
);

-- GEOScoreDaily: brand-level daily aggregation (time series)
CREATE TABLE IF NOT EXISTS geo_score_daily (
    id SERIAL PRIMARY KEY,
    brand_id INTEGER NOT NULL REFERENCES brands(id),
    date TIMESTAMP NOT NULL,
    target_llm VARCHAR(64),
    intent VARCHAR(64),
    language VARCHAR(8),
    total_queries INTEGER DEFAULT 0,
    mention_count INTEGER DEFAULT 0,
    mention_rate FLOAT DEFAULT 0.0,
    avg_position_rank FLOAT,
    first_place_count INTEGER DEFAULT 0,
    first_place_rate FLOAT DEFAULT 0.0,
    positive_rate FLOAT DEFAULT 0.0,
    negative_rate FLOAT DEFAULT 0.0,
    avg_sentiment_score FLOAT DEFAULT 0.0,
    citation_rate FLOAT DEFAULT 0.0,
    avg_sov FLOAT DEFAULT 0.0,
    avg_visibility FLOAT DEFAULT 0.0,
    avg_sentiment FLOAT DEFAULT 0.0,
    avg_sov_score FLOAT DEFAULT 0.0,
    avg_citation_score FLOAT DEFAULT 0.0,
    avg_geo_score FLOAT DEFAULT 0.0,
    industry VARCHAR(128),
    industry_rank INTEGER,
    industry_sov_pct FLOAT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    CONSTRAINT uq_geo_daily_dims UNIQUE (brand_id, date, target_llm, intent, language)
);

-- IndustryBenchmarkDaily: industry-level daily benchmarks
CREATE TABLE IF NOT EXISTS industry_benchmark_daily (
    id SERIAL PRIMARY KEY,
    industry VARCHAR(128) NOT NULL,
    date TIMESTAMP NOT NULL,
    target_llm VARCHAR(64),
    total_brands INTEGER DEFAULT 0,
    total_queries INTEGER DEFAULT 0,
    avg_mention_rate FLOAT DEFAULT 0.0,
    avg_geo_score FLOAT DEFAULT 0.0,
    avg_sentiment FLOAT DEFAULT 0.0,
    score_p25 FLOAT,
    score_p50 FLOAT,
    score_p75 FLOAT,
    top_brands_json JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    CONSTRAINT uq_industry_daily UNIQUE (industry, date, target_llm)
);

-- ProductScoreDaily: product-level daily aggregation
CREATE TABLE IF NOT EXISTS product_score_daily (
    id SERIAL PRIMARY KEY,
    brand_id INTEGER NOT NULL REFERENCES brands(id),
    product_name VARCHAR(256) NOT NULL,
    category VARCHAR(128),
    date TIMESTAMP NOT NULL,
    target_llm VARCHAR(64),
    total_queries INTEGER DEFAULT 0,
    mention_count INTEGER DEFAULT 0,
    mention_rate FLOAT DEFAULT 0.0,
    avg_position_rank FLOAT,
    first_place_count INTEGER DEFAULT 0,
    first_place_rate FLOAT DEFAULT 0.0,
    avg_sentiment_score FLOAT DEFAULT 0.0,
    avg_geo_score FLOAT DEFAULT 0.0,
    category_sov_pct FLOAT,
    category_rank INTEGER,
    comparison_wins INTEGER DEFAULT 0,
    comparison_total INTEGER DEFAULT 0,
    win_rate FLOAT DEFAULT 0.0,
    top_features_json JSONB,
    top_scenarios_json JSONB,
    price_positioning VARCHAR(32),
    price_positioning_json JSONB,
    top_drivers_json JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP,
    CONSTRAINT uq_product_daily UNIQUE (brand_id, product_name, date, target_llm)
);
