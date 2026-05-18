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

  it('maps the backend ok by-engine visibility contract without mixing metrics', () => {
    const rows = adaptEngineMetricsToBreakdown({
      project_id: 'p1',
      period: { from: '2026-05-01', to: '2026-05-12' },
      state: 'ok',
      state_reason: 'data_available',
      formula_status: 'ok',
      source_provenance: ['admin_facts', 'brand_mentions', 'citation_sources'],
      evidence_counts: { admin_fact_response_count: 2 },
      metric_formula_evidence: {
        coverage: { formula_status: 'ok' },
        sov: { formula_status: 'ok', denominator_count: 4 },
        citation: { formula_status: 'ok' },
      },
      selected_filters: {
        project_id: 'p1',
        from: '2026-05-01',
        to: '2026-05-12',
      },
      items: [
        {
          engine: 'chatgpt',
          mention_rate: 0.5,
          sov: 0.25,
          citation_rate: 1.0,
          sentiment: null,
        },
      ],
    })

    expect(rows).toEqual([
      {
        engine: 'chatgpt',
        mentionRate: 50,
        sov: 25,
        citationShare: 100,
      },
    ])
  })

  it('keeps target-only SoV unavailable while preserving fact-backed mention and citation values', () => {
    const rows = adaptEngineMetricsToBreakdown({
      project_id: 'p1',
      period: { from: '2026-05-01', to: '2026-05-12' },
      state: 'partial',
      state_reason: 'partial_analyzer_data',
      formula_status: 'partial',
      missing_inputs: ['target_only_sov'],
      metric_formula_evidence: {
        coverage: { formula_status: 'ok' },
        sov: {
          formula_status: 'missing_required_inputs',
          numerator_count: 2,
          denominator_count: 2,
        },
        citation: { formula_status: 'ok' },
      },
      items: [
        {
          engine: 'chatgpt',
          mention_rate: 1.0,
          sov: null,
          citation_rate: 1.0,
          sentiment: 0.7,
        },
      ],
    })

    expect(rows).toEqual([
      {
        engine: 'chatgpt',
        mentionRate: 100,
        sov: null,
        citationShare: 100,
      },
    ])
  })

  it('keeps citation-specific unusable evidence out of the visibility metrics', () => {
    const rows = adaptEngineMetricsToBreakdown({
      project_id: 'p1',
      period: { from: '2026-05-01', to: '2026-05-12' },
      state: 'partial',
      formula_status: 'partial',
      missing_inputs: ['unresolved_citation_attribution'],
      metric_formula_evidence: {
        coverage: { formula_status: 'ok' },
        sov: { formula_status: 'ok' },
        citation: {
          formula_status: 'missing_required_inputs',
          reason_codes: ['unresolved_citation_attribution'],
        },
      },
      items: [
        {
          engine: 'chatgpt',
          mention_rate: 1.0,
          sov: 0.5,
          citation_rate: null,
          sentiment: 0.7,
        },
      ],
    })

    expect(rows).toEqual([
      {
        engine: 'chatgpt',
        mentionRate: 100,
        sov: 50,
        citationShare: null,
      },
    ])
  })

  it('does not render sentiment-driven topic attribution rows from score-only evidence', () => {
    // `adaptTopicAttribution` legitimately gates on the `sentiment` metric
    // because the topic_attribution endpoint computes per-topic negative
    // counts from sentiment analysis. Without trustworthy sentiment evidence,
    // the explanatory chart should stay empty.
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

  // Issue #1175: the mention_samples endpoint is a paginated response-sample
  // list, not a sentiment-metric endpoint. It does not carry
  // `metric_formula_evidence.sentiment`. The previous gate
  // `canUseChartMetrics(out, ['sentiment'])` stripped every real response.
  // Live server diagnostics run 26032322450 against BestCoffer brandId=24
  // captured `state=ok, formula_status=ok, evidence_count=89, items=20`
  // — the user saw "Loaded 0 of 273 matching responses" anyway because
  // the adapter returned []. The fix gates on the endpoint's own
  // ChartState (ok/partial) instead.
  it('renders mention_samples rows when the endpoint state is ok and no sentiment metric evidence is present', () => {
    // Real shape captured from CONTRACT_SUMMARY for BestCoffer brandId=24:
    // {"state":"ok","state_reason":"data_available","formula_status":"ok",
    //  "evidence_count":89,"items":20}. Reproduce a 2-item slice with the
    // same field set the backend emits per mention sample.
    const rows = adaptMentionSamples({
      project_id: 'bestcoffer',
      state: 'ok',
      state_reason: 'data_available',
      formula_status: 'ok',
      evidence_count: 89,
      total: 273,
      limit: 20,
      offset: 0,
      has_more: true,
      items: [
        {
          mention_id: 501,
          response_id: 9001,
          query_id: 4242,
          label: 'positive',
          polarity: 'positive',
          summary: 'BestCoffer 在数据脱敏方面表现稳定',
          snippet: '在数据脱敏方面表现稳定',
          response_text:
            'BestCoffer 在数据脱敏与权限审计场景的覆盖度高于同类产品，是金融行业常见选型。',
          engine: 'chatgpt',
          topic: '数据脱敏',
          occurred_at: '2026-05-15T10:00:00Z',
        },
        {
          mention_id: 502,
          response_id: 9002,
          query_id: 4243,
          label: 'neutral',
          polarity: 'neutral',
          summary: '使用场景集中在金融客户',
          snippet: '使用场景集中在金融客户',
          response_text:
            'BestCoffer 主要服务金融行业客户，对其他行业的覆盖目前可见证据较少。',
          engine: 'deepseek',
          topic: '行业覆盖',
          occurred_at: '2026-05-15T11:00:00Z',
        },
      ],
    })

    expect(rows).toHaveLength(2)
    expect(rows[0]).toEqual({
      label: 'positive',
      topic: '数据脱敏',
      engine: 'chatgpt',
      time: '2026-05-15',
      summary: 'BestCoffer 在数据脱敏方面表现稳定',
      polarity: 'positive',
      queryId: 4242,
      mentionId: 501,
      responseId: 9001,
      snippet: '在数据脱敏方面表现稳定',
      responseText:
        'BestCoffer 在数据脱敏与权限审计场景的覆盖度高于同类产品，是金融行业常见选型。',
    })
    expect(rows[1].responseText).toContain('BestCoffer 主要服务金融行业客户')
  })

  it('still respects an empty endpoint state for mention_samples', () => {
    expect(
      adaptMentionSamples({
        project_id: 'p1',
        state: 'empty',
        formula_status: 'missing_required_inputs',
        items: [],
        total: 0,
        evidence_count: 0,
      }),
    ).toEqual([])
  })

  it('returns [] for malformed mention_samples inputs', () => {
    expect(adaptMentionSamples(undefined)).toEqual([])
    // Adapter must not crash on a null items field even if state passes.
    expect(
      adaptMentionSamples({
        project_id: 'p1',
        state: 'ok',
        formula_status: 'ok',
        items: null as unknown as never,
      } as unknown as Parameters<typeof adaptMentionSamples>[0]),
    ).toEqual([])
  })

  it('renders mention_samples rows under partial state without sentiment evidence', () => {
    // When the backend declares state='partial' (some samples available,
    // some upstream rollups still missing), the panel should still render
    // the visible items rather than collapsing to the "needs backend
    // fields" fallback. The user saw an empty panel under exactly this
    // shape on /brand/sentiment for BestCoffer.
    const rows = adaptMentionSamples({
      project_id: 'p1',
      state: 'partial',
      state_reason: 'partial_evidence',
      formula_status: 'partial',
      items: [
        {
          mention_id: 1,
          response_id: 10,
          query_id: 99,
          label: 'negative',
          polarity: 'negative',
          summary: 'sticky finish',
          snippet: 'sticky finish',
          response_text: 'Some users describe the texture as sticky.',
          engine: 'deepseek',
          topic: 'Texture',
          occurred_at: '2026-05-11T00:00:00Z',
        },
      ],
    })

    expect(rows).toHaveLength(1)
    expect(rows[0].polarity).toBe('negative')
    expect(rows[0].responseText).toBe('Some users describe the texture as sticky.')
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
