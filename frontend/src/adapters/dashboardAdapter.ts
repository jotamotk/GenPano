/**
 * dashboardAdapter — convert backend responses into the prop shapes that
 * BrandPanoramaPanel's existing chart sub-components consume.
 *
 * Strategy: keep the rich PRD viz components untouched; only inject
 * backend-derived data via optional override props. When backend hasn't
 * generated data yet, the panel falls back to its existing mock arrays
 * so the visual is never blank.
 */

import type { BrandOverviewOut } from '../api/brandOverview'
import type {
  CompetitorMetricsOut,
  CompetitorTrendsOut,
  MetricsOut,
} from '../api/brandMetrics'
import type { DiagnosticOut } from '../api/diagnostics'
import type { IndustryAvgGeoOut } from '../api/industries'

export interface PrimaryBrandAdapted {
  id: string
  name: string
  nameZh?: string
  nameEn: string
  panoScore: number
  /** decimal 0..1 */
  mentionRate: number
  /** -1..1 */
  sentiment: number
  ranking: number
  industryId: string
  change?: string
}

export interface CompetitorAdapted {
  id: string
  name: string
  nameZh?: string
  nameEn: string
  panoScore: number
  /** decimal 0..1 */
  mentionRate?: number
  /** -1..1 */
  sentiment?: number
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
  panoScore: number
  mentionRate: number
  sentiment: number
}

export interface DiagnosticAdapted {
  id: string
  severity: 'P0' | 'P1' | 'P2' | 'P3'
  title: string
  engine: string
  type: string
}

/** Find a numeric metric in the kpi_cards array by Chinese label heuristic. */
function findKpiByLabel(
  cards: BrandOverviewOut['kpi_cards'],
  matchers: string[],
): number | null {
  for (const card of cards) {
    for (const m of matchers) {
      if (card.label_zh.includes(m) || card.label_en.toLowerCase().includes(m.toLowerCase())) {
        return card.value
      }
    }
  }
  return null
}

export function adaptOverviewToPrimary(
  overview: BrandOverviewOut,
): PrimaryBrandAdapted | null {
  if (overview.brand_id == null && !overview.brand_name?.trim()) {
    return null
  }
  const panoScore = findKpiByLabel(overview.kpi_cards, ['GEO', 'PANO', 'pano_score']) ?? 0
  const mentionPct = findKpiByLabel(overview.kpi_cards, ['提及率', 'mention']) ?? 0
  const sovPct = findKpiByLabel(overview.kpi_cards, ['声量', 'SoV', 'sov']) ?? 0
  const sentiment = findKpiByLabel(overview.kpi_cards, ['情感', 'sentiment']) ?? 0
  const ranking = Math.round(findKpiByLabel(overview.kpi_cards, ['排名', 'rank']) ?? 1)
  const id = String(overview.brand_id ?? overview.brand_name)
  const name = overview.brand_name ?? `Brand #${overview.brand_id}`

  return {
    id,
    name,
    nameZh: name,
    nameEn: name,
    panoScore: Math.round(panoScore),
    mentionRate: mentionPct > 1 ? mentionPct / 100 : mentionPct,
    sentiment: sentiment > 1 ? sentiment / 100 : sentiment,
    ranking,
    industryId: String(overview.industry_id ?? ''),
    change: undefined,
  }
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
      panoScore: row.avg_geo_score != null ? Math.round(row.avg_geo_score) : 0,
      mentionRate: row.avg_mention_rate ?? 0,
      sentiment: row.avg_sentiment ?? 0,
      ranking: 1,
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
      panoScore: row.avg_geo_score != null ? Math.round(row.avg_geo_score) : 0,
      mentionRate: row.avg_mention_rate ?? 0,
      sentiment: row.avg_sentiment ?? 0,
      industryId: '',
    }
  }

  return {
    primary: metrics.primary ? buildPrimary(metrics.primary) : null,
    competitors: metrics.competitors.map(buildComp),
  }
}

export function adaptCompetitorMetricsToSov(
  metrics: CompetitorMetricsOut,
): SovEntry[] {
  const all = [
    ...(metrics.primary ? [metrics.primary] : []),
    ...metrics.competitors,
  ]
  const filtered = all.filter((r) => r.avg_sov != null && (r.avg_sov ?? 0) > 0)
  if (filtered.length === 0) return []
  const top = filtered
    .map((r) => ({
      name: r.brand_name ?? r.brand_key ?? `Brand #${r.brand_id ?? '?'}`,
      value: Math.round(((r.avg_sov ?? 0) * 100 + Number.EPSILON) * 10) / 10,
    }))
    .sort((a, b) => b.value - a.value)
    .slice(0, 6)
  const totalShown = top.reduce((acc, x) => acc + x.value, 0)
  if (totalShown < 99) {
    top.push({ name: '其他', value: Math.max(0, +(100 - totalShown).toFixed(1)) })
  }
  return top
}

