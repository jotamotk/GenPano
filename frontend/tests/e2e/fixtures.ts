/**
 * Test fixtures: pre-canned API responses that match the backend DTO shapes
 * the chart-page hooks consume. Used by tests/e2e/* to bypass the real
 * backend so the FE can be exercised in isolation.
 */

import type { Route } from '@playwright/test'

export const FAKE_PROJECT_ID = '11111111-2222-3333-4444-555555555555'
export const FAKE_BRAND_ID = 42
export const FAKE_INDUSTRY_ID = 1

export const FAKE_USER = {
  id: 'user-uuid-test-1',
  email: 'test@example.com',
  name: 'Test User',
  company: null,
  role: 'paid',
  provider: 'email',
  emailVerified: true,
  locale: 'zh-CN' as const,
  needsOnboarding: false,
}

// Same identity as FAKE_USER but flagged for the onboarding flow.
// Used by onboarding-flow.spec.ts so the dashboard guard fires.
export const FAKE_USER_NEEDS_ONBOARDING = {
  ...FAKE_USER,
  needsOnboarding: true,
}

// Mock results for /v1/brands/search. The third entry simulates a brand
// the current user already monitors so the UI can show the ✓ badge.
export const FAKE_BRAND_SEARCH_RESULTS = [
  {
    brandId: 1,
    brandName: 'Nike',
    industry: 'Sports',
    isAlreadyMonitoring: false,
  },
  {
    brandId: 2,
    brandName: 'Nike China',
    industry: 'Sports',
    isAlreadyMonitoring: false,
  },
  {
    brandId: 3,
    brandName: 'Adidas',
    industry: 'Sports',
    isAlreadyMonitoring: true,
  },
]

export const FAKE_PROJECT = {
  id: FAKE_PROJECT_ID,
  user_id: FAKE_USER.id,
  name: 'Test Project',
  industry_id: FAKE_INDUSTRY_ID,
  primary_brand_id: FAKE_BRAND_ID,
  competitor_brand_ids: [99, 100],
  preferences: {},
  created_at: '2026-05-01T00:00:00',
  updated_at: '2026-05-09T00:00:00',
  competitors: [
    { brand_id: 99, pinned_at: '2026-05-01T00:00:00' },
    { brand_id: 100, pinned_at: '2026-05-01T00:00:00' },
  ],
}

const today = () => new Date().toISOString().slice(0, 10)
const dayBefore = (n: number) => {
  const d = new Date()
  d.setDate(d.getDate() - n)
  return d.toISOString().slice(0, 10)
}
const last30 = (gen: (i: number) => number) =>
  Array.from({ length: 30 }, (_, i) => ({
    date: dayBefore(29 - i),
    value: gen(i),
  }))

// ── Brand Overview ──────────────────────────────────────────────────
export const FAKE_OVERVIEW = {
  project_id: FAKE_PROJECT_ID,
  brand_id: FAKE_BRAND_ID,
  brand_name: 'Test Brand',
  industry_id: FAKE_INDUSTRY_ID,
  period: { from: dayBefore(29), to: today() },
  kpi_cards: [
    { label_zh: 'GEO 评分', label_en: 'GeoScore', value: 72.5, delta_30d_pct: 3.2, direction: 'up' },
    {
      label_zh: '提及率',
      label_en: 'Mention Rate',
      value: 65.3,
      unit: '%',
      delta_30d_pct: 1.5,
      direction: 'up',
    },
    {
      label_zh: '声量份额',
      label_en: 'Share of Voice',
      value: 22.1,
      unit: '%',
      delta_30d_pct: -0.8,
      direction: 'down',
    },
    { label_zh: '情感分', label_en: 'Sentiment', value: 0.65, delta_30d_pct: 2.1, direction: 'up' },
  ],
  geo_score_30d: last30(i => 70 + Math.sin(i / 4) * 5),
  sov_30d: last30(i => 0.22 + Math.sin(i / 5) * 0.03),
  sentiment_30d: last30(i => 0.65 + Math.cos(i / 3) * 0.05),
  top_prompts: [
    {
      prompt_id: 1,
      prompt_text: '推荐保湿精华',
      mention_count: 120,
      avg_position_rank: 1.5,
      avg_sentiment_score: 0.72,
    },
  ],
  same_group_shared_domains: [
    { domain: 'group.example.com', brand_count: 3, total_mentions: 45 },
  ],
  state: 'ok' as const,
}

