/**
 * BestCoffer demo fixtures.
 *
 * Narrative aligns with bestcoffer's production topic data (#1262):
 * AI 数据脱敏 / 虚拟数据室 SaaS for B2B 金融 + 合规 market.
 * Topic IDs (153, 154, 158, 159, 162, 170-177) match
 * `backend/tests/test_topic_heatmap_pad_with_owned_topics.py:45-61`.
 *
 * 30-day window ends 2026-05-18 (CLAUDE.md currentDate).
 *
 * Each fixture is typed against the live API contract so TS catches
 * shape drift on either side.
 */

import { DEMO_BRAND_ID, DEMO_PROJECT_ID } from '../../lib/demoMode'
import type {
  CompetitorMetricsOut,
  CompetitorTrendsOut,
  ProductsOut,
} from '../../api/brandMetrics'
import type { DiagnosticListOut, DiagnosticOut } from '../../api/diagnostics'
import type { IndustryRankingOut } from '../../api/industries'
import type { ReportListOut } from '../../api/reports'

const PERIOD = { from: '2026-04-18', to: '2026-05-18' }

const COMPETITORS: { id: number; name: string }[] = [
  { id: 9101, name: 'Securiti.ai' },
  { id: 9102, name: 'OneTrust' },
  { id: 9103, name: '数据安信' },
  { id: 9104, name: 'SafeRoom Cloud' },
  { id: 9105, name: 'BigID' },
  { id: 9106, name: '帆软合规云' },
]

function range(n: number): number[] {
  return Array.from({ length: n }, (_, i) => i)
}

function dateSeries(days = 30): string[] {
  const end = new Date('2026-05-18T00:00:00Z')
  return range(days).map((i) => {
    const d = new Date(end)
    d.setUTCDate(end.getUTCDate() - (days - 1 - i))
    return d.toISOString().slice(0, 10)
  })
}

function walk(start: number, amp: number, days = 30, seed = 1): number[] {
  // Deterministic pseudo-random walk so chart shapes are stable across runs.
  let v = start
  let s = seed
  return range(days).map(() => {
    s = (s * 9301 + 49297) % 233280
    const r = s / 233280 - 0.5
    v = Math.max(0, Math.min(100, v + r * amp))
    return Number(v.toFixed(2))
  })
}

// 行业排名 — bestcoffer ranked #4 of 10 in 数据安全合规 SaaS industry
export const INDUSTRY_RANKING: IndustryRankingOut = {
  industry_id: 0, // matched regardless of id; preserved on injection
  period: PERIOD,
  items: [
    { rank: 1, brand_id: 9101, brand_name: 'Securiti.ai',     avg_geo_score: 78.6, avg_mention_rate: 0.41, avg_sov: 0.18, avg_sentiment: 0.62, avg_citation_rate: 0.34, sparkline: walk(76, 4, 30, 11) },
    { rank: 2, brand_id: 9102, brand_name: 'OneTrust',        avg_geo_score: 74.1, avg_mention_rate: 0.38, avg_sov: 0.16, avg_sentiment: 0.58, avg_citation_rate: 0.31, sparkline: walk(72, 4, 30, 13) },
    { rank: 3, brand_id: 9103, brand_name: '数据安信',         avg_geo_score: 70.9, avg_mention_rate: 0.32, avg_sov: 0.13, avg_sentiment: 0.55, avg_citation_rate: 0.28, sparkline: walk(68, 4, 30, 17) },
    { rank: 4, brand_id: DEMO_BRAND_ID, brand_name: 'BestCoffer', avg_geo_score: 67.2, avg_mention_rate: 0.29, avg_sov: 0.12, avg_sentiment: 0.61, avg_citation_rate: 0.24, sparkline: walk(63, 5, 30, 19) },
    { rank: 5, brand_id: 9104, brand_name: 'SafeRoom Cloud',  avg_geo_score: 64.5, avg_mention_rate: 0.26, avg_sov: 0.10, avg_sentiment: 0.52, avg_citation_rate: 0.21, sparkline: walk(62, 4, 30, 23) },
    { rank: 6, brand_id: 9105, brand_name: 'BigID',           avg_geo_score: 61.8, avg_mention_rate: 0.24, avg_sov: 0.09, avg_sentiment: 0.49, avg_citation_rate: 0.18, sparkline: walk(60, 3, 30, 29) },
    { rank: 7, brand_id: 9106, brand_name: '帆软合规云',       avg_geo_score: 58.3, avg_mention_rate: 0.22, avg_sov: 0.08, avg_sentiment: 0.47, avg_citation_rate: 0.16, sparkline: walk(57, 3, 30, 31) },
    { rank: 8, brand_id: 9107, brand_name: 'DataMasker Pro',  avg_geo_score: 54.0, avg_mention_rate: 0.18, avg_sov: 0.06, avg_sentiment: 0.43, avg_citation_rate: 0.13, sparkline: walk(53, 3, 30, 37) },
    { rank: 9, brand_id: 9108, brand_name: 'DocuClean',       avg_geo_score: 49.7, avg_mention_rate: 0.15, avg_sov: 0.05, avg_sentiment: 0.41, avg_citation_rate: 0.11, sparkline: walk(48, 3, 30, 41) },
    { rank: 10, brand_id: 9109, brand_name: 'TrustGuard',     avg_geo_score: 45.2, avg_mention_rate: 0.12, avg_sov: 0.04, avg_sentiment: 0.39, avg_citation_rate: 0.09, sparkline: walk(44, 3, 30, 43) },
  ],
  total: 10,
  my_rank: 4,
  state: 'ok',
}

