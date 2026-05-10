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
  brandIdOverride?: number | null,
) {
  return useQuery({
    queryKey: ['brand', 'metrics', projectId, series.join(','), brandIdOverride ?? null],
    queryFn: () => brandMetricsApi.metrics(projectId as string, series, brandIdOverride),
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

export function useBrandTopics(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['brand', 'topics', projectId],
    queryFn: () => brandMetricsApi.topics(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
    retry: false,
  })
}

export function useBrandProducts(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['brand', 'products', projectId],
    queryFn: () => brandMetricsApi.products(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
    retry: false,
  })
}

export function useCompetitorMetrics(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['brand', 'competitor-metrics', projectId],
    queryFn: () => brandMetricsApi.competitorMetrics(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
    retry: false,
  })
}

export function useCompetitorTrends(
  projectId: string | null | undefined,
  metric:
    | 'geo_score'
    | 'mention_rate'
    | 'sov'
    | 'sentiment'
    | 'rank'
    | 'citation' = 'geo_score',
) {
  return useQuery({
    queryKey: ['brand', 'competitor-trends', projectId, metric],
    queryFn: () => brandMetricsApi.competitorTrends(projectId as string, metric),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
    retry: false,
  })
}
