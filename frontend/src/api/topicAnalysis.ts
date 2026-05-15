import { apiClient } from '../lib/apiClient'
import { ProjectAnalysisParams, buildQuery } from '../lib/projectAnalysisFilters'
import type { AnalyticsContractMetadata } from './analyticsContract'

export interface TopicMonitoringSummary {
  topic_count: number
  topic_count_total: number
  prompt_count: number
  query_count: number
  response_count: number
  analyzed_count: number
  target_mention_count: number
  citation_count: number
  last_collected: string | null
}

export interface TopicMonitoringRow {
  topic_id: number
  topic_name: string
  dimension: string | null
  associated_brand: string | null
  status: string | null
  prompt_count: number
  query_count: number
  response_count: number
  success_rate: number | null
  engine_coverage: string[]
  mention_rate: number | null
  visibility_rate: number | null
  sov: number | null
  avg_rank: number | null
  avg_geo_score: number | null
  sentiment_distribution: { positive: number; neutral: number; negative: number }
  citation_count: number
  citation_rate: number | null
  last_collected: string | null
}

export interface TopicIntentMatrixRow {
  topic_id: number | null
  topic_name: string | null
  intent: string
  prompt_count: number
  query_count: number
  response_count: number
}

export interface TopicMonitoringOut extends AnalyticsContractMetadata {
  project_id: string
  brand_id: number | null
  summary: TopicMonitoringSummary
  topics: TopicMonitoringRow[]
  intent_matrix: TopicIntentMatrixRow[]
  state: 'ok' | 'empty' | 'partial'
}

export interface TopicPromptRow {
  prompt_id: number
  topic_id: number
  prompt_text: string | null
  intent: string | null
  language: string | null
  status: string | null
  prompt_scope: string | null
  query_count: number
  response_count: number
  success_rate: number | null
  engine_coverage: string[]
  mention_rate: number | null
  visibility_rate: number | null
  avg_rank: number | null
  avg_geo_score: number | null
  sentiment_distribution: { positive: number; neutral: number; negative: number }
  citation_count: number
  citation_rate: number | null
  last_collected: string | null
}

export interface TopicPromptsOut extends AnalyticsContractMetadata {
  project_id: string
  topic_id: number
  items: TopicPromptRow[]
  total: number
  state: 'ok' | 'empty' | 'partial'
}

export interface PromptQueryRow {
  query_id: number
  prompt_id: number | null
  query_group_key: string | null
  query_text: string | null
  target_llm: string | null
  status: string | null
  profile_id: string | null
  profile_name: string
  created_at: string | null
  executed_at: string | null
  finished_at: string | null
  latency_ms: number | null
  response_id: number | null
  date: string | null
  attempt_count: number
  daily_latest: PromptQueryDailyRow[]
  target_mentioned: boolean
  citation_count: number
  geo_score: number | null
  sentiment_score: number | null
}

export interface PromptQueryDailyRow {
  date: string
  query_id: number
  response_id: number
  query_text: string | null
  target_llm: string | null
  status: string | null
  profile_id: string | null
  profile_name: string
  executed_at: string | null
  finished_at: string | null
  response_created_at: string | null
  response_preview: string | null
  latency_ms: number | null
  target_mentioned: boolean
  citation_count: number
  geo_score: number | null
  sentiment_score: number | null
}

export interface PromptQueriesOut extends AnalyticsContractMetadata {
  project_id: string
  prompt_id: number
  items: PromptQueryRow[]
  total: number
  state: 'ok' | 'empty' | 'partial'
}

export interface QueryDetail {
  query_id: number
  prompt_id: number | null
  topic_id: number | null
  query_text: string | null
  target_llm: string | null
  status: string | null
  profile_id: string | null
  profile_name: string
  created_at: string | null
  executed_at: string | null
  finished_at: string | null
  latency_ms: number | null
}

export interface ResponseDetail {
  response_id: number
  query_id: number | null
  prompt_id: number | null
  raw_text: string | null
  target_llm: string | null
  intent: string | null
  llm_version: string | null
  citations_json: unknown
  created_at: string | null
}

export interface ResponseAnalysisDetail {
  analysis_id?: number | null
  target_brand_mentioned?: boolean | null
  target_brand_rank?: number | null
  target_brand_sentiment?: string | null
  visibility_score?: number | null
  sentiment_score?: number | null
  sov_score?: number | null
  citation_score?: number | null
  geo_score?: number | null
  analyzed_at?: string | null
}