// 竞品四象限 — primary + 6 competitors with sentiment & sov for scatter
export const COMPETITOR_METRICS: CompetitorMetricsOut = {
  project_id: DEMO_PROJECT_ID,
  primary_brand_id: DEMO_BRAND_ID,
  period: PERIOD,
  primary: {
    brand_id: DEMO_BRAND_ID,
    brand_key: 'bestcoffer',
    brand_name: 'BestCoffer',
    avg_geo_score: 67.2,
    avg_mention_rate: 0.29,
    avg_sov: 0.18,
    avg_sentiment: 0.61,
    co_mention_count: 1284,
    delta_30d_pct: 8.4,
  },
  competitors: [
    { brand_id: 9101, brand_key: 'securiti', brand_name: 'Securiti.ai',    avg_geo_score: 78.6, avg_mention_rate: 0.41, avg_sov: 0.27, avg_sentiment: 0.62, co_mention_count: 421, delta_30d_pct: 5.1 },
    { brand_id: 9102, brand_key: 'onetrust', brand_name: 'OneTrust',       avg_geo_score: 74.1, avg_mention_rate: 0.38, avg_sov: 0.24, avg_sentiment: 0.58, co_mention_count: 387, delta_30d_pct: 2.3 },
    { brand_id: 9103, brand_key: 'shujuanxin', brand_name: '数据安信',     avg_geo_score: 70.9, avg_mention_rate: 0.32, avg_sov: 0.19, avg_sentiment: 0.55, co_mention_count: 312, delta_30d_pct: -1.2 },
    { brand_id: 9104, brand_key: 'saferoom', brand_name: 'SafeRoom Cloud', avg_geo_score: 64.5, avg_mention_rate: 0.26, avg_sov: 0.14, avg_sentiment: 0.52, co_mention_count: 263, delta_30d_pct: 11.7 },
    { brand_id: 9105, brand_key: 'bigid',    brand_name: 'BigID',          avg_geo_score: 61.8, avg_mention_rate: 0.24, avg_sov: 0.12, avg_sentiment: 0.49, co_mention_count: 248, delta_30d_pct: -3.6 },
    { brand_id: 9106, brand_key: 'fanruan',  brand_name: '帆软合规云',     avg_geo_score: 58.3, avg_mention_rate: 0.22, avg_sov: 0.10, avg_sentiment: 0.47, co_mention_count: 198, delta_30d_pct: 4.9 },
  ],
  state: 'ok',
}

// PANO 趋势 — 4 series (primary + top 3 competitors), 30 daily points each
function trendSeries(brandId: number, brandName: string, isPrimary: boolean, baseline: number, amp: number, seed: number) {
  const dates = dateSeries()
  return {
    brand_id: brandId,
    brand_key: brandName.toLowerCase().replace(/\./g, '').replace(/\s+/g, '-'),
    brand_name: brandName,
    is_primary: isPrimary,
    points: dates.map((date, i) => ({
      date,
      value: walk(baseline, amp, 30, seed)[i],
    })),
  }
}

