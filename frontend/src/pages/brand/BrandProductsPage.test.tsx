import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { LocaleProvider } from '../../contexts/LocaleContext'
import BrandProductsPage from './BrandProductsPage'

const mockState = vi.hoisted(() => ({
  brandProductsData: null as any,
  productRelationsData: null as any,
}))

vi.mock('recharts', async () => {
  const React = await import('react')
  const Passthrough = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>
  const Empty = () => <div />
  return {
    ResponsiveContainer: Passthrough,
    LineChart: Passthrough,
    Line: Empty,
    BarChart: Passthrough,
    Bar: Empty,
    Cell: Empty,
    ScatterChart: Passthrough,
    Scatter: Empty,
    ZAxis: Empty,
    Label: Empty,
    ReferenceArea: Empty,
    ReferenceLine: Empty,
    XAxis: Empty,
    YAxis: Empty,
    CartesianGrid: Empty,
    Tooltip: Empty,
  }
})

vi.mock('../../contexts/ProjectContext', () => ({
  useProject: () => ({
    activeProject: {
      id: '11111111-2222-3333-4444-555555555555',
      primaryBrandId: 42,
      primaryBrandName: 'Test Brand',
      name: 'Test Project',
      competitorBrandIds: [],
      industryId: 1,
    },
  }),
}))

vi.mock('../../hooks/useProjects', () => ({
  useProjects: () => ({
    data: [{ id: '11111111-2222-3333-4444-555555555555', primaryBrandId: 42 }],
  }),
}))

vi.mock('../../hooks/useBrandOverview', () => ({
  isLiveProjectId: () => true,
}))

vi.mock('../../lib/liveProject', () => ({
  resolveLiveProjectId: () => '11111111-2222-3333-4444-555555555555',
  isLiveProjectId: () => true,
}))

vi.mock('../../hooks/useBrandAnalysisFilters', () => ({
  useBrandAnalysisFilters: () => ({ filters: {} }),
}))

vi.mock('../../hooks/useTopicAnalysis', () => ({
  useProjectSegments: () => ({ data: { items: [] } }),
}))

vi.mock('../../hooks/useCharts', () => ({
  useProductRelations: () => ({
    data: mockState.productRelationsData,
  }),
}))

vi.mock('../../hooks/useBrandMetrics', () => ({
  useBrandProducts: () => ({
    data: mockState.brandProductsData,
  }),
}))

function productPayload(metricFormulaEvidence: Record<string, unknown>) {
  return {
    project_id: '11111111-2222-3333-4444-555555555555',
    state: 'ok',
    formula_status: 'ok',
    metric_formula_evidence: metricFormulaEvidence,
    items: [
      {
        product_id: 1,
        product_name: 'Unsupported Product',
        brand_id: 42,
        category: 'Serum',
        mention_count: 12,
        mention_rate: 0.42,
        sov: 37,
        avg_sentiment: 0.8,
        ranking: 1,
        trend_30d: 0.1,
        sparkline: [1, 2, 3],
        avg_geo_score: 74,
      },
    ],
    total: 1,
  }
}

function renderProductsPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/brand/products?brandId=42']}>
        <LocaleProvider initialLocale="en-US">
          <BrandProductsPage />
        </LocaleProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('BrandProductsPage analyzer evidence guards', () => {
  it('does not render product rows without explicit product or topic_product evidence', () => {
    mockState.brandProductsData = productPayload({
      mention_rate: { formula_status: 'ok' },
      sov: { formula_status: 'ok' },
      sentiment: { formula_status: 'ok' },
    })
    mockState.productRelationsData = {
      project_id: '11111111-2222-3333-4444-555555555555',
      state: 'ok',
      formula_status: 'ok',
      metric_formula_evidence: {
        product: { formula_status: 'ok' },
      },
      items: [],
    }

    renderProductsPage()

    expect(screen.queryByText('Unsupported Product')).not.toBeInTheDocument()
    expect(screen.getByText(/No product data|鏆傛棤浜у搧鏁版嵁|閺嗗倹妫ゆ禍褍鎼ч弫鐗堝祦/)).toBeInTheDocument()
  })

  it('withholds per-product metric values without explicit per-metric evidence', () => {
    mockState.brandProductsData = productPayload({
      product: { formula_status: 'ok' },
    })
    mockState.productRelationsData = {
      project_id: '11111111-2222-3333-4444-555555555555',
      state: 'ok',
      formula_status: 'ok',
      metric_formula_evidence: {
        product: { formula_status: 'ok' },
      },
      items: [],
    }

    renderProductsPage()

    expect(screen.getAllByText('Unsupported Product').length).toBeGreaterThan(0)
    expect(screen.queryByText('42.0%')).not.toBeInTheDocument()
    expect(screen.getAllByText('--').length).toBeGreaterThan(0)
  })
})
