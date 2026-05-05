/**
 * Reports API (Phase RP.6).
 *
 *   GET    /v1/projects/:id/reports
 *   POST   /v1/projects/:id/reports
 *   GET    /v1/projects/:id/reports/:rid
 *   GET    /v1/projects/:id/reports/:rid/download?format=markdown|json|csv
 *   POST   /v1/projects/:id/reports/:rid/share
 */

import { apiClient } from '../lib/apiClient'

export interface ReportJobOut {
  id: string
  project_id: string
  type: string
  status: string
  created_at: string
  finished_at: string | null
  output_url: string | null
  error: string | null
}

export interface ReportListOut {
  items: ReportJobOut[]
  total: number
}

export interface ReportDetailOut extends ReportJobOut {
  payload: Record<string, unknown> | null
}

export interface ReportCreateIn {
  report_type?: 'weekly' | 'monthly' | 'on_demand' | 'lead_diagnostic'
  locale?: 'zh-CN' | 'en-US'
  reader_perspective?: 'operator' | 'manager' | 'branding'
  from_date?: string | null
  to_date?: string | null
}

export interface ReportShareOut {
  token: string
  url: string
  expires_at: string
}

export const reportsApi = {
  list(projectId: string, limit = 50): Promise<ReportListOut> {
    return apiClient.get<ReportListOut>(
      `/v1/projects/${projectId}/reports?limit=${limit}`,
    )
  },
  create(projectId: string, payload: ReportCreateIn): Promise<ReportDetailOut> {
    return apiClient.post<ReportDetailOut>(
      `/v1/projects/${projectId}/reports`,
      payload,
    )
  },
  get(projectId: string, reportId: string): Promise<ReportDetailOut> {
    return apiClient.get<ReportDetailOut>(
      `/v1/projects/${projectId}/reports/${reportId}`,
    )
  },
  downloadUrl(projectId: string, reportId: string, fmt: 'markdown' | 'json' | 'csv' = 'markdown'): string {
    return `/api/v1/projects/${projectId}/reports/${reportId}/download?format=${fmt}`
  },
  share(
    projectId: string,
    reportId: string,
    expiresInHours = 72,
  ): Promise<ReportShareOut> {
    return apiClient.post<ReportShareOut>(
      `/v1/projects/${projectId}/reports/${reportId}/share`,
      { expires_in_hours: expiresInHours },
    )
  },
}
