import { describe, expect, it } from 'vitest'

import {
  brandIdFromSearchParams,
  toProjectAnalysisParams,
  withBrandIdOverride,
} from './projectAnalysisFilters'

describe('project analysis filter brand overrides', () => {
  it('reads numeric brandId from the URL without accepting invalid values', () => {
    expect(brandIdFromSearchParams(new URLSearchParams('brandId=24'))).toBe(24)
    expect(brandIdFromSearchParams(new URLSearchParams('brandId=bestcoffer'))).toBeNull()
    expect(brandIdFromSearchParams(new URLSearchParams(''))).toBeNull()
  })

  it('adds brand_id to backend analysis params only when a URL override exists', () => {
    expect(toProjectAnalysisParams({ from: '2026-05-01', to: '2026-05-12' }, 24)).toEqual({
      from: '2026-05-01',
      to: '2026-05-12',
      brand_id: 24,
    })
    expect(withBrandIdOverride({ engine: 'deepseek' }, null)).toEqual({ engine: 'deepseek' })
    expect(withBrandIdOverride({ engine: 'deepseek' }, 24)).toEqual({
      engine: 'deepseek',
      brand_id: 24,
    })
  })
})
