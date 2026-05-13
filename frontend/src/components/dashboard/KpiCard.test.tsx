import { fireEvent, render, screen } from '@testing-library/react'
import KpiCard from './KpiCard'

describe('KpiCard', () => {
  it('renders metric help as an info tooltip beside the label', () => {
    const { container } = render(
      <KpiCard
        label="Mention rate"
        value="12.4%"
        delta={1.2}
        deltaLabel="vs 7d"
        helpText="Calculated from category-generic queries only."
      />,
    )

    expect(screen.getByText('Mention rate')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'info' })).toBeInTheDocument()
    expect(screen.getByRole('tooltip')).toHaveTextContent(
      'Calculated from category-generic queries only.',
    )
    expect(
      Array.from(container.querySelectorAll('p')).some((node) =>
        node.textContent?.includes('Calculated from category-generic queries'),
      ),
    ).toBe(false)
  })

  it('does not trigger the card click handler when the info icon is clicked', () => {
    const onClick = vi.fn()

    render(
      <KpiCard
        label="Mention rate"
        value="12.4%"
        onClick={onClick}
        helpText="Calculated from category-generic queries only."
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'info' }))

    expect(onClick).not.toHaveBeenCalled()
  })

  it('shows metric trust state and withholds a partial KPI value', () => {
    render(
      <KpiCard
        label="SoV"
        value="0.0%"
        trustState={{
          tone: 'partial',
          label: 'Needs review',
          summary: 'Coverage incomplete: metric is waiting for more analyzed answers.',
          details: ['34 of 56 analyzed', '22 missing', 'Analyzer v3'],
          reasonLabels: ['Analysis coverage missing', 'Competitor evidence incomplete'],
          canShowValue: false,
        }}
      />,
    )

    expect(screen.getByText('SoV')).toBeInTheDocument()
    expect(screen.getByText('Needs review')).toBeInTheDocument()
    expect(screen.getByText('Coverage incomplete: metric is waiting for more analyzed answers.')).toBeInTheDocument()
    expect(screen.getByText('34 of 56 analyzed')).toBeInTheDocument()
    expect(screen.getByText('Analysis coverage missing')).toBeInTheDocument()
    expect(screen.queryByText('0.0%')).not.toBeInTheDocument()
    expect(screen.getByText('—')).toBeInTheDocument()
  })
})
