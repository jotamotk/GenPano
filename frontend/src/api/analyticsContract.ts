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
  numerator?: number | null
  denominator?: number | null
  analyzer_coverage?: AnalyzerCoverage | null
  [key: string]: unknown
}

export interface AnalyzerCoverage {
  eligible_response_count?: number | null
  analyzed_response_count?: number | null
  missing_response_count?: number | null
  failed_response_count?: number | null
  analyzer_version?: string | null
}

export interface DataFreshness {
  generated_at?: string | null
}

export interface SelectedAnalyticsFilters {
  project?: string | null
  project_id?: string | null
  brand_id?: number | string | null
  from?: string | null
  to?: string | null
  engine?: string | null
  segment_id?: string | null
  profile_id?: string | null
  [key: string]: unknown
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
  analyzer_coverage?: AnalyzerCoverage | null
  selected_filters?: SelectedAnalyticsFilters | null
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
  numerator?: number | null
  denominator?: number | null
  analyzer_coverage?: AnalyzerCoverage | null
}

export type MetricTrustTone = 'ok' | 'partial' | 'missing'

export interface MetricTrustState {
  tone: MetricTrustTone
  label: string
  summary: string
  details: string[]
  reasonLabels: string[]
  canShowValue: boolean
}

export interface MetricTrustInput extends MetricFormulaEvidence {
  metricKey?: string | null
  value?: unknown
  analyzer_coverage?: AnalyzerCoverage | null
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

const REASON_LABELS: Record<string, string> = {
  missing_analyzer_rows: 'Analysis coverage missing',
  insufficient_coverage: 'Coverage incomplete',
  missing_competitive_extraction: 'Competitor evidence incomplete',
  target_only_sov: 'Target-only SoV',
  unresolved_citation_attribution: 'Citation attribution unresolved',
  missing_sentiment_quote: 'Sentiment quote missing',
  missing_sentiment_driver_quote: 'Sentiment quote missing',
  valid_zero_proof_missing: 'Valid zero proof missing',
  valid_zero: 'Valid zero',
  geo_score_daily: 'PANO/GEO rows missing',
  no_aggregate_rows: 'PANO/GEO rows missing',
}

function uniqueText(items: Array<string | null | undefined>): string[] {
  return Array.from(new Set(items.map((item) => String(item || '').trim()).filter(Boolean)))
}

export function metricReasonLabel(reason: string | null | undefined): string {
  const text = String(reason || '').trim()
  if (!text) return ''
  const normalized = text.toLowerCase()
  return REASON_LABELS[normalized] || text
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function coverageIsPartial(coverage: AnalyzerCoverage | null | undefined): boolean {
  const eligible = asFiniteNumber(coverage?.eligible_response_count)
  const analyzed = asFiniteNumber(coverage?.analyzed_response_count)
  const missing = asFiniteNumber(coverage?.missing_response_count)
  if (eligible != null && analyzed != null && eligible > analyzed) return true
  return missing != null && missing > 0
}

function coverageDetails(coverage: AnalyzerCoverage | null | undefined): string[] {
  const eligible = asFiniteNumber(coverage?.eligible_response_count)
  const analyzed = asFiniteNumber(coverage?.analyzed_response_count)
  const missing = asFiniteNumber(coverage?.missing_response_count)
  const failed = asFiniteNumber(coverage?.failed_response_count)
  const details: string[] = []
  if (eligible != null && analyzed != null) {
    details.push(`${analyzed.toLocaleString()} of ${eligible.toLocaleString()} analyzed`)
  }
  if (missing != null && missing > 0) details.push(`${missing.toLocaleString()} missing`)
  if (failed != null && failed > 0) details.push(`${failed.toLocaleString()} failed`)
  if (coverage?.analyzer_version) details.push(`Analyzer ${coverage.analyzer_version}`)
  return details
}

function trustSummary(reasonLabels: string[], tone: MetricTrustTone): string {
  if (reasonLabels.includes('Valid zero') && tone === 'ok') {
    return 'Zero is supported by complete evidence.'
  }
  if (reasonLabels.includes('Coverage incomplete') || reasonLabels.includes('Analysis coverage missing')) {
    return 'Coverage incomplete: metric is waiting for more analyzed answers.'
  }
  if (reasonLabels.includes('Competitor evidence incomplete')) {
    return 'Competitor evidence is not ready for this metric.'
  }
  if (reasonLabels.includes('Target-only SoV')) {
    return 'SoV has target evidence but no competitive denominator yet.'
  }
  if (reasonLabels.includes('Citation attribution unresolved')) {
    return 'Citation attribution is not ready for this metric.'
  }
  if (reasonLabels.includes('Sentiment quote missing')) {
    return 'Sentiment needs source quotes before this metric is trusted.'
  }
  if (reasonLabels.includes('PANO/GEO rows missing')) {
    return 'PANO/GEO readiness is waiting for aggregate rows.'
  }
  return tone === 'missing'
    ? 'Required evidence is not available yet.'
    : 'Metric evidence is partial.'
}

export function buildMetricTrustState(input: MetricTrustInput | null | undefined): MetricTrustState {
  const status = lower(input?.formula_status || input?.status)
  const coverage = input?.analyzer_coverage
  const reasons = uniqueText([
    ...(input?.reason_codes ?? []),
    ...(input?.missing_inputs ?? []),
  ])
  if (coverageIsPartial(coverage)) {
    reasons.push('insufficient_coverage')
    if ((asFiniteNumber(coverage?.missing_response_count) ?? 0) > 0) {
      reasons.push('missing_analyzer_rows')
    }
  }
  const reasonLabels = uniqueText(reasons.map(metricReasonLabel))
  const ok = isOkFormulaStatus(status)
  const validZero = reasonLabels.includes('Valid zero')
  const numericValue = asFiniteNumber(input?.value)
  const hasZeroProof = validZero || (input?.numerator != null && input?.denominator != null)
  const zeroWithoutProof = ok && numericValue === 0 && !hasZeroProof
  if (zeroWithoutProof) {
    reasonLabels.push('Valid zero proof missing')
  }
  const missing =
    !ok &&
    (status === 'missing' ||
      status === 'empty' ||
      status === 'no_evidence' ||
      status === 'missing_required_inputs')
  const tone: MetricTrustTone = ok && !coverageIsPartial(coverage) && !zeroWithoutProof
    ? 'ok'
    : missing && reasonLabels.length === 0
      ? 'missing'
      : missing && !coverageIsPartial(coverage)
        ? 'missing'
        : 'partial'
  const canShowValue = tone === 'ok'
  const details = [
    ...coverageDetails(coverage),
    input?.numerator != null || input?.denominator != null
      ? `${input?.numerator ?? '--'} / ${input?.denominator ?? '--'} evidence`
      : '',
  ].filter(Boolean)
  const label = validZero && tone === 'ok'
    ? 'Valid zero'
    : tone === 'ok'
      ? 'Ready'
      : tone === 'missing'
        ? 'Unavailable'
        : 'Needs review'

  return {
    tone,
    label,
    summary: trustSummary(reasonLabels, tone),
    details,
    reasonLabels,
    canShowValue,
  }
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
