/**
 * Diagnostics hooks (Phase D.7).
 *
 * Includes a transform `toMockShape()` that maps backend DiagnosticOut
 * to the camelCase shape that DiagnosticsPage / DiagnosticCard already
 * consume from `data/mock.js`. Lets us flip the data source without
 * rewriting the card.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { diagnosticsApi, type DiagnosticOut } from '../api/diagnostics'
import { isLiveProjectId } from './useBrandOverview'

export function useDiagnostics(
  projectId: string | null | undefined,
  params: {
    status?: string
    severity?: string
    category?: string
    type?: string
    limit?: number
  } = {},
) {
  return useQuery({
    queryKey: ['diagnostics', projectId, params],
    queryFn: () => diagnosticsApi.list(projectId as string, params),
    enabled: isLiveProjectId(projectId),
    staleTime: 30_000,
    retry: false,
  })
}

export function useDiagnosticCounts(projectId: string | null | undefined) {
  return useQuery({
    queryKey: ['diagnostics', projectId, 'counts'],
    queryFn: () => diagnosticsApi.counts(projectId as string),
    enabled: isLiveProjectId(projectId),
    staleTime: 30_000,
    retry: false,
  })
}

export function useUpdateDiagnostic(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      diagId,
      status,
    }: {
      diagId: string
      status: 'acknowledged' | 'ignored' | 'resolved' | 'open'
    }) => diagnosticsApi.patch(projectId, diagId, status),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['diagnostics', projectId] })
    },
  })
}

export function useRefreshDiagnostics(projectId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => diagnosticsApi.refresh(projectId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['diagnostics', projectId] })
    },
  })
}

/**
 * Convert backend DiagnosticOut to the camelCase shape DiagnosticCard
 * already consumes (matches src/data/mock.js DIAGNOSTICS items).
 *
 * Fields the FE card expects but backend doesn't have: `engine`,
 * `decisionPrompt`, `affectedQueries`, etc. — derived from `evidence`
 * dict if present, otherwise left undefined and the card hides them.
 */
export function toMockShape(d: DiagnosticOut): Record<string, unknown> {
  const evidence = d.evidence ?? {}
  return {
    id: d.id,
    category: d.category,
    severity: d.severity,
    type: d.type,
    brandId: d.brand_id != null ? String(d.brand_id) : undefined,
    productId: d.product_id != null ? String(d.product_id) : undefined,
    title: d.title,
    description: d.description ?? '',
    detected: d.detected_at?.slice(0, 10) ?? '',
    focusArea: d.focus_area ?? '',
    direction: d.direction ?? '',
    readerHints: d.reader_hints ?? [],
    evidence,
    causalChain: d.causal_chain ?? null,
    anchorQuestions: d.anchor_questions ?? null,
    industryBenchmark: d.industry_benchmark ?? null,
    ifUntreated: d.if_untreated ?? null,
    status: d.status,
    ruleId: d.rule_id,
  }
}
