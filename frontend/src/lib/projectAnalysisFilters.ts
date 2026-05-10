export interface BrandAnalysisFiltersLike {
  from?: string
  to?: string
  engines?: string[]
  profileGroup?: string
}

export interface ProjectAnalysisParams {
  from?: string
  to?: string
  engine?: string
  segment_id?: string
  profile_id?: string
}

export function toProjectAnalysisParams(
  filters?: BrandAnalysisFiltersLike | null,
): ProjectAnalysisParams {
  const params: ProjectAnalysisParams = {}
  if (!filters) return params
  if (filters.from) params.from = filters.from
  if (filters.to) params.to = filters.to
  if (filters.engines?.length) params.engine = filters.engines.join(',')

  const audience = filters.profileGroup
  if (audience && audience !== 'all') {
    if (audience.startsWith('profile:')) {
      params.profile_id = audience.slice('profile:'.length)
    } else {
      params.segment_id = audience
    }
  }
  return params
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
