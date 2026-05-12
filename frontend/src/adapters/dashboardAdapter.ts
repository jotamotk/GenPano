/**
 * dashboardAdapter — convert backend responses into the prop shapes that
 * BrandPanoramaPanel's existing chart sub-components consume.
 *
 * Strategy: keep the rich PRD viz components untouched; only inject
 * backend-derived data via optional override props. In live mode, missing
 * backend evidence stays empty/null instead of borrowing mock truth.
 */

import type { BrandOverviewOut } from '../api/brandOverview'
import type {
  CompetitorMetricsOut,
  CompetitorTrendsOut,
  MetricsOut,
} from '../api/brandMetrics'
import {
  asFiniteNumber,
  asContractMetricNumber,
  canUseContractMetricValue,
  contractItemLabel,
  formatRatioLikeForPercent,
  formatRatioLikeForPercentOrNull,
  normalizeRatioLikeOrNull,
  normalizeScore0To100OrNull,
  normalizeSentimentRawOrNull,
  type AnalyticsContractMetadata,
  type ContractListItem,
  type MetricContractFields,
} from '../api/analyticsContract'
import type { DiagnosticOut } from '../api/diagnostics'
import type { IndustryAvgGeoOut } from '../api/industries'

export interface PrimaryBrandAdapted {
  id: string
  name: string
  nameZh?: string
  nameEn: string
  panoScore: number | null
  /** decimal 0..1 */
  mentionRate: number | null
  /** -1..1 */
  sentiment: number | null
  /** percent 0..100 */
  sov?: number | null
  ranking: number | null
  industryId: string
  change?: string
}

export interface CompetitorAdapted {
  id: string
  name: string
  nameZh?: string
  nameEn: string
  panoScore: number | null
  /** decimal 0..1 */
  mentionRate?: number | null
  /** percent 0..100 */
  sov?: number | null
  /** -1..1 */
  sentiment?: number | null
  industryId: string
}

export interface SovEntry {
  name: string
  value: number
}

export interface BubbleEntry {
  brand: string
  sov: number
  sentiment: number
  mentions: number
}

export interface TrendPoint {
  day: number
  panoScore: number | null
  mentionRate: number | null
  sentiment: number | null
}

export interface DiagnosticAdapted {
  id: string
  severity: 'P0' | 'P1' | 'P2' | 'P3'
  title: string
  engine: string
  type: string
}

type ContractKpiCard = BrandOverviewOut['kpi_cards'][number]

function findMetricDefinition(
  definitions: CompetitorMetricsOut['metric_definitions'] | undefined,
  keys: string[],
): MetricContractFields | null {
  if (!definitions) return null
  const wanted = new Set(keys.map((key) => key.toLowerCase()))
  for (const [key, definition] of Object.entries(definitions)) {
    const metricKey = String(definition?.metric_key || '').toLowerCase()
    if (wanted.has(key.toLowerCase()) || (metricKey && wanted.has(metricKey))) {
      return definition
    }
  }
  return null
}

function normalizeCompetitorMentionRate(
  metrics: CompetitorMetricsOut,
  value: unknown,
): number | null {
  const definition = findMetricDefinition(
    metrics.metric_definitions,
    ['avg_mention_rate', 'mention_rate'],
  )
  if (!canUseContractMetricValue(metrics.state, definition)) return null
  return normalizeRatioLikeOrNull(value, definition?.value_scale, definition?.unit)
}

function normalizeCompetitorSov(
  metrics: CompetitorMetricsOut,
  value: unknown,
): number | null {
  const definition = findMetricDefinition(
    metrics.metric_definitions,
    ['avg_sov', 'sov'],
  )
  if (!canUseContractMetricValue(metrics.state, definition)) return null
  return formatRatioLikeForPercentOrNull(value, definition?.value_scale, definition?.unit)
}

function normalizeCompetitorSentiment(
  metrics: CompetitorMetricsOut,
  value: unknown,
): number | null {
  const definition = findMetricDefinition(
    metrics.metric_definitions,
    ['avg_sentiment', 'sentiment'],
  )
  if (!canUseContractMetricValue(metrics.state, definition)) return null
  return normalizeSentimentRawOrNull(value, definition?.value_scale, definition?.unit)
}

function labelText(card: ContractKpiCard): string {
  return `${card.label_zh || ''} ${card.label_en || ''}`.toLowerCase()
}

