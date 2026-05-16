import { describe, expect, it } from 'vitest'

import {
  adaptCitationComposition,
  adaptEngineMetricsToBreakdown,
  adaptMentionSamples,
  adaptProductRelations,
  adaptSimulatorBaseline,
  adaptSentimentByEngine,
  adaptTopCitedPages,
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

  it('does not render simulator baseline when pano_geo evidence is missing', () => {
    expect(
      adaptSimulatorBaseline({
        project_id: 'p1',
        state: 'ok',
        formula_status: 'ok',
        metric_formula_evidence: {
          citation: { formula_status: 'ok' },
        },
        current_pano: 72,
        industry_median: 70,
        industry_top3_avg: 82,
        tiers: [{ tier: 1, current_count: 2, weight: 0.4, confidence: 1 }],
        presets: [],
      }),
    ).toBeNull()
  })

  it('does not synthesize product relation confidence when backend omits it', () => {
    expect(
      adaptProductRelations({
        project_id: 'p1',
        state: 'ok',
        formula_status: 'ok',
        metric_formula_evidence: {
          product: { formula_status: 'ok' },
        },
        items: [
          {
            product_a_id: 1,
            product_a_name: 'A',
            product_b_id: 2,
            product_b_name: 'B',
            type: 'COMPETES_WITH',
            confidence: null,
          },
        ],
      }),
    ).toEqual([
      {
        productA: 1,
        productAName: 'A',
        productB: 2,
        productBName: 'B',
        type: 'COMPETES_WITH',
        confidence: null,
      },
    ])
  })

  // Issue #1002 follow-up: the upstream citation_sources.title column
  // sometimes carries integer-like garbage (Doubao reference indices stored
  // as `-1`, `-2`, `[5]`, …). Live bestCoffer page showed these as the row
  // titles, which read like negative counts. Sanitize at the adapter so the
  // page renders a URL-derived label instead.
  it('falls back to URL-derived title when the upstream title is non-readable', () => {
    const okCitationEvidence = {
      state: 'ok',
      formula_status: 'ok',
      metric_formula_evidence: { citation: { formula_status: 'ok' } },
    } as const
    const rows = adaptTopCitedPages({
      ...okCitationEvidence,
      items: [
        // Bare negative integer → fall back.
        { url: 'https://example.com/foo/bar', title: '-1', domain: 'example.com', tier: 1, count: 6, first_seen_at: null, last_seen_at: null },
        // Bracketed reference → fall back.
        { url: 'https://example.com/baz', title: '[5]', domain: 'example.com', tier: 1, count: 4, first_seen_at: null, last_seen_at: null },
        // Empty after trim → fall back.
        { url: 'https://example.com/qux', title: '   ', domain: 'example.com', tier: 4, count: 2, first_seen_at: null, last_seen_at: null },
        // Genuine human title → keep.
        { url: 'https://example.com/keep', title: 'Real human title', domain: 'example.com', tier: 1, count: 1, first_seen_at: null, last_seen_at: null },
      ],
    } as any)
    expect(rows.map((r) => r.title)).toEqual([
      'bar',
      'baz',
      'qux',
      'Real human title',
    ])
  })
})
