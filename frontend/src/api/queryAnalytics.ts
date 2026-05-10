/**
 * Brand query analytics API — feeds TopicsPage QueryActivityCard.
 *
 *   GET /api/admin/queries/analytics?brand_id=&date_from=&date_to=&engine=
 *
 * Backend: backend/app/admin/queries/analytics.py:fetch_query_analytics
 *
 * Default window: backend resolves to last 30 days when date_from / date_to
 * are omitted. Caller can override by passing ISO date strings.
 */

import { apiClient } from '../lib/apiClient'

export interface QueryAnalyticsFilters {
  brand_id: number | null
  date_from: string
  date_to: string
  engine: string | null
}

export interface QueryAnalyticsTotals {
  queries: number
  responses: number
  analyzed: number
  mentions_target: number
}

export interface QueryAnalyticsByStatus {
  done: number
  failed: number
  pending: number
  running: number
}

export interface QueryAnalyticsByEngineRow {
  engine: string
  queries: number
  mention_rate: number | null
  avg_sentiment: number | null
  avg_position_rank: number | null
  avg_geo_score: number | null
}

export interface QueryAnalyticsDailyRow {
  date: string
  queries: number
  mention_rate: number | null
  avg_sentiment: number | null
  avg_geo_score: number | null
}

export interface QueryAnalyticsTopicRow {
  topic_id: number
  topic_text: string
  queries: number
  mention_rate: number | null
  avg_sentiment: number | null
  avg_geo_score: number | null
}

export interface QueryAnalyticsSentimentDistribution {
  positive: number
  neutral: number
  negative: number
}

export interface QueryAnalyticsPositionRow {
  bucket: 'Top1' | 'Top3' | 'Top5' | 'Top10' | 'Other'
  count: number
}

export interface QueryAnalyticsOut {
  filters: QueryAnalyticsFilters
  totals: QueryAnalyticsTotals
  by_status: QueryAnalyticsByStatus
  by_engine: QueryAnalyticsByEngineRow[]
  daily_trend: QueryAnalyticsDailyRow[]
  by_topic: QueryAnalyticsTopicRow[]
  sentiment_distribution: QueryAnalyticsSentimentDistribution
  position_distribution: QueryAnalyticsPositionRow[]
}

export interface QueryAnalyticsArgs {
  brandId: number | null | undefined
  dateFrom?: string
  dateTo?: string
  engine?: string
}

export const queryAnalyticsApi = {
  fetch(args: QueryAnalyticsArgs): Promise<QueryAnalyticsOut> {
    const params = new URLSearchParams()
    if (args.brandId != null) params.set('brand_id', String(args.brandId))
    if (args.dateFrom) params.set('date_from', args.dateFrom)
    if (args.dateTo) params.set('date_to', args.dateTo)
    if (args.engine) params.set('engine', args.engine)
    const qs = params.toString()
    return apiClient.get<QueryAnalyticsOut>(
      `/admin/queries/analytics${qs ? `?${qs}` : ''}`,
    )
  },
}