// ── Brand Metrics (sparklines) ──────────────────────────────────────
export const FAKE_METRICS = {
  project_id: FAKE_PROJECT_ID,
  brand_id: FAKE_BRAND_ID,
  period: { from: dayBefore(29), to: today() },
  engines: null,
  series: [
    {
      metric: 'mention_rate' as const,
      points: last30(i => 0.6 + Math.sin(i / 4) * 0.05),
    },
    {
      metric: 'sov' as const,
      points: last30(i => 0.22 + Math.cos(i / 5) * 0.03),
    },
    {
      metric: 'rank' as const,
      points: last30(i => 3 + Math.sin(i / 3) * 1),
    },
    {
      metric: 'sentiment' as const,
      points: last30(i => 0.65 + Math.cos(i / 4) * 0.04),
    },
    {
      metric: 'citation' as const,
      points: last30(i => 0.25 + Math.sin(i / 6) * 0.05),
    },
  ],
  state: 'ok' as const,
}

export const FAKE_COMPETITOR_METRICS = {
  project_id: FAKE_PROJECT_ID,
  primary_brand_id: FAKE_BRAND_ID,
  period: { from: dayBefore(29), to: today() },
  primary: {
    brand_id: FAKE_BRAND_ID,
    brand_name: 'Test Brand',
    avg_geo_score: 72.5,
    avg_mention_rate: 0.65,
    avg_sov: 0.22,
    avg_sentiment: 0.65,
    co_mention_count: 0,
    delta_30d_pct: 3.2,
  },
  competitors: [
    {
      brand_id: 99,
      brand_name: 'Competitor A',
      avg_geo_score: 68.0,
      avg_mention_rate: 0.52,
      avg_sov: 0.18,
      avg_sentiment: 0.58,
      co_mention_count: 12,
      delta_30d_pct: 1.2,
    },
    {
      brand_id: 100,
      brand_name: 'Competitor B',
      avg_geo_score: 75.5,
      avg_mention_rate: 0.7,
      avg_sov: 0.25,
      avg_sentiment: 0.72,
      co_mention_count: 8,
      delta_30d_pct: -1.5,
    },
  ],
  state: 'ok' as const,
}

export const FAKE_COMPETITOR_TRENDS = {
  project_id: FAKE_PROJECT_ID,
  metric: 'geo_score',
  period: { from: dayBefore(29), to: today() },
  series: [
    {
      brand_id: FAKE_BRAND_ID,
      brand_name: 'Test Brand',
      is_primary: true,
      points: last30(i => 70 + Math.sin(i / 4) * 5).map(p => ({
        date: p.date,
        value: p.value,
      })),
    },
    {
      brand_id: 99,
      brand_name: 'Competitor A',
      is_primary: false,
      points: last30(i => 65 + Math.cos(i / 3) * 4).map(p => ({
        date: p.date,
        value: p.value,
      })),
    },
  ],
  state: 'ok' as const,
}

// ── Engine breakdown ────────────────────────────────────────────────
export const FAKE_ENGINE_METRICS = {
  project_id: FAKE_PROJECT_ID,
  period: { from: dayBefore(29), to: today() },
  items: [
    {
      engine: 'chatgpt',
      mention_rate: 0.68,
      sov: 0.24,
      citation_rate: 0.3,
      sentiment: 0.7,
    },
    {
      engine: 'doubao',
      mention_rate: 0.62,
      sov: 0.2,
      citation_rate: 0.25,
      sentiment: 0.62,
    },
    {
      engine: 'deepseek',
      mention_rate: 0.65,
      sov: 0.22,
      citation_rate: 0.28,
      sentiment: 0.66,
    },
  ],
  state: 'ok' as const,
}

export const FAKE_POSITION_DISTRIBUTION = {
  project_id: FAKE_PROJECT_ID,
  period: { from: dayBefore(29), to: today() },
  items: [
    { bucket: 'Top1', count: 145, pct: 32.2 },
    { bucket: 'Top3', count: 128, pct: 28.4 },
    { bucket: 'Top5', count: 95, pct: 21.1 },
    { bucket: 'Top10', count: 50, pct: 11.1 },
    { bucket: '11+', count: 22, pct: 4.9 },
    { bucket: 'Unmentioned', count: 10, pct: 2.2 },
  ],
  total_mentions: 450,
  state: 'ok' as const,
}

