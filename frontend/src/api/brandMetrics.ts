/**
 * Brand metrics / sentiment / citations API (Phase 2.2).
 *
 *   GET /v1/projects/:id/metrics?series=mention,sov,rank,sentiment,citation
 *   GET /v1/projects/:id/sentiment
 *   GET /v1/projects/:id/citations
 *   GET /v1/projects/:id/topics
 */

import { apiClient } from '../lib/apiClient'

export interface MetricSeriesPoint {
  date: string
  value: number
}

export interface MetricSeries {
  metric: 'mention_rate' | 'sov' | 'rank' | 'sentiment' | 'citation'
  points: MetricSeriesPoint[]
}

export interface MetricsOut {
  project_id: string
  brand_id: number | null
  period: { from: string; to: string }
  engines: string[] | null
  series: MetricSeries[]
  state: 'ok' | 'empty' | 'partial'
}

export interface SentimentDistribution {
  positive_count: number
  neutral_count: number
  negative_count: number
  positive_pct: number
  neutral_pct: number
  negative_pct: number
  avg_sentiment_score: number
}

export interface SentimentKeywordRow {
  keyword: string
  polarity: 'positive' | 'negative'
  count: number
  avg_strength: number | null
}

export interface SentimentDriverRow {
  driver_text: string
  polarity: string
  category: string | null
  count: number
  avg_strength: number | null
}

export interface SentimentTrendPoint {
  date: string
  positive_pct: number
  negative_pct: number
  avg_score: number
}

export interface SentimentOut {
  project_id: string
  brand_id: number | null
  period: { from: string; to: string }
  distribution: SentimentDistribution
  trend_30d: SentimentTrendPoint[]
  top_keywords: SentimentKeywordRow[]
  top_drivers: SentimentDriverRow[]
  state: 'ok' | 'empty' | 'partial'
}

export interface CitationRow {
  citation_id: number
  response_id: number
  url: string
  domain: string | null
  title: string | null
  source_type: string | null
  occurred_at: string | null
}

export interface CitationDomainRow {
  domain: string
  count: number
}

export interface CitationsOut {
  project_id: string
  brand_id: number | null
  period: { from: string; to: string }
  items: CitationRow[]
  next_cursor: string | null
  total: number
  by_domain_top: CitationDomainRow[]
  state: 'ok' | 'empty' | 'partial'
}

export interface TopicRow {
  topic_id: number
  topic_name: string
  state: 'tracked' | 'ignored' | 'unpinned'
  mention_count: number
  avg_sentiment: number | null
  avg_position_rank: number | null
  last_seen_at: string | null
}

export interface TopicsOut {
  project_id: string
  items: TopicRow[]
  total: number
  state: 'ok' | 'empty' | 'partial'
}

export interface ProductRow {
  product_id: number
  product_name: string
  brand_id: number | null
  sku: string | null
  category: string | null
  mention_count: number
  avg_position_rank: number | null
  avg_geo_score: number | null
  win_rate: number | null
}

export interface ProductsOut {
  project_id: string
  items: ProductRow[]
  total: number
  state: 'ok' | 'empty' | 'partial'
}

export interface CompetitorBrandRow {
  brand_id: number
  brand_name: string | null
  avg_geo_score: number | null
  avg_mention_rate: number | null
  avg_sov: number | null
  avg_sentiment: number | null
  co_mention_count: number
  delta_30d_pct: number | null
}

export interface CompetitorMetricsOut {
  project_id: string
  primary_brand_id: number | null
  period: { from: string; to: string }
  primary: CompetitorBrandRow | null
  competitors: CompetitorBrandRow[]
  state?: 'ok' | 'empty' | 'partial'
}

export const brandMetricsApi = {
  metrics(
    projectId: string,
    series: string[] = ['mention_rate', 'sov', 'rank', 'sentiment'],
  ): Promise<MetricsOut> {
    const q = series.join(',')
    return apiClient.get<MetricsOut>(`/v1/projects/${projectId}/metrics?series=${q}`)
  },
  sentiment(projectId: string): Promise<SentimentOut> {
    return apiClient.get<SentimentOut>(`/v1/projects/${projectId}/sentiment`)
  },
  citations(projectId: string, pageSize = 50): Promise<CitationsOut> {
    return apiClient.get<CitationsOut>(
      `/v1/projects/${projectId}/citations?page_size=${pageSize}`,
    )
  },
  topics(projectId: string): Promise<TopicsOut> {
    return apiClient.get<TopicsOut>(`/v1/projects/${projectId}/topics`)
  },
  products(projectId: string): Promise<ProductsOut> {
    return apiClient.get<ProductsOut>(`/v1/projects/${projectId}/products`)
  },
  competitorMetrics(projectId: string): Promise<CompetitorMetricsOut> {
    return apiClient.get<CompetitorMetricsOut>(
      `/v1/projects/${projectId}/competitors/metrics`,
    )
  },
  competitorTrends(
    projectId: string,
    metric: 'geo_score' | 'mention_rate' | 'sov' | 'sentiment' | 'rank' | 'citation' = 'geo_score',
  ): Promise<CompetitorTrendsOut> {
    return apiClient.get<CompetitorTrendsOut>(
      `/v1/projects/${projectId}/competitors/trends?metric=${metric}`,
    )
  },
}

export interface CompetitorTrendPoint {
  date: string
  value: number | null
}

export interface CompetitorTrendSeries {
  brand_id: number
  brand_name: string | null
  is_primary: boolean
  points: CompetitorTrendPoint[]
}

export interface CompetitorTrendsOut {
  project_id: string
  metric: string
  period: { from: string; to: string }
  series: CompetitorTrendSeries[]
  state: 'ok' | 'empty' | 'partial'
}
