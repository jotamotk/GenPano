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
import type { CompetitorMetricsOut } from '../api/brandMetrics'
import type { DiagnosticOut } from '../api/diagnostics'

export interface PrimaryBrandAdapted {
  id: string
  name: string
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
  nameEn: string
  panoScore: number
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
): PrimaryBrandAdapted {
  const panoScore = findKpiByLabel(overview.kpi_cards, ['GEO', 'PANO', 'pano_score']) ?? 0
  const mentionPct = findKpiByLabel(overview.kpi_cards, ['提及率', 'mention']) ?? 0
  const sovPct = findKpiByLabel(overview.kpi_cards, ['声量', 'SoV', 'sov']) ?? 0
  const sentiment = findKpiByLabel(overview.kpi_cards, ['情感', 'sentiment']) ?? 0
  const ranking = Math.round(findKpiByLabel(overview.kpi_cards, ['排名', 'rank']) ?? 1)
  const id = String(overview.brand_id ?? 0)

  return {
    id,
    name: overview.brand_name ?? `Brand #${overview.brand_id ?? '?'}`,
    nameEn: '',
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
  ): PrimaryBrandAdapted => ({
    id: String(row.brand_id),
    name: row.brand_name ?? `Brand #${row.brand_id}`,
    nameEn: '',
    panoScore: row.avg_geo_score != null ? Math.round(row.avg_geo_score) : 0,
    mentionRate: row.avg_mention_rate ?? 0,
    sentiment: row.avg_sentiment ?? 0,
    ranking: 1,
    industryId: '',
  })

  const buildComp = (row: CompetitorMetricsOut['competitors'][number]): CompetitorAdapted => ({
    id: String(row.brand_id),
    name: row.brand_name ?? `Brand #${row.brand_id}`,
    nameEn: '',
    panoScore: row.avg_geo_score != null ? Math.round(row.avg_geo_score) : 0,
    industryId: '',
  })

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
      name: r.brand_name ?? `Brand #${r.brand_id}`,
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
      brand: r.brand_name ?? `Brand #${r.brand_id}`,
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
