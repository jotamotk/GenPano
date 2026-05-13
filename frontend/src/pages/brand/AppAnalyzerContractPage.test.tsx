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

  it('renders analyzer trust states in product language without raw contract field names', () => {
    render(<AppAnalyzerContractPage />)

    expect(screen.getByText(/Analyzer trust states/i)).toBeInTheDocument()
    expect(screen.getByText('Analysis coverage missing')).toBeInTheDocument()
    expect(screen.getByText('Coverage incomplete')).toBeInTheDocument()
    expect(screen.getByText('Competitor evidence incomplete')).toBeInTheDocument()
    expect(screen.getByText('Target-only SoV')).toBeInTheDocument()
    expect(screen.getByText('Citation attribution unresolved')).toBeInTheDocument()
    expect(screen.getByText('Sentiment quote missing')).toBeInTheDocument()
    expect(screen.getByText('Valid zero')).toBeInTheDocument()

    expect(screen.queryByText(/formula_status/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/metric_formula_evidence/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/missing_inputs/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/analyzer_coverage/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/eligible_response_count/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/analyzed_response_count/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/missing_response_count/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/analyzer_version/i)).not.toBeInTheDocument()
    expect(screen.getAllByText(/34 analyzed \/ 56 eligible \/ 22 missing/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/30 target mentions \/ 138 competitive mentions/i)).toBeInTheDocument()
  })
})
