/**
 * Notification preferences hook + mutation.
 *
 * SettingsPage uses these to persist the 3 toggles. Optimistic update
 * keeps the toggle UI responsive; on PATCH failure (offline / 401)
 * the value rolls back so the user sees the truth.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  notificationsApi,
  type NotificationPrefsOut,
  type NotificationPrefsPatch,
} from '../api/notifications'

const KEY = ['user', 'notifications'] as const

export function useNotifications() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => notificationsApi.get(),
    staleTime: 30_000,
    retry: false,
  })
}

export function useUpdateNotifications() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (patch: NotificationPrefsPatch) => notificationsApi.patch(patch),
    onMutate: async (patch) => {
      await qc.cancelQueries({ queryKey: KEY })
      const previous = qc.getQueryData<NotificationPrefsOut>(KEY)
      if (previous) {
        qc.setQueryData<NotificationPrefsOut>(KEY, { ...previous, ...patch } as NotificationPrefsOut)
      }
      return { previous }
    },
    onError: (_err, _patch, ctx) => {
      if (ctx?.previous) {
        qc.setQueryData<NotificationPrefsOut>(KEY, ctx.previous)
      }
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: KEY })
    },
  })
}
