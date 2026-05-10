/**
 * useQueryAnalytics — TanStack Query hook for the brand query analytics
 * endpoint. Used by the TopicsPage QueryActivityCard.
 *
 * Fires only when brandId is a positive integer; otherwise stays disabled
 * so the empty/auth-pending state doesn't issue a useless 401/empty call.
 */

import { useQuery } from '@tanstack/react-query'
import {
  QueryAnalyticsArgs,
  QueryAnalyticsOut,
  queryAnalyticsApi,
} from '../api/queryAnalytics'

export function useQueryAnalytics(args: QueryAnalyticsArgs) {
  const { brandId, dateFrom, dateTo, engine } = args
  return useQuery<QueryAnalyticsOut>({
    queryKey: ['admin', 'queries', 'analytics', brandId, dateFrom, dateTo, engine],
    queryFn: () => queryAnalyticsApi.fetch(args),
    enabled: typeof brandId === 'number' && brandId > 0,
    staleTime: 60_000,
    retry: false,
  })
}