export const FAKE_TOPIC_HEATMAP = {
  project_id: FAKE_PROJECT_ID,
  metric: 'mention_rate' as const,
  rows: [
    {
      brand_id: FAKE_BRAND_ID,
      brand_name: 'Test Brand',
      values: Array.from({ length: 8 }, (_, i) => ({
        topic_id: i + 1,
        topic_label: `Topic ${i + 1}`,
        value: 0.4 + (i % 4) * 0.1,
        sample: 30 + i * 3,
      })),
    },
    {
      brand_id: 99,
      brand_name: 'Competitor A',
      values: Array.from({ length: 8 }, (_, i) => ({
        topic_id: i + 1,
        topic_label: `Topic ${i + 1}`,
        value: 0.3 + (i % 3) * 0.1,
        sample: 25 + i * 2,
      })),
    },
  ],
  state: 'ok' as const,
}

// ── Sentiment ───────────────────────────────────────────────────────
export const FAKE_SENTIMENT = {
  project_id: FAKE_PROJECT_ID,
  brand_id: FAKE_BRAND_ID,
  period: { from: dayBefore(29), to: today() },
  distribution: {
    positive_count: 240,
    neutral_count: 130,
    negative_count: 80,
    positive_pct: 53.3,
    neutral_pct: 28.9,
    negative_pct: 17.8,
    avg_sentiment_score: 0.65,
  },
  trend_30d: last30(i => i * 0.01).map(p => ({
    date: p.date,
    positive_pct: 50 + p.value * 50,
    negative_pct: 18 - p.value * 5,
    avg_score: 0.6 + p.value,
  })),
  top_keywords: [
    { keyword: '保湿', polarity: 'positive', count: 45, avg_strength: 0.8 },
    { keyword: '抗老', polarity: 'positive', count: 32, avg_strength: 0.75 },
    { keyword: '价格高', polarity: 'negative', count: 18, avg_strength: 0.6 },
  ],
  top_drivers: [
    {
      driver_text: '保湿效果好',
      polarity: 'positive',
      category: 'efficacy',
      count: 22,
      avg_strength: 0.8,
    },
  ],
  state: 'ok' as const,
}

export const FAKE_SENTIMENT_BY_ENGINE = {
  project_id: FAKE_PROJECT_ID,
  period: { from: dayBefore(29), to: today() },
  items: [
    { engine: 'chatgpt', positive: 120, neutral: 60, negative: 30 },
    { engine: 'doubao', positive: 80, neutral: 40, negative: 25 },
    { engine: 'deepseek', positive: 90, neutral: 50, negative: 20 },
  ],
  state: 'ok' as const,
}

export const FAKE_SENTIMENT_TREND_BY_ENGINE = {
  project_id: FAKE_PROJECT_ID,
  period: { from: dayBefore(29), to: today() },
  engines: ['chatgpt', 'doubao', 'deepseek'],
  items: last30(i => 0.6 + Math.sin(i / 4) * 0.1).map(p => ({
    date: p.date,
    by_engine: { chatgpt: p.value, doubao: p.value - 0.05, deepseek: p.value + 0.02 },
  })),
  state: 'ok' as const,
}

export const FAKE_TOPIC_ATTRIBUTION = {
  project_id: FAKE_PROJECT_ID,
  items: [
    {
      topic_id: 1,
      topic_name: '价格争议',
      negative_count: 30,
      negative_ratio: 0.45,
      sample_snippet: '部分用户反映价格偏高',
    },
    {
      topic_id: 2,
      topic_name: '产品使用感',
      negative_count: 18,
      negative_ratio: 0.32,
      sample_snippet: null,
    },
  ],
  state: 'ok' as const,
}

export const FAKE_MENTION_SAMPLES = {
  project_id: FAKE_PROJECT_ID,
  items: [
    {
      mention_id: 1,
      response_id: 100,
      label: '正面',
      polarity: 'positive' as const,
      summary: '保湿效果显著',
      snippet: '保湿效果显著',
      engine: 'chatgpt',
      topic: '保湿精华',
      occurred_at: today(),
    },
    {
      mention_id: 2,
      response_id: 101,
      label: '负面',
      polarity: 'negative' as const,
      summary: '价格偏高',
      snippet: '价格偏高',
      engine: 'doubao',
      topic: '价格',
      occurred_at: today(),
    },
  ],
  state: 'ok' as const,
}

