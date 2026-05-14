import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import DashboardPage from './DashboardPage'
import { LocaleProvider } from '../contexts/LocaleContext'

vi.mock('recharts', async () => {
  const React = await import('react')
  const Passthrough = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>
  const Empty = () => <div />
  return {
    ResponsiveContainer: Passthrough,
    LineChart: Passthrough,
    Line: Empty,
    PieChart: Passthrough,
    Pie: Passthrough,
    Cell: Empty,
    ScatterChart: Passthrough,
    Scatter: Empty,
    ZAxis: Empty,
    ReferenceLine: Empty,
    XAxis: Empty,
    YAxis: Empty,
    CartesianGrid: Empty,
    Tooltip: Empty,
    Legend: Empty,
  }
})

vi.mock('../contexts/ProjectContext', () => ({
  useProject: () => ({
    projects: [{ id: 'local-project', primaryBrandId: 12, primaryBrandName: 'Estee Lauder' }],
    activeProject: {
      id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      primaryBrandId: 12,
      primaryBrandName: 'Estee Lauder',
      name: 'Estee Lauder',
      competitorBrandIds: [],
      industryId: 7,
    },
  }),
}))

vi.mock('../hooks/useProjects', () => ({
  useProjects: () => ({
    data: [{ id: '95d43022-a5c8-5944-b6d6-34b29faa18b5', primaryBrandId: 12 }],
  }),
}))

vi.mock('../hooks/useTopicAnalysis', () => ({
  useProjectSegments: () => ({
    data: { items: [] },
  }),
}))

vi.mock('../lib/liveProject', () => ({
  isLiveProjectId: () => true,
  resolveLiveProjectId: () => '95d43022-a5c8-5944-b6d6-34b29faa18b5',
}))

vi.mock('../hooks/useBrandOverview', () => ({
  isLiveProjectId: () => true,
  useBrandOverview: () => ({
    data: {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      brand_id: 12,
      brand_name: 'Estee Lauder',
      industry_id: 7,
      period: { from: '2026-05-01', to: '2026-05-11' },
      state: 'partial',
      state_reason: 'rank_inputs_missing',
      request_id: 'req-partial-582',
      missing_sources: ['brand_mentions.position_rank'],
      kpi_cards: [
        {
          metric_key: 'mention_rate',
          label_zh: 'Mention',
          label_en: 'Mention',
          value: 82.9,
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
          delta_30d_pct: null,
          direction: null,
        },
        {
          metric_key: 'sov',
          label_zh: 'SoV',
          label_en: 'Share of Voice',
          value: 97.3,
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
          delta_30d_pct: null,
          direction: null,
        },
        {
          metric_key: 'rank',
          label_zh: 'Rank',
          label_en: 'Rank',
          value: 1,
          unit: 'rank',
          value_scale: 'ordinal',
          formula_status: 'rank_evidence_missing',
          delta_30d_pct: null,
          direction: null,
        },
      ],
      geo_score_30d: [],
      sov_30d: [],
      sentiment_30d: [],
      top_prompts: [],
      same_group_shared_domains: [],
    },
    isLoading: false,
    error: null,
  }),
}))

vi.mock('../hooks/useBrandMetrics', () => ({
  useBrandMetrics: () => ({
    data: {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      brand_id: 12,
      period: { from: '2026-05-01', to: '2026-05-11' },
      engines: null,
      state: 'partial',
      state_reason: 'rank_inputs_missing',
      series: [
        {
          metric: 'mention_rate',
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
          points: [{ date: '2026-05-11', value: 82.9 }],
        },
        {
          metric: 'sov',
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
          points: [{ date: '2026-05-11', value: 97.3 }],
        },
      ],
    },
    isLoading: false,
    error: null,
  }),
  useCompetitorMetrics: () => ({
    data: {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      primary_brand_id: 12,
      period: { from: '2026-05-01', to: '2026-05-11' },
      state: 'partial',
      state_reason: 'competitor_rows_missing',
      primary: null,
      competitors: [],
      metric_definitions: {
        avg_sov: {
          metric_key: 'avg_sov',
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'formula_pending_upstream',
        },
      },
    },
    isLoading: false,
    error: null,
  }),
  useCompetitorTrends: () => ({
    data: {
      project_id: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
      metric: 'geo_score',
      period: { from: '2026-05-01', to: '2026-05-11' },
      state: 'partial',
      series: [],
    },
    isLoading: false,
    error: null,
  }),
}))

vi.mock('../hooks/useDiagnostics', () => ({
  useDiagnostics: () => ({
    data: { items: [] },
    error: null,
  }),
}))

vi.mock('../hooks/useIndustries', () => ({
  useIndustries: () => ({
    data: [],
    isLoading: false,
    error: null,
  }),
  useIndustryAvgGeo: () => ({
    data: null,
    error: null,
  }),
}))

describe('DashboardPage partial analytics rendering', () => {
  it('shows the partial banner while rendering usable overview SoV KPI without pie rows', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/brand/overview?brandId=12']}>
          <LocaleProvider initialLocale="en-US">
            <DashboardPage />
          </LocaleProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(screen.getByText('partial')).toBeInTheDocument()
    expect(screen.getByText('Partial analytics')).toBeInTheDocument()
    expect(screen.getAllByText('rank_inputs_missing').length).toBeGreaterThan(0)
    expect(screen.getAllByText('82.9%').length).toBeGreaterThan(0)
    expect(screen.getAllByText('97.3%').length).toBeGreaterThan(0)
    expect(screen.getByText('暂无声量份额数据')).toBeInTheDocument()
    expect(screen.getAllByText(/#—|#-/).length).toBeGreaterThan(0)
  })
})
