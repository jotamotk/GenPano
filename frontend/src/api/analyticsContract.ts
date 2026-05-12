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

export interface MetricFormulaEvidence extends MetricContractFields {
  status?: string | null
  reason_codes?: string[]
  missing_inputs?: string[]
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
  missing_inputs?: ContractListItem[]
  missing_reasons?: ContractListItem[]
  invalid_fields?: ContractListItem[]
  evidence_counts?: Record<string, number>
  identity_diagnostics?: IdentityDiagnostics | null
  formula_diagnostics?: FormulaDiagnostics | null
  formula_status?: string | null
  metric_formula_evidence?: Record<string, MetricFormulaEvidence>
  request_id?: string | null
  data_freshness?: DataFreshness | null
}

export interface MetricContractFields {
  metric_key?: string | null
  state?: AnalyticsState | null
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
  if (value === null || value === undefined || value === '') return null
  const next = Number(value)
  return Number.isFinite(next) ? next : null
}

export function isOkAnalyticsState(state: AnalyticsState | null | undefined): boolean {
  const normalized = lower(state)
  return normalized === 'ok'
}

export function isUsableAnalyticsEndpointState(state: AnalyticsState | null | undefined): boolean {
  const normalized = lower(state)
  return !normalized || normalized === 'ok' || normalized === 'partial'
}

function hasUsableMetricEvidence(fields: MetricContractFields | null | undefined): boolean {
  if (!fields) return false
  const metricState = lower(fields.state)
  const formulaStatus = lower(fields.formula_status)
  if (formulaStatus) return isOkFormulaStatus(fields.formula_status)
  return metricState === 'ok'
}

export function isOkFormulaStatus(status: string | null | undefined): boolean {
  const normalized = lower(status)
  if (!normalized) return false
  return normalized === 'ok' ||
    normalized === 'valid' ||
    normalized === 'ready' ||
    normalized === 'complete' ||
    normalized === 'computed' ||
    normalized === 'formula_ok'
}

export function canUseContractMetricValue(
  state: AnalyticsState | null | undefined,
  fields: MetricContractFields | null | undefined,
): boolean {
  if (!isUsableAnalyticsEndpointState(state)) return false
  return hasUsableMetricEvidence(fields)
}

const METRIC_EVIDENCE_ALIASES: Record<string, string[]> = {
  mention_rate: ['mention_rate', 'coverage', 'visibility'],
  avg_mention_rate: ['mention_rate', 'coverage', 'visibility'],
  sov: ['sov'],
  avg_sov: ['sov'],
  sentiment: ['sentiment'],
  avg_sentiment: ['sentiment'],
  citation: ['citation', 'citations'],
  citation_rate: ['citation', 'citations'],
  citation_share: ['citation', 'citations'],
  rank: ['rank', 'pano_geo'],
  avg_position_rank: ['rank', 'pano_geo'],
  trend: ['trend', 'trend_30d'],
  trend_30d: ['trend_30d', 'trend'],
  geo_score: ['pano_geo', 'geo_score', 'pano_score'],
  avg_geo_score: ['pano_geo', 'geo_score', 'pano_score'],
  pano_score: ['pano_geo', 'geo_score', 'pano_score'],
  product: ['topic_product', 'product'],
  topic: ['topic_product', 'topic'],
}

function uniqueStrings(items: Array<unknown>): string[] {
  return Array.from(
    new Set(
      items
        .flatMap((item) => (Array.isArray(item) ? item : [item]))
        .filter((item) => item !== null && item !== undefined && item !== '')
        .map((item) => contractItemLabel(item as ContractListItem))
        .filter(Boolean),
    ),
  )
}

export function metricEvidenceFor(
  source: AnalyticsContractMetadata | null | undefined,
  metricKeys: string | string[],
): MetricFormulaEvidence | null {
  const evidence = source?.metric_formula_evidence
  if (!evidence) return null
  const keys = Array.isArray(metricKeys) ? metricKeys : [metricKeys]
  const expanded = keys.flatMap((key) => {
    const normalized = lower(key)
    return [normalized, ...(METRIC_EVIDENCE_ALIASES[normalized] ?? [])]
  })
  const wanted = new Set(expanded.filter(Boolean))
  for (const [key, item] of Object.entries(evidence)) {
    if (wanted.has(lower(key))) return item
  }
  return null
}

export function canUseMetricEvidence(
  source: AnalyticsContractMetadata | null | undefined,
  metricKeys: string | string[],
): boolean {
  if (!source || !isUsableAnalyticsEndpointState(source.state)) return false
  const evidence = metricEvidenceFor(source, metricKeys)
  if (evidence) return canUseContractMetricValue(source.state, evidence)
  return false
}

export function contractEvidenceReasons(
  source: AnalyticsContractMetadata | null | undefined,
  metricKeys?: string | string[],
): string[] {
  if (!source) return []
  const evidence = metricKeys ? metricEvidenceFor(source, metricKeys) : null
  return uniqueStrings([
    evidence?.reason_codes,
    evidence?.missing_inputs,
    source.missing_reasons,
    source.missing_inputs,
    source.missing_sources,
  ])
}

export function asContractMetricNumber(
  value: unknown,
  state: AnalyticsState | null | undefined,
  fields: MetricContractFields | null | undefined,
): number | null {
  if (!canUseContractMetricValue(state, fields)) return null
  return asFiniteNumber(value)
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

export function formatRatioLikeForPercentOrNull(
  value: unknown,
  valueScale?: string | null,
  unit?: string | null,
): number | null {
  const raw = asFiniteNumber(value)
  if (raw == null) return null
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

export function normalizeRatioLikeOrNull(
  value: unknown,
  valueScale?: string | null,
  unit?: string | null,
): number | null {
  const raw = asFiniteNumber(value)
  if (raw == null) return null
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

export function normalizeScore0To100OrNull(
  value: unknown,
  valueScale?: string | null,
): number | null {
  const raw = asFiniteNumber(value)
  if (raw == null) return null
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

export function normalizeSentimentRawOrNull(
  value: unknown,
  valueScale?: string | null,
  unit?: string | null,
): number | null {
  const raw = asFiniteNumber(value)
  if (raw == null) return null
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
