/**
 * Chart-data hooks (Phase 5).
 *
 * One hook per backend chart endpoint. All hooks gate on a UUID-shaped
 * project id (`isLiveProjectId`); mock-only users don't trigger requests.
 */

import { useQuery } from '@tanstack/react-query'

import { projectChartsApi } from '../api/charts'
import { isLiveProjectId } from './useBrandOverview'

const STALE = 60_000

export function useEngineMetrics(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['charts', 'engine-metrics', projectId],
    queryFn: () => projectChartsApi.engineMetrics(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function usePositionDistribution(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['charts', 'position-distribution', projectId],
    queryFn: () => projectChartsApi.positionDistribution(projectId as string),
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
    ],
    queryFn: () => projectChartsApi.topicHeatmap(projectId as string, opts),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useSentimentByEngine(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['charts', 'sentiment-by-engine', projectId],
    queryFn: () => projectChartsApi.sentimentByEngine(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useSentimentTrendByEngine(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['charts', 'sentiment-trend-by-engine', projectId],
    queryFn: () => projectChartsApi.sentimentTrendByEngine(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useTopicAttribution(
  projectId: string | null | undefined,
  limit = 10,
) {
  return useQuery({
    queryKey: ['charts', 'topic-attribution', projectId, limit],
    queryFn: () => projectChartsApi.topicAttribution(projectId as string, limit),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useMentionSamples(
  projectId: string | null | undefined,
  opts: { polarity?: string; limit?: number } = {},
) {
  return useQuery({
    queryKey: ['charts', 'mention-samples', projectId, opts.polarity, opts.limit],
    queryFn: () => projectChartsApi.mentionSamples(projectId as string, opts),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useAuthorityTrend(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['charts', 'authority-trend', projectId],
    queryFn: () => projectChartsApi.authorityTrend(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useCitationComposition(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['charts', 'citation-composition', projectId],
    queryFn: () => projectChartsApi.citationComposition(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useContentGap(projectId: string | null | undefined, limit = 12) {
  return useQuery({
    queryKey: ['charts', 'content-gap', projectId, limit],
    queryFn: () => projectChartsApi.contentGap(projectId as string, limit),
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
