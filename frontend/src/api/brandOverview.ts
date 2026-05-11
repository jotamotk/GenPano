/**
 * Brand overview API (Phase 2.1).
 *
 *   GET /v1/projects/:id/overview
 *     -> {
 *          project_id, brand_id, brand_name, industry_id, period,
 *          kpi_cards: [{label_zh, label_en, value, unit, delta_30d_pct, direction}],
 *          geo_score_30d: [{date, value}],
 *          sov_30d: [{date, value}],
 *          sentiment_30d: [{date, value}],
 *          top_prompts: [{prompt_text, mention_count, ...}],
 *          same_group_shared_domains: [{domain, brand_count, total_mentions}],
 *          state: 'ok' | 'empty' | 'partial',
 *        }
 */

import { apiClient } from '../lib/apiClient'
import type {
  AnalyticsContractMetadata,
  AnalyticsState,
  MetricContractFields,
} from './analyticsContract'

export interface KpiCard extends MetricContractFields {
  label_zh: string
  label_en: string
  value: number
  unit: string | null
  delta_30d_pct: number | null
  direction: 'up' | 'down' | 'flat' | null
}

export interface TrendPoint {
  date: string
  value: number
}

export interface TopPromptRow {
  prompt_id: number | null
  prompt_text: string
  mention_count: number
  avg_position_rank: number | null
  avg_sentiment_score: number | null
}

export interface GroupSharedDomainRow {
  domain: string
  brand_count: number
  total_mentions: number
}

export interface BrandOverviewOut extends AnalyticsContractMetadata {
  project_id: string
  brand_id: number | null
  brand_name: string | null
  industry_id: number | null
  period: { from: string; to: string }
  kpi_cards: KpiCard[]
  geo_score_30d: TrendPoint[]
  sov_30d: TrendPoint[]
  sentiment_30d: TrendPoint[]
  top_prompts: TopPromptRow[]
  same_group_shared_domains: GroupSharedDomainRow[]
  state: AnalyticsState
}

export const brandOverviewApi = {
  get(projectId: string, brandId?: number | null): Promise<BrandOverviewOut> {
    const qs = brandId != null ? `?brand_id=${encodeURIComponent(String(brandId))}` : ''
    return apiClient.get<BrandOverviewOut>(`/v1/projects/${projectId}/overview${qs}`)
  },
}
