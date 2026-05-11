import { apiClient } from '../lib/apiClient'
import { ProjectAnalysisParams, buildQuery } from '../lib/projectAnalysisFilters'

export interface TopicMonitoringSummary {
  topic_count: number
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
  sov: number | null
  avg_rank: number | null
  avg_geo_score: number | null
  sentiment_distribution: { positive: number; neutral: number; negative: number }
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

export interface TopicMonitoringOut {
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
  query_count: number
  response_count: number
  success_rate: number | null
  engine_coverage: string[]
  mention_rate: number | null
  avg_rank: number | null
  avg_geo_score: number | null
  citation_rate: number | null
  last_collected: string | null
}

export interface TopicPromptsOut {
  project_id: string
  topic_id: number
  items: TopicPromptRow[]
  total: number
  state: 'ok' | 'empty' | 'partial'
}

export interface PromptQueryRow {
  query_id: number
  prompt_id: number | null
  query_text: string | null
  target_llm: string | null
  status: string | null
  profile_id: string | null
  created_at: string | null
  executed_at: string | null
  finished_at: string | null
  latency_ms: number | null
  response_id: number | null
  target_mentioned: boolean
  citation_count: number
  geo_score: number | null
  sentiment_score: number | null
}

export interface PromptQueriesOut {
  project_id: string
  prompt_id: number
  items: PromptQueryRow[]
  total: number
  state: 'ok' | 'empty' | 'partial'
}

export interface QueryResponseDetailOut {
  project_id: string
  query: Record<string, unknown>
  response: Record<string, unknown> | null
  analysis: Record<string, unknown> | null
  brand_mentions: Array<Record<string, unknown>>
  citations: Array<Record<string, unknown>>
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
