import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { LocaleProvider } from '../../contexts/LocaleContext'
import BrandSentimentPage from './BrandSentimentPage'

const mockSamples = Array.from({ length: 8 }, (_, idx) => ({
  mention_id: idx + 1,
  response_id: 1000 + idx,
  label: idx % 2 === 0 ? 'Positive' : 'Negative',
  polarity: idx % 2 === 0 ? 'positive' : 'negative',
  summary: `Response summary ${idx + 1}`,
  snippet: `Full response text ${idx + 1}`,
  engine: 'ChatGPT',
  topic: `Topic ${idx + 1}`,
  occurred_at: '2026-05-18T00:00:00Z',
}))

vi.mock('recharts', async () => {
  const React = await import('react')
  const Passthrough = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>
  const Empty = () => <div />
  return {
    ResponsiveContainer: Passthrough,
    BarChart: Passthrough,
    Bar: Empty,
    XAxis: Empty,
    YAxis: Empty,
    CartesianGrid: Empty,
    Tooltip: Empty,
  }
})

vi.mock('../../components/charts', () => ({
  TrendChart: () => <div data-testid="trend-chart" />,
  DonutChart: () => <div data-testid="donut-chart" />,
}))

vi.mock('../../components/charts/BrandTopicHeatmap', () => ({
  default: () => <div data-testid="topic-heatmap" />,
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

vi.mock('../../hooks/useTopicAnalysis', () => ({
  useProjectSegments: () => ({
    data: { items: [] },
  }),
}))

vi.mock('../../hooks/useBrandAnalysisFilters', () => ({
  useBrandAnalysisFilters: () => ({ filters: {} }),
}))

vi.mock('../../hooks/useBrandMetrics', () => ({
  useBrandSentiment: () => ({
    data: {
      state: 'ok',
      metric_formula_evidence: { sentiment: { formula_status: 'ok' } },
      distribution: {
        positive_pct: 60,
        neutral_pct: 20,
        negative_pct: 20,
        avg_sentiment_score: 0.7,
      },
      top_keywords: [],
    },
    isLoading: false,
    error: null,
  }),
}))

vi.mock('../../hooks/useCharts', () => ({
  useSentimentByEngine: () => ({
    data: {
      state: 'ok',
      metric_formula_evidence: { sentiment: { formula_status: 'ok' } },
      items: [],
    },
  }),
  useSentimentTrendByEngine: () => ({
    data: {
      state: 'ok',
      metric_formula_evidence: { sentiment: { formula_status: 'ok' } },
      engines: [],
      items: [],
    },
  }),
  useTopicHeatmap: () => ({
    data: {
      state: 'ok',
      metric_formula_evidence: { sentiment: { formula_status: 'ok' } },
      metric: 'sentiment',
      rows: [],
    },
  }),
  useTopicAttribution: () => ({
    data: {
      state: 'ok',
      metric_formula_evidence: { sentiment: { formula_status: 'ok' } },
      items: [],
    },
  }),
  useMentionSamples: () => ({
    data: {
      project_id: '11111111-2222-3333-4444-555555555555',
      state: 'ok',
      metric_formula_evidence: { sentiment: { formula_status: 'ok' } },
      items: mockSamples,
    },
    isLoading: false,
    error: null,
  }),
}))

function renderSentimentPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/brand/sentiment?brandId=42']}>
        <LocaleProvider initialLocale="en-US">
          <BrandSentimentPage />
        </LocaleProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('BrandSentimentPage response evidence contract', () => {
  it('renders every fetched response and exposes a full response interaction', () => {
    renderSentimentPage()

    expect(screen.getByText('Response summary 1')).toBeInTheDocument()
    expect(screen.getByText('Response summary 8')).toBeInTheDocument()
    expect(screen.getByText(/Showing 8 of 8 fetched responses/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Inspect full response for Response summary 1/ }))

    expect(screen.getByText('Full response inspection')).toBeInTheDocument()
    expect(screen.getByText(/Full response text is not available from the current API payload/)).toBeInTheDocument()
    expect(screen.getByText(/response_id: 1000/)).toBeInTheDocument()
  })
})
