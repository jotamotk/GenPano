/**
 * Projects API wrappers.
 *
 * Backend endpoints (Phase 1):
 *   GET    /v1/projects/                       -> list user's projects
 *   POST   /v1/projects/                       -> create
 *   GET    /v1/projects/:id                    -> detail
 *   PATCH  /v1/projects/:id                    -> partial update
 *   DELETE /v1/projects/:id                    -> soft delete
 *   POST   /v1/projects/:id/competitors        -> add competitor
 *   DELETE /v1/projects/:id/competitors/:bid   -> remove competitor
 */

import { apiClient } from '../lib/apiClient'

export interface CompetitorOut {
  brand_id: number
  pinned_at: string
}

export interface ProjectOut {
  id: string
  user_id: string
  org_id: string | null
  name: string
  industry_id: number | null
  primary_brand_id: number | null
  is_active: boolean
  preferred_engines: string[] | null
  default_profile_group_id: string | null
  preferences: Record<string, unknown> | null
  created_at: string
  updated_at: string
  competitors: CompetitorOut[]
}

export interface ProjectListOut {
  items: ProjectOut[]
  total: number
}

export interface ProjectIn {
  name: string
  industry_id?: number | null
  primary_brand_id?: number | null
  preferred_engines?: string[] | null
  competitor_brand_ids?: number[] | null
}

export interface ProjectPatch {
  name?: string
  industry_id?: number | null
  primary_brand_id?: number | null
  is_active?: boolean
  preferred_engines?: string[] | null
  default_profile_group_id?: string | null
  preferences?: Record<string, unknown> | null
}

export const projectsApi = {
  list(): Promise<ProjectListOut> {
    return apiClient.get<ProjectListOut>('/v1/projects/')
  },
  get(id: string): Promise<ProjectOut> {
    return apiClient.get<ProjectOut>(`/v1/projects/${id}`)
  },
  create(payload: ProjectIn): Promise<ProjectOut> {
    return apiClient.post<ProjectOut>('/v1/projects/', payload)
  },
  patch(id: string, payload: ProjectPatch): Promise<ProjectOut> {
    return apiClient.patch<ProjectOut>(`/v1/projects/${id}`, payload)
  },
  remove(id: string): Promise<void> {
    return apiClient.delete<void>(`/v1/projects/${id}`)
  },
  addCompetitor(id: string, brandId: number): Promise<ProjectOut> {
    return apiClient.post<ProjectOut>(`/v1/projects/${id}/competitors`, {
      brand_id: brandId,
    })
  },
  removeCompetitor(id: string, brandId: number): Promise<void> {
    return apiClient.delete<void>(`/v1/projects/${id}/competitors/${brandId}`)
  },
}
