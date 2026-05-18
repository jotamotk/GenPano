import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { LocaleProvider } from '../../contexts/LocaleContext'
import BrandCompetitorsPage from './BrandCompetitorsPage'

vi.mock('recharts', async () => {
  const React = await import('react')
  const Passthrough = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>
  const Empty = () => <div />
  return {
    ResponsiveContainer: Passthrough,
    RadarChart: Passthrough,
    PolarGrid: Empty,
    PolarAngleAxis: Empty,
    PolarRadiusAxis: Empty,
    Radar: Empty,
    Legend: Empty,
  }
})

vi.mock('../../components/filters/BrandAnalysisFilterBar', () => ({
  default: () => <div data-testid="filter-bar" />,
}))

vi.mock('../../components/charts/BrandTopicHeatmap', () => ({
  default: () => <div data-testid="topic-heatmap" />,
}))

vi.mock('../../contexts/ProjectContext', () => ({
  useProject: () => ({
    activeProject: {
      id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      primaryBrandId: 12,
      primaryBrandName: 'Estee Lauder',
      name: 'Estee Lauder',
      competitorBrandIds: [2],
      industryId: 7,
    },
  }),
}))

vi.mock('../../hooks/useBrandAnalysisFilters', () => ({
  useBrandAnalysisFilters: () => ({ filters: {} }),
}))

vi.mock('../../hooks/useProjects', () => ({
  useProjects: () => ({
    data: [{ id: '95d43022-a5c8-5944-b6d6-34b29faa18b5', primaryBrandId: 12 }],
  }),
}))

vi.mock('../../lib/liveProject', () => ({
  resolveLiveProjectId: () => '95d43022-a5c8-5944-b6d6-34b29faa18b5',
}))

vi.mock('../../hooks/useBrandOverview', () => ({
  isLiveProjectId: () => true,
}))

vi.mock('../../hooks/useBrandMetrics', () => ({
  useCompetitorMetrics: () => ({
    data: {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      primary_brand_id: 12,
      period: { from: '2026-05-11', to: '2026-05-18' },
      state: 'partial',
      state_reason: 'missing_formula_inputs',
      formula_status: 'missing_required_inputs',
      missing_inputs: ['eligible_response_denominator'],
      primary: null,
      competitors: [],
      project_scope: {
        exists: true,
        project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
        primary_brand_id: 12,
        requested_brand_id: 12,
        competitor_brand_ids: [2],
      },
      evidence_counts: {
        competitor_brand_count: 1,
        eligible_response_count: 0,
        competitive_mention_count: 468,
      },
    },
  }),
  useCompetitorTrends: () => ({
    data: { series: [], state: 'partial' },
  }),
}))

vi.mock('../../hooks/useCharts', () => ({
  useAuthorityRadar: () => ({ data: null }),
  useGroupSharedDomains: () => ({ data: null }),
  useTopicHeatmap: () => ({ data: null }),
}))

describe('BrandCompetitorsPage live competitor metric states', () => {
  it('renders endpoint partial evidence instead of a generic no-competitor state', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/brand/competitors?brandId=12']}>
          <LocaleProvider initialLocale="en-US">
            <BrandCompetitorsPage />
          </LocaleProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(screen.getByText('Competitor comparison is partial')).toBeInTheDocument()
    expect(screen.getByText(/missing formula inputs/i)).toBeInTheDocument()
    expect(screen.getByText(/eligible response denominator/i)).toBeInTheDocument()
    expect(screen.getByText(/1 configured competitor/i)).toBeInTheDocument()
  })
})
