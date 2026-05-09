/**
 * Project chart-data endpoints (Phase 5).
 *
 * Each method maps 1:1 to a backend route under
 *   /v1/projects/:id/...
 * and returns the DTO shape defined in
 *   backend/app/api/v1/projects/_charts_dto.py
 *
 * The shapes mirror what the existing recharts components on the brand pages
 * already consume; adapters in `src/adapters/brandPagesAdapter.ts` shape them
 * into chart-component props.
 */

import { apiClient } from '../lib/apiClient'

// ── /metrics/by-engine ──────────────────────────────────────────────
export interface EngineMetricRow {
  engine: string
  mention_rate: number | null
  sov: number | null
  citation_rate: number | null
  sentiment: number | null
}

export interface EngineMetricsOut {
  project_id: string
  period: { from: string; to: string }
  items: EngineMetricRow[]
  state: 'ok' | 'empty' | 'partial'
}

// ── /position-distribution ──────────────────────────────────────────
export interface PositionBucketRow {
  bucket: string
  count: number
  pct: number
}

export interface PositionDistributionOut {
  project_id: string
  period: { from: string; to: string }
  items: PositionBucketRow[]
  total_mentions: number
  state: 'ok' | 'empty' | 'partial'
}

// ── /topic-heatmap ──────────────────────────────────────────────────
export interface HeatmapCell {
  topic_id: number
  topic_label: string
  value: number | null
  sample: number
}

export interface HeatmapRow {
  brand_id: number
  brand_name: string | null
  values: HeatmapCell[]
}

export interface TopicHeatmapOut {
  project_id: string
  metric: 'mention_rate' | 'sentiment'
  rows: HeatmapRow[]
  state: 'ok' | 'empty' | 'partial'
}

// ── /sentiment/by-engine ────────────────────────────────────────────
export interface SentimentByEngineRow {
  engine: string
  positive: number
  neutral: number
  negative: number
}

export interface SentimentByEngineOut {
  project_id: string
  period: { from: string; to: string }
  items: SentimentByEngineRow[]
  state: 'ok' | 'empty' | 'partial'
}

// ── /sentiment/trend-by-engine ──────────────────────────────────────
export interface SentimentTrendByEngineRow {
  date: string
  by_engine: Record<string, number | null>
}

export interface SentimentTrendByEngineOut {
  project_id: string
  period: { from: string; to: string }
  engines: string[]
  items: SentimentTrendByEngineRow[]
  state: 'ok' | 'empty' | 'partial'
}

// ── /sentiment/topic-attribution ────────────────────────────────────
export interface TopicAttributionRow {
  topic_id: number
  topic_name: string
  negative_count: number
  negative_ratio: number
  sample_snippet: string | null
}

export interface TopicAttributionOut {
  project_id: string
  items: TopicAttributionRow[]
  state: 'ok' | 'empty' | 'partial'
}

// ── /mention-samples ────────────────────────────────────────────────
export interface MentionSampleRow {
  mention_id: number
  response_id: number
  label: string
  polarity: 'positive' | 'negative' | 'neutral'
  summary: string | null
  snippet: string | null
  engine: string | null
  topic: string | null
  occurred_at: string | null
}

export interface MentionSamplesOut {
  project_id: string
  items: MentionSampleRow[]
  state: 'ok' | 'empty' | 'partial'
}

// ── /citations/authority-trend ──────────────────────────────────────
export interface AuthorityTrendPoint {
  date: string
  tier1_pct: number
  tier2_pct: number
  tier3_pct: number
  tier4_pct: number
  untiered_pct: number
}

export interface AuthorityTrendOut {
  project_id: string
  period: { from: string; to: string }
  points: AuthorityTrendPoint[]
  state: 'ok' | 'empty' | 'partial'
}

// ── /citations/composition ──────────────────────────────────────────
export interface CitationCompositionRow {
  label: string
  tier: number | null
  count: number
  pct: number
}

export interface CitationCompositionOut {
  project_id: string
  period: { from: string; to: string }
  segments: CitationCompositionRow[]
  total: number
  state: 'ok' | 'empty' | 'partial'
}

// ── /citations/content-gap ──────────────────────────────────────────
export interface ContentGapTopicRow {
  topic_id: number | null
  topic_name: string
  mention_rate: number
  citation_rate: number
  gap_score: number
  suggestion: string | null
}

export interface ContentGapPageTypeRow {
  page_type: string
  count: number
  pct: number
}

export interface ContentGapOut {
  project_id: string
  topics: ContentGapTopicRow[]
  page_type_distribution: ContentGapPageTypeRow[]
  state: 'ok' | 'empty' | 'partial'
}

// ── /citations/pr-targets ───────────────────────────────────────────
export interface PrTargetRow {
  domain: string
  tier: number | null
  we_count: number
  competitors_count: number
  gap: number
  suggestion: string | null
}

export interface KolScorecard {
  name: string
  platform: string | null
  audience_score: number | null
  quality_score: number | null
  risk: string | null
  notes: string | null
}

export interface Tier2MatrixRow {
  brand_id: number
  label: string
  counts: number[]
}

export interface Tier2MatrixOut {
  domains: string[]
  brands: Tier2MatrixRow[]
}

export interface PrTargetsOut {
  project_id: string
  targets: PrTargetRow[]
  kol_scorecards: KolScorecard[]
  tier2_matrix: Tier2MatrixOut
  state: 'ok' | 'empty' | 'partial'
}

// ── /citations/simulator-baseline ───────────────────────────────────
export interface SimulatorTierWeight {
  tier: number
  weight: number
  confidence: number
  current_count: number
}

