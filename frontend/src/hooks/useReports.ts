/**
 * Reports hooks — wrap /v1/projects/:id/reports.
 *
 * Used by ReportsPage to:
 *   - List recent live reports above the mock catalog (LIVE banner pattern)
 *   - Generate a real report from the GenerateModal when the active
 *     project is a real backend project (UUID id)
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  reportsApi,
  type ReportCreateIn,
  type ReportDetailOut,
  type ReportListOut,
} from '../api/reports'

export const REPORTS_QUERY_KEY = ['reports'] as const

export function isLiveProjectId(id: string | null | undefined): boolean {
  return (
    typeof id === 'string' &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)
  )
}

export function useReports(projectId: string | null | undefined, limit = 50) {
  const enabled = isLiveProjectId(projectId)
  return useQuery<ReportListOut>({
    queryKey: [...REPORTS_QUERY_KEY, projectId, limit],
    queryFn: () => reportsApi.list(projectId as string, limit),
    enabled,
    staleTime: 30 * 1000,
  })
}

export function useCreateReport(projectId: string | null | undefined) {
  const qc = useQueryClient()
  return useMutation<ReportDetailOut, Error, ReportCreateIn>({
    mutationFn: (payload) =>
      reportsApi.create(projectId as string, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [...REPORTS_QUERY_KEY, projectId] })
    },
    onError: (err) => {
      // eslint-disable-next-line no-console
      console.warn('reports.create failed:', err)
    },
  })
}
