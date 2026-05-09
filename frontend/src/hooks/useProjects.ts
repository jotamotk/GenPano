/**
 * React Query hooks for projects API.
 *
 * Companion to ProjectContext — the context still owns the
 * "active project" + optimistic mutations + 30s competitor debounce.
 * These hooks just expose the underlying CRUD as queries that the
 * context can seed from on mount, plus standalone mutations for
 * pages that don't need the broader context.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  projectsApi,
  type ProjectIn,
  type ProjectOut,
  type ProjectPatch,
} from '../api/projects'

export const PROJECTS_QUERY_KEY = ['projects'] as const

export function useProjects(options: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: PROJECTS_QUERY_KEY,
    queryFn: () => projectsApi.list(),
    select: (data) => data.items,
    staleTime: 30_000,
    retry: false, // 401 should fail fast; user gets redirected to /login
    // Skip the request entirely when the caller knows there is no auth
    // context (e.g. ProjectProvider mounted on a public page). Without
    // this gate, the unauthenticated request 401s, which used to push
    // the user into a redirect loop on /login.
    enabled: options.enabled !== false,
  })
}

export function useProject(id: string | null | undefined) {
  return useQuery({
    queryKey: ['projects', id ?? 'none'],
    queryFn: () => projectsApi.get(id as string),
    enabled: !!id,
    staleTime: 30_000,
  })
}

export function useCreateProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: ProjectIn) => projectsApi.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY })
    },
  })
}

export function useUpdateProject(id: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (patch: ProjectPatch) => projectsApi.patch(id, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY })
      qc.invalidateQueries({ queryKey: ['projects', id] })
    },
  })
}

export function useDeleteProject() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => projectsApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY })
    },
  })
}

export function useAddCompetitor(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (brandId: number) => projectsApi.addCompetitor(projectId, brandId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects', projectId] })
      qc.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY })
    },
  })
}

export function useRemoveCompetitor(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (brandId: number) => projectsApi.removeCompetitor(projectId, brandId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['projects', projectId] })
      qc.invalidateQueries({ queryKey: PROJECTS_QUERY_KEY })
    },
  })
}

export type { ProjectOut }
