/**
 * Alerts API wrappers (Phase N + B3-3 snooze).
 *
 *   GET  /v1/alerts/?status&severity&project_id&limit
 *   GET  /v1/alerts/unread-count
 *   PATCH /v1/alerts/:id              {status: 'read'|'ignored'|'resolved'}
 *   POST /v1/alerts/:id/snooze        {hours: int}   (audit #1044 B3-3)
 *   POST /v1/alerts/mark-all-read
 */

import { apiClient } from '../lib/apiClient'

export type AlertStatus = 'unread' | 'read' | 'ignored' | 'resolved' | 'snoozed'

export interface AlertOut {
  id: string
  project_id: string | null
  brand_id: number | null
  source: string
  source_ref_id: string | null
  severity: 'P0' | 'P1' | 'P2' | 'P3'
  scope: string
  title: string
  body: string | null
  status: AlertStatus
  triggered_at: string
  read_at: string | null
  resolved_at: string | null
  snoozed_until: string | null
  assigned_to: string | null
  runbook_url: string | null
}

export interface AlertListOut {
  items: AlertOut[]
  total: number
}

export interface UnreadCountOut {
  unread_count: number
}

export const SNOOZE_PRESET_HOURS = [1, 4, 24, 24 * 7] as const

export const alertsApi = {
  list(params: {
    status?: string
    severity?: string
    project_id?: string
    limit?: number
  } = {}): Promise<AlertListOut> {
    const query = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== null && v !== '')
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join('&')
    return apiClient.get<AlertListOut>(`/v1/alerts/${query ? '?' + query : ''}`)
  },
  unreadCount(): Promise<UnreadCountOut> {
    return apiClient.get<UnreadCountOut>('/v1/alerts/unread-count')
  },
  patch(id: string, status: 'read' | 'ignored' | 'resolved'): Promise<AlertOut> {
    return apiClient.patch<AlertOut>(`/v1/alerts/${id}`, { status })
  },
  snooze(id: string, hours = 24): Promise<AlertOut> {
    return apiClient.post<AlertOut>(`/v1/alerts/${id}/snooze`, { hours })
  },
  markAllRead(): Promise<{ updated_count: number }> {
    return apiClient.post<{ updated_count: number }>('/v1/alerts/mark-all-read')
  },
}