// ── Citations ───────────────────────────────────────────────────────
export const FAKE_AUTHORITY_TREND = {
  project_id: FAKE_PROJECT_ID,
  period: { from: dayBefore(29), to: today() },
  points: last30(i => i).map(p => ({
    date: p.date,
    tier1_pct: 30 + Math.sin(p.value / 4) * 5,
    tier2_pct: 25 + Math.cos(p.value / 5) * 4,
    tier3_pct: 25,
    tier4_pct: 15,
    untiered_pct: 5,
  })),
  state: 'ok' as const,
}

export const FAKE_CITATION_COMPOSITION = {
  project_id: FAKE_PROJECT_ID,
  period: { from: dayBefore(29), to: today() },
  segments: [
    { label: 'Tier 1 · 官方', tier: 1, count: 120, pct: 30.0 },
    { label: 'Tier 2 · 权威媒体', tier: 2, count: 100, pct: 25.0 },
    { label: 'Tier 3 · KOL', tier: 3, count: 100, pct: 25.0 },
    { label: 'Tier 4 · UGC', tier: 4, count: 60, pct: 15.0 },
    { label: '未分类', tier: null, count: 20, pct: 5.0 },
  ],
  total: 400,
  state: 'ok' as const,
}

export const FAKE_CITATIONS = {
  project_id: FAKE_PROJECT_ID,
  brand_id: FAKE_BRAND_ID,
  period: { from: dayBefore(29), to: today() },
  items: Array.from({ length: 10 }, (_, i) => ({
    citation_id: i + 1,
    response_id: 1000 + i,
    url: `https://example${i}.com/article-${i}`,
    domain: `example${i}.com`,
    title: `示例文章 ${i + 1}`,
    source_type: i < 3 ? 'official' : i < 6 ? 'media' : 'kol',
    occurred_at: today(),
  })),
  next_cursor: null,
  total: 10,
  by_domain_top: [
    { domain: 'official.example.com', count: 45, tier: 1 },
    { domain: 'media.example.com', count: 32, tier: 2 },
    { domain: 'blog.example.com', count: 18, tier: 3 },
  ],
  state: 'ok' as const,
}

export const FAKE_CONTENT_GAP = {
  project_id: FAKE_PROJECT_ID,
  topics: [
    {
      topic_id: 1,
      topic_name: '抗老护肤',
      mention_rate: 0.8,
      citation_rate: 0.2,
      gap_score: 0.6,
      suggestion: '增加权威媒体引用',
    },
  ],
  page_type_distribution: [
    { page_type: 'media', count: 40, pct: 40.0 },
    { page_type: 'kol', count: 30, pct: 30.0 },
  ],
  state: 'ok' as const,
}

export const FAKE_PR_TARGETS = {
  project_id: FAKE_PROJECT_ID,
  targets: [
    {
      domain: 'media.example.com',
      tier: 2,
      we_count: 5,
      competitors_count: 18,
      gap: 13,
      suggestion: '权威媒体投放',
    },
  ],
  kol_scorecards: [
    {
      name: '美妆 KOL A',
      platform: 'weibo',
      audience_score: 85,
      quality_score: 78,
      risk: 'low',
      notes: null,
    },
  ],
  tier2_matrix: {
    domains: ['media1.com', 'media2.com'],
    brands: [
      { brand_id: FAKE_BRAND_ID, label: 'Test Brand', counts: [12, 8] },
      { brand_id: 99, label: 'Competitor A', counts: [20, 15] },
    ],
  },
  state: 'ok' as const,
}

export const FAKE_SIMULATOR_BASELINE = {
  project_id: FAKE_PROJECT_ID,
  current_pano: 72.5,
  industry_median: 65.0,
  industry_top3_avg: 80.0,
  tiers: [
    { tier: 1, weight: 0.4, confidence: 0.95, current_count: 25 },
    { tier: 2, weight: 0.3, confidence: 0.85, current_count: 18 },
    { tier: 3, weight: 0.2, confidence: 0.65, current_count: 32 },
    { tier: 4, weight: 0.1, confidence: 0.5, current_count: 45 },
  ],
  presets: [
    { id: 'official_push', label: '官方域强化', delta_by_tier: { '1': 5, '2': 0, '3': 0, '4': 0 } },
  ],
  state: 'ok' as const,
}

