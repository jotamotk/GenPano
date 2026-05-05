/**
 * Unit tests for the simulator API contract.
 * Verifies the wrapper builds the correct URL + body shape and that
 * the response shape parses correctly.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

import type { SimulatorOut } from './simulator'

vi.mock('../lib/apiClient', () => ({
  apiClient: {
    post: vi.fn(),
  },
}))

import { apiClient } from '../lib/apiClient'
import { simulatorApi } from './simulator'

const mockedPost = apiClient.post as unknown as ReturnType<typeof vi.fn>

beforeEach(() => {
  mockedPost.mockReset()
})

describe('simulatorApi.run', () => {
  it('POSTs to /v1/projects/:id/simulator/run with payload', async () => {
    const fakeResp: SimulatorOut = {
      current_pano_a: 70,
      simulated_pano_a: 78,
      delta: 8,
      delta_breakdown: {
        visibility: 2,
        sov: 1.5,
        sentiment: 1,
        citation_authority: 3.5,
      },
      base_price_equivalent_cny: 50000,
      confidence: 0.85,
    }
    mockedPost.mockResolvedValueOnce(fakeResp)

    const result = await simulatorApi.run('proj-uuid-1', {
      brand_id: 1001,
      delta_by_tier: { '1': 5, '2': 3 },
    })

    expect(mockedPost).toHaveBeenCalledTimes(1)
    expect(mockedPost.mock.calls[0][0]).toBe(
      '/v1/projects/proj-uuid-1/simulator/run',
    )
    expect(mockedPost.mock.calls[0][1]).toEqual({
      brand_id: 1001,
      delta_by_tier: { '1': 5, '2': 3 },
    })
    expect(result).toEqual(fakeResp)
  })

  it('passes confidence_override when provided', async () => {
    mockedPost.mockResolvedValueOnce({
      current_pano_a: 0,
      simulated_pano_a: 0,
      delta: 0,
      delta_breakdown: {
        visibility: 0,
        sov: 0,
        sentiment: 0,
        citation_authority: 0,
      },
      base_price_equivalent_cny: 0,
      confidence: 0.5,
    })

    await simulatorApi.run('proj-uuid-2', {
      brand_id: 42,
      delta_by_tier: {},
      confidence_override: 0.5,
    })

    expect(mockedPost.mock.calls[0][1]).toMatchObject({
      confidence_override: 0.5,
    })
  })
})
