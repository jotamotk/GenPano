import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { LocaleProvider } from '../../contexts/LocaleContext'
import BrandVisibilityPage from './BrandVisibilityPage'

vi.mock('recharts', async () => {
  const React = await import('react')
  const Passthrough = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>
  const Empty = () => <div />
  return {
    ResponsiveContainer: Passthrough,
    BarChart: Passthrough,
    Bar: Empty,
    CartesianGrid: Empty,
    XAxis: Empty,
    YAxis: Empty,
    Tooltip: Empty,
    Legend: Empty,
  }
})

vi.mock('../../components/charts', () => ({
  TrendChart: () => <div data-testid="trend-chart" />,
  DonutChart: () => <div data-testid="donut-chart" />,
  HorizontalBar: () => <div data-testid="horizontal-bar" />,
  MiniSparkline: () => <div data-testid="mini-sparkline" />,
}))

vi.mock('../../components/charts/BrandTopicHeatmap', () => ({
  default: () => <div data-testid="brand-topic-heatmap" />,
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
  useBrandMetrics: () => ({
    data: {
      project_id: '11111111-2222-3333-4444-555555555555',
      brand_id: 42,
      period: { from: '2026-05-01', to: '2026-05-03' },
      state: 'ok',
      formula_status: 'ok',
      series: [
        {
          metric: 'mention_rate',
          unit: 'ratio',
          value_scale: 'decimal',
          formula_status: 'ok',
          // Window in % after scaling: 10%, 30%, 50%. Average = 30%; last = 50%.
          // /v1/projects/:id/overview KPI card emits the 30-day average (30%);
          // BrandVisibilityPage must render the same window average so the
          // numbers match across surfaces.
          points: [
            { date: '2026-05-01', value: 0.1 },
            { date: '2026-05-02', value: 0.3 },
            { date: '2026-05-03', value: 0.5 },
          ],
        },
        {
          metric: 'sov',
          unit: 'ratio',
          value_scale: 'decimal',
          formula_status: 'ok',
          // Window in % after scaling: 20%, 40%, 60%. Average = 40%; last = 60%.
          points: [
            { date: '2026-05-01', value: 0.2 },
            { date: '2026-05-02', value: 0.4 },
            { date: '2026-05-03', value: 0.6 },
          ],
        },
      ],
    },
    isLoading: false,
    error: null,
  }),
  useCompetitorMetrics: () => ({
    data: { competitors: [], primary: null, metric_definitions: {} },
    isLoading: false,
    error: null,
  }),
  useCompetitorTrends: () => ({
    data: { series: [] },
    isLoading: false,
    error: null,
  }),
}))

vi.mock('../../hooks/useCharts', () => ({
  useEngineMetrics: () => ({ data: undefined }),
  usePositionDistribution: () => ({ data: undefined }),
  useTopicHeatmap: () => ({ data: undefined }),
}))

function renderVisibilityPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/brand/visibility?brandId=42']}>
        <LocaleProvider initialLocale="en-US">
          <BrandVisibilityPage />
        </LocaleProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('BrandVisibilityPage KPI cards (issue #988)', () => {
  it('renders the window average — not the last sparkline point — so values match the Overview page', () => {
    renderVisibilityPage()

    // Mention rate series in % is [10, 30, 50]; window average = 30.0%.
    // If the page regressed to the last-point reading we would see 50.0%.
    expect(screen.getByText('30.0%')).toBeInTheDocument()
    expect(screen.queryByText('50.0%')).not.toBeInTheDocument()

    // SoV series in % is [20, 40, 60]; window average = 40.0%.
    expect(screen.getByText('40.0%')).toBeInTheDocument()
    expect(screen.queryByText('60.0%')).not.toBeInTheDocument()
  })
})
