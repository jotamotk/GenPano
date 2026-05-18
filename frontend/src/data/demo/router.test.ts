import { describe, expect, test } from 'vitest'

import { tryMockResponse } from './router'
import type { CompetitorMetricsOut, CompetitorTrendsOut, ProductsOut } from '../../api/brandMetrics'
import type { DiagnosticListOut } from '../../api/diagnostics'
import type { IndustryRankingOut } from '../../api/industries'
import type { ReportListOut } from '../../api/reports'
import { DEMO_BRAND_ID, DEMO_PROJECT_ID } from '../../lib/demoMode'

const PID = '7380c0e0-8798-4a5f-998f-42010a7d9caa'

describe('demo router — tryMockResponse', () => {
  test('returns null for non-GET methods', () => {
    expect(tryMockResponse(`/v1/projects/${PID}/products`, 'POST')).toBeNull()
    expect(tryMockResponse(`/v1/projects/${PID}/products`, 'PATCH')).toBeNull()
  })

  test('returns null for unknown paths', () => {
    expect(tryMockResponse(`/v1/projects/${PID}/metrics`, 'GET')).toBeNull()
    expect(tryMockResponse('/v1/health', 'GET')).toBeNull()
  })

  test('industry ranking — preserves industry_id from path', () => {
    const out = tryMockResponse<IndustryRankingOut>('/v1/industries/42/ranking', 'GET')
    expect(out).not.toBeNull()
    expect(out!.industry_id).toBe(42)
    expect(out!.items.length).toBeGreaterThan(0)
    expect(out!.items.some((r) => r.brand_id === DEMO_BRAND_ID)).toBe(true)
  })

  test('competitors/metrics — bestcoffer primary + competitors', () => {
    const out = tryMockResponse<CompetitorMetricsOut>(
      `/v1/projects/${PID}/competitors/metrics`,
      'GET',
    )
    expect(out).not.toBeNull()
    expect(out!.primary?.brand_id).toBe(DEMO_BRAND_ID)
    expect(out!.competitors.length).toBeGreaterThanOrEqual(3)
  })

  test('competitors/trends — metric param reflected, 4 series', () => {
    const out = tryMockResponse<CompetitorTrendsOut>(
      `/v1/projects/${PID}/competitors/trends?metric=geo_score`,
      'GET',
    )
    expect(out).not.toBeNull()
    expect(out!.metric).toBe('geo_score')
    expect(out!.series.length).toBe(4)
    expect(out!.series.find((s) => s.is_primary)?.brand_id).toBe(DEMO_BRAND_ID)
    expect(out!.series[0].points.length).toBe(30)
  })

  test('products — 6 SKU rows', () => {
    const out = tryMockResponse<ProductsOut>(`/v1/projects/${PID}/products`, 'GET')
    expect(out).not.toBeNull()
    expect(out!.items.length).toBe(6)
    expect(out!.items[0].brand_id).toBe(DEMO_BRAND_ID)
  })

  test('diagnostics — full list when no filters', () => {
    const out = tryMockResponse<DiagnosticListOut>(
      `/v1/projects/${PID}/diagnostics/`,
      'GET',
    )
    expect(out).not.toBeNull()
    expect(out!.items.length).toBe(10)
  })

  test('diagnostics — severity filter narrows to P0/P1', () => {
    const out = tryMockResponse<DiagnosticListOut>(
      `/v1/projects/${PID}/diagnostics/?status=open&severity=P0,P1&limit=3`,
      'GET',
    )
    expect(out).not.toBeNull()
    expect(out!.items.length).toBe(3)
    out!.items.forEach((d) => expect(['P0', 'P1']).toContain(d.severity))
  })

  test('reports — 4 entries', () => {
    const out = tryMockResponse<ReportListOut>(`/v1/projects/${PID}/reports?limit=50`, 'GET')
    expect(out).not.toBeNull()
    expect(out!.total).toBe(4)
    expect(out!.items[0].project_id).toBe(DEMO_PROJECT_ID)
  })

  test('returned object is a deep copy — mutations do not pollute', () => {
    const first = tryMockResponse<ProductsOut>(`/v1/projects/${PID}/products`, 'GET')!
    first.items[0].product_name = '__mutated__'
    const second = tryMockResponse<ProductsOut>(`/v1/projects/${PID}/products`, 'GET')!
    expect(second.items[0].product_name).not.toBe('__mutated__')
  })
})
