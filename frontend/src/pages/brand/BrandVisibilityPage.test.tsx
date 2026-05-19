import { render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { LocaleProvider } from '../../contexts/LocaleContext'
import BrandVisibilityPage from './BrandVisibilityPage'

const mockState = vi.hoisted(() => ({
  engineData: undefined as any,
  engineError: null as Error | null,
  engineIsLoading: false,
  competitorTrendData: undefined as any,
}))

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
  TrendChart: ({ lines = [] }: { lines?: Array<{ key: string; label: string }> }) => (
    <div data-testid="trend-chart">
      {lines.map((line) => (
        <span key={line.key}>{line.label}</span>
      ))}
    </div>
  ),
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
      primaryBrandName: 'bestCoffer',
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
  // /overview emits one aggregate ratio over the window:
  // mention = sum(target_responses) / sum(eligible_denominator). For
  // bestCoffer this lives around 48.0% and 43.2%.
  useBrandOverview: () => ({
    data: {
      project_id: '11111111-2222-3333-4444-555555555555',
      brand_id: 42,
      brand_name: 'bestCoffer',
      industry_id: 1,
      period: { from: '2026-05-08', to: '2026-05-15' },
      state: 'ok',
      formula_status: 'ok',
      kpi_cards: [
        {
          label_zh: '提及率',
          label_en: 'Mention Rate',
          value: 48.0,
          unit: '%',
          formula_status: 'ok',
        },
        {
          label_zh: '声量份额',
          label_en: 'Share of Voice',
          value: 43.2,
          unit: '%',
          formula_status: 'ok',
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

vi.mock('../../lib/liveProject', () => ({
  resolveLiveProjectId: () => '11111111-2222-3333-4444-555555555555',
  isLiveProjectId: () => true,
}))

vi.mock('../../hooks/useBrandAnalysisFilters', () => ({
  useBrandAnalysisFilters: () => ({ filters: {} }),
}))

vi.mock('../../hooks/useBrandMetrics', () => ({
  // /metrics returns per-day ratios that average to a much smaller number
  // (Simpson's paradox vs the overall ratio in /overview). The page must NOT
  // read its KPI value from this series — only the sparkline does.
  useBrandMetrics: () => ({
    data: {
      project_id: '11111111-2222-3333-4444-555555555555',
      brand_id: 42,
      period: { from: '2026-05-08', to: '2026-05-15' },
      state: 'ok',
      formula_status: 'ok',
      series: [
        {
          metric: 'mention_rate',
          unit: 'ratio',
          value_scale: 'decimal',
          formula_status: 'ok',
          points: [
            { date: '2026-05-08', value: 0.005 },
            { date: '2026-05-09', value: 0.01 },
            { date: '2026-05-10', value: 0.028 },
          ],
        },
        {
          metric: 'sov',
          unit: 'ratio',
          value_scale: 'decimal',
          formula_status: 'ok',
          points: [
            { date: '2026-05-08', value: 0.45 },
            { date: '2026-05-09', value: 0.48 },
            { date: '2026-05-10', value: 0.478 },
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
    data: mockState.competitorTrendData ?? { series: [] },
    isLoading: false,
    error: null,
  }),
}))

vi.mock('../../hooks/useCharts', () => ({
  useEngineMetrics: () => ({
    data: mockState.engineData,
    error: mockState.engineError,
    isLoading: mockState.engineIsLoading,
  }),
  usePositionDistribution: () => ({ data: undefined }),
  useTopicHeatmap: () => ({ data: undefined }),
}))

function renderVisibilityPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/brand/visibility']}>
        <LocaleProvider initialLocale="en-US">
          <BrandVisibilityPage />
        </LocaleProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('BrandVisibilityPage KPI cards (issue #988)', () => {
  beforeEach(() => {
    mockState.engineData = undefined
    mockState.engineError = null
    mockState.engineIsLoading = false
    mockState.competitorTrendData = undefined
  })

  it('reads KPI values from /overview so numbers match the Overview page, not from /metrics series points', () => {
    renderVisibilityPage()

    // /overview emits the same aggregate ratio Overview displays.
    // Visibility must render those values, NOT anything derived from /metrics
    // per-day points (which average to ~1.4% for mention here).
    expect(screen.getByText('48.0%')).toBeInTheDocument()
    expect(screen.getByText('43.2%')).toBeInTheDocument()

    // Sanity guards: should never see the /metrics-derived numbers from this
    // mock, neither the last point nor the unweighted average.
    expect(screen.queryByText('2.8%')).not.toBeInTheDocument()
    expect(screen.queryByText('1.4%')).not.toBeInTheDocument()
    expect(screen.queryByText('47.8%')).not.toBeInTheDocument()
  })

  it('labels the live PANO trend primary line from /competitors/trends, not the stale mock fallback brand', () => {
    mockState.competitorTrendData = {
      project_id: '7380c0e0-8798-4a5f-998f-42010a7d9caa',
      metric: 'geo_score',
      period: { from: '2026-05-17', to: '2026-05-17' },
      state: 'ok',
      metric_definition: {
        metric_key: 'geo_score',
        unit: 'score',
        value_scale: 'score_0_100',
        formula_status: 'ok',
      },
      series: [
        {
          brand_id: 24,
          brand_key: 'bestcoffer',
          brand_name: 'bestCoffer',
          is_primary: true,
          points: [{ date: '2026-05-17', value: 80 }],
        },
        {
          brand_id: 25,
          brand_key: 'ibm_security',
          brand_name: 'IBM Security',
          is_primary: false,
          points: [{ date: '2026-05-17', value: 68 }],
        },
      ],
    }

    renderVisibilityPage()

    const chart = screen.getByTestId('trend-chart')
    expect(within(chart).getByText('bestCoffer')).toBeInTheDocument()
    expect(within(chart).queryByText(/Estee|Est\u00e9e|\u96c5\u8bd7\u5170\u9edb/i)).not.toBeInTheDocument()
  })

  it('falls back to the empty-data placeholder when by-engine items are empty', () => {
    mockState.engineData = {
      project_id: '11111111-2222-3333-4444-555555555555',
      period: { from: '2026-05-08', to: '2026-05-15' },
      state: 'empty',
      formula_status: 'missing_required_inputs',
      state_detail: 'No engine-level Mention Rate or SoV rows are available yet.',
      items: [],
    }

    renderVisibilityPage()

    const block = screen.getByTestId('engine-visibility-breakdown')
    expect(within(block).getByText('Engine visibility data unavailable')).toBeInTheDocument()
  })

  it('falls back to the empty-data placeholder when the by-engine hook errors', () => {
    mockState.engineError = new Error('metrics by-engine request failed')

    renderVisibilityPage()

    const block = screen.getByTestId('engine-visibility-breakdown')
    expect(within(block).getByText('Engine visibility data unavailable')).toBeInTheDocument()
  })
})
