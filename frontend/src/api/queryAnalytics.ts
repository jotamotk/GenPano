import { apiClient } from '../lib/apiClient'
import { ProjectAnalysisParams, buildQuery } from '../lib/projectAnalysisFilters'

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
  projectId: string | null | undefined
  dateFrom?: string
  dateTo?: string
  engine?: string
  segmentId?: string
  profileId?: string
}

const EMPTY_TOTALS = { queries: 0, responses: 0, analyzed: 0, mentions_target: 0 }

export const queryAnalyticsApi = {
  async fetch(args: QueryAnalyticsArgs): Promise<QueryAnalyticsOut> {
    const params: ProjectAnalysisParams = {
      from: args.dateFrom,
      to: args.dateTo,
      engine: args.engine,
      segment_id: args.segmentId,
      profile_id: args.profileId,
    }
    const raw = await apiClient.get<any>(
      `/v1/projects/${args.projectId}/query-activity${buildQuery(params)}`,
    )
    const position = raw.position_distribution || {}
    return {
      filters: {
        brand_id: raw.brand_id ?? null,
        date_from: raw.period?.from ?? args.dateFrom ?? '',
        date_to: raw.period?.to ?? args.dateTo ?? '',
        engine: args.engine ?? null,
      },
      totals: raw.totals || EMPTY_TOTALS,
      by_status: {
        done: raw.by_status?.done ?? 0,
        failed: raw.by_status?.failed ?? 0,
        pending: raw.by_status?.pending ?? 0,
        running: raw.by_status?.running ?? 0,
      },
      by_engine: (raw.by_engine || []).map((row: any) => ({
        engine: row.engine,
        queries: row.query_count ?? row.queries ?? 0,
        mention_rate: row.mention_rate ?? null,
        avg_sentiment: row.avg_sentiment ?? null,
        avg_position_rank: row.avg_position_rank ?? null,
        avg_geo_score: row.avg_geo_score ?? null,
      })),
      daily_trend: (raw.daily || []).map((row: any) => ({
        date: row.date,
        queries: row.queries ?? 0,
        mention_rate: row.responses > 0 ? (row.target_mentions ?? 0) / row.responses : null,
        avg_sentiment: row.avg_sentiment ?? null,
        avg_geo_score: row.avg_geo_score ?? null,
      })),
      by_topic: (raw.by_topic || []).map((row: any) => ({
        topic_id: row.topic_id,
        topic_text: row.topic_name ?? row.topic_text ?? '',
        queries: row.query_count ?? row.queries ?? 0,
        mention_rate: row.mention_rate ?? null,
        avg_sentiment: row.avg_sentiment ?? null,
        avg_geo_score: row.avg_geo_score ?? null,
      })),
      sentiment_distribution: raw.sentiment_distribution || {
        positive: 0,
        neutral: 0,
        negative: 0,
      },
      position_distribution: ['Top1', 'Top3', 'Top5', 'Top10', 'Other'].map((bucket) => ({
        bucket: bucket as QueryAnalyticsPositionRow['bucket'],
        count: position[bucket] ?? 0,
      })),
    }
  },
}
