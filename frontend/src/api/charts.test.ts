import { describe, expect, it, vi } from 'vitest'

import { apiClient } from '../lib/apiClient'
import { projectChartsApi } from './charts'

vi.mock('../lib/apiClient', () => ({
  apiClient: {
    get: vi.fn(async () => ({ state: 'ok', items: [] })),
  },
}))

describe('projectChartsApi.engineMetrics', () => {
  it('sends date, engine, and brand filters to the by-engine endpoint', async () => {
    await projectChartsApi.engineMetrics('project-1154', {
      from: '2026-05-01',
      to: '2026-05-12',
      engine: 'chatgpt,deepseek',
      brand_id: 42,
    })

    const [path] = vi.mocked(apiClient.get).mock.calls[0]
    const url = new URL(`https://genpano.test${path}`)

    expect(url.pathname).toBe('/v1/projects/project-1154/metrics/by-engine')
    expect(url.searchParams.get('from')).toBe('2026-05-01')
    expect(url.searchParams.get('to')).toBe('2026-05-12')
    expect(url.searchParams.get('engine')).toBe('chatgpt,deepseek')
    expect(url.searchParams.get('brand_id')).toBe('42')
  })
})