export const COMPETITOR_TRENDS_GEO: CompetitorTrendsOut = {
  project_id: DEMO_PROJECT_ID,
  metric: 'geo_score',
  period: PERIOD,
  series: [
    trendSeries(DEMO_BRAND_ID, 'BestCoffer', true, 63, 5, 19),
    trendSeries(9101, 'Securiti.ai', false, 76, 4, 11),
    trendSeries(9102, 'OneTrust', false, 72, 4, 13),
    trendSeries(9103, '数据安信', false, 68, 4, 17),
  ],
  state: 'ok',
}

// 产品组合 — 6 SKU rows with sparkline + features
export const PRODUCTS: ProductsOut = {
  project_id: DEMO_PROJECT_ID,
  items: [
    {
      product_id: 5001, product_name: 'AI 脱敏引擎 Pro',
      brand_id: DEMO_BRAND_ID, sku: 'BC-DM-PRO', category: '核心产品',
      mention_count: 412, mention_rate: 0.34, avg_position_rank: 2.1,
      avg_geo_score: 71.5, avg_sentiment: 0.66, sov: 0.24, ranking: 1,
      win_rate: 0.58, trend_30d: 9.2, sparkline: walk(68, 5, 30, 51),
      top_features: [
        { feature_name: '准确率 99.2%', feature_sentiment: 'positive', mention_count: 134, avg_score: 0.74 },
        { feature_name: '行业模板丰富', feature_sentiment: 'positive', mention_count: 98, avg_score: 0.69 },
        { feature_name: '部署速度快',   feature_sentiment: 'positive', mention_count: 73, avg_score: 0.61 },
      ],
      top_scenarios: [
        { scenario: '金融 KYC 合规', mention_count: 142 },
        { scenario: '跨境数据出境', mention_count: 96 },
        { scenario: '医疗病历脱敏', mention_count: 71 },
      ],
    },
    {
      product_id: 5002, product_name: 'VDR 协作工作台',
      brand_id: DEMO_BRAND_ID, sku: 'BC-VDR-STD', category: '核心产品',
      mention_count: 287, mention_rate: 0.24, avg_position_rank: 3.4,
      avg_geo_score: 65.8, avg_sentiment: 0.59, sov: 0.18, ranking: 2,
      win_rate: 0.47, trend_30d: 4.6, sparkline: walk(62, 4, 30, 53),
      top_features: [
        { feature_name: '权限分层细', feature_sentiment: 'positive', mention_count: 89, avg_score: 0.63 },
        { feature_name: '审阅协同顺畅', feature_sentiment: 'positive', mention_count: 71, avg_score: 0.58 },
        { feature_name: '价格偏高',   feature_sentiment: 'negative', mention_count: 28, avg_score: -0.32 },
      ],
      top_scenarios: [
        { scenario: '并购尽调',     mention_count: 118 },
        { scenario: 'IPO 文档协作', mention_count: 84 },
      ],
    },
    {
      product_id: 5003, product_name: '合规模板库',
      brand_id: DEMO_BRAND_ID, sku: 'BC-CT-ENT', category: '增值模块',
      mention_count: 198, mention_rate: 0.17, avg_position_rank: 2.8,
      avg_geo_score: 62.4, avg_sentiment: 0.64, sov: 0.13, ranking: 3,
      win_rate: 0.51, trend_30d: 12.1, sparkline: walk(58, 5, 30, 57),
      top_features: [
        { feature_name: '行业覆盖广', feature_sentiment: 'positive', mention_count: 64, avg_score: 0.61 },
        { feature_name: '更新及时',   feature_sentiment: 'positive', mention_count: 53, avg_score: 0.57 },
      ],
      top_scenarios: [
        { scenario: '金融合规自查', mention_count: 74 },
        { scenario: '行业准入审计', mention_count: 52 },
      ],
    },
    {
      product_id: 5004, product_name: 'API 接入 SDK',
      brand_id: DEMO_BRAND_ID, sku: 'BC-API-DEV', category: '集成工具',
      mention_count: 156, mention_rate: 0.13, avg_position_rank: 4.1,
      avg_geo_score: 58.7, avg_sentiment: 0.53, sov: 0.09, ranking: 4,
      win_rate: 0.42, trend_30d: -2.3, sparkline: walk(60, 3, 30, 59),
      top_features: [
        { feature_name: '文档清晰', feature_sentiment: 'positive', mention_count: 48, avg_score: 0.55 },
        { feature_name: '调用速率限制偏严', feature_sentiment: 'negative', mention_count: 31, avg_score: -0.41 },
      ],
      top_scenarios: [
        { scenario: '企业系统对接', mention_count: 67 },
      ],
    },
    {
      product_id: 5005, product_name: '审计报表服务',
      brand_id: DEMO_BRAND_ID, sku: 'BC-AR-MGR', category: '增值模块',
      mention_count: 112, mention_rate: 0.09, avg_position_rank: 5.2,
      avg_geo_score: 54.1, avg_sentiment: 0.56, sov: 0.06, ranking: 5,
      win_rate: 0.39, trend_30d: 3.4, sparkline: walk(52, 3, 30, 61),
      top_features: [
        { feature_name: '可视化好',     feature_sentiment: 'positive', mention_count: 39, avg_score: 0.52 },
        { feature_name: '导出格式丰富', feature_sentiment: 'positive', mention_count: 28, avg_score: 0.48 },
      ],
      top_scenarios: [
        { scenario: '合规季度复盘', mention_count: 41 },
      ],
    },
    {
      product_id: 5006, product_name: '移动审阅 App',
      brand_id: DEMO_BRAND_ID, sku: 'BC-MOB-V2', category: '集成工具',
      mention_count: 78, mention_rate: 0.06, avg_position_rank: 6.3,
      avg_geo_score: 48.6, avg_sentiment: 0.48, sov: 0.04, ranking: 6,
      win_rate: 0.33, trend_30d: 15.8, sparkline: walk(44, 5, 30, 67),
      top_features: [
        { feature_name: '随时随地审阅', feature_sentiment: 'positive', mention_count: 32, avg_score: 0.51 },
        { feature_name: 'iPad 体验好',  feature_sentiment: 'positive', mention_count: 21, avg_score: 0.46 },
      ],
      top_scenarios: [
        { scenario: '出差审批', mention_count: 28 },
      ],
    },
  ],
  total: 6,
  state: 'ok',
}

