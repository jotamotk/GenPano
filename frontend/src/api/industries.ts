/**
 * Industries API wrappers.
 *
 * Backend endpoints (Phase 3):
 *   GET /api/v1/industries/                    -> list of industries
 *   GET /api/v1/industries/:id/top-brands?n=N  -> top N brands by 30d GEO score
 *   GET /api/v1/industries/:id/overview        -> KPI snapshot
 *   GET /api/v1/industries/:id/ranking         -> brand ranking
 *   GET /api/v1/industries/:id/topics          -> top topics
 *   GET /api/v1/industries/:id/kg              -> knowledge graph nodes/edges
 */

import { apiClient } from '../lib/apiClient'

export interface IndustryRow {
  industry_id: number
  name: string
  brand_count: number
}

export interface IndustriesListOut {
  items: IndustryRow[]
  total: number
}

export interface TopBrandRow {
  brand_id: number
  brand_name: string | null
  avg_geo_score: number | null
  rank: number
}

export interface IndustryKpiCard {
  label_zh: string
  label_en: string
  value: number
  unit: string | null
  delta_30d_pct: number | null
}

export interface IndustryEvent {
  date: string
  event_type: string
  description: string
  brand_id: number | null
}

export interface IndustryOverviewOut {
  industry_id: number
  industry_name: string | null
  period: { from: string; to: string }
  kpi_cards: IndustryKpiCard[]
  top_brands: TopBrandRow[]
  events_30d: IndustryEvent[]
  hero_counts?: IndustryHeroCounts | null
  state: 'ok' | 'empty' | 'partial'
}

export interface IndustryRankingRow {
  rank: number
  brand_id: number
  brand_name: string | null
  avg_geo_score: number | null
  avg_mention_rate: number | null
  avg_sov: number | null
  avg_sentiment: number | null
  avg_citation_rate?: number | null
  sparkline?: number[]
}

export interface IndustryRankingOut {
  industry_id: number
  period: { from: string; to: string }
  items: IndustryRankingRow[]
  total: number
  my_rank?: number | null
  state: 'ok' | 'empty' | 'partial'
}

export interface IndustryTopicRow {
  topic_id: number | null
  topic_name: string
  mention_count: number
  unique_brand_count: number
  hot_score: number | null
}

export interface IndustryTopicsOut {
  industry_id: number
  period: { from: string; to: string }
  items: IndustryTopicRow[]
  total: number
  state: 'ok' | 'empty' | 'partial'
}

export interface KGNode {
  id: string
  type: string
  name: string
  metadata: Record<string, unknown> | null
}

export interface KGEdge {
  source: string
  target: string
  type: string
  weight: number | null
}

export interface IndustryKgOut {
  industry_id: number
  focus: string
  depth: number
  nodes: KGNode[]
  edges: KGEdge[]
  state: 'ok' | 'empty' | 'partial'
}

export interface IndustryAvgGeoPoint {
  date: string
  avg_geo_score: number | null
  industry_median: number | null
  top10_avg: number | null
  total_brands: number | null
}

export interface IndustryAvgGeoOut {
  industry_id: number
  industry_name: string | null
  period: { from: string; to: string }
  points: IndustryAvgGeoPoint[]
  summary: Record<string, number | null>
  state: 'ok' | 'empty' | 'partial'
}

export interface IndustryHeroCounts {
  brand_count: number
  topic_count: number
  category_count: number
  response_count: number
}

export interface IndustryDistributionStats {
  metric: 'mention_rate' | 'sov' | 'sentiment' | 'citation' | 'rank'
  values: number[]
  p25: number | null
  p50: number | null
  p75: number | null
  min: number | null
  max: number | null
  n: number
}

export interface IndustryDistributionOut {
  industry_id: number
  industry_name: string | null
  period: { from: string; to: string }
  stats: IndustryDistributionStats[]
  state: 'ok' | 'empty' | 'partial'
}

export interface IndustryMoverRow {
  brand_id: number
  brand_name: string | null
  delta_pct: number
  current_pano: number | null
  sparkline: number[]
  driver: string | null
}

export interface IndustryMoversOut {
  industry_id: number
  period: { from: string; to: string }
  gainers: IndustryMoverRow[]
  losers: IndustryMoverRow[]
  state: 'ok' | 'empty' | 'partial'
}

export interface IndustryGroupRow {
  group_id: number
  group_name: string
  parent_company: string | null
  member_brand_ids: number[]
  member_brand_names: string[]
  aggregate_geo_score: number | null
  aggregate_sov: number | null
}

export interface IndustryGroupsOut {
  industry_id: number
  items: IndustryGroupRow[]
  state: 'ok' | 'empty' | 'partial'
}

export interface IndustryTopDomainRow {
  domain: string
  tier: number | null
  total_citations: number
  top_brand_id: number | null
  top_brand_name: string | null
  top_brand_share: number | null
}

export interface IndustryTopDomainsOut {
  industry_id: number
  period: { from: string; to: string }
  items: IndustryTopDomainRow[]
  state: 'ok' | 'empty' | 'partial'
}

export interface IndustrySegmentRow {
  segment: string
  label_zh: string
  items: IndustryRankingRow[]
}

export interface IndustrySegmentsOut {
  industry_id: number
  items: IndustrySegmentRow[]
  state: 'ok' | 'empty' | 'partial'
}

export interface IndustryRankingByEngineCell {
  engine: string
  rank: number | null
  avg_geo_score: number | null
}

