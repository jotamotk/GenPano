/**
 * Brand overview hook — composite KPI + 30d trends.
 *
 * Used by DashboardPage / BrandPanorama to overlay live backend data on
 * the existing mock-driven viz. The hook is only enabled when the
 * caller provides a real backend project id (UUID-shaped); mock
 * project ids ('proj-001') return null without firing a 404 request.
 */

import { useQuery } from '@tanstack/react-query'
import { brandOverviewApi } from '../api/brandOverview'

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function isLiveProjectId(id: string | null | undefined): boolean {
  return !!id && UUID_RE.test(id)
}

export function useBrandOverview(
  projectId: string | null | undefined,
  brandIdOverride?: number | null,
) {
  return useQuery({
    queryKey: ['brand', 'overview', projectId, brandIdOverride ?? null],
    queryFn: () => brandOverviewApi.get(projectId as string, brandIdOverride),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
    retry: false,
  })
}