// 诊断 — full list (10 items covering P0/P1/P2 across categories)
function diag(
  i: number,
  severity: 'P0' | 'P1' | 'P2' | 'P3',
  category: string,
  title: string,
  description: string,
  evidence: Record<string, unknown> = {},
  ruleId = 'demo_v1',
): DiagnosticOut {
  return {
    id: `diag-bc-${String(i).padStart(3, '0')}`,
    project_id: DEMO_PROJECT_ID,
    brand_id: DEMO_BRAND_ID,
    product_id: null,
    industry_id: null,
    category,
    severity,
    type: 'brand',
    title,
    description,
    focus_area: '品牌曝光',
    direction: severity === 'P0' || severity === 'P1' ? 'down' : 'flat',
    reader_hints: ['operator', 'manager'],
    evidence,
    causal_chain: null,
    industry_benchmark: null,
    anchor_questions: null,
    if_untreated: null,
    rule_id: ruleId,
    rule_version: '1.0',
    status: 'open',
    detected_at: '2026-05-17T08:00:00Z',
    acknowledged_at: null,
    resolved_at: null,
  }
}

const DIAGNOSTIC_ITEMS: DiagnosticOut[] = [
  diag(1, 'P0', 'visibility_decline',
    'BestCoffer 在 ChatGPT「金融脱敏」主题 SoV 下滑 14%',
    '过去 7 天 SoV 从 0.21 跌至 0.18，主要被 Securiti.ai 抢占。',
    { engine: 'ChatGPT', topic_id: 153, sov_before: 0.21, sov_after: 0.18, delta_pct: -14 },
    'sov_drop_v1'),
  diag(2, 'P1', 'competitor_overtake',
    'Securiti.ai 在「跨境数据出境合规」主题完成反超',
    'Securiti.ai SoV 0.27，BestCoffer SoV 0.18，差距扩大至 9pt。',
    { engine: 'Doubao', topic_id: 158, competitor_brand_id: 9101, gap_pt: 9 },
    'competitor_overtake_v1'),
  diag(3, 'P1', 'topic_emerging_missed',
    '「AI 自动合规审计」新兴主题 BestCoffer 0 提及',
    '过去 14 天该主题竞品累计 76 次提及，BestCoffer 未被命中。',
    { topic_id: 174, competitor_mentions: 76, our_mentions: 0 },
    'topic_emerging_missed_v1'),
  diag(4, 'P1', 'sentiment_drop',
    '"价格偏高" 负面驱动词在 VDR 协作产品上升',
    '近 30 天负面提及 +43%，集中于中小企业客户语境。',
    { product_id: 5002, driver: '价格偏高', delta_pct: 43 },
    'sentiment_drop_v1'),
  diag(5, 'P2', 'citation_gap',
    '权威媒体 36kr.com 引用率低于行业中位',
    '行业 Top10 平均 8.2%，BestCoffer 当前 2.1%。',
    { domain: '36kr.com', our_rate: 0.021, industry_median: 0.082 },
    'citation_gap_v1'),
  diag(6, 'P2', 'engine_coverage_gap',
    'Doubao 引擎覆盖率显著低于 ChatGPT',
    'BestCoffer 在 Doubao 上 mention_rate 0.08，远低于 ChatGPT 0.29。',
    { engines: { ChatGPT: 0.29, Doubao: 0.08, DeepSeek: 0.22 } },
    'engine_coverage_gap_v1'),
  diag(7, 'P2', 'topic_drift',
    '主题「医疗病历脱敏」位次连续 3 周下降',
    '从第 2 位下滑至第 6 位，被 OneTrust + 数据安信 联合挤压。',
    { topic_id: 173, rank_before: 2, rank_after: 6, weeks: 3 },
    'topic_drift_v1'),
  diag(8, 'P2', 'feature_negative',
    '「API 调用速率限制」负面提及集中',
    '近 14 天负面驱动词 31 次，CIO 角色权重高。',
    { product_id: 5004, feature: 'API 调用速率限制', count: 31 },
    'feature_negative_v1'),
  diag(9, 'P2', 'product_attention',
    '「移动审阅 App」提及量增速领先（+15.8%）',
    '需评估增量投放价值，目前 SoV 仍仅 0.04。',
    { product_id: 5006, growth_pct: 15.8, sov: 0.04 },
    'product_attention_v1'),
  diag(10, 'P2', 'competitor_radical_growth',
    'SafeRoom Cloud 30 天 SoV +11.7%',
    '从 0.10 上升至 0.14，主要靠尽调场景突破。',
    { competitor_brand_id: 9104, sov_growth_pct: 11.7 },
    'competitor_radical_growth_v1'),
]