export interface SimulatorPreset {
  id: string
  label: string
  delta_by_tier: Record<string, number>
}

export interface SimulatorBaselineOut {
  project_id: string
  current_pano: number
  industry_median: number | null
  industry_top3_avg: number | null
  tiers: SimulatorTierWeight[]
  presets: SimulatorPreset[]
  state: 'ok' | 'empty' | 'partial'
}

// ── /competitors/authority-radar ────────────────────────────────────
export interface AuthorityRadarRow {
  tier: string
  me: number
  industry_median: number
  top_competitor: number
  top_competitor_id: number | null
  top_competitor_name: string | null
}

export interface AuthorityRadarOut {
  project_id: string
  rows: AuthorityRadarRow[]
  state: 'ok' | 'empty' | 'partial'
}

// ── /group-shared-domains ───────────────────────────────────────────
export interface GroupSharedDomainEntry {
  domain: string
  tier: number | null
  brand_count: number
  total_mentions: number
  sister_brand_ids: number[]
  sister_brand_names: string[]
}

export interface GroupSharedDomainsOut {
  project_id: string
  group_id: number | null
  group_name: string | null
  shared_ratio: number | null
  items: GroupSharedDomainEntry[]
  state: 'ok' | 'empty' | 'partial'
}

// ── /products/relations ─────────────────────────────────────────────
export interface ProductRelationRow {
  product_a_id: number
  product_a_name: string | null
  product_b_id: number
  product_b_name: string | null
  type: string
  confidence: number | null
}

export interface ProductRelationsOut {
  project_id: string
  items: ProductRelationRow[]
  state: 'ok' | 'empty' | 'partial'
}

// ── API client ──────────────────────────────────────────────────────
export const projectChartsApi = {
  engineMetrics(projectId: string): Promise<EngineMetricsOut> {
    return apiClient.get<EngineMetricsOut>(`/v1/projects/${projectId}/metrics/by-engine`)
  },
  positionDistribution(projectId: string): Promise<PositionDistributionOut> {
    return apiClient.get<PositionDistributionOut>(
      `/v1/projects/${projectId}/position-distribution`,
    )
  },
  topicHeatmap(
    projectId: string,
    opts: { metric?: 'mention_rate' | 'sentiment'; compareWith?: number[]; topN?: number } = {},
  ): Promise<TopicHeatmapOut> {
    const q: string[] = []
    if (opts.metric) q.push(`metric=${opts.metric}`)
    if (opts.compareWith?.length) q.push(`compare_with=${opts.compareWith.join(',')}`)
    if (opts.topN) q.push(`top_n=${opts.topN}`)
    const qs = q.length ? `?${q.join('&')}` : ''
    return apiClient.get<TopicHeatmapOut>(`/v1/projects/${projectId}/topic-heatmap${qs}`)
  },
  sentimentByEngine(projectId: string): Promise<SentimentByEngineOut> {
    return apiClient.get<SentimentByEngineOut>(`/v1/projects/${projectId}/sentiment/by-engine`)
  },
  sentimentTrendByEngine(projectId: string): Promise<SentimentTrendByEngineOut> {
    return apiClient.get<SentimentTrendByEngineOut>(
      `/v1/projects/${projectId}/sentiment/trend-by-engine`,
    )
  },
  topicAttribution(projectId: string, limit = 10): Promise<TopicAttributionOut> {
    return apiClient.get<TopicAttributionOut>(
      `/v1/projects/${projectId}/sentiment/topic-attribution?limit=${limit}`,
    )
  },
  mentionSamples(
    projectId: string,
    opts: { polarity?: string; limit?: number } = {},
  ): Promise<MentionSamplesOut> {
    const q: string[] = []
    if (opts.polarity) q.push(`polarity=${opts.polarity}`)
    if (opts.limit) q.push(`limit=${opts.limit}`)
    const qs = q.length ? `?${q.join('&')}` : ''
    return apiClient.get<MentionSamplesOut>(`/v1/projects/${projectId}/mention-samples${qs}`)
  },
  authorityTrend(projectId: string): Promise<AuthorityTrendOut> {
    return apiClient.get<AuthorityTrendOut>(
      `/v1/projects/${projectId}/citations/authority-trend`,
    )
  },
  citationComposition(projectId: string): Promise<CitationCompositionOut> {
    return apiClient.get<CitationCompositionOut>(
      `/v1/projects/${projectId}/citations/composition`,
    )
  },
  contentGap(projectId: string, limit = 12): Promise<ContentGapOut> {
    return apiClient.get<ContentGapOut>(
      `/v1/projects/${projectId}/citations/content-gap?limit=${limit}`,
    )
  },
  prTargets(projectId: string): Promise<PrTargetsOut> {
    return apiClient.get<PrTargetsOut>(`/v1/projects/${projectId}/citations/pr-targets`)
  },
  simulatorBaseline(projectId: string): Promise<SimulatorBaselineOut> {
    return apiClient.get<SimulatorBaselineOut>(
      `/v1/projects/${projectId}/citations/simulator-baseline`,
    )
  },
  authorityRadar(projectId: string): Promise<AuthorityRadarOut> {
    return apiClient.get<AuthorityRadarOut>(
      `/v1/projects/${projectId}/competitors/authority-radar`,
    )
  },
  groupSharedDomains(projectId: string): Promise<GroupSharedDomainsOut> {
    return apiClient.get<GroupSharedDomainsOut>(
      `/v1/projects/${projectId}/group-shared-domains`,
    )
  },
  productRelations(projectId: string): Promise<ProductRelationsOut> {
    return apiClient.get<ProductRelationsOut>(`/v1/projects/${projectId}/products/relations`)
  },
}
