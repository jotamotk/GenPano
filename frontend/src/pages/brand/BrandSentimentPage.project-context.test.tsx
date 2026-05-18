import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { LocaleProvider } from '../../contexts/LocaleContext'
import BrandSentimentPage from './BrandSentimentPage'

const bestCofferProjectId = '11111111-1111-4111-8111-111111111111'
const esteeProjectId = '22222222-2222-4222-8222-222222222222'

const mocks = vi.hoisted(() => ({
  useMentionSamples: vi.fn(() => ({
    data: {
      project_id: '22222222-2222-4222-8222-222222222222',
      state: 'ok',
      metric_formula_evidence: { sentiment: { formula_status: 'ok' } },
      items: [],
      total: 0,
      limit: 100,
      offset: 0,
      has_more: false,
      evidence_count: 20,
      selected_filters: { brand_id: 12, polarity: null },
    },
    isLoading: false,
    error: null,
  })),
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

// ProjectContext is now URL-aware (Epic #1175): when the route carries
// `?brandId=12`, the context overrides activeProject to the Estée project
// (the one that owns brand 12) regardless of which project the user
// last clicked. The page now reads activeProject directly and resolves
// the live project from it; no page-level brand→project resolution.
vi.mock('../../contexts/ProjectContext', () => ({
  useProject: () => ({
    activeProject: {
      id: esteeProjectId,
      name: 'Estée Lauder App Analytics',
      primaryBrandId: 12,
      primaryBrandName: '雅诗兰黛',
      competitorBrandIds: [],
      industryId: 7,
    },
  }),
}))

vi.mock('../../hooks/useProjects', () => ({
  useProjects: () => ({
    data: [
      {
        id: bestCofferProjectId,
        name: 'BestCoffer App Analytics',
        primary_brand_id: 24,
        industry_id: 3,
        competitors: [],
      },
      {
        id: esteeProjectId,
        name: 'Estée Lauder App Analytics',
        primary_brand_id: 12,
        industry_id: 7,
        competitors: [],
      },
    ],
  }),
}))

vi.mock('../../hooks/useBrandOverview', () => ({
  isLiveProjectId: (id: string | null | undefined) =>
    !!id && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id),
}))

vi.mock('../../hooks/useTopicAnalysis', () => ({
  useProjectSegments: () => ({ data: { items: [] } }),
}))

vi.mock('../../hooks/useBrandAnalysisFilters', () => ({
  useBrandAnalysisFilters: () => ({ filters: { engines: ['ChatGPT'] } }),
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
  useMentionSamples: mocks.useMentionSamples,
}))

function renderSentimentPage(initialEntry: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <LocaleProvider initialLocale="en-US">
          <BrandSentimentPage />
        </LocaleProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('BrandSentimentPage project context resolution', () => {
  it('calls useMentionSamples with the project from the URL-overridden activeProject (Epic #1175)', () => {
    renderSentimentPage('/brand/sentiment?brandId=12&range=30d&profileGroup=all')

    expect(mocks.useMentionSamples).toHaveBeenCalled()
    const [calledProjectId] = mocks.useMentionSamples.mock.calls[0]
    expect(calledProjectId).toBe(esteeProjectId)
    expect(calledProjectId).not.toBe(bestCofferProjectId)
  })
})