export interface IndustryRankingByEngineRow {
  brand_id: number
  brand_name: string | null
  overall_rank: number
  cells: IndustryRankingByEngineCell[]
  delta_max: number | null
}

export interface IndustryRankingByEngineOut {
  industry_id: number
  period: { from: string; to: string }
  engines: string[]
  items: IndustryRankingByEngineRow[]
  state: 'ok' | 'empty' | 'partial'
}

export interface TopicIntentCell {
  intent: string
  count: number
  pct: number
}

export interface TopicIntentRow {
  topic_id: number
  topic_name: string
  total_count: number
  cells: TopicIntentCell[]
}

export interface TopicIntentMatrixOut {
  industry_id: number
  intents: string[]
  rows: TopicIntentRow[]
  state: 'ok' | 'empty' | 'partial'
}

export interface IndustryTopicDetailOut {
  industry_id: number
  topic_id: number
  topic_name: string
  mention_count: number
  unique_brand_count: number
  avg_sentiment: number | null
  top_brands: TopBrandRow[]
  sparkline: number[]
  intents: TopicIntentCell[]
  state: 'ok' | 'empty' | 'partial'
}

export const industriesApi = {
  list(): Promise<IndustriesListOut> {
    return apiClient.get<IndustriesListOut>('/v1/industries/')
  },
  topBrands(industryId: number, n = 3): Promise<TopBrandRow[]> {
    return apiClient.get<TopBrandRow[]>(
      `/v1/industries/${industryId}/top-brands?n=${n}`,
    )
  },
  overview(
    industryId: number,
    params: { name?: string; from?: string; to?: string } = {},
  ): Promise<IndustryOverviewOut> {
    return apiClient.get<IndustryOverviewOut>(
      `/v1/industries/${industryId}/overview${buildQuery(params)}`,
    )
  },
  ranking(
    industryId: number,
    params: {
      name?: string
      offset?: number
      limit?: number
      primary_brand_id?: number
    } = {},
  ): Promise<IndustryRankingOut> {
    return apiClient.get<IndustryRankingOut>(
      `/v1/industries/${industryId}/ranking${buildQuery(params)}`,
    )
  },
  distribution(
    industryId: number,
    params: { name?: string } = {},
  ): Promise<IndustryDistributionOut> {
    return apiClient.get<IndustryDistributionOut>(
      `/v1/industries/${industryId}/distribution${buildQuery(params)}`,
    )
  },
  movers(
    industryId: number,
    params: { name?: string; limit?: number } = {},
  ): Promise<IndustryMoversOut> {
    return apiClient.get<IndustryMoversOut>(
      `/v1/industries/${industryId}/movers${buildQuery(params)}`,
    )
  },
  groups(
    industryId: number,
    params: { name?: string; limit?: number } = {},
  ): Promise<IndustryGroupsOut> {
    return apiClient.get<IndustryGroupsOut>(
      `/v1/industries/${industryId}/groups${buildQuery(params)}`,
    )
  },
  topDomains(
    industryId: number,
    params: { name?: string; limit?: number } = {},
  ): Promise<IndustryTopDomainsOut> {
    return apiClient.get<IndustryTopDomainsOut>(
      `/v1/industries/${industryId}/top-domains${buildQuery(params)}`,
    )
  },
  segments(
    industryId: number,
    params: { name?: string; limit?: number } = {},
  ): Promise<IndustrySegmentsOut> {
    return apiClient.get<IndustrySegmentsOut>(
      `/v1/industries/${industryId}/segments${buildQuery(params)}`,
    )
  },
  rankingByEngine(
    industryId: number,
    params: { name?: string; limit?: number } = {},
  ): Promise<IndustryRankingByEngineOut> {
    return apiClient.get<IndustryRankingByEngineOut>(
      `/v1/industries/${industryId}/ranking-by-engine${buildQuery(params)}`,
    )
  },
  topicIntentMatrix(
    industryId: number,
    params: { name?: string; limit?: number } = {},
  ): Promise<TopicIntentMatrixOut> {
    return apiClient.get<TopicIntentMatrixOut>(
      `/v1/industries/${industryId}/topic-intent-matrix${buildQuery(params)}`,
    )
  },
  topicDetail(
    industryId: number,
    topicId: number,
    params: { name?: string } = {},
  ): Promise<IndustryTopicDetailOut> {
    return apiClient.get<IndustryTopicDetailOut>(
      `/v1/industries/${industryId}/topics/${topicId}${buildQuery(params)}`,
    )
  },
  topics(
    industryId: number,
    params: { name?: string; limit?: number } = {},
  ): Promise<IndustryTopicsOut> {
    return apiClient.get<IndustryTopicsOut>(
      `/v1/industries/${industryId}/topics${buildQuery(params)}`,
    )
  },
  kg(
    industryId: number,
    params: { name?: string; focus?: string; depth?: number } = {},
  ): Promise<IndustryKgOut> {
    return apiClient.get<IndustryKgOut>(
      `/v1/industries/${industryId}/kg${buildQuery(params)}`,
    )
  },
  avgGeoScore(
    industryId: number,
    params: { name?: string; from?: string; to?: string } = {},
  ): Promise<IndustryAvgGeoOut> {
    return apiClient.get<IndustryAvgGeoOut>(
      `/v1/industries/${industryId}/avg-geo-score${buildQuery(params)}`,
    )
  },
}

function buildQuery(params: Record<string, unknown>): string {
  const q = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join('&')
  return q ? `?${q}` : ''
}
