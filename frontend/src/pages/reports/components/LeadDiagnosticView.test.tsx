import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'

const mockDiagnostics = vi.hoisted(() => [
  {
    id: 'diag-estee-1',
    type: 'brand',
    brandId: 'estee-lauder',
    severity: 'P1',
    category: 'visibility_decline',
    title: 'Estée Lauder visibility down',
  },
  {
    id: 'diag-lancome-1',
    type: 'brand',
    brandId: 'lancome',
    severity: 'P1',
    category: 'visibility_decline',
    title: 'Lancôme noise — must NOT appear',
  },
  {
    id: 'diag-industry-1',
    type: 'industry',
    brandId: 'cosmetics',
    severity: 'P2',
    category: 'industry_lag_top10',
    title: 'Industry-level signal',
  },
])

vi.mock('../../../data/mock', () => ({
  DIAGNOSTICS: mockDiagnostics,
}))

vi.mock('../../../components/ui', () => ({
  Badge: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  Card: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('./LeadLayerCard', () => ({
  LEAD_LAYER_META: {
    quickWins: { borderColor: '#000', bg: '#fff', color: '#000' },
    strategicBets: { borderColor: '#000', bg: '#fff', color: '#000' },
    brandingRisks: { borderColor: '#000', bg: '#fff', color: '#000' },
    consultingAccelerators: { borderColor: '#000', bg: '#fff', color: '#000' },
  },
  LeadLayerCard: ({
    items,
    layerKey,
  }: {
    items: { id: string; title: string }[]
    layerKey: string
  }) => (
    <div data-testid={`layer-${layerKey}`}>
      {items.map((d) => (
        <div key={d.id} data-testid={`row-${d.id}`}>
          {d.title}
        </div>
      ))}
    </div>
  ),
  classifyDiagnosticsForLead: (
    items: { id: string; title: string; severity: string }[],
  ) => ({
    // Stub classifier: dump everything into quickWins so the test can
    // observe what was passed in.
    quickWins: items,
    strategicBets: [],
    brandingRisks: [],
    consultingAccelerators: [],
  }),
}))

describe('LeadDiagnosticView filter (AC-4.7-25 / audit #1044 F4-4)', () => {
  it('filters by normalized brand id + includes industry-type, drops other brands', async () => {
    const { LeadDiagnosticView } = await import('./LeadDiagnosticView')
    render(
      <LeadDiagnosticView
        report={{ brand: { id: 'brand-estee-lauder' } } as never}
        brandName="Estée Lauder"
        t={(k: string) => k}
      />,
    )

    // Filter must include the matching brand's diagnostic and the
    // industry-level item.
    expect(screen.getByTestId('row-diag-estee-1')).toBeInTheDocument()
    expect(screen.getByTestId('row-diag-industry-1')).toBeInTheDocument()
    // Must exclude unrelated brand's diagnostic — regression for
    // the `|| true` filter no-op bug.
    expect(screen.queryByTestId('row-diag-lancome-1')).not.toBeInTheDocument()
  })

  it('still excludes unmatched brands when report uses non-prefixed brand id', async () => {
    const { LeadDiagnosticView } = await import('./LeadDiagnosticView')
    render(
      <LeadDiagnosticView
        report={{ brand: { id: 'estee-lauder' } } as never}
        brandName="Estée Lauder"
        t={(k: string) => k}
      />,
    )
    expect(screen.queryByTestId('row-diag-lancome-1')).not.toBeInTheDocument()
    expect(screen.getByTestId('row-diag-estee-1')).toBeInTheDocument()
  })
})
