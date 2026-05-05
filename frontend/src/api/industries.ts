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

export const industriesApi = {
  list(): Promise<IndustriesListOut> {
    return apiClient.get<IndustriesListOut>('/v1/industries/')
  },
  topBrands(industryId: number, n = 3): Promise<TopBrandRow[]> {
    return apiClient.get<TopBrandRow[]>(
      `/v1/industries/${industryId}/top-brands?n=${n}`,
    )
  },
}