export function adaptCompetitorMetricsToBubble(
  metrics: CompetitorMetricsOut,
): BubbleEntry[] {
  const all = [
    ...(metrics.primary ? [metrics.primary] : []),
    ...metrics.competitors,
  ]
  return all
    .filter((r) => r.avg_sov != null || r.avg_sentiment != null)
    .map((r) => ({
      brand: r.brand_name ?? r.brand_key ?? `Brand #${r.brand_id ?? '?'}`,
      sov: r.avg_sov != null ? +(r.avg_sov * 100).toFixed(1) : 0,
      sentiment: r.avg_sentiment ?? 0,
      mentions: r.co_mention_count ?? 0,
    }))
}

export function adaptOverviewToTrend(
  overview: BrandOverviewOut,
): TrendPoint[] {
  // Merge geo / sov / sentiment series by date into one row per day
  const dates = new Set<string>()
  for (const p of overview.geo_score_30d) dates.add(p.date)
  for (const p of overview.sov_30d) dates.add(p.date)
  for (const p of overview.sentiment_30d) dates.add(p.date)
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
    const geo = lookup(overview.geo_score_30d, d) ?? 0
    const sov = lookup(overview.sov_30d, d) ?? 0
    const sent = lookup(overview.sentiment_30d, d) ?? 0
    return {
      day,
      panoScore: Math.round(geo),
      // mentionRate exposed as decimal-ish so existing formatters match
      mentionRate: Math.round(sov * 100 * 10) / 10,
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
  if (!metrics?.series) return empty

  const find = (name: string) => metrics.series.find((s) => s.metric === name)

  const mention = find('mention_rate')
  const sov = find('sov')
  const sentiment = find('sentiment')
  const citation = find('citation')
  const rank = find('rank')

  return {
    mention: mention ? mention.points.map((p) => +(p.value * 100).toFixed(1)) : [],
    sov: sov ? sov.points.map((p) => +(p.value * 100).toFixed(1)) : [],
    sentiment: sentiment ? sentiment.points.map((p) => +(p.value * 100).toFixed(1)) : [],
    citation: citation ? citation.points.map((p) => +(p.value * 100).toFixed(1)) : [],
    rank: rank ? rank.points.map((p) => +p.value.toFixed(1)) : [],
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
  panoScore: number
  mentionRate: number
  sentiment: number
  // dynamic competitor brand scores keyed by brand_name
  [brand: string]: number | string
}

export function adaptCompetitorTrendsToTrendData(
  trends: CompetitorTrendsOut,
  overviewTrend: BrandOverviewOut | null,
): TrendRowAdapted[] {
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
      panoScore: 0,
      mentionRate: 0,
      sentiment: 0,
    }
    // Primary panoScore
    if (primarySeries) {
      const p = primarySeries.points.find((q) => q.date === date)
      row.panoScore = p?.value != null ? Math.round(p.value) : 0
    } else if (overviewTrend) {
      const p = overviewTrend.geo_score_30d.find((q) => q.date === date)
      row.panoScore = p?.value != null ? Math.round(p.value) : 0
    }
    // mentionRate / sentiment from overview's other series
    if (overviewTrend) {
      const sov = overviewTrend.sov_30d.find((q) => q.date === date)
      row.mentionRate = sov?.value != null ? +(sov.value * 100).toFixed(1) : 0
      const sent = overviewTrend.sentiment_30d.find((q) => q.date === date)
      row.sentiment = sent?.value ?? 0
    }
    // Per-competitor scores keyed by brand name (or fallback id)
    for (const comp of competitorSeries) {
      const key =
        comp.brand_name && comp.brand_name.length > 0
          ? comp.brand_name
          : comp.brand_key ?? `Brand #${comp.brand_id ?? '?'}`
      const cp = comp.points.find((q) => q.date === date)
      row[key] = cp?.value != null ? Math.round(cp.value) : 0
    }
    return row
  })
}


// ── Industry average GEO (for hero comparison bar) ──

export function adaptIndustryAvgGeo(avgOut: IndustryAvgGeoOut): number | null {
  return avgOut?.summary?.avg_geo_score ?? null
}
