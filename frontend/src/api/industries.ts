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
    const query = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== null && v !== '')
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join('&')
    return apiClient.get<IndustryOverviewOut>(
      `/v1/industries/${industryId}/overview${query ? '?' + query : ''}`,
    )
  },
}
