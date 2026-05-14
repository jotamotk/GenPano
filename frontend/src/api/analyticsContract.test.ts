import { describe, expect, it } from 'vitest'

import {
  buildMetricTrustState,
  canUseContractMetricValue,
  canUseMetricEvidence,
  contractEvidenceReasons,
} from './analyticsContract'

describe('analytics formula-status guards', () => {
  it('renders a metric-level ok value under an endpoint-level partial state', () => {
    expect(
      canUseMetricEvidence(
        {
          state: 'partial',
          formula_status: 'partial',
          metric_formula_evidence: {
            mention_rate: { formula_status: 'ok' },
          },
        },
        ['mention_rate'],
      ),
    ).toBe(true)
  })

  it('withholds a metric-level partial value even when the row has a numeric value', () => {
    expect(
      canUseMetricEvidence(
        {
          state: 'partial',
          formula_status: 'partial',
          metric_formula_evidence: {
            sov: {
              formula_status: 'missing_required_inputs',
              reason_codes: ['target_only_sov'],
            },
          },
        },
        ['sov'],
      ),
    ).toBe(false)
  })

  it('uses metric evidence reasons for honest partial and empty states', () => {
    expect(
      contractEvidenceReasons(
        {
          state: 'partial',
          missing_inputs: ['response_analyses.raw_analysis_json.analyzer_fact_packages'],
          metric_formula_evidence: {
            citation: {
              formula_status: 'partial',
              reason_codes: ['unresolved_citation_attribution'],
            },
          },
        },
        ['citation'],
      ),
    ).toEqual([
      'unresolved_citation_attribution',
      'response_analyses.raw_analysis_json.analyzer_fact_packages',
    ])
  })

  it('does not treat missing metric fields as ok for a partial endpoint', () => {
    expect(canUseContractMetricValue('partial', undefined)).toBe(false)
  })

  it('does not treat endpoint ok as metric ok when metric evidence is missing', () => {
    expect(
      canUseMetricEvidence(
        {
          state: 'ok',
          formula_status: 'ok',
          metric_formula_evidence: {
            coverage: { formula_status: 'ok' },
          },
        },
        ['sov'],
      ),
    ).toBe(false)
  })

  it('requires an explicit metric object before using a live contract value', () => {
    expect(canUseContractMetricValue('ok', undefined)).toBe(false)
    expect(canUseContractMetricValue('ok', { state: 'ok' })).toBe(true)
    expect(canUseContractMetricValue('ok', { formula_status: 'ok' })).toBe(true)
  })

  it('surfaces a metric value when formula_status is partial (#948)', () => {
    // Backend `_apply_kpi_contract` / `_apply_metric_series_contract` emit
    // `formula_status: partial` when the value was computed from real
    // evidence but peripheral analyzer rollup pointers are missing.
    // The frontend must surface the trustworthy value instead of '—'.
    expect(canUseContractMetricValue('partial', { formula_status: 'partial' })).toBe(true)
    expect(canUseContractMetricValue('ok', { formula_status: 'partial' })).toBe(true)
    expect(
      canUseMetricEvidence(
        {
          state: 'partial',
          formula_status: 'partial',
          metric_formula_evidence: {
            mention_rate: { formula_status: 'partial' },
          },
        },
        ['mention_rate'],
      ),
    ).toBe(true)
  })

  it('classifies analyzer coverage and reason codes without turning partial evidence into zero', () => {
    const state = buildMetricTrustState({
      metricKey: 'sov',
      formula_status: 'partial',
      numerator: 30,
      denominator: 138,
      analyzer_coverage: {
        eligible_response_count: 56,
        analyzed_response_count: 34,
        missing_response_count: 22,
        analyzer_version: 'v3',
      },
      reason_codes: [
        'missing_analyzer_rows',
        'insufficient_coverage',
        'missing_competitive_extraction',
        'target_only_sov',
      ],
    })

    expect(state.tone).toBe('partial')
    expect(state.canShowValue).toBe(false)
    expect(state.label).toBe('Needs review')
    expect(state.summary).toContain('Coverage incomplete')
    expect(state.details).toContain('34 of 56 analyzed')
    expect(state.details).toContain('22 missing')
    expect(state.details).toContain('Analyzer v3')
    expect(state.details).toContain('30 / 138 evidence')
    expect(state.reasonLabels).toEqual(
      expect.arrayContaining([
        'Analysis coverage missing',
        'Coverage incomplete',
        'Competitor evidence incomplete',
        'Target-only SoV',
      ]),
    )
  })

  it('allows a real zero only when formula proof says the metric is ok', () => {
    const state = buildMetricTrustState({
      metricKey: 'visibility',
      value: 0,
      formula_status: 'ok',
      numerator: 0,
      denominator: 56,
      analyzer_coverage: {
        eligible_response_count: 56,
        analyzed_response_count: 56,
        missing_response_count: 0,
        analyzer_version: 'v3',
      },
      reason_codes: ['valid_zero'],
    })

    expect(state.tone).toBe('ok')
    expect(state.canShowValue).toBe(true)
    expect(state.label).toBe('Valid zero')
    expect(state.summary).toBe('Zero is supported by complete evidence.')
    expect(state.reasonLabels).toContain('Valid zero')
  })

  it('withholds an ok zero when numerator or denominator proof is missing', () => {
    const state = buildMetricTrustState({
      metricKey: 'visibility',
      value: 0,
      formula_status: 'ok',
      numerator: 0,
      reason_codes: ['valid_zero'],
    })

    expect(state.tone).toBe('partial')
    expect(state.canShowValue).toBe(false)
    expect(state.label).toBe('Needs review')
    expect(state.summary).toBe('Metric evidence is partial.')
    expect(state.reasonLabels).toContain('Valid zero')
    expect(state.reasonLabels).toContain('Valid zero proof missing')
  })

  it('withholds zero values when the metric lacks valid-zero proof', () => {
    const state = buildMetricTrustState({
      metricKey: 'citation',
      value: 0,
      formula_status: 'ok',
      analyzer_coverage: {
        eligible_response_count: 56,
        analyzed_response_count: 56,
        missing_response_count: 0,
        analyzer_version: 'v3',
      },
    })

    expect(state.canShowValue).toBe(false)
    expect(state.tone).toBe('partial')
    expect(state.reasonLabels).toContain('Valid zero proof missing')
  })
})
