/**
 * Brand metrics / sentiment / citations API (Phase 2.2).
 *
 *   GET /v1/projects/:id/metrics?series=mention,sov,rank,sentiment,citation
 *   GET /v1/projects/:id/sentiment
 *   GET /v1/projects/:id/citations
 *   GET /v1/projects/:id/topics
 */

import { apiClient } from '../lib/apiClient'
import { ProjectAnalysisParams, buildQuery } from '../lib/projectAnalysisFilters'
import type {
  AnalyticsContractMetadata,
  AnalyticsState,
  MetricContractFields,
} from './analyticsContract'

export interface MetricSeriesPoint {
  date: string
  value: number | null
}

export interface MetricSeries extends MetricContractFields {
  metric: 'mention_rate' | 'sov' | 'rank' | 'sentiment' | 'citation'
  points: MetricSeriesPoint[]
  state?: AnalyticsState
  state_reason?: string | null
  evidence_count?: number
}

export interface MetricsOut extends AnalyticsContractMetadata {
  project_id: string
  brand_id: number | null
  period: { from: string; to: string }
  engines: string[] | null
  series: MetricSeries[]
  state: AnalyticsState
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
  tier?: number | null
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

export interface ProductFeatureRow {
  feature_name: string
  feature_sentiment: 'positive' | 'neutral' | 'negative' | null
  mention_count: number
  avg_score: number | null
}

export interface ProductScenarioRow {
  scenario: string
  mention_count: number
}

export interface ProductRow {
  product_id: number
  product_name: string
  brand_id: number | null
  sku: string | null
  category: string | null
  mention_count: number
  mention_rate?: number | null
  avg_position_rank: number | null
  avg_geo_score: number | null
  avg_sentiment?: number | null
  sov?: number | null
  ranking?: number | null
  win_rate: number | null
  trend_30d?: number | null
  sparkline?: number[]
  top_features?: ProductFeatureRow[]
  top_scenarios?: ProductScenarioRow[]
}

export interface ProductsOut {
  project_id: string
  items: ProductRow[]
  total: number
  state: 'ok' | 'empty' | 'partial'
}

export interface CompetitorBrandRow {
  brand_id: number | null
  brand_key?: string | null
  brand_name: string | null
  avg_geo_score: number | null
  avg_mention_rate: number | null
  avg_sov: number | null
  avg_sentiment: number | null
  co_mention_count: number
  delta_30d_pct: number | null
}

export interface CompetitorMetricsOut extends AnalyticsContractMetadata {
  project_id: string
  primary_brand_id: number | null
  period: { from: string; to: string }
  primary: CompetitorBrandRow | null
  competitors: CompetitorBrandRow[]
  state?: AnalyticsState
  metric_definitions?: Record<string, MetricContractFields>
}

export const brandMetricsApi = {
  metrics(
    projectId: string,
    series: string[] = ['mention_rate', 'sov', 'rank', 'sentiment'],
    brandId?: number | null,
    filters: ProjectAnalysisParams = {},
  ): Promise<MetricsOut> {
    const params: Record<string, unknown> = { ...filters, series: series.join(',') }
    if (brandId != null) params.brand_id = String(brandId)
    return apiClient.get<MetricsOut>(
      `/v1/projects/${projectId}/metrics${buildQuery(params)}`,
    )
  },
  sentiment(projectId: string, filters: ProjectAnalysisParams = {}): Promise<SentimentOut> {
    return apiClient.get<SentimentOut>(
      `/v1/projects/${projectId}/sentiment${buildQuery(filters)}`,
    )
  },
  citations(
    projectId: string,
    pageSize = 50,
    filters: ProjectAnalysisParams = {},
  ): Promise<CitationsOut> {
    return apiClient.get<CitationsOut>(
      `/v1/projects/${projectId}/citations${buildQuery({ ...filters, page_size: pageSize })}`,
    )
  },
  topics(projectId: string): Promise<TopicsOut> {
    return apiClient.get<TopicsOut>(`/v1/projects/${projectId}/topics`)
  },
  products(projectId: string): Promise<ProductsOut> {
    return apiClient.get<ProductsOut>(`/v1/projects/${projectId}/products`)
  },
  competitorMetrics(
    projectId: string,
    brandId?: number | null,
    filters: ProjectAnalysisParams = {},
  ): Promise<CompetitorMetricsOut> {
    const params: Record<string, unknown> = { ...filters }
    if (brandId != null) params.brand_id = String(brandId)
    return apiClient.get<CompetitorMetricsOut>(
      `/v1/projects/${projectId}/competitors/metrics${buildQuery(params)}`,
    )
  },
  competitorTrends(
    projectId: string,
    metric: 'geo_score' | 'mention_rate' | 'sov' | 'sentiment' | 'rank' | 'citation' = 'geo_score',
    brandId?: number | null,
    filters: ProjectAnalysisParams = {},
  ): Promise<CompetitorTrendsOut> {
    const params: Record<string, unknown> = { ...filters, metric }
    if (brandId != null) params.brand_id = String(brandId)
    return apiClient.get<CompetitorTrendsOut>(
      `/v1/projects/${projectId}/competitors/trends${buildQuery(params)}`,
    )
  },
}

export interface CompetitorTrendPoint {
  date: string
  value: number | null
}

export interface CompetitorTrendSeries {
  brand_id: number | null
  brand_key?: string | null
  brand_name: string | null
  is_primary: boolean
  points: CompetitorTrendPoint[]
}

export interface CompetitorTrendsOut extends AnalyticsContractMetadata {
  project_id: string
  metric: string
  period: { from: string; to: string }
  series: CompetitorTrendSeries[]
  state: AnalyticsState
  metric_definition?: MetricContractFields | null
}