export const DIAGNOSTICS_FULL: DiagnosticListOut = {
  items: DIAGNOSTIC_ITEMS,
  total: DIAGNOSTIC_ITEMS.length,
}

// 告警条 — Top 3 P0/P1 (server filters via query params; we filter client-side)
export function buildDiagnosticsResponse(
  severityFilter: string | null,
  limit: number | null,
): DiagnosticListOut {
  let filtered = DIAGNOSTIC_ITEMS
  if (severityFilter) {
    const allowed = new Set(severityFilter.split(',').map((s) => s.trim()))
    filtered = filtered.filter((d) => allowed.has(d.severity))
  }
  if (limit && limit > 0) filtered = filtered.slice(0, limit)
  return { items: filtered, total: filtered.length }
}

// 报告 — 4 entries (weekly / monthly / competitor deep-dive / custom)
export const REPORTS: ReportListOut = {
  items: [
    {
      id: 'rpt-bc-001',
      project_id: DEMO_PROJECT_ID,
      type: 'weekly',
      status: 'finished',
      created_at: '2026-05-17T02:00:00Z',
      finished_at: '2026-05-17T02:08:33Z',
      output_url: '/api/v1/projects/demo/reports/rpt-bc-001/download?format=markdown',
      error: null,
    },
    {
      id: 'rpt-bc-002',
      project_id: DEMO_PROJECT_ID,
      type: 'monthly',
      status: 'finished',
      created_at: '2026-05-01T02:00:00Z',
      finished_at: '2026-05-01T02:13:11Z',
      output_url: '/api/v1/projects/demo/reports/rpt-bc-002/download?format=markdown',
      error: null,
    },
    {
      id: 'rpt-bc-003',
      project_id: DEMO_PROJECT_ID,
      type: 'on_demand',
      status: 'finished',
      created_at: '2026-05-12T09:14:00Z',
      finished_at: '2026-05-12T09:21:42Z',
      output_url: '/api/v1/projects/demo/reports/rpt-bc-003/download?format=markdown',
      error: null,
    },
    {
      id: 'rpt-bc-004',
      project_id: DEMO_PROJECT_ID,
      type: 'lead_diagnostic',
      status: 'finished',
      created_at: '2026-05-15T16:30:00Z',
      finished_at: '2026-05-15T16:38:09Z',
      output_url: '/api/v1/projects/demo/reports/rpt-bc-004/download?format=markdown',
      error: null,
    },
  ],
  total: 4,
}

export const _COMPETITORS_META = COMPETITORS
