/**
 * Unit tests for brands.search — verifies URL shape + response passthrough.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

import type { BrandSearchResponse } from './brands'

vi.mock('../lib/apiClient', () => ({
  apiClient: {
    get: vi.fn(),
  },
}))

import { apiClient } from '../lib/apiClient'
import { brandsApi } from './brands'

const mockedGet = apiClient.get as unknown as ReturnType<typeof vi.fn>

beforeEach(() => {
  mockedGet.mockReset()
})

describe('brandsApi.search', () => {
  const fakeResp: BrandSearchResponse = {
    items: [
      { brandId: 1, brandName: 'Nike', industry: 'Sports', isAlreadyMonitoring: false },
    ],
  }

  it('builds the GET URL with q + default limit=10', async () => {
    mockedGet.mockResolvedValueOnce(fakeResp)
    const out = await brandsApi.search('Nike')
    expect(mockedGet).toHaveBeenCalledWith('/v1/brands/search?q=Nike&limit=10')
    expect(out).toEqual(fakeResp)
  })

  it('honours custom limit', async () => {
    mockedGet.mockResolvedValueOnce(fakeResp)
    await brandsApi.search('Nike', 25)
    expect(mockedGet).toHaveBeenCalledWith('/v1/brands/search?q=Nike&limit=25')
  })

  it('URL-encodes special characters in q', async () => {
    mockedGet.mockResolvedValueOnce(fakeResp)
    await brandsApi.search('Nike & Co')
    expect(mockedGet).toHaveBeenCalledWith(
      '/v1/brands/search?q=Nike+%26+Co&limit=10',
    )
  })

  it('passes through Chinese query unchanged in semantic content', async () => {
    mockedGet.mockResolvedValueOnce(fakeResp)
    await brandsApi.search('耐克')
    const calledWith = mockedGet.mock.calls[0][0] as string
    // URLSearchParams encodes UTF-8; verify it round-trips.
    expect(decodeURIComponent(calledWith.split('q=')[1].split('&')[0])).toBe('耐克')
  })
})
