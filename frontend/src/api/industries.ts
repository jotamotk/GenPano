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
}

export interface IndustryRankingOut {
  industry_id: number
  period: { from: string; to: string }
  items: IndustryRankingRow[]
  total: number
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
    params: { name?: string; offset?: number; limit?: number } = {},
  ): Promise<IndustryRankingOut> {
    return apiClient.get<IndustryRankingOut>(
      `/v1/industries/${industryId}/ranking${buildQuery(params)}`,
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
}

function buildQuery(params: Record<string, unknown>): string {
  const q = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
    .join('&')
  return q ? `?${q}` : ''
}
