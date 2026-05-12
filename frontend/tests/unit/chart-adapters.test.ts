import { describe, expect, it } from 'vitest'

import {
  adaptEngineMetricsToBreakdown,
  adaptHeatmap,
  adaptPrTargets,
  adaptSentimentTrend,
} from '../../src/adapters/chartAdapters'
import type {
  EngineMetricsOut,
  PrTargetsOut,
  SentimentTrendByEngineOut,
  TopicHeatmapOut,
} from '../../src/api/charts'

describe('chart adapters no-fallback contract', () => {
  it('preserves missing engine metric cells instead of converting them to zero', () => {
    const out = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      period: { from: '2026-05-01', to: '2026-05-11' },
      state: 'ok',
      items: [
        {
          engine: 'chatgpt',
          mention_rate: null,
          sov: 0.25,
          citation_rate: null,
          sentiment: null,
        },
      ],
    } as EngineMetricsOut

    expect(adaptEngineMetricsToBreakdown(out)).toEqual([
      {
        engine: 'chatgpt',
        mentionRate: null,
        sov: 25,
        citationShare: null,
      },
    ])
  })

  it('preserves explicit null heatmap cells for partial topic evidence', () => {
    const out = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      metric: 'mention_rate',
      state: 'partial',
      rows: [
        {
          brand_id: 12,
          brand_name: 'Estee Lauder',
          values: [
            {
              topic_id: 7,
              topic_label: 'Anti-aging',
              value: null,
              sample: 0,
            },
          ],
        },
      ],
    } as TopicHeatmapOut

    expect(adaptHeatmap(out, 12)[0]?.values[0]).toMatchObject({
      topicId: '7',
      topicLabel: 'Anti-aging',
      value: null,
      sample: 0,
    })
  })

  it('preserves null sentiment trend points instead of drawing fake zero lines', () => {
    const out = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      period: { from: '2026-05-01', to: '2026-05-11' },
      engines: ['chatgpt'],
      state: 'ok',
      items: [
        {
          date: '2026-05-11',
          by_engine: { chatgpt: null },
        },
      ],
    } as SentimentTrendByEngineOut

    expect(adaptSentimentTrend(out)).toEqual({
      engines: ['chatgpt'],
      rows: [{ name: '05-11', chatgpt: null }],
    })
  })

  it('does not derive PR scores or KOL diversity when the backend omits formula evidence', () => {
    const out = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      state: 'ok',
      targets: [
        {
          domain: 'example.com',
          tier: 2,
          we_count: 0,
          competitors_count: 8,
          gap: 8,
          suggestion: null,
        },
      ],
      kol_scorecards: [
        {
          name: 'Creator A',
          platform: 'video',
          audience_score: null,
          quality_score: 88,
          risk: null,
          notes: null,
        },
      ],
      tier2_matrix: { domains: [], brands: [] },
    } as PrTargetsOut

    const adapted = adaptPrTargets(out)

    expect(adapted.targets[0]).toMatchObject({
      prScore: null,
      trending30dPct: null,
      authorityConfidence: null,
      citations30d: 8,
    })
    expect(adapted.kolScorecards[0]).toMatchObject({
      authorityConfidence: null,
      avgCitationsPerWeek: null,
      diversity: null,
      brandDiversity90d: [],
    })
  })

  it('drops non-ok citation chart payloads instead of charting them as normal', () => {
    const out = {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      state: 'partial',
      targets: [
        {
          domain: 'example.com',
          tier: null,
          we_count: 0,
          competitors_count: 0,
          gap: 0,
          suggestion: null,
        },
      ],
      kol_scorecards: [],
      tier2_matrix: { domains: [], brands: [] },
    } as PrTargetsOut

    expect(adaptPrTargets(out).targets).toEqual([])
  })
})
