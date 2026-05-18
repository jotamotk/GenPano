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
    data: { series: [] },
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

  it('makes missing by-engine Mention Rate and SoV explicit while keeping citation share secondary', () => {
    mockState.engineData = {
      project_id: '11111111-2222-3333-4444-555555555555',
      period: { from: '2026-05-08', to: '2026-05-15' },
      state: 'partial',
      formula_status: 'partial',
      state_reason: 'visibility_metrics_partial',
      state_detail: 'Mention Rate and SoV are waiting for analyzer evidence.',
      metric_formula_evidence: {
        mention_rate: {
          formula_status: 'missing_required_inputs',
          reason_codes: ['missing_analyzer_rows'],
          missing_inputs: ['brand_mentions'],
        },
        sov: {
          formula_status: 'missing_required_inputs',
          reason_codes: ['missing_competitive_extraction', 'target_only_sov'],
        },
        citation: {
          formula_status: 'ok',
          numerator: 31,
          denominator: 50,
        },
      },
      items: [
        {
          engine: 'ChatGPT',
          mention_rate: null,
          sov: null,
          citation_rate: 0.62,
          sentiment: null,
        },
      ],
    }

    renderVisibilityPage()

    const block = screen.getByTestId('engine-visibility-breakdown')
    expect(within(block).getByText('ChatGPT')).toBeInTheDocument()
    expect(within(block).getByText('Mention Rate')).toBeInTheDocument()
    expect(within(block).getByText('SoV')).toBeInTheDocument()
    expect(within(block).getAllByText('Unavailable')).toHaveLength(2)
    expect(within(block).getByText(/Mention Rate and SoV are waiting for analyzer evidence/i)).toBeInTheDocument()
    expect(within(block).getByText(/Citation share is secondary context/i)).toBeInTheDocument()
    expect(within(block).getByText('62.0%')).toBeInTheDocument()
  })

  it('renders an explicit empty by-engine visibility state', () => {
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
    expect(within(block).getByText('No by-engine visibility evidence')).toBeInTheDocument()
    expect(
      within(block).getByText('No engine-level Mention Rate or SoV rows are available yet.'),
    ).toBeInTheDocument()
    expect(within(block).getByText('Engine visibility data unavailable')).toBeInTheDocument()
  })

  it('renders an explicit by-engine visibility error state from the hook', () => {
    mockState.engineError = new Error('metrics by-engine request failed')

    renderVisibilityPage()

    const block = screen.getByTestId('engine-visibility-breakdown')
    expect(within(block).getByText('By-engine visibility error')).toBeInTheDocument()
    expect(within(block).getByText('Error: metrics by-engine request failed')).toBeInTheDocument()
    expect(within(block).getByText('Engine visibility data unavailable')).toBeInTheDocument()
  })

  it('renders healthy by-engine Mention Rate and SoV as primary values while citation remains secondary', () => {
    mockState.engineData = {
      project_id: '11111111-2222-3333-4444-555555555555',
      period: { from: '2026-05-08', to: '2026-05-15' },
      state: 'ok',
      formula_status: 'ok',
      metric_formula_evidence: {
        mention_rate: { formula_status: 'ok', numerator: 37, denominator: 100 },
        sov: { formula_status: 'ok', numerator: 24, denominator: 100 },
        citation: { formula_status: 'ok', numerator: 11, denominator: 100 },
      },
      items: [
        {
          engine: 'ChatGPT',
          mention_rate: 0.37,
          sov: 0.24,
          citation_rate: 0.11,
          sentiment: null,
        },
      ],
    }

    renderVisibilityPage()

    const block = screen.getByTestId('engine-visibility-breakdown')
    expect(within(block).getByText('ChatGPT')).toBeInTheDocument()
    expect(within(block).getByText('37.0%')).toBeInTheDocument()
    expect(within(block).getByText('24.0%')).toBeInTheDocument()
    expect(within(block).getByText('11.0%')).toBeInTheDocument()
    expect(within(block).getByText(/Citation share is secondary context/i)).toBeInTheDocument()
    expect(within(block).queryByText('Unavailable')).not.toBeInTheDocument()
    expect(within(block).queryByText('Partial by-engine visibility evidence')).not.toBeInTheDocument()
    expect(within(block).queryByText('No by-engine visibility evidence')).not.toBeInTheDocument()
    expect(within(block).queryByText('By-engine visibility error')).not.toBeInTheDocument()
  })

  it('renders target-only SoV as unavailable while keeping mention and citation values fact-backed', () => {
    mockState.engineData = {
      project_id: '11111111-2222-3333-4444-555555555555',
      period: { from: '2026-05-08', to: '2026-05-15' },
      state: 'partial',
      formula_status: 'partial',
      state_reason: 'partial_analyzer_data',
      missing_inputs: ['target_only_sov'],
      source_provenance: ['admin_facts', 'brand_mentions', 'citation_sources'],
      evidence_counts: { admin_fact_response_count: 2 },
      metric_formula_evidence: {
        coverage: { formula_status: 'ok' },
        sov: {
          formula_status: 'missing_required_inputs',
          numerator_count: 2,
          denominator_count: 2,
        },
        citation: { formula_status: 'ok' },
      },
      items: [
        {
          engine: 'chatgpt',
          mention_rate: 1.0,
          sov: null,
          citation_rate: 1.0,
          sentiment: 0.7,
        },
      ],
    }

    renderVisibilityPage()

    const block = screen.getByTestId('engine-visibility-breakdown')
    expect(within(block).getByText('chatgpt')).toBeInTheDocument()
    expect(within(block).getByText('Visibility metrics incomplete')).toBeInTheDocument()
    expect(within(block).getAllByText('100.0%')).toHaveLength(2)
    expect(within(block).getByText('Unavailable')).toBeInTheDocument()
    expect(
      within(block).getByText('SoV has target evidence but no competitive denominator yet.'),
    ).toBeInTheDocument()
    expect(within(block).getByText('2 / 2 evidence')).toBeInTheDocument()
  })
})