export const FAKE_AUTHORITY_RADAR = {
  project_id: FAKE_PROJECT_ID,
  rows: [
    {
      tier: 'Tier1',
      me: 25,
      industry_median: 20,
      top_competitor: 30,
      top_competitor_id: 100,
      top_competitor_name: 'Competitor B',
    },
    {
      tier: 'Tier2',
      me: 18,
      industry_median: 22,
      top_competitor: 28,
      top_competitor_id: 100,
      top_competitor_name: 'Competitor B',
    },
    {
      tier: 'Tier3',
      me: 32,
      industry_median: 28,
      top_competitor: 26,
      top_competitor_id: 100,
      top_competitor_name: 'Competitor B',
    },
    {
      tier: 'Tier4',
      me: 45,
      industry_median: 30,
      top_competitor: 38,
      top_competitor_id: 100,
      top_competitor_name: 'Competitor B',
    },
    {
      tier: '总覆盖',
      me: 120,
      industry_median: 100,
      top_competitor: 122,
      top_competitor_id: 100,
      top_competitor_name: 'Competitor B',
    },
  ],
  state: 'ok' as const,
}

export const FAKE_GROUP_SHARED_DOMAINS = {
  project_id: FAKE_PROJECT_ID,
  group_id: 1,
  group_name: 'Test Group',
  shared_ratio: 0.32,
  items: [
    {
      domain: 'group-shared.com',
      tier: 2,
      brand_count: 3,
      total_mentions: 24,
      sister_brand_ids: [99, 100],
      sister_brand_names: ['Competitor A', 'Competitor B'],
    },
  ],
  state: 'ok' as const,
}

// ── Products ────────────────────────────────────────────────────────
export const FAKE_PRODUCTS = {
  project_id: FAKE_PROJECT_ID,
  items: [
    {
      product_id: 1,
      product_name: '保湿精华',
      brand_id: FAKE_BRAND_ID,
      sku: 'SKU-001',
      category: '护肤',
      mention_count: 120,
      mention_rate: 0.65,
      avg_position_rank: 1.8,
      avg_geo_score: 75.5,
      avg_sentiment: 0.7,
      sov: 25.5,
      ranking: 2,
      win_rate: 0.55,
      trend_30d: 0.08,
      sparkline: Array.from({ length: 30 }, (_, i) => 0.5 + (i % 10) * 0.02),
      top_features: [],
      top_scenarios: [],
    },
    {
      product_id: 2,
      product_name: '抗老面霜',
      brand_id: FAKE_BRAND_ID,
      sku: 'SKU-002',
      category: '护肤',
      mention_count: 95,
      mention_rate: 0.55,
      avg_position_rank: 2.2,
      avg_geo_score: 70.5,
      avg_sentiment: 0.65,
      sov: 20.0,
      ranking: 5,
      win_rate: 0.48,
      trend_30d: 0.04,
      sparkline: Array.from({ length: 30 }, (_, i) => 0.4 + (i % 8) * 0.02),
      top_features: [],
      top_scenarios: [],
    },
  ],
  total: 2,
  state: 'ok' as const,
}

export const FAKE_PRODUCT_RELATIONS = {
  project_id: FAKE_PROJECT_ID,
  items: [
    {
      product_a_id: 1,
      product_a_name: '保湿精华',
      product_b_id: 2,
      product_b_name: '抗老面霜',
      type: 'PAIRS_WITH',
      confidence: 0.85,
    },
  ],
  state: 'ok' as const,
}

export const FAKE_DIAGNOSTICS = {
  project_id: FAKE_PROJECT_ID,
  period: { from: dayBefore(29), to: today() },
  items: [],
  counts_by_severity: { P0: 0, P1: 0, P2: 0, P3: 0 },
  state: 'empty' as const,
}

// ── Industry endpoints ──────────────────────────────────────────────
export const FAKE_INDUSTRIES_LIST = {
  items: [
    { industry_id: FAKE_INDUSTRY_ID, name: 'beauty', brand_count: 50 },
  ],
  total: 1,
}

