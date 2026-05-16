import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LocaleProvider } from '../../contexts/LocaleContext'
import BrandCitationsPage from './BrandCitationsPage'

const mockState = vi.hoisted(() => ({
  citationsData: null as any,
  citationsCalls: [] as any[],
  topPagesData: null as any,
  topPagesCalls: [] as any[],
}))

vi.mock('../../components/charts', () => ({
  TrendChart: () => <div data-testid="trend-chart" />,
  DonutChart: () => <div data-testid="donut-chart" />,
}))

vi.mock('../../components/citation/ContentGapPanel', () => ({
  default: () => <div data-testid="content-gap-panel" />,
}))

vi.mock('../../components/citation/PrTargetsPanel', () => ({
  default: () => <div data-testid="pr-targets-panel" />,
}))

vi.mock('../../components/filters/BrandAnalysisFilterBar', () => ({
  default: () => <div data-testid="brand-analysis-filter-bar" />,
}))

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

vi.mock('../../hooks/useBrandMetrics', () => ({
  useBrandCitations: (...args: any[]) => {
    mockState.citationsCalls.push(args)
    return { data: mockState.citationsData }
  },
}))

vi.mock('../../hooks/useCharts', () => ({
  useAuthorityTrend: () => ({ data: undefined }),
  useCitationComposition: () => ({ data: undefined }),
  useContentGap: () => ({ data: undefined }),
  usePrTargets: () => ({ data: undefined }),
  useSimulatorBaseline: () => ({ data: undefined }),
  useTopCitedPages: (...args: any[]) => {
    mockState.topPagesCalls.push(args)
    return { data: mockState.topPagesData }
  },
}))

function renderCitationsPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/brand/citations?brandId=42']}>
        <LocaleProvider initialLocale="en-US">
          <BrandCitationsPage />
        </LocaleProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('BrandCitationsPage analyzer evidence guards', () => {
  beforeEach(() => {
    mockState.citationsData = null
    mockState.citationsCalls = []
    mockState.topPagesData = null
    mockState.topPagesCalls = []
  })

  it('passes the URL brandId to citation requests as brand_id', () => {
    renderCitationsPage()

    expect(mockState.citationsCalls[0]?.[2]).toMatchObject({ brand_id: 42 })
  })

  it('renders top cited pages from the authoritative endpoint, not from raw citation items', () => {
    // Raw `/citations` items endpoint returns the most-recent N citations,
    // which is NOT the top-by-count list. The page must source Top
    // 引用页面 from `/citations/top-pages` (Issue #1019), never reconstruct
    // from `citationsQ.data.items`.
    mockState.citationsData = {
      project_id: '11111111-2222-3333-4444-555555555555',
      brand_id: 42,
      period: { from: '2026-05-01', to: '2026-05-12' },
      state: 'ok',
      formula_status: 'ok',
      metric_formula_evidence: {
        citation: { formula_status: 'ok' },
      },
      items: [
        {
          citation_id: 1,
          response_id: 101,
          url: 'https://raw.example/page',
          domain: 'raw.example',
          title: 'Raw Reconstructed Page',
          source_type: 'web',
          occurred_at: '2026-05-12T00:00:00Z',
          tier: 2,
        },
      ],
      next_cursor: null,
      total: 1,
      by_domain_top: [],
    }
    mockState.topPagesData = {
      project_id: '11111111-2222-3333-4444-555555555555',
      brand_id: 42,
      period: { from: '2026-05-01', to: '2026-05-12' },
      state: 'ok',
      formula_status: 'ok',
      metric_formula_evidence: {
        citation: { formula_status: 'ok' },
      },
      items: [
        {
          url: 'https://authoritative.example/top-page',
          title: 'Authoritative Top Page',
          domain: 'authoritative.example',
          tier: null,
          count: 12,
          first_seen_at: '2026-05-01T00:00:00Z',
          last_seen_at: '2026-05-12T00:00:00Z',
        },
      ],
      total: 1,
    }

    renderCitationsPage()

    // Hook must have been invoked with the live project id (positional arg 0).
    expect(mockState.topPagesCalls.length).toBeGreaterThan(0)
    expect(mockState.topPagesCalls[0]?.[0]).toBe('11111111-2222-3333-4444-555555555555')

    // The authoritative endpoint's row renders.
    expect(screen.getByText('Authoritative Top Page')).toBeInTheDocument()
    expect(screen.getByText('https://authoritative.example/top-page')).toBeInTheDocument()

    // The raw `/citations.items` entry MUST NOT leak into the Top Pages block
    // (the contract this test originally locked).
    expect(screen.queryByText('Raw Reconstructed Page')).not.toBeInTheDocument()
    expect(screen.queryByText('https://raw.example/page')).not.toBeInTheDocument()
  })
})
