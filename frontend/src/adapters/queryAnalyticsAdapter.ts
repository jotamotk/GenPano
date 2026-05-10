/**
 * Query-analytics adapters — pure functions reshaping the API response
 * from `/admin/queries/analytics` into the prop shapes the recharts
 * components expect.
 *
 * Same convention as `dashboardAdapter.ts`: small focused helpers, no
 * data fetching, all `null`-safe.
 */

import {
  QueryAnalyticsByEngineRow,
  QueryAnalyticsDailyRow,
  QueryAnalyticsOut,
  QueryAnalyticsPositionRow,
  QueryAnalyticsSentimentDistribution,
  QueryAnalyticsTopicRow,
} from '../api/queryAnalytics'

/**
 * KPI tiles. Renders 4 numbers above the charts.
 *   - 总查询: totals.queries
 *   - 命中率: totals.mentions_target / totals.responses (NaN-safe)
 *   - 平均情感 / 平均GEO分: averaged from daily_trend (weighted by queries)
 */
export interface QueryAnalyticsKpis {
  totalQueries: number
  mentionRate: number | null
  avgSentiment: number | null
  avgGeoScore: number | null
}

export function toKpis(data: QueryAnalyticsOut | undefined): QueryAnalyticsKpis {
  if (!data) {
    return { totalQueries: 0, mentionRate: null, avgSentiment: null, avgGeoScore: null }
  }
  const totalQueries = data.totals?.queries ?? 0
  const mentionDenominator = data.totals?.mention_denominator ?? data.totals?.responses ?? 0
  const mentionRate =
    mentionDenominator > 0
      ? (data.totals.mentions_target ?? 0) / mentionDenominator
      : null
  const trend = data.daily_trend ?? []
  const wAvg = (key: 'avg_sentiment' | 'avg_geo_score'): number | null => {
    let num = 0
    let den = 0
    for (const row of trend) {
      const v = row[key]
      if (v == null) continue
      const w = row.queries || 0
      num += v * w
      den += w
    }
    return den > 0 ? num / den : null
  }
  return {
    totalQueries,
    mentionRate,
    avgSentiment: wAvg('avg_sentiment'),
    avgGeoScore: wAvg('avg_geo_score'),
  }
}

/**
 * TrendChart input. Each point feeds three lines (mention_rate, sentiment,
 * geo_score). Backend may return a sparse series — keep `null` so recharts
 * draws gaps instead of forcing zeros.
 */
export interface TrendPoint {
  name: string
  mentionRate: number | null
  sentiment: number | null
  geoScore: number | null
}

export function toTrendSeries(rows: QueryAnalyticsDailyRow[] | undefined): TrendPoint[] {
  return (rows ?? []).map((r) => ({
    name: r.date,
    mentionRate: r.mention_rate,
    sentiment: r.avg_sentiment,
    geoScore: r.avg_geo_score,
  }))
}

/**
 * DonutChart segments. The recharts pie reads `name`/`value`/`color` (see
 * `frontend/src/components/charts/DonutChart.tsx`), so we match those keys
 * verbatim — adapter changes that don't will silently render a blank ring.
 */
export interface DonutSegment {
  name: string
  value: number
  color: string
}

export function toSentimentDonut(
  d: QueryAnalyticsSentimentDistribution | undefined,
): DonutSegment[] {
  const v = d ?? { positive: 0, neutral: 0, negative: 0 }
  return [
    { name: '正面', value: v.positive, color: 'var(--color-sentiment-positive)' },
    { name: '中性', value: v.neutral, color: 'var(--color-sentiment-neutral)' },
    { name: '负面', value: v.negative, color: 'var(--color-sentiment-warning)' },
  ]
}

/**
 * HorizontalBar items. The shared component reads `name`/`value`/`color?`
 * (see `frontend/src/components/charts/HorizontalBar.tsx`). Mention rates
 * are pre-multiplied to whole-percent integers so the inline label shows
 * "83%" not "0.83%".
 */
export interface HorizontalBarItem {
  name: string
  value: number
  color?: string
}

const _toPctValue = (v: number | null | undefined): number =>
  v == null ? 0 : Math.round(v * 100)

export function toEngineBars(rows: QueryAnalyticsByEngineRow[] | undefined): HorizontalBarItem[] {
  return (rows ?? []).map((r) => ({
    name: r.engine,
    value: _toPctValue(r.mention_rate),
  }))
}

export function toTopicBars(rows: QueryAnalyticsTopicRow[] | undefined): HorizontalBarItem[] {
  return (rows ?? []).map((r) => ({
    name: r.topic_text || `Topic #${r.topic_id}`,
    value: _toPctValue(r.mention_rate),
  }))
}

export function toPositionBars(rows: QueryAnalyticsPositionRow[] | undefined): HorizontalBarItem[] {
  return (rows ?? []).map((r) => ({
    name: r.bucket,
    value: r.count,
  }))
}