export const FAKE_INDUSTRY_OVERVIEW = {
  industry_id: FAKE_INDUSTRY_ID,
  industry_name: 'beauty',
  period: { from: dayBefore(29), to: today() },
  kpi_cards: [
    { label_zh: 'industry GEO', label_en: 'Industry GEO', value: 65.0, unit: null, delta_30d_pct: null },
    { label_zh: 'avg mention rate', label_en: 'Avg Mention Rate', value: 50.0, unit: '%', delta_30d_pct: null },
    { label_zh: 'avg sentiment', label_en: 'Avg Sentiment', value: 0.6, unit: null, delta_30d_pct: null },
    { label_zh: 'active brands', label_en: 'Active Brands', value: 50, unit: null, delta_30d_pct: null },
  ],
  top_brands: [
    { brand_id: FAKE_BRAND_ID, brand_name: 'Test Brand', avg_geo_score: 72.5, rank: 1 },
    { brand_id: 99, brand_name: 'Competitor A', avg_geo_score: 68.0, rank: 2 },
  ],
  events_30d: [],
  hero_counts: {
    brand_count: 50,
    topic_count: 25,
    category_count: 8,
    response_count: 1200,
  },
  state: 'ok' as const,
}

export const FAKE_INDUSTRY_RANKING = {
  industry_id: FAKE_INDUSTRY_ID,
  period: { from: dayBefore(29), to: today() },
  items: Array.from({ length: 12 }, (_, i) => ({
    rank: i + 1,
    brand_id: i === 0 ? FAKE_BRAND_ID : 100 + i,
    brand_name: i === 0 ? 'Test Brand' : `Brand ${i}`,
    avg_geo_score: 80 - i * 1.2,
    avg_mention_rate: 0.7 - i * 0.04,
    avg_sov: 0.25 - i * 0.015,
    avg_sentiment: 0.7 - i * 0.02,
    avg_citation_rate: 0.3 - i * 0.015,
    sparkline: Array.from({ length: 30 }, (_, j) => 70 + Math.sin(j / 4) * 5),
  })),
  total: 12,
  my_rank: 1,
  state: 'ok' as const,
}

export const FAKE_INDUSTRY_AVG_GEO = {
  industry_id: FAKE_INDUSTRY_ID,
  industry_name: 'beauty',
  period: { from: dayBefore(29), to: today() },
  points: last30(i => 65 + Math.sin(i / 5) * 3).map(p => ({
    date: p.date,
    avg_geo_score: p.value,
    industry_median: p.value - 2,
    top10_avg: p.value + 8,
    total_brands: 50,
  })),
  summary: { avg_geo_score: 65.5, industry_median: 63.0, top10_avg: 73.5 },
  state: 'ok' as const,
}

export const FAKE_INDUSTRY_DISTRIBUTION = {
  industry_id: FAKE_INDUSTRY_ID,
  industry_name: 'beauty',
  period: { from: dayBefore(29), to: today() },
  stats: [
    {
      metric: 'mention_rate',
      values: [40, 45, 50, 55, 60, 65, 70, 75, 80],
      p25: 47,
      p50: 60,
      p75: 72,
      min: 40,
      max: 80,
      n: 9,
    },
    {
      metric: 'sov',
      values: [10, 15, 20, 25, 30],
      p25: 12,
      p50: 20,
      p75: 27,
      min: 10,
      max: 30,
      n: 5,
    },
    {
      metric: 'sentiment',
      values: [50, 55, 60, 65, 70],
      p25: 52,
      p50: 60,
      p75: 67,
      min: 50,
      max: 70,
      n: 5,
    },
    {
      metric: 'citation',
      values: [10, 20, 30],
      p25: 15,
      p50: 20,
      p75: 25,
      min: 10,
      max: 30,
      n: 3,
    },
    { metric: 'rank', values: [1, 5, 10, 15, 20], p25: 3, p50: 10, p75: 17, min: 1, max: 20, n: 5 },
  ],
  state: 'ok' as const,
}

export const FAKE_INDUSTRY_MOVERS = {
  industry_id: FAKE_INDUSTRY_ID,
  period: { from: dayBefore(29), to: today() },
  gainers: [
    {
      brand_id: 105,
      brand_name: 'Brand 5',
      delta_pct: 12.5,
      current_pano: 78.0,
      sparkline: Array.from({ length: 30 }, (_, i) => 70 + i * 0.3),
      driver: null,
    },
  ],
  losers: [
    {
      brand_id: 110,
      brand_name: 'Brand 10',
      delta_pct: -8.2,
      current_pano: 65.0,
      sparkline: Array.from({ length: 30 }, (_, i) => 73 - i * 0.3),
      driver: null,
    },
  ],
  state: 'ok' as const,
}

