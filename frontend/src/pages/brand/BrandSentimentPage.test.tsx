import { fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { LocaleProvider } from '../../contexts/LocaleContext'
import BrandSentimentPage from './BrandSentimentPage'

const mocks = vi.hoisted(() => {
  const allSamples = Array.from({ length: 108 }, (_, idx) => ({
    query_id: 9000 + idx,
    mention_id: idx + 1,
    response_id: 1000 + idx,
    label: idx % 2 === 0 ? 'Positive' : 'Negative',
    polarity: idx % 2 === 0 ? 'positive' : 'negative',
    summary: `Response summary ${idx + 1}`,
    snippet: `Response snippet ${idx + 1}`,
    response_text: `Full response text from API ${idx + 1}`,
    engine: 'ChatGPT',
    topic: `Topic ${idx + 1}`,
    occurred_at: '2026-05-18T00:00:00Z',
  }))

  return {
    useMentionSamples: vi.fn((_: string | null | undefined, opts: { offset?: number; limit?: number; polarity?: string } = {}) => {
    const offset = opts.offset ?? 0
    const limit = opts.limit ?? 100
    const pageItems = allSamples.slice(offset, offset + limit)
    return {
      data: {
        project_id: '11111111-2222-3333-4444-555555555555',
        state: 'ok',
        metric_formula_evidence: { sentiment: { formula_status: 'ok' } },
        items: pageItems,
        total: allSamples.length,
        limit,
        offset,
        has_more: offset + pageItems.length < allSamples.length,
        evidence_count: allSamples.length,
        selected_filters: {
          brand_id: 42,
          polarity: opts.polarity ?? null,
        },
      },
      isLoading: false,
      error: null,
    }
  }),
  }
})

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
  resolveLiveProjectIdForBrand: () => '11111111-2222-3333-4444-555555555555',
  isLiveProjectId: () => true,
}))

