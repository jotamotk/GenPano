/**
 * Chart-data hooks (Phase 5).
 *
 * One hook per backend chart endpoint. All hooks gate on a UUID-shaped
 * project id (`isLiveProjectId`); mock-only users don't trigger requests.
 */

import { useQuery } from '@tanstack/react-query'

import { projectChartsApi } from '../api/charts'
import { isLiveProjectId } from './useBrandOverview'
import { ProjectAnalysisParams } from '../lib/projectAnalysisFilters'

const STALE = 60_000
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

export function useEngineMetrics(
  projectId: string | null | undefined,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: ['charts', 'engine-metrics', projectId, filterKey(filters)],
    queryFn: () => projectChartsApi.engineMetrics(projectId as string, filters),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function usePositionDistribution(
  projectId: string | null | undefined,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: ['charts', 'position-distribution', projectId, filterKey(filters)],
    queryFn: () => projectChartsApi.positionDistribution(projectId as string, filters),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useTopicHeatmap(
  projectId: string | null | undefined,
  opts: {
    metric?: 'mention_rate' | 'sentiment'
    compareWith?: number[]
    topN?: number
    filters?: ProjectAnalysisParams
  } = {},
) {
  return useQuery({
    queryKey: [
      'charts',
      'topic-heatmap',
      projectId,
      opts.metric,
      (opts.compareWith ?? []).join(','),
      opts.topN,
      filterKey(opts.filters),
    ],
    queryFn: () => projectChartsApi.topicHeatmap(projectId as string, opts),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useSentimentByEngine(
  projectId: string | null | undefined,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: ['charts', 'sentiment-by-engine', projectId, filterKey(filters)],
    queryFn: () => projectChartsApi.sentimentByEngine(projectId as string, filters),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useSentimentTrendByEngine(
  projectId: string | null | undefined,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: ['charts', 'sentiment-trend-by-engine', projectId, filterKey(filters)],
    queryFn: () => projectChartsApi.sentimentTrendByEngine(projectId as string, filters),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useTopicAttribution(
  projectId: string | null | undefined,
  limit = 10,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: ['charts', 'topic-attribution', projectId, limit, filterKey(filters)],
    queryFn: () => projectChartsApi.topicAttribution(projectId as string, limit, filters),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useMentionSamples(
  projectId: string | null | undefined,
  opts: { polarity?: string; limit?: number; filters?: ProjectAnalysisParams } = {},
) {
  return useQuery({
    queryKey: [
      'charts',
      'mention-samples',
      projectId,
      opts.polarity,
      opts.limit,
      filterKey(opts.filters),
    ],
    queryFn: () => projectChartsApi.mentionSamples(projectId as string, opts),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useAuthorityTrend(
  projectId: string | null | undefined,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: ['charts', 'authority-trend', projectId, filterKey(filters)],
    queryFn: () => projectChartsApi.authorityTrend(projectId as string, filters),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useCitationComposition(
  projectId: string | null | undefined,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: ['charts', 'citation-composition', projectId, filterKey(filters)],
    queryFn: () => projectChartsApi.citationComposition(projectId as string, filters),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useContentGap(
  projectId: string | null | undefined,
  limit = 12,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: ['charts', 'content-gap', projectId, limit, filterKey(filters)],
    queryFn: () => projectChartsApi.contentGap(projectId as string, limit, filters),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function usePrTargets(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['charts', 'pr-targets', projectId],
    queryFn: () => projectChartsApi.prTargets(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useSimulatorBaseline(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['charts', 'simulator-baseline', projectId],
    queryFn: () => projectChartsApi.simulatorBaseline(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useAuthorityRadar(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['charts', 'authority-radar', projectId],
    queryFn: () => projectChartsApi.authorityRadar(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useGroupSharedDomains(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['charts', 'group-shared-domains', projectId],
    queryFn: () => projectChartsApi.groupSharedDomains(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useProductRelations(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['charts', 'product-relations', projectId],
    queryFn: () => projectChartsApi.productRelations(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}
