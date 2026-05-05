/**
 * Brand metrics / sentiment / citations hooks (Phase 2.2).
 *
 * Each only fires for UUID-shaped project ids so mock-only users
 * don't 404 the backend.
 */

import { useQuery } from '@tanstack/react-query'
import { brandMetricsApi } from '../api/brandMetrics'
import { isLiveProjectId } from './useBrandOverview'

export function useBrandMetrics(
  projectId: string | null | undefined,
  series: string[] = ['mention_rate', 'sov', 'rank', 'sentiment'],
) {
  return useQuery({
    queryKey: ['brand', 'metrics', projectId, series.join(',')],
    queryFn: () => brandMetricsApi.metrics(projectId as string, series),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
    retry: false,
  })
}

export function useBrandSentiment(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['brand', 'sentiment', projectId],
    queryFn: () => brandMetricsApi.sentiment(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
    retry: false,
  })
}

export function useBrandCitations(
  projectId: string | null | undefined,
  pageSize = 50,
) {
  return useQuery({
    queryKey: ['brand', 'citations', projectId, pageSize],
    queryFn: () => brandMetricsApi.citations(projectId as string, pageSize),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
    retry: false,
  })
}
