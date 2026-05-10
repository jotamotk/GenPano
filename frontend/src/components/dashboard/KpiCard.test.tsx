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
})
