export interface BrandAnalysisFiltersLike {
  from?: string
  to?: string
  engines?: string[]
  profileGroup?: string
  dimensions?: string[]
  intents?: string[]
  promptScope?: string
}

export interface ProjectAnalysisParams {
  from?: string
  to?: string
  engine?: string
  segment_id?: string
  profile_id?: string
  dimension?: string
  intent?: string
  prompt_scope?: string
  brand_id?: number
}

export function brandIdFromSearchParams(searchParams: URLSearchParams): number | null {
  const raw = searchParams.get('brandId')
  if (!raw || !/^\d+$/.test(raw)) return null
  const brandId = Number(raw)
  return Number.isSafeInteger(brandId) ? brandId : null
}

export function withBrandIdOverride(
  params: ProjectAnalysisParams,
  brandIdOverride?: number | null,
): ProjectAnalysisParams {
  if (brandIdOverride == null) return params
  return { ...params, brand_id: brandIdOverride }
}

export function toProjectAnalysisParams(
  filters?: BrandAnalysisFiltersLike | null,
  brandIdOverride?: number | null,
): ProjectAnalysisParams {
  const params: ProjectAnalysisParams = {}
  if (!filters) return withBrandIdOverride(params, brandIdOverride)
  if (filters.from) params.from = filters.from
  if (filters.to) params.to = filters.to
  if (filters.engines?.length) params.engine = filters.engines.join(',')
  if (filters.dimensions?.length) params.dimension = filters.dimensions.join(',')
  if (filters.intents?.length) params.intent = filters.intents.join(',')
  if (filters.promptScope) params.prompt_scope = filters.promptScope

  const audience = filters.profileGroup
  if (audience && audience !== 'all') {
    if (audience.startsWith('profile:')) {
      params.profile_id = audience.slice('profile:'.length)
    } else {
      params.segment_id = audience
    }
  }
  return withBrandIdOverride(params, brandIdOverride)
}

export function buildQuery(params: Record<string, unknown> = {}): string {
  const sp = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value == null || value === '') return
    sp.set(key, String(value))
  })
  const qs = sp.toString()
  return qs ? `?${qs}` : ''
}