function findKpiCard(
  cards: BrandOverviewOut['kpi_cards'],
  metricKeys: string[],
  labelMatchers: string[] = [],
): ContractKpiCard | null {
  const keys = new Set(metricKeys.map((key) => key.toLowerCase()))
  for (const card of cards) {
    const metricKey = String(card.metric_key || '').toLowerCase()
    if (metricKey && keys.has(metricKey)) return card
  }
  for (const card of cards) {
    const labels = labelText(card)
    for (const matcher of labelMatchers) {
      if (labels.includes(matcher.toLowerCase())) return card
    }
  }
  return null
}

function kpiNumber(card: ContractKpiCard | null, state?: BrandOverviewOut['state']): number | null {
  return card ? asContractMetricNumber(card.value, state, card) : null
}

export function adaptOverviewToPrimary(
  overview: BrandOverviewOut,
): PrimaryBrandAdapted | null {
  if (overview.brand_id == null && !overview.brand_name?.trim()) {
    return null
  }
  if (!Array.isArray(overview.kpi_cards)) {
    return null
  }
  const panoCard = findKpiCard(
    overview.kpi_cards,
    ['pano_score', 'geo_score', 'avg_geo_score'],
    ['geo', 'pano', 'score'],
  )
  const mentionCard = findKpiCard(
    overview.kpi_cards,
    ['mention_rate', 'avg_mention_rate'],
    ['mention', '提及'],
  )
  const sentimentCard = findKpiCard(
    overview.kpi_cards,
    ['sentiment', 'avg_sentiment'],
    ['sentiment', '情感'],
  )
  const sovCard = findKpiCard(
    overview.kpi_cards,
    ['sov', 'share_of_voice'],
    ['sov', 'share of voice'],
  )
  const rankCard = findKpiCard(
    overview.kpi_cards,
    ['rank', 'avg_position_rank'],
    ['rank', 'position', '排名'],
  )
  const id = String(overview.brand_id ?? overview.brand_name)
  const name = overview.brand_name ?? `Brand #${overview.brand_id}`

  return {
    id,
    name,
    nameZh: name,
    nameEn: name,
    panoScore: normalizeScore0To100OrNull(
      kpiNumber(panoCard, overview.state),
      panoCard?.value_scale,
    ),
    mentionRate: normalizeRatioLikeOrNull(
      kpiNumber(mentionCard, overview.state),
      mentionCard?.value_scale,
      mentionCard?.unit,
    ),
    sentiment: normalizeSentimentRawOrNull(
      kpiNumber(sentimentCard, overview.state),
      sentimentCard?.value_scale,
      sentimentCard?.unit,
    ),
    sov: formatRatioLikeForPercentOrNull(
      kpiNumber(sovCard, overview.state),
      sovCard?.value_scale,
      sovCard?.unit,
    ),
    ranking: kpiNumber(rankCard, overview.state) == null
      ? null
      : Math.max(1, Math.round(kpiNumber(rankCard, overview.state) as number)),
    industryId: String(overview.industry_id ?? ''),
    change: undefined,
  }
}

export function adaptOverviewToSov(overview: BrandOverviewOut): SovEntry[] {
  void overview
  return []
}

export function adaptCompetitorMetricsToList(
  metrics: CompetitorMetricsOut,
): { primary: PrimaryBrandAdapted | null; competitors: CompetitorAdapted[] } {
  const buildPrimary = (
    row: NonNullable<CompetitorMetricsOut['primary']>,
  ): PrimaryBrandAdapted => {
    const name = row.brand_name ?? row.brand_key ?? `Brand #${row.brand_id ?? '?'}`
    return {
      id: String(row.brand_id ?? row.brand_key ?? name),
      name,
      nameZh: name,
      nameEn: name,
      panoScore: canUseContractMetricValue(
        metrics.state,
        findMetricDefinition(metrics.metric_definitions, ['avg_geo_score', 'geo_score', 'pano_score']),
      ) && row.avg_geo_score != null
        ? Math.round(row.avg_geo_score)
        : null,
      mentionRate: normalizeCompetitorMentionRate(metrics, row.avg_mention_rate),
      sov: normalizeCompetitorSov(metrics, row.avg_sov),
      sentiment: normalizeCompetitorSentiment(metrics, row.avg_sentiment),
      ranking: null,
      industryId: '',
    }
  }

  const buildComp = (row: CompetitorMetricsOut['competitors'][number]): CompetitorAdapted => {
    const name = row.brand_name ?? row.brand_key ?? `Brand #${row.brand_id ?? '?'}`
    return {
      id: String(row.brand_id ?? row.brand_key ?? name),
      name,
      nameZh: name,
      nameEn: name,
      panoScore: canUseContractMetricValue(
        metrics.state,
        findMetricDefinition(metrics.metric_definitions, ['avg_geo_score', 'geo_score', 'pano_score']),
      ) && row.avg_geo_score != null
        ? Math.round(row.avg_geo_score)
        : null,
      mentionRate: normalizeCompetitorMentionRate(metrics, row.avg_mention_rate),
      sov: normalizeCompetitorSov(metrics, row.avg_sov),
      sentiment: normalizeCompetitorSentiment(metrics, row.avg_sentiment),
      industryId: '',
    }
  }
  const competitors = Array.isArray(metrics.competitors) ? metrics.competitors : []

  return {
    primary: metrics.primary ? buildPrimary(metrics.primary) : null,
    competitors: competitors.map(buildComp),
  }
}

