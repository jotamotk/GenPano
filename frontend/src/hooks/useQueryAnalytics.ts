import { useQuery } from '@tanstack/react-query'

import {
  QueryAnalyticsArgs,
  QueryAnalyticsOut,
  queryAnalyticsApi,
} from '../api/queryAnalytics'
import { isLiveProjectId } from '../lib/liveProject'

export function useQueryAnalytics(args: QueryAnalyticsArgs) {
  const {
    projectId,
    dateFrom,
    dateTo,
    engine,
    segmentId,
    profileId,
    dimension,
    intent,
    promptScope,
  } = args
  return useQuery<QueryAnalyticsOut>({
    queryKey: [
      'projects',
      projectId,
      'query-activity',
      dateFrom,
      dateTo,
      engine,
      segmentId,
      profileId,
      dimension,
      intent,
      promptScope,
    ],
    queryFn: () => queryAnalyticsApi.fetch(args),
    enabled: isLiveProjectId(projectId),
    staleTime: 60_000,
    retry: false,
  })
}
