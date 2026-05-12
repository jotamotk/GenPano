import { describe, expect, it } from 'vitest'

import {
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
})