vi.mock('../../hooks/useTopicAnalysis', () => ({
  useProjectSegments: () => ({
    data: { items: [] },
  }),
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
  it('renders every fetched response without a silent six-item cap', () => {
    renderSentimentPage()

    expect(screen.getByText('Response summary 1')).toBeInTheDocument()
    expect(screen.getByText('Response summary 8')).toBeInTheDocument()
    expect(screen.getByText('Response summary 100')).toBeInTheDocument()
    expect(screen.queryByText('Response summary 101')).not.toBeInTheDocument()
    expect(screen.getByText(/Showing 100 of 108 responses/)).toBeInTheDocument()
  })

  it('uses response_text from the API for full response inspection', () => {
    renderSentimentPage()

    fireEvent.click(screen.getByRole('button', { name: /^Inspect full response for Response summary 1$/ }))

    expect(screen.getByText('Full response inspection')).toBeInTheDocument()
    expect(screen.getByText('Full response text from API 1')).toBeInTheDocument()
    expect(screen.getByText(/query_id: 9000/)).toBeInTheDocument()
  })

  it('loads additional pages using total and has_more metadata', async () => {
    renderSentimentPage()

    fireEvent.click(screen.getByRole('button', { name: /Load more responses/ }))

    expect(await screen.findByText('Response summary 108')).toBeInTheDocument()
    expect(screen.getByText(/Showing all 108 responses/)).toBeInTheDocument()
  })

  it('preserves project, brand, and engine scope when filters change', () => {
    // Issue #1248: polarity is now a pure client-side display filter (see
    // useMentionSamples call in BrandSentimentPage.tsx). The backend always
    // receives the all-view request so the client filter can narrow it.
    // We assert here that the project/brand/engine scope still threads
    // through, and that polarity is not forwarded.
    renderSentimentPage()

    fireEvent.click(screen.getByRole('button', { name: 'Positive' }))

    expect(mocks.useMentionSamples).toHaveBeenLastCalledWith(
      '11111111-2222-3333-4444-555555555555',
      expect.objectContaining({
        limit: 100,
        offset: 0,
        filters: expect.objectContaining({
          brand_id: 42,
          engine: 'ChatGPT',
        }),
      }),
    )
    const lastCall = mocks.useMentionSamples.mock.calls.at(-1)
    expect(lastCall?.[1]).not.toHaveProperty('polarity')
  })

  it('does not show demo badges on live response evidence', () => {
    renderSentimentPage()

    expect(screen.queryByText(/Mock/i)).not.toBeInTheDocument()
  })

  // Issue #1248: BestCoffer brand 24 ships responses where the backend
  // `get_mention_samples` polarity filter joins through `brand_mentions`
  // (empty for that brand per readonly evidence run
  // https://github.com/jotamotk/trash_test/actions/runs/26034927203 with
  // brand_mention_count: 0), so the user sees the loaded window for
  // polarity=all but 0 visible rows after clicking 正面/负面. The frontend
  // must apply its own client-side polarity filter on the already-loaded
  // items regardless of `isLive`.
  describe('Issue #1248 client-side polarity filter', () => {
    it('hides negative and neutral rows when Positive is selected (live mode)', async () => {
      renderSentimentPage()

      // Sanity: under "All" the mixed fixture renders both polarities.
      expect(screen.getByText('Response summary 1')).toBeInTheDocument()
      expect(screen.getByText('Response summary 2')).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'Positive' }))

      // Even-indexed fixture rows are positive; they stay visible. Await
      // the re-render that re-accumulates the live samples after the
      // polarity-button click resets accumulatedLiveSamples to [].
      expect(await screen.findByText('Response summary 1')).toBeInTheDocument()
      expect(screen.getByText('Response summary 3')).toBeInTheDocument()
      // Odd-indexed fixture rows are negative; they must be filtered out
      // client-side even though the mocked backend still returns them.
      expect(screen.queryByText('Response summary 2')).not.toBeInTheDocument()
      expect(screen.queryByText('Response summary 4')).not.toBeInTheDocument()
    })

    it('hides positive and neutral rows when Negative is selected (live mode)', async () => {
      renderSentimentPage()

      fireEvent.click(screen.getByRole('button', { name: 'Negative' }))

      expect(await screen.findByText('Response summary 2')).toBeInTheDocument()
      expect(screen.getByText('Response summary 4')).toBeInTheDocument()
      expect(screen.queryByText('Response summary 1')).not.toBeInTheDocument()
      expect(screen.queryByText('Response summary 3')).not.toBeInTheDocument()
    })

    it('restores every loaded row when 全部 (All) is reselected', async () => {
      renderSentimentPage()

      fireEvent.click(screen.getByRole('button', { name: 'Positive' }))
      expect(await screen.findByText('Response summary 1')).toBeInTheDocument()
      expect(screen.queryByText('Response summary 2')).not.toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'All' }))

      expect(await screen.findByText('Response summary 2')).toBeInTheDocument()
      expect(screen.getByText('Response summary 1')).toBeInTheDocument()
    })

    it('surfaces the filter delta in the window label when a polarity is active', async () => {
      renderSentimentPage()

      fireEvent.click(screen.getByRole('button', { name: 'Positive' }))

      // Loaded window stays the same; the filter delta is appended so the
      // user does not see "Showing 100 of 108" while only 50 rows render.
      // The substring appears in both the header window label and the live
      // diagnostic block — at least one match proves the filter delta is
      // surfaced.
      const matches = await screen.findAllByText(/match the positive filter/)
      expect(matches.length).toBeGreaterThan(0)
    })
  })

  // Issue #1247: backend's `_label_for_polarity` emits English titlecase
  // ('Positive' / 'Negative' / 'Neutral'). The previous code compared
  // `item.label === '正面'` (Chinese), which never matched, so every
  // badge fell through to the default (pale gray) variant. The fix uses
  // `item.polarity` (lowercase canonical) for color resolution.
  //
  // NOTE: this test calls `mocks.useMentionSamples.mockImplementation(...)`,
  // which permanently overrides the default mock for any test that runs
  // after it in this file. It is placed LAST so the #1248 describe block
  // above keeps the default 108-row fixture. Do not move it earlier
  // without also adding a mock restore in an afterEach hook.
  it('colors the polarity badge by item.polarity (not item.label) so backend English titlecase still resolves Positive→green / Negative→red / Neutral→default', () => {
    const polarityFixtures = [
      { polarity: 'positive', label: 'Positive', expectedClass: 't-badge-success' },
      { polarity: 'negative', label: 'Negative', expectedClass: 't-badge-danger' },
      { polarity: 'neutral', label: 'Neutral', expectedClass: 't-badge-default' },
    ]
    const polaritySamples = polarityFixtures.map((row, idx) => ({
      query_id: 7000 + idx,
      mention_id: 800 + idx,
      response_id: 900 + idx,
      label: row.label,
      polarity: row.polarity,
      summary: `Polarity row ${row.polarity}`,
      snippet: `Snippet ${row.polarity}`,
      response_text: `Full text ${row.polarity}`,
      engine: 'ChatGPT',
      topic: `Topic ${row.polarity}`,
      occurred_at: '2026-05-18T00:00:00Z',
    }))

    mocks.useMentionSamples.mockImplementation(() => ({
      data: {
        project_id: '11111111-2222-3333-4444-555555555555',
        state: 'ok',
        metric_formula_evidence: { sentiment: { formula_status: 'ok' } },
        items: polaritySamples,
        total: polaritySamples.length,
        limit: 100,
        offset: 0,
        has_more: false,
        evidence_count: polaritySamples.length,
        selected_filters: { brand_id: 42, polarity: null },
      },
      isLoading: false,
      error: null,
    }))

    renderSentimentPage()

    for (const fixture of polarityFixtures) {
      // The polarity badge sits next to a topic of `Topic <polarity>` and
      // a summary of `Polarity row <polarity>`. Scope by summary card to
      // avoid colliding with the polarity *filter* buttons of the same name.
      const summary = screen.getByText(`Polarity row ${fixture.polarity}`)
      const card = summary.closest('.rounded-card') as HTMLElement
      expect(card).not.toBeNull()
      const badge = card.querySelector('.t-badge') as HTMLElement
      expect(badge).not.toBeNull()
      expect(badge).toHaveTextContent(fixture.label)
      expect(badge).toHaveClass(fixture.expectedClass)
    }
  })
})
