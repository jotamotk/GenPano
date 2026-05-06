/**
 * React Query hooks for industries API + onboarding helpers.
 *
 * Pattern: hook returns React Query state + a hand-merged display
 * record that overlays static FE constants (icon, nameEn) onto the
 * backend payload by name match.
 */

import { useQueries, useQuery } from '@tanstack/react-query'
import { industriesApi, type IndustryRow, type TopBrandRow } from '../api/industries'

/**
 * Static UI overlay keyed by industry English name (case-insensitive).
 * Backend doesn't store icon / nameEn — this list keeps the visual
 * polish without mock data.
 *
 * If backend returns an industry name not in this map, `?` icon is
 * shown and `nameEn` falls back to the backend name.
 */
const INDUSTRY_OVERLAY: Record<string, { icon: string; nameZh: string; nameEn: string }> = {
  beauty: { icon: '💄', nameZh: '美妆个护', nameEn: 'Beauty' },
  美妆个护: { icon: '💄', nameZh: '美妆个护', nameEn: 'Beauty' },
  luxury: { icon: '👑', nameZh: '奢侈品', nameEn: 'Luxury' },
  奢侈品: { icon: '👑', nameZh: '奢侈品', nameEn: 'Luxury' },
  food: { icon: '🍽️', nameZh: '食品饮料', nameEn: 'Food & Beverage' },
  食品饮料: { icon: '🍽️', nameZh: '食品饮料', nameEn: 'Food & Beverage' },
  fashion: { icon: '👗', nameZh: '服装时尚', nameEn: 'Fashion' },
  服装时尚: { icon: '👗', nameZh: '服装时尚', nameEn: 'Fashion' },
  electronics: { icon: '📱', nameZh: '电子产品', nameEn: 'Electronics' },
  电子产品: { icon: '📱', nameZh: '电子产品', nameEn: 'Electronics' },
}

export interface IndustryDisplay {
  industry_id: number
  /** Original backend name (used as map key) */
  name: string
  /** Human-readable Chinese name (overlay or backend fallback) */
  nameZh: string
  /** English / latin display name (overlay or backend fallback) */
  nameEn: string
  /** Emoji icon (overlay or generic fallback) */
  icon: string
  brandCount: number
}

function decorate(row: IndustryRow): IndustryDisplay {
  const overlay = INDUSTRY_OVERLAY[row.name.toLowerCase()] ?? INDUSTRY_OVERLAY[row.name]
  return {
    industry_id: row.industry_id,
    name: row.name,
    nameZh: overlay?.nameZh ?? row.name,
    nameEn: overlay?.nameEn ?? row.name,
    icon: overlay?.icon ?? '🏷️',
    brandCount: row.brand_count,
  }
}

export function useIndustries() {
  return useQuery({
    queryKey: ['industries', 'list'],
    queryFn: () => industriesApi.list(),
    select: (data): IndustryDisplay[] => data.items.map(decorate),
    staleTime: 5 * 60_000, // 5 min
  })
}

/**
 * Onboarding view-model: list of industries + top-3 brands per industry.
 *
 * Issues N+1 fan-out queries (one /top-brands per industry) but caches
 * each independently in React Query so re-renders don't refetch.
 */
export function useIndustryOverview(
  industryId: number | null | undefined,
  params: { name?: string } = {},
) {
  return useQuery({
    queryKey: ['industries', 'overview', industryId, params],
    queryFn: () => industriesApi.overview(industryId as number, params),
    enabled: typeof industryId === 'number' && industryId > 0,
    staleTime: 60_000,
    retry: false,
  })
}

export function useIndustryRanking(
  industryId: number | null | undefined,
  params: { name?: string; limit?: number } = {},
) {
  return useQuery({
    queryKey: ['industries', 'ranking', industryId, params],
    queryFn: () => industriesApi.ranking(industryId as number, params),
    enabled: typeof industryId === 'number' && industryId > 0,
    staleTime: 60_000,
    retry: false,
  })
}

export function useIndustryTopics(
  industryId: number | null | undefined,
  params: { name?: string; limit?: number } = {},
) {
  return useQuery({
    queryKey: ['industries', 'topics', industryId, params],
    queryFn: () => industriesApi.topics(industryId as number, params),
    enabled: typeof industryId === 'number' && industryId > 0,
    staleTime: 60_000,
    retry: false,
  })
}

export function useIndustryKg(
  industryId: number | null | undefined,
  params: { name?: string; focus?: string; depth?: number } = {},
) {
  return useQuery({
    queryKey: ['industries', 'kg', industryId, params],
    queryFn: () => industriesApi.kg(industryId as number, params),
    enabled: typeof industryId === 'number' && industryId > 0,
    staleTime: 60_000,
    retry: false,
  })
}

export function useIndustryAvgGeo(
  industryId: number | null | undefined,
  params: { name?: string; from?: string; to?: string } = {},
) {
  return useQuery({
    queryKey: ['industries', 'avg-geo-score', industryId, params],
    queryFn: () => industriesApi.avgGeoScore(industryId as number, params),
    enabled: typeof industryId === 'number' && industryId > 0,
    staleTime: 60_000,
    retry: false,
  })
}

export function useIndustriesWithTopBrands() {
  const industries = useIndustries()
  const topBrandsList = useQueries({
    queries: (industries.data ?? []).map((row) => ({
      queryKey: ['industries', 'top-brands', row.industry_id],
      queryFn: () => industriesApi.topBrands(row.industry_id, 3),
      enabled: !!industries.data,
      staleTime: 60_000,
    })),
  })

  const decorated = (industries.data ?? []).map((row, i) => ({
    ...row,
    topBrands: (topBrandsList[i]?.data ?? []) as TopBrandRow[],
    topBrandsLoading: topBrandsList[i]?.isLoading ?? false,
  }))

  return {
    isLoading: industries.isLoading,
    isError: industries.isError,
    error: industries.error,
    data: decorated,
  }
}