export const FAKE_INDUSTRY_GROUPS = {
  industry_id: FAKE_INDUSTRY_ID,
  items: [
    {
      group_id: 1,
      group_name: 'Estee Lauder Companies',
      parent_company: 'EL',
      member_brand_ids: [FAKE_BRAND_ID, 99],
      member_brand_names: ['Test Brand', 'Competitor A'],
      aggregate_geo_score: 70.25,
      aggregate_sov: 0.2,
    },
  ],
  state: 'ok' as const,
}

export const FAKE_INDUSTRY_TOP_DOMAINS = {
  industry_id: FAKE_INDUSTRY_ID,
  period: { from: dayBefore(29), to: today() },
  items: Array.from({ length: 10 }, (_, i) => ({
    domain: `top${i}.example.com`,
    tier: (i % 4) + 1,
    total_citations: 100 - i * 8,
    top_brand_id: FAKE_BRAND_ID,
    top_brand_name: 'Test Brand',
    top_brand_share: 0.3 - i * 0.02,
  })),
  state: 'ok' as const,
}

export const FAKE_INDUSTRY_SEGMENTS = {
  industry_id: FAKE_INDUSTRY_ID,
  items: [
    {
      segment: 'luxury_intl',
      label_zh: '国际高端',
      items: [
        {
          rank: 1,
          brand_id: FAKE_BRAND_ID,
          brand_name: 'Test Brand',
          avg_geo_score: 80,
          avg_mention_rate: 0.7,
          avg_sov: 0.25,
          avg_sentiment: 0.7,
          avg_citation_rate: 0.3,
          sparkline: [],
        },
      ],
    },
    { segment: 'mass_premium', label_zh: '大众高端', items: [] },
    { segment: 'niche_emerging', label_zh: '小众-新锐', items: [] },
  ],
  state: 'ok' as const,
}

export const FAKE_INDUSTRY_RANKING_BY_ENGINE = {
  industry_id: FAKE_INDUSTRY_ID,
  period: { from: dayBefore(29), to: today() },
  engines: ['chatgpt', 'doubao', 'deepseek'],
  items: Array.from({ length: 5 }, (_, i) => ({
    brand_id: i === 0 ? FAKE_BRAND_ID : 100 + i,
    brand_name: i === 0 ? 'Test Brand' : `Brand ${i}`,
    overall_rank: i + 1,
    cells: [
      { engine: 'chatgpt', rank: i + 1, avg_geo_score: 80 - i * 2 },
      { engine: 'doubao', rank: i + 1, avg_geo_score: 78 - i * 2 },
      { engine: 'deepseek', rank: i + 1, avg_geo_score: 82 - i * 2 },
    ],
    delta_max: 4,
  })),
  state: 'ok' as const,
}

export const FAKE_INDUSTRY_TOPICS = {
  industry_id: FAKE_INDUSTRY_ID,
  period: { from: dayBefore(29), to: today() },
  items: Array.from({ length: 8 }, (_, i) => ({
    topic_id: i + 1,
    topic_name: `行业 Topic ${i + 1}`,
    mention_count: 200 - i * 15,
    unique_brand_count: 30 - i * 2,
    hot_score: 90 - i * 5,
  })),
  total: 8,
  state: 'ok' as const,
}

export const FAKE_INDUSTRY_TOPIC_INTENT = {
  industry_id: FAKE_INDUSTRY_ID,
  intents: ['推荐', '比较', '问题', '其他'],
  rows: Array.from({ length: 8 }, (_, i) => ({
    topic_id: i + 1,
    topic_name: `Topic ${i + 1}`,
    total_count: 200 - i * 15,
    cells: [
      { intent: '推荐', count: 80 - i * 5, pct: 40 },
      { intent: '比较', count: 60 - i * 4, pct: 30 },
      { intent: '问题', count: 40 - i * 3, pct: 20 },
      { intent: '其他', count: 20, pct: 10 },
    ],
  })),
  state: 'ok' as const,
}

