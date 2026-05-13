import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import AppAnalyzerContractPage from './AppAnalyzerContractPage'

describe('AppAnalyzerContractPage', () => {
  it('renders the chart contract matrix and analyzer reset callouts', () => {
    render(<AppAnalyzerContractPage />)

    expect(screen.getByRole('heading', { name: /Analyzer chart data contract/i })).toBeInTheDocument()
    expect(screen.getByText('Chart/KPI')).toBeInTheDocument()
    expect(screen.getByText('Required source facts')).toBeInTheDocument()
    expect(screen.getByText('Failure state')).toBeInTheDocument()
    expect(screen.getAllByText('ok').length).toBeGreaterThan(0)
    expect(screen.getAllByText('partial').length).toBeGreaterThan(0)
    expect(screen.getAllByText('empty').length).toBeGreaterThan(0)

    expect(screen.getByText(/SoV requires response-level competitive brand extraction/i)).toBeInTheDocument()
    expect(screen.getByText(/not target-only mentions or stale aggregate fallback/i)).toBeInTheDocument()
    expect(screen.getByText(/score, label, driver, and source quote/i)).toBeInTheDocument()

    expect(screen.getAllByText('/brand/overview').length).toBeGreaterThan(0)
    expect(screen.getByText('Competitor quadrant')).toBeInTheDocument()
    expect(screen.getByText('Product BCG quadrant')).toBeInTheDocument()
    expect(screen.getByText('Brand x Topic sentiment heatmap')).toBeInTheDocument()
  })

  it('renders analyzer trust states and payload examples for worker handoff', () => {
    render(<AppAnalyzerContractPage />)

    expect(screen.getByText(/Analyzer trust states/i)).toBeInTheDocument()
    expect(screen.getByText('missing_analyzer_rows')).toBeInTheDocument()
    expect(screen.getByText('insufficient_coverage')).toBeInTheDocument()
    expect(screen.getByText('missing_competitive_extraction')).toBeInTheDocument()
    expect(screen.getByText('target_only_sov')).toBeInTheDocument()
    expect(screen.getByText('unresolved_citation_attribution')).toBeInTheDocument()
    expect(screen.getByText('missing_sentiment_quote')).toBeInTheDocument()
    expect(screen.getByText('valid_zero')).toBeInTheDocument()

    expect(screen.getAllByText(/formula_status/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/metric_formula_evidence/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/missing_inputs/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/analyzer_coverage/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/eligible_response_count/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/analyzed_response_count/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/missing_response_count/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/analyzer_version/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/34 analyzed \/ 56 eligible \/ 22 missing/i)).toBeInTheDocument()
    expect(screen.getByText(/numerator.*30/i)).toBeInTheDocument()
    expect(screen.getByText(/denominator.*138/i)).toBeInTheDocument()
  })
})
