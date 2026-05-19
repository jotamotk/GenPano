import { describe, expect, it } from 'vitest'

import {
  adaptMetricsToSparklines,
  adaptCompetitorMetricsToBubble,
  adaptCompetitorMetricsToList,
  adaptCompetitorMetricsToSov,
  adaptCompetitorTrendsToTrendData,
  adaptCompetitorTrendsToVisibilityPanoTrend,
  adaptOverviewToPrimary,
  adaptOverviewToSov,
  adaptOverviewToTrend,
} from '../../src/adapters/dashboardAdapter'
import type { BrandOverviewOut } from '../../src/api/brandOverview'
import type { CompetitorMetricsOut, CompetitorTrendsOut, MetricsOut } from '../../src/api/brandMetrics'

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
          formula_status: 'ok',
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
          formula_status: 'ok',
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
          formula_status: 'ok',
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
          formula_status: 'ok',
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
          formula_status: 'ok',
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

  it('normalizes sentiment defensively when final API metadata is absent on ok payloads', () => {
    const overview = {
      ...emptyOverview,
      brand_id: 12,
      brand_name: 'Estee Lauder',
      state: 'ok',
      kpi_cards: [
        {
          metric_key: 'sentiment',
          label_zh: 'Sentiment',
          label_en: 'Sentiment',
          value: 72,
          unit: null,
          formula_status: 'ok',
          delta_30d_pct: null,
          direction: null,
        },
      ],
    } as unknown as BrandOverviewOut

    expect(adaptOverviewToPrimary(overview)?.sentiment).toBeCloseTo(0.72)
  })

  it('does not render non-ok formula KPI values as normal production metrics', () => {
    const overview = {
      ...emptyOverview,
      brand_id: 12,
      brand_name: 'Estee Lauder',
      state: 'partial',
      state_reason: 'brand_mentions.competitive_set_missing',
      kpi_cards: [
        {
          metric_key: 'mention_rate',
          label_zh: 'Mention',
          label_en: 'Mention',
          value: 100,
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'formula_pending_upstream',
          delta_30d_pct: 9.9,
          direction: 'up',
        },
        {
          metric_key: 'rank',
          label_zh: 'Rank',
          label_en: 'Rank',
          value: 1,
          unit: 'rank',
          value_scale: 'ordinal',
          formula_status: 'rank_evidence_missing',
          delta_30d_pct: null,
          direction: null,
        },
      ],
    } as unknown as BrandOverviewOut

    const primary = adaptOverviewToPrimary(overview)

    expect(primary?.mentionRate).toBeNull()
    expect(primary?.ranking).toBeNull()
  })

  it('renders usable metric-level KPI values when the overview endpoint is partial', () => {
    const overview = {
      ...emptyOverview,
      brand_id: 12,
      brand_name: 'Estee Lauder',
      industry_id: 7,
      state: 'partial',
      state_reason: 'brand_mentions.position_rank_missing',
      kpi_cards: [
        {
          metric_key: 'pano_score',
          label_zh: 'PANO',
          label_en: 'PANO',
          value: 80,
          unit: 'score',
          value_scale: 'score_0_100',
          formula_status: 'ok',
          delta_30d_pct: null,
          direction: null,
        },
        {
          metric_key: 'mention_rate',
          label_zh: 'Mention',
          label_en: 'Mention',
          value: 82.9,
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
          delta_30d_pct: null,
          direction: null,
        },
        {
          metric_key: 'sov',
          label_zh: 'SoV',
          label_en: 'Share of Voice',
          value: 97.3,
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
          delta_30d_pct: null,
          direction: null,
        },
        {
          metric_key: 'sentiment',
          label_zh: 'Sentiment',
          label_en: 'Sentiment',
          value: 0,
          unit: 'score',
          value_scale: 'raw_-1_1',
          formula_status: 'ok',
          delta_30d_pct: null,
          direction: null,
        },
        {
          metric_key: 'rank',
          label_zh: 'Rank',
          label_en: 'Rank',
          value: 1,
          unit: 'rank',
          value_scale: 'ordinal',
          formula_status: 'rank_evidence_missing',
          delta_30d_pct: null,
          direction: null,
        },
      ],
    } as unknown as BrandOverviewOut

    const primary = adaptOverviewToPrimary(overview)

    expect(primary?.panoScore).toBe(80)
    expect(primary?.mentionRate).toBeCloseTo(0.829)
    expect(primary?.sov).toBeCloseTo(97.3)
    expect(primary?.sentiment).toBe(0)
    expect(primary?.ranking).toBeNull()
  })

  it('does not use partial overview KPI values that lack metric-level evidence', () => {
    const overview = {
      ...emptyOverview,
      brand_id: 12,
      brand_name: 'Estee Lauder',
      state: 'partial',
      kpi_cards: [
        {
          metric_key: 'mention_rate',
          label_zh: 'Mention',
          label_en: 'Mention',
          value: 82.9,
          unit: 'percent',
          value_scale: 'percent',
          delta_30d_pct: null,
          direction: null,
        },
      ],
    } as unknown as BrandOverviewOut

    expect(adaptOverviewToPrimary(overview)?.mentionRate).toBeNull()
  })

  it('does not synthesize SoV slices or Others from a single overview KPI card', () => {
    const overview = {
      ...emptyOverview,
      brand_id: 12,
      brand_name: 'Estee Lauder',
      state: 'ok',
      kpi_cards: [
        {
          metric_key: 'sov',
          label_zh: 'SoV',
          label_en: 'Share of Voice',
          value: 38.4,
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
          delta_30d_pct: null,
          direction: null,
        },
      ],
    } as unknown as BrandOverviewOut

    expect(adaptOverviewToSov(overview)).toEqual([])
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
          formula_status: 'ok',
          denominator_label: 'eligible non-brand/category responses',
          points: [{ date: '2026-05-11', value: 0.162 }],
        },
        {
          metric: 'sov',
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
          denominator_label: 'competitive-set brand-mentioned responses',
          points: [{ date: '2026-05-11', value: 38.4 }],
        },
        {
          metric: 'citation',
          unit: 'ratio',
          value_scale: 'decimal',
          formula_status: 'ok',
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

  it('normalizes competitor avg_sentiment score_0_100 metadata before list and bubble use', () => {
    const metrics = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      primary_brand_id: 12,
      period: { from: '2026-05-01', to: '2026-05-11' },
      state: 'ok',
      metric_definitions: {
        avg_sov: {
          metric_key: 'avg_sov',
          unit: 'ratio',
          value_scale: 'decimal',
          formula_status: 'ok',
        },
        avg_sentiment: {
          metric_key: 'avg_sentiment',
          unit: 'score',
          value_scale: 'score_0_100',
          formula_status: 'ok',
        },
      },
      primary: {
        brand_id: 12,
        brand_key: 'estee_lauder',
        brand_name: 'Estee Lauder',
        avg_geo_score: 80,
        avg_mention_rate: 0.162,
        avg_sov: 0.384,
        avg_sentiment: 64,
        co_mention_count: 9,
        delta_30d_pct: null,
      },
      competitors: [
        {
          brand_id: 34,
          brand_key: 'lancome',
          brand_name: 'Lancome',
          avg_geo_score: 73,
          avg_mention_rate: 0.141,
          avg_sov: 0.284,
          avg_sentiment: 72,
          co_mention_count: 7,
          delta_30d_pct: null,
        },
      ],
    } as CompetitorMetricsOut

    const list = adaptCompetitorMetricsToList(metrics)
    const bubble = adaptCompetitorMetricsToBubble(metrics)

    expect(list.primary?.sentiment).toBeCloseTo(0.64)
    expect(list.competitors[0]?.sentiment).toBeCloseTo(0.72)
    expect(bubble[0]?.sentiment).toBeCloseTo(0.64)
    expect(bubble[1]?.sentiment).toBeCloseTo(0.72)
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
      { day: 1, date: '2026-05-11', name: '2026-05-11', panoScore: 80, mentionRate: null, sentiment: 0.72 },
    ])
  })

  it('drops non-ok metric series instead of turning pending formulas into sparklines', () => {
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
          formula_status: 'formula_pending_upstream',
          points: [{ date: '2026-05-11', value: 1 }],
        },
        {
          metric: 'sov',
          unit: 'ratio',
          value_scale: 'decimal',
          formula_status: 'ok',
          points: [{ date: '2026-05-11', value: null }],
        },
      ],
    } as unknown as MetricsOut

    expect(adaptMetricsToSparklines(metrics)).toMatchObject({
      mention: [],
      sov: [],
    })
  })

  it('keeps usable metric-level sparklines when the metrics endpoint is partial', () => {
    const metrics = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      brand_id: 12,
      period: { from: '2026-05-01', to: '2026-05-11' },
      engines: null,
      state: 'partial',
      state_reason: 'rank_inputs_missing',
      series: [
        {
          metric: 'mention_rate',
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
          points: [{ date: '2026-05-11', value: 82.9 }],
        },
        {
          metric: 'sov',
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
          points: [{ date: '2026-05-11', value: 97.3 }],
        },
        {
          metric: 'sentiment',
          unit: 'score',
          value_scale: 'raw_-1_1',
          formula_status: 'ok',
          points: [{ date: '2026-05-11', value: 0 }],
        },
        {
          metric: 'rank',
          unit: 'rank',
          value_scale: 'ordinal',
          formula_status: 'rank_evidence_missing',
          points: [{ date: '2026-05-11', value: 1 }],
        },
      ],
    } as unknown as MetricsOut

    expect(adaptMetricsToSparklines(metrics)).toMatchObject({
      mention: [82.9],
      sov: [97.3],
      sentiment: [0],
      rank: [],
    })
  })

  it('keeps real competitor rows under unrelated endpoint partial state', () => {
    const metrics = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      primary_brand_id: 12,
      period: { from: '2026-05-01', to: '2026-05-11' },
      state: 'partial',
      state_reason: 'position_rank_missing',
      metric_definitions: {
        avg_sov: {
          metric_key: 'avg_sov',
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
        },
        avg_sentiment: {
          metric_key: 'avg_sentiment',
          unit: 'score',
          value_scale: 'raw_-1_1',
          formula_status: 'ok',
        },
      },
      primary: {
        brand_id: 12,
        brand_key: 'estee_lauder',
        brand_name: 'Estee Lauder',
        avg_geo_score: 80,
        avg_mention_rate: 82.9,
        avg_sov: 97.3,
        avg_sentiment: 0,
        co_mention_count: 9,
        delta_30d_pct: null,
      },
      competitors: [
        {
          brand_id: 34,
          brand_key: 'lancome',
          brand_name: 'Lancome',
          avg_geo_score: 73,
          avg_mention_rate: 12.4,
          avg_sov: 2.7,
          avg_sentiment: 0.2,
          co_mention_count: 7,
          delta_30d_pct: null,
        },
      ],
    } as CompetitorMetricsOut

    expect(adaptCompetitorMetricsToSov(metrics)).toEqual([
      { name: 'Estee Lauder', value: 97.3 },
      { name: 'Lancome', value: 2.7 },
    ])
    expect(adaptCompetitorMetricsToBubble(metrics)).toEqual([
      {
        brand: '',
        sov: null,
        sentiment: null,
        mentions: 0,
        endpointState: 'partial',
        stateReason: 'position_rank_missing',
        missingInputs: [],
        configuredCompetitorCount: null,
      },
      { brand: 'Estee Lauder', sov: 97.3, sentiment: 0, mentions: 9 },
      { brand: 'Lancome', sov: 2.7, sentiment: 0.2, mentions: 7 },
    ])
  })

  it('preserves competitor bubble rows with missing axis evidence for the visualization state', () => {
    const metrics = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      primary_brand_id: 12,
      period: { from: '2026-05-01', to: '2026-05-11' },
      state: 'partial',
      state_reason: 'competitive_axis_missing',
      metric_definitions: {
        avg_sov: {
          metric_key: 'avg_sov',
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
        },
        avg_sentiment: {
          metric_key: 'avg_sentiment',
          unit: 'score',
          value_scale: 'raw_-1_1',
          formula_status: 'sentiment_evidence_missing',
        },
      },
      primary: {
        brand_id: 12,
        brand_key: 'bestcoffer',
        brand_name: 'bestCoffer',
        avg_geo_score: 80,
        avg_mention_rate: 82.9,
        avg_sov: 97.3,
        avg_sentiment: 0,
        co_mention_count: 9,
        delta_30d_pct: null,
      },
      competitors: [
        {
          brand_id: 34,
          brand_key: 'lancome',
          brand_name: 'Lancome',
          avg_geo_score: 73,
          avg_mention_rate: 12.4,
          avg_sov: 2.7,
          avg_sentiment: null,
          co_mention_count: 7,
          delta_30d_pct: null,
        },
      ],
    } as CompetitorMetricsOut

    expect(adaptCompetitorMetricsToBubble(metrics)).toEqual([
      {
        brand: '',
        sov: null,
        sentiment: null,
        mentions: 0,
        endpointState: 'partial',
        stateReason: 'competitive_axis_missing',
        missingInputs: [],
        configuredCompetitorCount: null,
      },
      { brand: 'bestCoffer', sov: 97.3, sentiment: null, mentions: 9 },
      { brand: 'Lancome', sov: 2.7, sentiment: null, mentions: 7 },
    ])
  })

  it('preserves competitor endpoint state when partial metrics return no plottable rows', () => {
    const metrics = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      primary_brand_id: 12,
      period: { from: '2026-05-11', to: '2026-05-18' },
      state: 'partial',
      state_reason: 'missing_formula_inputs',
      formula_status: 'missing_required_inputs',
      missing_inputs: ['eligible_response_denominator'],
      primary: null,
      competitors: [],
      project_scope: {
        exists: true,
        project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
        primary_brand_id: 12,
        requested_brand_id: 12,
        competitor_brand_ids: [2],
      },
      evidence_counts: {
        competitor_brand_count: 1,
        eligible_response_count: 0,
        competitive_mention_count: 468,
      },
    } as CompetitorMetricsOut

    expect(adaptCompetitorMetricsToBubble(metrics)).toEqual([
      {
        brand: '',
        sov: null,
        sentiment: null,
        mentions: 0,
        endpointState: 'partial',
        stateReason: 'missing_formula_inputs',
        missingInputs: ['eligible_response_denominator'],
        configuredCompetitorCount: 1,
      },
    ])
  })

  it('preserves competitor endpoint state ahead of row data when partial metrics include rows', () => {
    const metrics = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      primary_brand_id: 12,
      period: { from: '2026-05-11', to: '2026-05-18' },
      state: 'partial',
      state_reason: 'missing_formula_inputs',
      formula_status: 'missing_required_inputs',
      missing_inputs: ['eligible_response_denominator'],
      primary: {
        brand_id: 12,
        brand_key: 'estee_lauder',
        brand_name: 'Estee Lauder',
        avg_geo_score: 80,
        avg_mention_rate: 82.9,
        avg_sov: 97.3,
        avg_sentiment: 0.2,
        co_mention_count: 9,
        delta_30d_pct: null,
      },
      competitors: [
        {
          brand_id: 2,
          brand_key: 'la_roche_posay',
          brand_name: 'La Roche-Posay',
          avg_geo_score: 73,
          avg_mention_rate: 12.4,
          avg_sov: 2.7,
          avg_sentiment: 0.1,
          co_mention_count: 7,
          delta_30d_pct: null,
        },
      ],
      project_scope: {
        exists: true,
        project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
        primary_brand_id: 12,
        requested_brand_id: 12,
        competitor_brand_ids: [2],
      },
      evidence_counts: {
        competitor_brand_count: 1,
        eligible_response_count: 0,
        competitive_mention_count: 468,
      },
      metric_definitions: {
        avg_sov: {
          metric_key: 'avg_sov',
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
        },
        avg_sentiment: {
          metric_key: 'avg_sentiment',
          unit: 'score',
          value_scale: 'raw_-1_1',
          formula_status: 'ok',
        },
      },
    } as CompetitorMetricsOut

    expect(adaptCompetitorMetricsToBubble(metrics)).toEqual([
      {
        brand: '',
        sov: null,
        sentiment: null,
        mentions: 0,
        endpointState: 'partial',
        stateReason: 'missing_formula_inputs',
        missingInputs: ['eligible_response_denominator'],
        configuredCompetitorCount: 1,
      },
      { brand: 'Estee Lauder', sov: 97.3, sentiment: 0.2, mentions: 9 },
      { brand: 'La Roche-Posay', sov: 2.7, sentiment: 0.1, mentions: 7 },
    ])
  })

  it('uses /metrics mention_rate for competitor trend rows and never rebuilds it from SoV', () => {
    const overview = {
      ...emptyOverview,
      brand_id: 12,
      brand_name: 'Estee Lauder',
      state: 'ok',
      sov_30d: [{ date: '2026-05-11', value: 0.384 }],
      sentiment_30d: [{ date: '2026-05-11', value: 0.72 }],
    } as BrandOverviewOut
    const trends = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      metric: 'geo_score',
      period: { from: '2026-05-01', to: '2026-05-11' },
      state: 'ok',
      metric_definition: {
        metric_key: 'geo_score',
        unit: 'score',
        value_scale: 'score_0_100',
        formula_status: 'ok',
      },
      series: [
        {
          brand_id: 12,
          brand_key: 'estee_lauder',
          brand_name: 'Estee Lauder',
          is_primary: true,
          points: [{ date: '2026-05-11', value: 80 }],
        },
        {
          brand_id: 34,
          brand_key: 'lancome',
          brand_name: 'Lancome',
          is_primary: false,
          points: [{ date: '2026-05-11', value: 73 }],
        },
      ],
    } as CompetitorTrendsOut
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
          formula_status: 'ok',
          denominator_label: 'eligible non-brand/category responses',
          points: [{ date: '2026-05-11', value: 0.162 }],
        },
      ],
    } as MetricsOut

    expect(adaptCompetitorTrendsToTrendData(trends, overview, metrics)).toEqual([
      { day: 1, date: '2026-05-11', name: '2026-05-11', panoScore: 80, mentionRate: 16.2, sentiment: 0.72, Lancome: 73 },
    ])
    expect(adaptCompetitorTrendsToTrendData(trends, overview)).toEqual([
      { day: 1, date: '2026-05-11', name: '2026-05-11', panoScore: 80, mentionRate: null, sentiment: 0.72, Lancome: 73 },
    ])
  })

  it('does not build live visibility PANO trends from mention metric rows', () => {
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
          formula_status: 'ok',
          points: [{ date: '2026-05-11', value: 0.162 }],
        },
      ],
    } as MetricsOut

    expect(adaptMetricsToSparklines(metrics).mention).toEqual([16.2])
    expect(adaptCompetitorTrendsToVisibilityPanoTrend(null, 'Estee Lauder')).toEqual({
      rows: [],
      lines: [],
    })
  })

  it('passes real geo trend rows through for live visibility PANO trends', () => {
    const trends = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      metric: 'geo_score',
      period: { from: '2026-05-01', to: '2026-05-11' },
      state: 'ok',
      metric_definition: {
        metric_key: 'geo_score',
        unit: 'score',
        value_scale: 'score_0_100',
        formula_status: 'ok',
      },
      series: [
        {
          brand_id: 12,
          brand_key: 'estee_lauder',
          brand_name: 'Estee Lauder',
          is_primary: true,
          points: [
            { date: '2026-05-10', value: 80 },
            { date: '2026-05-11', value: null },
          ],
        },
        {
          brand_id: 34,
          brand_key: 'lancome',
          brand_name: 'Lancome',
          is_primary: false,
          points: [
            { date: '2026-05-10', value: 73 },
            { date: '2026-05-11', value: null },
          ],
        },
      ],
    } as CompetitorTrendsOut

    const trend = adaptCompetitorTrendsToVisibilityPanoTrend(trends, 'Estee Lauder')

    expect(trend.rows).toEqual([
      { name: '2026-05-10', day: 1, date: '2026-05-10', panoScore: 80, mentionRate: null, sentiment: null, Lancome: 73 },
      { name: '2026-05-11', day: 2, date: '2026-05-11', panoScore: null, mentionRate: null, sentiment: null, Lancome: null },
    ])
    expect(trend.lines.map((line) => line.key)).toEqual(['panoScore', 'Lancome'])
  })

  it('labels live visibility PANO primary from /competitors/trends instead of stale page fallback', () => {
    const trends = {
      project_id: '7380c0e0-8798-4a5f-998f-42010a7d9caa',
      metric: 'geo_score',
      period: { from: '2026-05-17', to: '2026-05-17' },
      state: 'ok',
      metric_definition: {
        metric_key: 'geo_score',
        unit: 'score',
        value_scale: 'score_0_100',
        formula_status: 'ok',
      },
      series: [
        {
          brand_id: 24,
          brand_key: 'bestcoffer',
          brand_name: 'bestCoffer',
          is_primary: true,
          points: [{ date: '2026-05-17', value: 80 }],
        },
        {
          brand_id: 25,
          brand_key: 'ibm_security',
          brand_name: 'IBM Security',
          is_primary: false,
          points: [{ date: '2026-05-17', value: 68 }],
        },
      ],
    } as CompetitorTrendsOut

    const trend = adaptCompetitorTrendsToVisibilityPanoTrend(trends, '雅诗兰黛')

    expect(trend.lines.find((line) => line.key === 'panoScore')?.label).toBe('bestCoffer')
    expect(trend.lines.map((line) => line.label).join('|')).not.toMatch(/雅诗兰黛|Estee|Estée/i)
  })

  it('does not append frontend Others slices to backend competitor SoV rows', () => {
    const metrics = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      primary_brand_id: 12,
      period: { from: '2026-05-01', to: '2026-05-11' },
      state: 'ok',
      metric_definitions: {
        avg_sov: {
          metric_key: 'avg_sov',
          unit: 'ratio',
          value_scale: 'decimal',
          formula_status: 'ok',
        },
      },
      primary: {
        brand_id: 12,
        brand_key: 'estee_lauder',
        brand_name: 'Estee Lauder',
        avg_geo_score: 80,
        avg_mention_rate: 0.162,
        avg_sov: 0.384,
        avg_sentiment: 0.64,
        co_mention_count: 9,
        delta_30d_pct: null,
      },
      competitors: [],
    } as CompetitorMetricsOut

    expect(adaptCompetitorMetricsToSov(metrics)).toEqual([
      { name: 'Estee Lauder', value: 38.4 },
    ])
  })

})
