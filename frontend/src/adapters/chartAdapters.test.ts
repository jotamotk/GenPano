import { describe, expect, it } from 'vitest'

import {
  adaptCitationComposition,
  adaptEngineMetricsToBreakdown,
  adaptMentionSamples,
  adaptSentimentByEngine,
  adaptTopicAttribution,
} from './chartAdapters'

describe('chart adapters analyzer formula-status guards', () => {
  it('renders metric-level ok cells under an endpoint-level partial state', () => {
    const rows = adaptEngineMetricsToBreakdown({
      project_id: 'p1',
      period: { from: '2026-05-01', to: '2026-05-12' },
      state: 'partial',
      formula_status: 'partial',
      metric_formula_evidence: {
        coverage: { formula_status: 'ok' },
        sov: { formula_status: 'missing_required_inputs', reason_codes: ['target_only_sov'] },
        citation: { formula_status: 'ok' },
      },
      items: [
        {
          engine: 'deepseek',
          mention_rate: 0.42,
          sov: 1,
          citation_rate: 0.25,
          sentiment: 0.3,
        },
      ],
    })

    expect(rows).toEqual([
      {
        engine: 'deepseek',
        mentionRate: 42,
        sov: null,
        citationShare: 25,
      },
    ])
  })

  it('does not render sentiment explanatory rows from score-only evidence', () => {
    const partialEvidence = {
      project_id: 'p1',
      state: 'partial',
      formula_status: 'partial',
      metric_formula_evidence: {
        sentiment: {
          formula_status: 'missing_required_inputs',
          reason_codes: ['missing_sentiment_driver_quote'],
        },
      },
    } as const

    expect(
      adaptTopicAttribution({
        ...partialEvidence,
        items: [
          {
            topic_id: 1,
            topic_name: 'Texture',
            negative_count: 3,
            negative_ratio: 0.75,
            sample_snippet: 'sticky finish',
          },
        ],
      }),
    ).toEqual([])

    expect(
      adaptMentionSamples({
        ...partialEvidence,
        items: [
          {
            mention_id: 1,
            response_id: 10,
            label: 'negative',
            polarity: 'negative',
            summary: 'sticky finish',
            snippet: 'sticky finish',
            engine: 'deepseek',
            topic: 'Texture',
            occurred_at: '2026-05-11T00:00:00Z',
          },
        ],
      }),
    ).toEqual([])
  })

  it('renders sentiment distribution rows only when sentiment evidence is ok', () => {
    expect(
      adaptSentimentByEngine({
        project_id: 'p1',
        period: { from: '2026-05-01', to: '2026-05-12' },
        state: 'partial',
        formula_status: 'partial',
        metric_formula_evidence: {
          sentiment: { formula_status: 'ok' },
        },
        items: [{ engine: 'deepseek', positive: 2, neutral: 1, negative: 0 }],
      }),
    ).toEqual([{ engine: 'deepseek', positive: 2, neutral: 1, negative: 0 }])
  })

  it('keeps unresolved citation attribution separate from chart-ready composition', () => {
    expect(
      adaptCitationComposition({
        project_id: 'p1',
        period: { from: '2026-05-01', to: '2026-05-12' },
        state: 'partial',
        formula_status: 'partial',
        metric_formula_evidence: {
          citation: {
            formula_status: 'missing_required_inputs',
            reason_codes: ['unresolved_citation_attribution'],
            attributed_citation_count: 1,
            unresolved_citation_count: 1,
          },
        },
        total: 1,
        segments: [{ label: 'Tier 1', tier: 1, count: 1, pct: 100 }],
      }),
    ).toEqual([])
  })
})
