/**
 * Brand metrics / sentiment / citations hooks (Phase 2.2).
 *
 * Each only fires for UUID-shaped project ids so mock-only users
 * don't 404 the backend.
 */

import { useQuery } from '@tanstack/react-query'
import { brandMetricsApi } from '../api/brandMetrics'
import { isLiveProjectId } from './useBrandOverview'
import { ProjectAnalysisParams } from '../lib/projectAnalysisFilters'

const filterKey = (filters: ProjectAnalysisParams = {}) =>
  [
    filters.from ?? '',
    filters.to ?? '',
    filters.engine ?? '',
    filters.segment_id ?? '',
    filters.profile_id ?? '',
    filters.dimension ?? '',
    filters.intent ?? '',
    filters.prompt_scope ?? '',
    filters.brand_id ?? '',
  ].join('|')

export function useBrandMetrics(
  projectId: string | null | undefined,
  series: string[] = ['mention_rate', 'sov', 'rank', 'sentiment'],
  brandIdOverride?: number | null,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: [
      'brand',
      'metrics',
      projectId,
      series.join(','),
      brandIdOverride ?? null,
      filterKey(filters),
    ],
    queryFn: () => brandMetricsApi.metrics(projectId as string, series, brandIdOverride, filters),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
  })
}

export function useBrandSentiment(
  projectId: string | null | undefined,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: ['brand', 'sentiment', projectId, filterKey(filters)],
    queryFn: () => brandMetricsApi.sentiment(projectId as string, filters),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
  })
}

export function useBrandCitations(
  projectId: string | null | undefined,
  pageSize = 50,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: ['brand', 'citations', projectId, pageSize, filterKey(filters)],
    queryFn: () => brandMetricsApi.citations(projectId as string, pageSize, filters),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
  })
}

export function useBrandTopics(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['brand', 'topics', projectId],
    queryFn: () => brandMetricsApi.topics(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
  })
}

export function useBrandProducts(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['brand', 'products', projectId],
    queryFn: () => brandMetricsApi.products(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
  })
}

export function useCompetitorMetrics(
  projectId: string | null | undefined,
  brandIdOverride?: number | null,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: [
      'brand',
      'competitor-metrics',
      projectId,
      brandIdOverride ?? null,
      filterKey(filters),
    ],
    queryFn: () => brandMetricsApi.competitorMetrics(
      projectId as string,
      brandIdOverride,
      filters,
    ),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
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
  brandIdOverride?: number | null,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: [
      'brand',
      'competitor-trends',
      projectId,
      metric,
      brandIdOverride ?? null,
      filterKey(filters),
    ],
    queryFn: () => brandMetricsApi.competitorTrends(
      projectId as string,
      metric,
      brandIdOverride,
      filters,
    ),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
  })
}
