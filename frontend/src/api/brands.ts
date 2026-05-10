/**
 * Brands API wrappers — currently only the search endpoint used by the
 * onboarding flow. Extended endpoints (catalog, detail, ...) live elsewhere.
 */

import { apiClient } from '../lib/apiClient'

export interface BrandSearchHit {
  brandId: number
  brandName: string
  industry: string | null
  isAlreadyMonitoring: boolean
}

export interface BrandSearchResponse {
  items: BrandSearchHit[]
}

export const brandsApi = {
  search(q: string, limit = 10): Promise<BrandSearchResponse> {
    const params = new URLSearchParams({ q, limit: String(limit) })
    return apiClient.get<BrandSearchResponse>(`/v1/brands/search?${params.toString()}`)
  },
}