// ── Route handler factory ───────────────────────────────────────────
type Handler = (route: Route) => Promise<void> | void

export function buildApiHandlers(): Record<string, Handler> {
  const json = (data: unknown): Handler => async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(data),
    })
  }

  return {
    [`**/api/auth/me`]: json(FAKE_USER),
    [`**/api/v1/projects/`]: json({ items: [FAKE_PROJECT], total: 1 }),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}`]: json(FAKE_PROJECT),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/overview`]: json(FAKE_OVERVIEW),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/metrics**`]: json(FAKE_METRICS),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/metrics/by-engine`]: json(FAKE_ENGINE_METRICS),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/position-distribution`]: json(FAKE_POSITION_DISTRIBUTION),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/topic-heatmap**`]: json(FAKE_TOPIC_HEATMAP),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/sentiment`]: json(FAKE_SENTIMENT),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/sentiment/by-engine`]: json(FAKE_SENTIMENT_BY_ENGINE),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/sentiment/trend-by-engine`]: json(FAKE_SENTIMENT_TREND_BY_ENGINE),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/sentiment/topic-attribution**`]: json(FAKE_TOPIC_ATTRIBUTION),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/mention-samples**`]: json(FAKE_MENTION_SAMPLES),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/citations**`]: json(FAKE_CITATIONS),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/citations/authority-trend`]: json(FAKE_AUTHORITY_TREND),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/citations/composition`]: json(FAKE_CITATION_COMPOSITION),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/citations/content-gap**`]: json(FAKE_CONTENT_GAP),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/citations/pr-targets`]: json(FAKE_PR_TARGETS),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/citations/simulator-baseline`]: json(FAKE_SIMULATOR_BASELINE),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/competitors/metrics`]: json(FAKE_COMPETITOR_METRICS),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/competitors/trends**`]: json(FAKE_COMPETITOR_TRENDS),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/competitors/authority-radar`]: json(FAKE_AUTHORITY_RADAR),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/group-shared-domains`]: json(FAKE_GROUP_SHARED_DOMAINS),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/products`]: json(FAKE_PRODUCTS),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/products/relations`]: json(FAKE_PRODUCT_RELATIONS),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/topics`]: json({ project_id: FAKE_PROJECT_ID, items: [], total: 0, state: 'empty' }),
    [`**/api/v1/projects/${FAKE_PROJECT_ID}/diagnostics**`]: json(FAKE_DIAGNOSTICS),

    [`**/api/v1/industries/`]: json(FAKE_INDUSTRIES_LIST),
    [`**/api/v1/industries/${FAKE_INDUSTRY_ID}/overview**`]: json(FAKE_INDUSTRY_OVERVIEW),
    [`**/api/v1/industries/${FAKE_INDUSTRY_ID}/ranking**`]: json(FAKE_INDUSTRY_RANKING),
    [`**/api/v1/industries/${FAKE_INDUSTRY_ID}/avg-geo-score**`]: json(FAKE_INDUSTRY_AVG_GEO),
    [`**/api/v1/industries/${FAKE_INDUSTRY_ID}/distribution**`]: json(FAKE_INDUSTRY_DISTRIBUTION),
    [`**/api/v1/industries/${FAKE_INDUSTRY_ID}/movers**`]: json(FAKE_INDUSTRY_MOVERS),
    [`**/api/v1/industries/${FAKE_INDUSTRY_ID}/groups**`]: json(FAKE_INDUSTRY_GROUPS),
    [`**/api/v1/industries/${FAKE_INDUSTRY_ID}/top-domains**`]: json(FAKE_INDUSTRY_TOP_DOMAINS),
    [`**/api/v1/industries/${FAKE_INDUSTRY_ID}/segments**`]: json(FAKE_INDUSTRY_SEGMENTS),
    [`**/api/v1/industries/${FAKE_INDUSTRY_ID}/ranking-by-engine**`]: json(FAKE_INDUSTRY_RANKING_BY_ENGINE),
    [`**/api/v1/industries/${FAKE_INDUSTRY_ID}/topics**`]: json(FAKE_INDUSTRY_TOPICS),
    [`**/api/v1/industries/${FAKE_INDUSTRY_ID}/topic-intent-matrix**`]: json(FAKE_INDUSTRY_TOPIC_INTENT),
  }
}
