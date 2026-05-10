/**
 * useBrandSearch — debounced live search for the onboarding brand picker.
 *
 * Wraps GET /v1/brands/search via React Query. Returns `[]` for queries
 * shorter than 1 char and skips the network entirely while debouncing,
 * so the dropdown never flickers when the user is mid-typing.
 */

import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { brandsApi, type BrandSearchHit } from '../api/brands'

const DEFAULT_DEBOUNCE_MS = 300

export function useBrandSearch(rawQuery: string, options?: { debounceMs?: number; limit?: number }) {
  const debounceMs = options?.debounceMs ?? DEFAULT_DEBOUNCE_MS
  const limit = options?.limit ?? 10

  const [debounced, setDebounced] = useState(rawQuery)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(rawQuery), debounceMs)
    return () => clearTimeout(t)
  }, [rawQuery, debounceMs])

  const trimmed = debounced.trim()
  const enabled = trimmed.length >= 1

  return useQuery<BrandSearchHit[]>({
    queryKey: ['brands', 'search', trimmed, limit],
    queryFn: async () => {
      if (!enabled) return []
      const res = await brandsApi.search(trimmed, limit)
      return res.items
    },
    enabled,
    staleTime: 30_000,
    retry: false,
  })
}