export function adaptCompetitorMetricsToSov(
  metrics: CompetitorMetricsOut,
): SovEntry[] {
  const all = [
    ...(metrics.primary ? [metrics.primary] : []),
    ...(Array.isArray(metrics.competitors) ? metrics.competitors : []),
  ]
  const filtered = all
    .map((row) => ({
      row,
      value: normalizeCompetitorSov(metrics, row.avg_sov),
    }))
    .filter((item) => item.value != null && item.value > 0)
  if (filtered.length === 0) return []
  const top = filtered
    .map(({ row, value }) => ({
      name: row.brand_name ?? row.brand_key ?? `Brand #${row.brand_id ?? '?'}`,
      value: value as number,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 6)
  return top
}

export function adaptCompetitorMetricsToBubble(
  metrics: CompetitorMetricsOut,
): BubbleEntry[] {
  const all = [
    ...(metrics.primary ? [metrics.primary] : []),
    ...(Array.isArray(metrics.competitors) ? metrics.competitors : []),
  ]
  return all
    .map((row) => ({
      row,
      sov: normalizeCompetitorSov(metrics, row.avg_sov),
      sentiment: normalizeCompetitorSentiment(metrics, row.avg_sentiment),
    }))
    .filter((item) => item.sov != null && item.sentiment != null)
    .map(({ row, sov, sentiment }) => ({
      brand: row.brand_name ?? row.brand_key ?? `Brand #${row.brand_id ?? '?'}`,
      sov: sov as number,
      sentiment: sentiment as number,
      mentions: row.co_mention_count ?? 0,
    }))
}

export function adaptOverviewToTrend(
  overview: BrandOverviewOut,
): TrendPoint[] {
  // Merge geo / sov / sentiment series by date into one row per day
  const geoSeries = Array.isArray(overview.geo_score_30d) ? overview.geo_score_30d : []
  const sovSeries = Array.isArray(overview.sov_30d) ? overview.sov_30d : []
  const sentimentSeries = Array.isArray(overview.sentiment_30d) ? overview.sentiment_30d : []
  const dates = new Set<string>()
  for (const p of geoSeries) dates.add(p.date)
  for (const p of sovSeries) dates.add(p.date)
  for (const p of sentimentSeries) dates.add(p.date)
  const sorted = Array.from(dates).sort()
  const lookup = (
    arr: { date: string; value: number }[],
    d: string,
  ): number | null => {
    const found = arr.find((p) => p.date === d)
    return found ? found.value : null
  }
  return sorted.map((d, idx) => {
    const day = idx + 1
    const geo = lookup(geoSeries, d)
    const sent = lookup(sentimentSeries, d)
    return {
      day,
      panoScore: geo == null ? null : Math.round(geo),
      // Mention rate is supplied by /metrics. Do not reuse SoV as a proxy.
      mentionRate: null,
      sentiment: sent,
    }
  })
}

export function adaptDiagnostics(
  items: DiagnosticOut[],
): DiagnosticAdapted[] {
  return items
    .filter((d) => d.severity === 'P0' || d.severity === 'P1')
    .slice(0, 3)
    .map((d) => ({
      id: d.id,
      severity: d.severity,
      title: d.title,
      engine: '',
      type: d.type,
    }))
}

export type AnalyticsNoticeTone = 'loading' | 'partial' | 'empty' | 'error' | 'auth' | 'info'

export interface AnalyticsContractNotice {
  tone: AnalyticsNoticeTone
  title: string
  stateReason?: string | null
  details: string[]
  requestId?: string
}

export interface AnalyticsContractNoticeInput {
  isLive: boolean
  liveProjectId: string | null | undefined
  overview?: (BrandOverviewOut & AnalyticsContractMetadata) | null
  metrics?: (MetricsOut & AnalyticsContractMetadata) | null
  isLoading?: boolean
  error?: unknown
}

function errorField(error: unknown, key: string): unknown {
  return error && typeof error === 'object' ? (error as Record<string, unknown>)[key] : undefined
}

function contractList(items: ContractListItem[] | undefined): string[] {
  return (items ?? []).map(contractItemLabel).filter(Boolean)
}

function pushUnique(details: string[], value: string | null | undefined): void {
  if (value && !details.includes(value)) details.push(value)
}

function metricContractDetails(overview: BrandOverviewOut | null | undefined): string[] {
  const details: string[] = []
  for (const card of overview?.kpi_cards ?? []) {
    const key = card.metric_key
    if (key !== 'mention_rate' && key !== 'sov') continue
    const pieces = [
      `${key} denominator: ${card.denominator_label || 'unspecified'}`,
      card.value_scale ? `scale: ${card.value_scale}` : '',
      card.formula_status ? `formula: ${card.formula_status}` : '',
    ].filter(Boolean)
    details.push(pieces.join('; '))
  }
  return details
}

export function buildAnalyticsContractNotice(
  input: AnalyticsContractNoticeInput,
): AnalyticsContractNotice | null {
  if (!input.isLive) return null
  if (input.isLoading) {
    return {
      tone: 'loading',
      title: 'Loading analytics',
      details: input.liveProjectId ? [`Project ${input.liveProjectId}`] : [],
    }
  }

  if (input.error) {
    const status = Number(errorField(input.error, 'status') ?? 0)
    const requestId = String(
      errorField(input.error, 'requestId') ||
      errorField(input.error, 'request_id') ||
      '',
    )
    const path = String(errorField(input.error, 'path') || '')
    const details = [
      status ? `status ${status}` : '',
      requestId ? `request_id ${requestId}` : '',
      path,
    ].filter(Boolean)
    return {
      tone: status === 401 || status === 403 ? 'auth' : 'error',
      title: status === 401 || status === 403
        ? 'Analytics access needs authorization'
        : 'Analytics failed to load',
      details,
      requestId,
    }
  }

  const overview = input.overview
  const metrics = input.metrics
  if (!overview && !metrics) return null

  const source = overview ?? metrics
  const state = String(source?.state || 'ok')
  const stateReason = source?.state_reason ?? null
  const details: string[] = []
  pushUnique(details, stateReason || undefined)
  pushUnique(details, source?.state_detail || undefined)
  for (const item of contractList(source?.missing_sources)) {
    pushUnique(details, item)
  }
  for (const item of contractList(source?.missing_reasons)) {
    pushUnique(details, item)
  }
  for (const item of contractList(source?.invalid_fields)) {
    pushUnique(details, item)
  }
  for (const item of metricContractDetails(overview)) {
    pushUnique(details, item)
  }

  const projectScope = source?.project_scope
  const projectId = projectScope?.project_id || input.liveProjectId
  if (projectScope && projectScope.exists === false) {
    pushUnique(details, projectId ? `Project ${projectId}` : null)
    pushUnique(details, projectScope.missing_reason || undefined)
  }

  const identity = source?.identity_diagnostics
  if (identity?.canonical_alias_repair_count) {
    pushUnique(details, `alias repairs ${identity.canonical_alias_repair_count}`)
  }
  for (const ownerId of identity?.raw_text_owner_brand_ids ?? []) {
    pushUnique(details, `owner brand ${ownerId}`)
  }

  const counts = source?.evidence_counts ?? {}
  if (counts.eligible_response_count != null) {
    pushUnique(details, `eligible responses ${counts.eligible_response_count}`)
  }
  if (counts.brand_mentioned_response_count != null) {
    pushUnique(details, `brand-mentioned responses ${counts.brand_mentioned_response_count}`)
  }

  if (state === 'partial') {
    return {
      tone: 'partial',
      title: 'Partial analytics',
      stateReason,
      details,
      requestId: source?.request_id || undefined,
    }
  }
  if (state === 'empty') {
    const projectPending =
      projectScope?.exists === false ||
      String(stateReason || '').includes('project')
    return {
      tone: 'empty',
      title: projectPending ? 'Project context pending' : 'No analytics data yet',
      stateReason,
      details,
      requestId: source?.request_id || undefined,
    }
  }
  if (details.some((detail) => detail.includes('formula_pending') || detail.includes('upstream_formula'))) {
    return {
      tone: 'info',
      title: 'Formula provenance pending',
      stateReason,
      details,
      requestId: source?.request_id || undefined,
    }
  }
  return null
}


// ── Sparkline arrays (for KpiSparklineSummary in BrandPanoramaPanel) ──
//
// Each sparkline is a number[]; positions correspond to days in
// chronological order. We pull these from the /metrics endpoint which
// returns a series-per-metric shape with date-aligned points.

export interface SparklineSet {
  mention: number[]
  sov: number[]
  sentiment: number[]
  citation: number[]
  rank: number[]
}

export function adaptMetricsToSparklines(metrics: MetricsOut): SparklineSet {
  const empty: SparklineSet = {
    mention: [],
    sov: [],
    sentiment: [],
    citation: [],
    rank: [],
  }
  if (!Array.isArray(metrics?.series)) return empty

  const find = (name: string) => metrics.series.find((s) => s.metric === name)

  const mention = find('mention_rate')
  const sov = find('sov')
  const sentiment = find('sentiment')
  const citation = find('citation')
  const rank = find('rank')
  const percentPoints = (series: MetricsOut['series'][number] | undefined) =>
    series && Array.isArray(series.points) && canUseContractMetricValue(metrics.state, series)
      ? series.points
          .map((p) => formatRatioLikeForPercentOrNull(p.value, series.value_scale, series.unit))
          .filter((value): value is number => value != null)
      : []
  const rawPoints = (series: MetricsOut['series'][number] | undefined) =>
    series && Array.isArray(series.points) && canUseContractMetricValue(metrics.state, series)
      ? series.points
          .map((p) => asFiniteNumber(p.value))
          .filter((value): value is number => value != null)
          .map((value) => +value.toFixed(1))
      : []

  return {
    mention: percentPoints(mention),
    sov: percentPoints(sov),
    sentiment: sentiment && Array.isArray(sentiment.points) && canUseContractMetricValue(metrics.state, sentiment)
      ? sentiment.points
          .map((p) => normalizeSentimentRawOrNull(p.value, sentiment.value_scale, sentiment.unit))
          .filter((value): value is number => value != null)
          .map((value) => +(value * 100).toFixed(1))
      : [],
    citation: percentPoints(citation),
    rank: rawPoints(rank),
  }
}


// ── Per-competitor 30d trend (replaces synthetic sin lines on PanoTrendChart) ──
//
// Returns trend data shaped like the legacy mock TREND_DATA:
//   [{ day: 1, panoScore: <primary>, mentionRate, sentiment, <comp_id>: score }]
// PanoTrendChart consumes `trendData[d.day]: { primaryName: panoScore, c1.name: score, ... }`
// — but our backend gives us per-brand series, so we merge them by date.

export interface TrendRowAdapted {
  day: number
  panoScore: number | null
  mentionRate: number | null
  sentiment: number | null
  // dynamic competitor brand scores keyed by brand_name
  [brand: string]: number | string | null
}

export interface TrendLineAdapted {
  key: string
  label: string
  color: string
  area?: boolean
  dashed?: boolean
}

export interface VisibilityPanoTrendAdapted {
  rows: Array<TrendRowAdapted & { name: string }>
  lines: TrendLineAdapted[]
}

function metricSeriesPercentValue(
  metrics: MetricsOut | null | undefined,
  metric: MetricsOut['series'][number]['metric'],
  date: string,
): number | null {
  if (!Array.isArray(metrics?.series)) return null
  const series = metrics?.series?.find((item) => item.metric === metric)
  if (series && !canUseContractMetricValue(metrics?.state, series)) return null
  const point = Array.isArray(series?.points) ? series?.points.find((item) => item.date === date) : null
  if (point?.value == null) return null
  return formatRatioLikeForPercent(point.value, series?.value_scale, series?.unit)
}

export function adaptCompetitorTrendsToTrendData(
  trends: CompetitorTrendsOut,
  overviewTrend: BrandOverviewOut | null,
  metricsTrend: MetricsOut | null = null,
): TrendRowAdapted[] {
  if (!canUseContractMetricValue(trends.state, trends.metric_definition)) return []
  if (!Array.isArray(trends.series)) return []
  // Find primary series
  const primarySeries = trends.series.find((s) => s.is_primary)
  const competitorSeries = trends.series.filter((s) => !s.is_primary)

  // Use primary's date list as the canonical timeline (or overview's if primary missing)
  const dateList: string[] = primarySeries
    ? primarySeries.points.map((p) => p.date)
    : overviewTrend
      ? overviewTrend.geo_score_30d.map((p) => p.date)
      : []

  if (dateList.length === 0) return []

  return dateList.map((date, idx) => {
    const row: TrendRowAdapted = {
      day: idx + 1,
      panoScore: null,
      mentionRate: metricSeriesPercentValue(metricsTrend, 'mention_rate', date),
      sentiment: null,
    }
    // Primary panoScore
    if (primarySeries) {
      const p = primarySeries.points.find((q) => q.date === date)
      row.panoScore = p?.value != null ? Math.round(p.value) : null
    } else if (overviewTrend) {
      const p = overviewTrend.geo_score_30d.find((q) => q.date === date)
      row.panoScore = p?.value != null ? Math.round(p.value) : null
    }
    // mentionRate comes from /metrics; overview SoV is a separate contract field.
    if (overviewTrend) {
      const sent = overviewTrend.sentiment_30d.find((q) => q.date === date)
      row.sentiment = sent?.value ?? null
    }
    // Per-competitor scores keyed by brand name (or fallback id)
    for (const comp of competitorSeries) {
      const key =
        comp.brand_name && comp.brand_name.length > 0
          ? comp.brand_name
          : comp.brand_key ?? `Brand #${comp.brand_id ?? '?'}`
      const cp = comp.points.find((q) => q.date === date)
      row[key] = cp?.value != null ? Math.round(cp.value) : null
    }
    return row
  })
}


// Visibility page PANO trend from the competitor geo trend contract.
const VISIBILITY_TREND_RESERVED_KEYS = new Set([
  'day',
  'name',
  'panoScore',
  'mentionRate',
  'sentiment',
])

const VISIBILITY_COMPETITOR_TREND_COLORS = [
  'var(--color-chart-3)',
  'var(--color-chart-7)',
  'var(--color-chart-4)',
  'var(--color-chart-5)',
  'var(--color-chart-line-grid)',
]

function rowHasValue(row: TrendRowAdapted, key: string): boolean {
  return typeof row[key] === 'number' && Number.isFinite(row[key] as number)
}

export function adaptCompetitorTrendsToVisibilityPanoTrend(
  trends: CompetitorTrendsOut | null | undefined,
  primaryLabel: string,
): VisibilityPanoTrendAdapted {
  if (!trends) return { rows: [], lines: [] }

  const rows = adaptCompetitorTrendsToTrendData(trends, null).map((row, idx) => ({
    name: row.day != null ? `D${row.day}` : `D${idx + 1}`,
    ...row,
  }))
  if (!rows.length) return { rows: [], lines: [] }

  const hasPrimary = rows.some((row) => rowHasValue(row, 'panoScore'))
  const competitorKeys = Array.from(new Set(
    rows.flatMap((row) =>
      Object.keys(row).filter((key) =>
        !VISIBILITY_TREND_RESERVED_KEYS.has(key) && rowHasValue(row, key),
      ),
    ),
  ))

  const lines: TrendLineAdapted[] = [
    ...(hasPrimary
      ? [{
          key: 'panoScore',
          label: primaryLabel || 'PANO Score',
          color: 'var(--color-accent)',
          area: true,
        }]
      : []),
    ...competitorKeys.map((key, index) => ({
      key,
      label: key,
      color: VISIBILITY_COMPETITOR_TREND_COLORS[index % VISIBILITY_COMPETITOR_TREND_COLORS.length],
      area: false,
      dashed: true,
    })),
  ]

  return { rows, lines }
}

// ── Industry average GEO (for hero comparison bar) ──

export function adaptIndustryAvgGeo(avgOut: IndustryAvgGeoOut): number | null {
  return avgOut?.summary?.avg_geo_score ?? null
}
