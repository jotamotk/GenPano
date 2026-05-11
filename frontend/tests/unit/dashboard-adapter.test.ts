import { describe, expect, it } from 'vitest'

import {
  adaptMetricsToSparklines,
  adaptCompetitorMetricsToList,
  adaptOverviewToPrimary,
  adaptOverviewToTrend,
  buildAnalyticsContractNotice,
} from '../../src/adapters/dashboardAdapter'
import type { BrandOverviewOut } from '../../src/api/brandOverview'
import type { CompetitorMetricsOut, MetricsOut } from '../../src/api/brandMetrics'

const emptyOverview: BrandOverviewOut = {
  project_id: 'project-1',
  brand_id: null,
  brand_name: null,
  industry_id: null,
  period: { from: '2026-05-01', to: '2026-05-11' },
  kpi_cards: [],
  geo_score_30d: [],
  sov_30d: [],
  sentiment_30d: [],
  top_prompts: [],
  same_group_shared_domains: [],
  state: 'empty',
}

describe('dashboard adapter', () => {
  it('does not fabricate Brand #? for an empty unbound overview response', () => {
    expect(adaptOverviewToPrimary(emptyOverview)).toBeNull()
  })

  it('uses #495 KPI contract keys and percent scale without label heuristics', () => {
    const overview = {
      ...emptyOverview,
      brand_id: 12,
      brand_name: 'Estee Lauder',
      industry_id: 7,
      state: 'ok',
      kpi_cards: [
        {
          metric_key: 'mention_rate',
          label_zh: 'MR',
          label_en: 'MR',
          value: 16.2,
          unit: 'percent',
          value_scale: 'percent',
          denominator_label: 'eligible non-brand/category responses',
          formula_status: 'formula_pending_upstream',
          delta_30d_pct: null,
          direction: null,
        },
        {
          metric_key: 'sov',
          label_zh: 'Share',
          label_en: 'Share',
          value: 38.4,
          unit: 'percent',
          value_scale: 'percent',
          denominator_label: 'competitive-set brand-mentioned responses',
          formula_status: 'formula_pending_upstream',
          delta_30d_pct: null,
          direction: null,
        },
        {
          metric_key: 'pano_score',
          label_zh: 'Score',
          label_en: 'Score',
          value: 80,
          unit: 'score',
          value_scale: 'score_0_100',
          delta_30d_pct: null,
          direction: null,
        },
        {
          metric_key: 'sentiment',
          label_zh: 'Mood',
          label_en: 'Mood',
          value: 0.72,
          unit: 'score',
          value_scale: 'raw_-1_1',
          delta_30d_pct: null,
          direction: null,
        },
        {
          metric_key: 'rank',
          label_zh: 'Position',
          label_en: 'Position',
          value: 3,
          unit: 'rank',
          value_scale: 'ordinal',
          delta_30d_pct: null,
          direction: null,
        },
      ],
    } as unknown as BrandOverviewOut

    const primary = adaptOverviewToPrimary(overview)

    expect(primary?.panoScore).toBe(80)
    expect(primary?.mentionRate).toBeCloseTo(0.162)
    expect(primary?.sentiment).toBeCloseTo(0.72)
    expect(primary?.ranking).toBe(3)
  })

  it('normalizes sentiment defensively when final API metadata is absent', () => {
    const overview = {
      ...emptyOverview,
      brand_id: 12,
      brand_name: 'Estee Lauder',
      state: 'partial',
      kpi_cards: [
        {
          metric_key: 'sentiment',
          label_zh: 'Sentiment',
          label_en: 'Sentiment',
          value: 72,
          unit: null,
          delta_30d_pct: null,
          direction: null,
        },
      ],
    } as unknown as BrandOverviewOut

    expect(adaptOverviewToPrimary(overview)?.sentiment).toBeCloseTo(0.72)
  })

  it('formats decimal ratio series once as percent and leaves percent series unchanged', () => {
    const metrics = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      brand_id: 12,
      period: { from: '2026-05-01', to: '2026-05-11' },
      engines: null,
      state: 'ok',
      series: [
        {
          metric: 'mention_rate',
          unit: 'ratio',
          value_scale: 'decimal',
          denominator_label: 'eligible non-brand/category responses',
          points: [{ date: '2026-05-11', value: 0.162 }],
        },
        {
          metric: 'sov',
          unit: 'percent',
          value_scale: 'percent',
          denominator_label: 'competitive-set brand-mentioned responses',
          points: [{ date: '2026-05-11', value: 38.4 }],
        },
        {
          metric: 'citation',
          unit: 'ratio',
          value_scale: 'decimal',
          points: [{ date: '2026-05-11', value: 0.125 }],
        },
      ],
    } as unknown as MetricsOut

    expect(adaptMetricsToSparklines(metrics)).toMatchObject({
      mention: [16.2],
      sov: [38.4],
      citation: [12.5],
    })
  })

  it('treats malformed empty competitor payloads as deliberate empty data', () => {
    const malformed = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      state: 'empty',
      items: [],
    } as unknown as CompetitorMetricsOut

    expect(adaptCompetitorMetricsToList(malformed)).toEqual({
      primary: null,
      competitors: [],
    })
  })

  it('does not reuse SoV trend values as mention-rate trend truth', () => {
    const overview = {
      ...emptyOverview,
      brand_id: 12,
      brand_name: 'Estee Lauder',
      state: 'ok',
      geo_score_30d: [{ date: '2026-05-11', value: 80 }],
      sov_30d: [{ date: '2026-05-11', value: 0.384 }],
      sentiment_30d: [{ date: '2026-05-11', value: 0.72 }],
    } as BrandOverviewOut

    expect(adaptOverviewToTrend(overview)).toEqual([
      { day: 1, panoScore: 80, mentionRate: 0, sentiment: 0.72 },
    ])
  })

  it('summarizes partial alias-repair payloads without treating them as ok', () => {
    const notice = buildAnalyticsContractNotice({
      isLive: true,
      liveProjectId: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      overview: {
        ...emptyOverview,
        brand_id: 12,
        brand_name: 'Estee Lauder',
        state: 'partial',
        state_reason: 'partial_analyzer_data',
        identity_diagnostics: {
          canonical_brand_id: 12,
          canonical_alias_repair_count: 1,
          raw_text_owner_brand_ids: [2],
        },
        missing_sources: ['canonical_alias_repair.partial'],
        evidence_counts: {
          eligible_response_count: 58,
          brand_mentioned_response_count: 9,
        },
      } as unknown as BrandOverviewOut,
      isLoading: false,
    })

    expect(notice?.tone).toBe('partial')
    expect(notice?.stateReason).toBe('partial_analyzer_data')
    expect(notice?.details.join(' ')).toContain('canonical_alias_repair.partial')
    expect(notice?.details.join(' ')).toContain('owner brand 2')
  })

  it('summarizes missing project context as an empty state with the target id', () => {
    const notice = buildAnalyticsContractNotice({
      isLive: true,
      liveProjectId: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      overview: {
        ...emptyOverview,
        state: 'empty',
        state_reason: 'missing_project_context',
        project_scope: {
          exists: false,
          project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
          primary_brand_id: 12,
          requested_brand_id: 12,
          competitor_brand_ids: [2],
          missing_reason: 'no_project_for_primary_brand',
        },
        missing_sources: ['projects.primary_brand_id=12'],
      } as unknown as BrandOverviewOut,
      isLoading: false,
    })

    expect(notice?.tone).toBe('empty')
    expect(notice?.title).toContain('Project context pending')
    expect(notice?.details.join(' ')).toContain('95d43022-a5c8-5944-b6d6-34b29faa18b5')
  })

  it('summarizes 401 and 403 failures as auth states', () => {
    const notice = buildAnalyticsContractNotice({
      isLive: true,
      liveProjectId: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      isLoading: false,
      error: { status: 403, requestId: 'req-forbidden', path: '/api/v1/projects/x/overview' },
    })

    expect(notice?.tone).toBe('auth')
    expect(notice?.details.join(' ')).toContain('req-forbidden')
  })
})
