/**
 * Alerts hooks — top-bar bell badge + dropdown list.
 *
 * Bell badge uses a 30s refetch so the count stays close-to-fresh
 * without server-sent events. The future Phase N webhook can replace
 * this with a websocket push.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { alertsApi } from '../api/alerts'

const KEY_LIST = ['alerts', 'list'] as const
const KEY_UNREAD = ['alerts', 'unread-count'] as const

export function useUnreadAlertCount() {
  return useQuery({
    queryKey: KEY_UNREAD,
    queryFn: () => alertsApi.unreadCount(),
    refetchInterval: 30_000,
    refetchOnWindowFocus: true,
    staleTime: 10_000,
    retry: false,
    select: (data) => data.unread_count,
  })
}

export function useAlerts(
  params: {
    status?: string
    severity?: string
    project_id?: string
    limit?: number
  } = {},
) {
  return useQuery({
    queryKey: [...KEY_LIST, params],
    queryFn: () => alertsApi.list(params),
    staleTime: 30_000,
    retry: false,
  })
}

export function useUpdateAlertStatus() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      id,
      status,
    }: {
      id: string
      status: 'read' | 'ignored' | 'resolved'
    }) => alertsApi.patch(id, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY_LIST })
      qc.invalidateQueries({ queryKey: KEY_UNREAD })
    },
  })
}

export function useMarkAllAlertsRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => alertsApi.markAllRead(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY_LIST })
      qc.invalidateQueries({ queryKey: KEY_UNREAD })
    },
  })
}

export function useSnoozeAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, hours }: { id: string; hours: number }) =>
      alertsApi.snooze(id, hours),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY_LIST })
      qc.invalidateQueries({ queryKey: KEY_UNREAD })
    },
  })
}
