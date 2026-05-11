import { useQuery } from '@tanstack/react-query'

import { topicAnalysisApi } from '../api/topicAnalysis'
import { ProjectAnalysisParams } from '../lib/projectAnalysisFilters'
import { isLiveProjectId } from '../lib/liveProject'

const STALE = 60_000

function keyOf(filters: ProjectAnalysisParams = {}) {
  return [
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
}

export function useTopicMonitoring(
  projectId: string | null | undefined,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: ['topic-analysis', 'monitoring', projectId, keyOf(filters)],
    queryFn: () => topicAnalysisApi.monitoring(projectId as string, filters),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}

export function useTopicPrompts(
  projectId: string | null | undefined,
  topicId: number | null | undefined,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: ['topic-analysis', 'prompts', projectId, topicId, keyOf(filters)],
    queryFn: () => topicAnalysisApi.prompts(projectId as string, topicId as number, filters),
    enabled: isLiveProjectId(projectId) && typeof topicId === 'number',
    staleTime: STALE,
    retry: false,
  })
}

export function usePromptQueries(
  projectId: string | null | undefined,
  promptId: number | null | undefined,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: ['topic-analysis', 'queries', projectId, promptId, keyOf(filters)],
    queryFn: () => topicAnalysisApi.queries(projectId as string, promptId as number, filters),
    enabled: isLiveProjectId(projectId) && typeof promptId === 'number',
    staleTime: STALE,
    retry: false,
  })
}

export function useQueryResponse(
  projectId: string | null | undefined,
  queryId: number | null | undefined,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: ['topic-analysis', 'response', projectId, queryId, keyOf(filters)],
    queryFn: () => topicAnalysisApi.response(projectId as string, queryId as number, filters),
    enabled: isLiveProjectId(projectId) && typeof queryId === 'number',
    staleTime: STALE,
    retry: false,
  })
}

export function useProjectSegments(
  projectId: string | null | undefined,
  filters: ProjectAnalysisParams = {},
) {
  return useQuery({
    queryKey: ['topic-analysis', 'segments', projectId, keyOf(filters)],
    queryFn: () => topicAnalysisApi.segments(projectId as string, filters),
    enabled: isLiveProjectId(projectId),
    staleTime: STALE,
    retry: false,
  })
}