export interface BrandMentionDetail {
  mention_id: number
  response_id: number
  brand_id?: number | null
  brand_name: string
  product_name?: string | null
  is_target?: boolean | null
  position_rank?: number | null
  sentiment?: string | null
  sentiment_score?: number | null
  context_snippet?: string | null
  mention_count?: number | null
  created_at?: string | null
}

export interface CitationDetail {
  citation_id: number
  response_id: number
  mention_id?: number | null
  url: string
  domain?: string | null
  title?: string | null
  citation_index?: number | null
  source_type?: string | null
  created_at?: string | null
}

export interface ProductFeatureAttributeDetail {
  feature_id: number
  analysis_id?: number | null
  brand_name?: string | null
  product_name?: string | null
  feature_name?: string | null
  feature_sentiment?: string | null
  context_snippet?: string | null
  scenario?: string | null
  price_positioning?: string | null
  created_at?: string | null
}

export interface ResponseRelationDetail {
  source: string
  entity_kind?: string | null
  type: string
  a_id?: number | null
  b_id?: number | null
  a_name?: string | null
  b_name?: string | null
  confidence?: number | null
  evidence?: unknown
  response_id?: number | null
}

export interface SentimentDriverDetail {
  driver_id: number
  mention_id?: number | null
  response_id?: number | null
  brand_name?: string | null
  driver_text: string
  polarity?: string | null
  category?: string | null
  strength?: number | null
  source_quote?: string | null
  created_at?: string | null
}

export interface AnalyzerFacts {
  citations: CitationDetail[]
  brands_mentioned: BrandMentionDetail[]
  products_features_attributes: ProductFeatureAttributeDetail[]
  relations: ResponseRelationDetail[]
  sentiment_drivers: SentimentDriverDetail[]
}

export interface ResponseAttemptDetail {
  query_id: number
  response_id: number
  query_text: string | null
  target_llm: string | null
  status: string | null
  profile_id: string | null
  profile_name: string
  executed_at: string | null
  finished_at: string | null
  latency_ms: number | null
  response: ResponseDetail
  analysis: ResponseAnalysisDetail | null
  citations: CitationDetail[]
  analyzer_facts: AnalyzerFacts
}

export interface QueryResponseDetailOut {
  project_id: string
  query: QueryDetail
  response: ResponseDetail | null
  analysis: ResponseAnalysisDetail | null
  brand_mentions: BrandMentionDetail[]
  citations: CitationDetail[]
  analyzer_facts: AnalyzerFacts
  attempts: ResponseAttemptDetail[]
  state: 'ok' | 'empty' | 'partial'
}

export interface ProjectProfileRow {
  profile_id: string
  name: string
  status: string | null
  demographic: string | null
  need: string | null
  weight: number | null
}

export interface ProjectSegmentRow {
  segment_id: string
  code: string | null
  name: string
  status: string | null
  weight: number | null
  active_profile_count: number
  profiles: ProjectProfileRow[]
}

export interface ProjectSegmentsOut {
  project_id: string
  items: ProjectSegmentRow[]
  total: number
  state: 'ok' | 'empty' | 'partial'
}

export const topicAnalysisApi = {
  monitoring(projectId: string, filters: ProjectAnalysisParams = {}): Promise<TopicMonitoringOut> {
    return apiClient.get<TopicMonitoringOut>(
      `/v1/projects/${projectId}/topics/monitoring${buildQuery(filters)}`,
    )
  },

  prompts(
    projectId: string,
    topicId: number,
    filters: ProjectAnalysisParams = {},
  ): Promise<TopicPromptsOut> {
    return apiClient.get<TopicPromptsOut>(
      `/v1/projects/${projectId}/topics/${topicId}/prompts${buildQuery(filters)}`,
    )
  },

  queries(
    projectId: string,
    promptId: number,
    filters: ProjectAnalysisParams = {},
  ): Promise<PromptQueriesOut> {
    return apiClient.get<PromptQueriesOut>(
      `/v1/projects/${projectId}/prompts/${promptId}/queries${buildQuery(filters)}`,
    )
  },

  response(
    projectId: string,
    queryId: number,
    filters: ProjectAnalysisParams = {},
  ): Promise<QueryResponseDetailOut> {
    return apiClient.get<QueryResponseDetailOut>(
      `/v1/projects/${projectId}/queries/${queryId}/response${buildQuery(filters)}`,
    )
  },

  segments(projectId: string, filters: ProjectAnalysisParams = {}): Promise<ProjectSegmentsOut> {
    return apiClient.get<ProjectSegmentsOut>(
      `/v1/projects/${projectId}/segments${buildQuery(filters)}`,
    )
  },
}
