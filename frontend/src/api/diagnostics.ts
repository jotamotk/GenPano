/**
 * Diagnostics API (Phase D.7).
 *
 *   GET    /v1/projects/:id/diagnostics?status&severity&category&type
 *   GET    /v1/projects/:id/diagnostics/counts
 *   GET    /v1/projects/:id/diagnostics/:diag_id
 *   PATCH  /v1/projects/:id/diagnostics/:diag_id  {status}
 *   POST   /v1/projects/:id/diagnostics/refresh
 */

import { apiClient } from '../lib/apiClient'

export interface DiagnosticOut {
  id: string
  project_id: string
  brand_id: number | null
  product_id: number | null
  industry_id: number | null
  category: string
  severity: 'P0' | 'P1' | 'P2' | 'P3'
  type: 'brand' | 'product' | 'industry'
  title: string
  description: string | null
  focus_area: string | null
  direction: string | null
  reader_hints: string[]
  evidence: Record<string, unknown>
  causal_chain: Record<string, unknown> | null
  industry_benchmark: Record<string, unknown> | null
  anchor_questions: Record<string, unknown> | null
  if_untreated: string | null
  rule_id: string
  rule_version: string | null
  status: 'open' | 'acknowledged' | 'ignored' | 'resolved'
  detected_at: string
  acknowledged_at: string | null
  resolved_at: string | null
}

export interface DiagnosticListOut {
  items: DiagnosticOut[]
  total: number
}

export interface DiagnosticCountsOut {
  total: number
  by_status: Record<string, number>
  by_severity_open: Record<string, number>
}

export const diagnosticsApi = {
  list(
    projectId: string,
    params: {
      status?: string
      severity?: string
      category?: string
      type?: string
      limit?: number
    } = {},
  ): Promise<DiagnosticListOut> {
    const query = Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== null && v !== '')
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join('&')
    return apiClient.get<DiagnosticListOut>(
      `/v1/projects/${projectId}/diagnostics/${query ? '?' + query : ''}`,
    )
  },
  counts(projectId: string): Promise<DiagnosticCountsOut> {
    return apiClient.get<DiagnosticCountsOut>(
      `/v1/projects/${projectId}/diagnostics/counts`,
    )
  },
  patch(
    projectId: string,
    diagId: string,
    status: 'acknowledged' | 'ignored' | 'resolved' | 'open',
  ): Promise<DiagnosticOut> {
    return apiClient.patch<DiagnosticOut>(
      `/v1/projects/${projectId}/diagnostics/${diagId}`,
      { status },
    )
  },
  refresh(projectId: string): Promise<{ inserted: number; project_id: string }> {
    return apiClient.post<{ inserted: number; project_id: string }>(
      `/v1/projects/${projectId}/diagnostics/refresh`,
    )
  },
}
