export type AnalyticsState = 'ok' | 'empty' | 'partial' | 'error' | string

export interface ValueRange {
  min: number
  max: number
}

export interface ProjectScope {
  exists: boolean
  project_id?: string | null
  primary_brand_id?: number | null
  requested_brand_id?: number | null
  competitor_brand_ids?: number[]
  missing_reason?: string | null
}

export interface IdentityDiagnostics {
  canonical_brand_id?: number | null
  normalized_brand_mention_count?: number
  brand_mentioned_response_count?: number
  response_analysis_count?: number
  canonical_alias_repair_count?: number
  raw_text_owner_brand_ids?: number[]
  repair_missing_sources?: string[]
  [key: string]: unknown
}

export interface FormulaDiagnostics {
  status?: string | null
  pending_sources?: string[]
  details?: string[]
  [key: string]: unknown
}

export interface DataFreshness {
  generated_at?: string | null
}

export type ContractListItem =
  | string
  | {
      source?: string | null
      field?: string | null
      reason?: string | null
      owner_issue?: string | null
      [key: string]: unknown
    }

export interface AnalyticsContractMetadata {
  state?: AnalyticsState
  state_reason?: string | null
  state_detail?: string | null
  project_scope?: ProjectScope | null
  brand_aliases?: string[]
  missing_sources?: ContractListItem[]
  missing_reasons?: ContractListItem[]
  invalid_fields?: ContractListItem[]
  evidence_counts?: Record<string, number>
  identity_diagnostics?: IdentityDiagnostics | null
  formula_diagnostics?: FormulaDiagnostics | null
  request_id?: string | null
  data_freshness?: DataFreshness | null
}

export interface MetricContractFields {
  metric_key?: string | null
  unit?: string | null
  value_scale?: string | null
  value_range?: ValueRange | null
  denominator_label?: string | null
  numerator_label?: string | null
  source?: string | null
  formula_status?: string | null
}

function lower(value: string | null | undefined): string {
  return String(value || '').toLowerCase()
}

function round1(value: number): number {
  return Math.round((value + Number.EPSILON) * 10) / 10
}

export function asFiniteNumber(value: unknown): number | null {
  const next = Number(value)
  return Number.isFinite(next) ? next : null
}

export function formatRatioLikeForPercent(
  value: unknown,
  valueScale?: string | null,
  unit?: string | null,
): number {
  const raw = asFiniteNumber(value)
  if (raw == null) return 0
  const scale = lower(valueScale)
  const normalizedUnit = lower(unit)
  if (scale === 'percent' || normalizedUnit === 'percent') return round1(raw)
  if (scale === 'decimal' || normalizedUnit === 'ratio') return round1(raw * 100)
  return round1(Math.abs(raw) <= 1 ? raw * 100 : raw)
}

export function normalizeRatioLike(
  value: unknown,
  valueScale?: string | null,
  unit?: string | null,
): number {
  const raw = asFiniteNumber(value)
  if (raw == null) return 0
  const scale = lower(valueScale)
  const normalizedUnit = lower(unit)
  if (scale === 'percent' || normalizedUnit === 'percent') return raw / 100
  if (scale === 'decimal' || normalizedUnit === 'ratio') return raw
  return Math.abs(raw) > 1 ? raw / 100 : raw
}

export function normalizeScore0To100(
  value: unknown,
  valueScale?: string | null,
): number {
  const raw = asFiniteNumber(value)
  if (raw == null) return 0
  const scale = lower(valueScale)
  if (scale === 'decimal') return Math.round(raw * 100)
  return Math.round(Math.abs(raw) <= 1 ? raw * 100 : raw)
}

export function normalizeSentimentRaw(
  value: unknown,
  valueScale?: string | null,
  unit?: string | null,
): number {
  const raw = asFiniteNumber(value)
  if (raw == null) return 0
  const scale = lower(valueScale)
  const normalizedUnit = lower(unit)
  if (scale === 'percent' || normalizedUnit === 'percent' || scale === 'score_0_100') {
    return raw / 100
  }
  if (!scale && !normalizedUnit && Math.abs(raw) > 1) return raw / 100
  return raw
}

export function contractItemLabel(item: ContractListItem): string {
  if (typeof item === 'string') return item
  return (
    item.source ||
    item.field ||
    item.reason ||
    item.owner_issue ||
    JSON.stringify(item)
  )
}
