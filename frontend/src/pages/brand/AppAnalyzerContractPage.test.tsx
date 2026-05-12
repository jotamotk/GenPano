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
})
