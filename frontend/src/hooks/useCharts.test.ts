import { describe, expect, it, vi } from 'vitest'
import { useQuery } from '@tanstack/react-query'

import { projectChartsApi } from '../api/charts'
import { useEngineMetrics } from './useCharts'

vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn((options) => options),
}))

vi.mock('../api/charts', () => ({
  projectChartsApi: {
    engineMetrics: vi.fn(async () => ({ state: 'ok', items: [] })),
  },
}))

vi.mock('./useBrandOverview', () => ({
  isLiveProjectId: () => true,
}))

describe('useEngineMetrics', () => {
  it('keeps date, engine, and brand filters in both the query key and request params', async () => {
    const filters = {
      from: '2026-05-01',
      to: '2026-05-12',
      engine: 'chatgpt,deepseek',
      brand_id: 42,
    }

    const query = useEngineMetrics('11111111-2222-3333-4444-555555555555', filters) as any

    expect(useQuery).toHaveBeenCalledWith(
      expect.objectContaining({
        queryKey: [
          'charts',
          'engine-metrics',
          '11111111-2222-3333-4444-555555555555',
          '2026-05-01|2026-05-12|chatgpt,deepseek||||||42',
        ],
      }),
    )

    await query.queryFn()

    expect(projectChartsApi.engineMetrics).toHaveBeenCalledWith(
      '11111111-2222-3333-4444-555555555555',
      filters,
    )
  })
})
