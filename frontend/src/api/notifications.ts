/**
 * User notification preferences API.
 *
 * Backend (Phase N):
 *   GET   /v1/users/me/notifications  -> current prefs
 *   PATCH /v1/users/me/notifications  -> partial update
 */

import { apiClient } from '../lib/apiClient'

export interface NotificationPrefsOut {
  user_id: string
  p0p1_alerts: boolean
  weekly_report: boolean
  competitor_alert: boolean
  email_locale: string
  quiet_hours: { start?: string; end?: string; tz?: string } | null
  channels: string[] | null
  updated_at: string
}

export interface NotificationPrefsPatch {
  p0p1_alerts?: boolean
  weekly_report?: boolean
  competitor_alert?: boolean
  email_locale?: string
  quiet_hours?: { start?: string; end?: string; tz?: string } | null
  channels?: string[] | null
}

export const notificationsApi = {
  get(): Promise<NotificationPrefsOut> {
    return apiClient.get<NotificationPrefsOut>('/v1/users/me/notifications')
  },
  patch(payload: NotificationPrefsPatch): Promise<NotificationPrefsOut> {
    return apiClient.patch<NotificationPrefsOut>('/v1/users/me/notifications', payload)
  },
}
