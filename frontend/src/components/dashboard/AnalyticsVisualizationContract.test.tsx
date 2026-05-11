import { render, screen } from '@testing-library/react'
import AnalyticsVisualizationContract, { formatMetricPercent } from './AnalyticsVisualizationContract'

describe('AnalyticsVisualizationContract', () => {
  it('renders decimal mention rate and percent SoV without double scaling', () => {
    expect(formatMetricPercent(0.162, 'decimal')).toBe('16.2%')
    expect(formatMetricPercent(16.2, 'percent')).toBe('16.2%')
    expect(formatMetricPercent(38.4, 'percent')).toBe('38.4%')
  })

  it('shows distinct mention rate and SoV denominators for issue 482', () => {
    render(<AnalyticsVisualizationContract />)

    expect(screen.getByText('App analytics visualization contract')).toBeInTheDocument()
    expect(screen.getByText('70 brand-mentioned responses / 432 non-brand category responses')).toBeInTheDocument()
    expect(screen.getByText('70 Estee Lauder mentions / 182 competitive-set brand mentions')).toBeInTheDocument()
    expect(screen.getByText('kpi_cards[].value_scale')).toBeInTheDocument()
  })
})
