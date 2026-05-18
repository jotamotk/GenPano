import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import BrandPanoramaPanel from './BrandPanoramaPanel'
import PanoTrendChart from './brand-panorama/charts/PanoTrendChart'
import { LocaleProvider } from '../../contexts/LocaleContext'

vi.mock('recharts', async () => {
  const React = await import('react')
  const Passthrough = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>
  const LineChart = ({ data, children }: { data?: unknown; children?: React.ReactNode }) => (
    <div>
      <pre data-testid="pano-trend-data">{JSON.stringify(data)}</pre>
      {children}
    </div>
  )
  const Line = ({ dataKey }: { dataKey?: string }) => (
    <span data-testid="pano-trend-line">{dataKey}</span>
  )
  const Empty = () => <div />
  return {
    ResponsiveContainer: Passthrough,
    LineChart,
    Line,
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

describe('BrandPanoramaPanel live KPI rendering', () => {
  it('renders the overview SoV KPI even when pie rows are unavailable', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/brand/overview']}>
          <LocaleProvider initialLocale="en-US">
            <BrandPanoramaPanel
              primary={{
                id: '12',
                name: 'Estee Lauder',
                nameZh: 'Estee Lauder',
                nameEn: 'Estee Lauder',
                panoScore: 80,
                mentionRate: 0.829,
                sov: 97.3,
                sentiment: 0,
                ranking: null,
                industryId: '7',
              }}
              competitors={[]}
              sovDataOverride={[]}
              bubbleDataOverride={[]}
              trendDataOverride={[]}
              sparklineOverride={{
                mention: [82.9],
                sov: [97.3],
                sentiment: [0],
                citation: [],
                rank: [],
              }}
              isLive
            />
          </LocaleProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(screen.getAllByText('82.9%').length).toBeGreaterThan(0)
    expect(screen.getAllByText('97.3%').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/#—|#-/).length).toBeGreaterThan(0)
    expect(screen.getByText('暂无声量份额数据')).toBeInTheDocument()
  })

  it('renders concrete live trend dates for the current primary brand', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/brand/overview']}>
          <LocaleProvider initialLocale="en-US">
            <BrandPanoramaPanel
              primary={{
                id: 'bestcoffer',
                name: 'bestcoffer',
                nameZh: 'bestcoffer',
                nameEn: 'bestcoffer',
                panoScore: 81,
                mentionRate: 0.41,
                sov: 52,
                sentiment: 0.2,
                ranking: 2,
                industryId: '7',
              }}
              competitors={[]}
              sovDataOverride={[]}
              bubbleDataOverride={[]}
              trendDataOverride={[
                {
                  day: 1,
                  date: '2026-05-10',
                  name: '2026-05-10',
                  panoScore: 81,
                  mentionRate: null,
                  sentiment: null,
                },
                {
                  day: 2,
                  date: '2026-05-11',
                  name: '2026-05-11',
                  panoScore: 83,
                  mentionRate: null,
                  sentiment: null,
                },
              ]}
              isLive
            />
          </LocaleProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const chartData = screen.getByTestId('pano-trend-data').textContent || ''
    expect(chartData).toContain('2026-05-10')
    expect(chartData).toContain('2026-05-11')
    expect(chartData).toContain('bestcoffer')
    expect(chartData).not.toContain('1d')
    expect(chartData).not.toContain('Estee Lauder')
    expect(screen.getByTestId('pano-trend-line')).toHaveTextContent('bestcoffer')
  })

  it('makes the competitor quadrant axis and evidence contract explicit', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/brand/overview']}>
          <LocaleProvider initialLocale="en-US">
            <BrandPanoramaPanel
              primary={{
                id: '12',
                name: 'bestCoffer',
                nameZh: 'bestCoffer',
                nameEn: 'bestCoffer',
                panoScore: 80,
                mentionRate: 0.829,
                sov: 97.3,
                sentiment: 0,
                ranking: null,
                industryId: '7',
              }}
              competitors={[]}
              sovDataOverride={[{ name: 'bestCoffer', value: 97.3 }]}
              bubbleDataOverride={[
                { brand: 'bestCoffer', sov: 97.3, sentiment: 0, mentions: 9 },
                { brand: 'Lancome', sov: null, sentiment: 0.2, mentions: 7 },
              ]}
              trendDataOverride={[]}
              sparklineOverride={{
                mention: [82.9],
                sov: [97.3],
                sentiment: [0],
                citation: [],
                rank: [],
              }}
              isLive
            />
          </LocaleProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(screen.getByText('X: Share of Voice')).toBeInTheDocument()
    expect(screen.getByText('Y: Sentiment')).toBeInTheDocument()
    expect(screen.getByText('Bubble: co-mentions / evidence count')).toBeInTheDocument()
    expect(screen.getByText(/1 brand has incomplete SoV or sentiment evidence/i)).toBeInTheDocument()
  })

  it('shows an explicit live trend state when dated rows are missing', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/brand/overview']}>
          <LocaleProvider initialLocale="en-US">
            <BrandPanoramaPanel
              primary={{
                id: 'bestcoffer',
                name: 'bestcoffer',
                nameZh: 'bestcoffer',
                nameEn: 'bestcoffer',
                panoScore: 81,
                mentionRate: 0.41,
                sov: 52,
                sentiment: 0.2,
                ranking: 2,
                industryId: '7',
              }}
              competitors={[]}
              sovDataOverride={[]}
              bubbleDataOverride={[]}
              trendDataOverride={[
                {
                  day: 1,
                  panoScore: 81,
                  mentionRate: null,
                  sentiment: null,
                },
              ]}
              isLive
            />
          </LocaleProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(screen.getByText('Live trend dates are missing.')).toBeInTheDocument()
    expect(screen.queryByTestId('pano-trend-data')).not.toBeInTheDocument()
  })

  it('shows endpoint partial state instead of plotting finite competitor rows', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/brand/overview']}>
          <LocaleProvider initialLocale="en-US">
            <BrandPanoramaPanel
              primary={{
                id: '12',
                name: 'Estee Lauder',
                nameZh: 'Estee Lauder',
                nameEn: 'Estee Lauder',
                panoScore: 80,
                mentionRate: 0.829,
                sov: 97.3,
                sentiment: 0,
                ranking: null,
                industryId: '7',
              }}
              competitors={[]}
              sovDataOverride={[{ name: 'Estee Lauder', value: 97.3 }]}
              bubbleDataOverride={[
                {
                  brand: '',
                  sov: null,
                  sentiment: null,
                  mentions: 0,
                  endpointState: 'partial',
                  stateReason: 'missing_formula_inputs',
                  missingInputs: ['eligible_response_denominator'],
                  configuredCompetitorCount: 1,
                },
                { brand: 'Estee Lauder', sov: 97.3, sentiment: 0.2, mentions: 9 },
                { brand: 'La Roche-Posay', sov: 2.7, sentiment: 0.1, mentions: 7 },
              ]}
              trendDataOverride={[]}
              sparklineOverride={{
                mention: [82.9],
                sov: [97.3],
                sentiment: [0],
                citation: [],
                rank: [],
              }}
              isLive
            />
          </LocaleProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(screen.getByText('Competitor quadrant is partial')).toBeInTheDocument()
    expect(screen.getByText(/missing formula inputs/i)).toBeInTheDocument()
    expect(screen.getByText(/eligible response denominator/i)).toBeInTheDocument()
    expect(screen.queryByText('X: Share of Voice')).not.toBeInTheDocument()
  })

  it('falls through partial_competitor_data to plot bubbles with a small partial badge', () => {
    // Issue #1185 follow-up — fixture mirrors the bestCoffer live API readback
    // captured in PR #1253's evidence ledger:
    //   https://github.com/jotamotk/trash_test/actions/runs/26035019036
    // state=partial, state_reason=partial_competitor_data, competitors[] carries
    // scoped rows with finite SoV / sentiment. This case must fall through to
    // bubble render with a small "数据为 partial" badge (mirrors
    // BrandCompetitorsPage.tsx:368-374 from PR #1253), not the full suppression.
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/brand/overview']}>
          <LocaleProvider initialLocale="en-US">
            <BrandPanoramaPanel
              primary={{
                id: '24',
                name: 'bestCoffer',
                nameZh: 'bestCoffer',
                nameEn: 'bestCoffer',
                panoScore: 70,
                mentionRate: 0.65,
                sov: 64.96,
                sentiment: 0.707,
                ranking: null,
                industryId: '数据安全',
              }}
              competitors={[]}
              sovDataOverride={[{ name: 'bestCoffer', value: 64.96 }]}
              bubbleDataOverride={[
                {
                  brand: '',
                  sov: null,
                  sentiment: null,
                  mentions: 0,
                  endpointState: 'partial',
                  stateReason: 'partial_competitor_data',
                  missingInputs: ['partial_analyzer_data', 'brand_unresolved'],
                  configuredCompetitorCount: 1,
                },
                { brand: 'bestCoffer', sov: 64.96, sentiment: 0.707, mentions: 0 },
                { brand: 'IBM Security', sov: 15.94, sentiment: 0.22, mentions: 33 },
              ]}
              trendDataOverride={[]}
              sparklineOverride={{
                mention: [65],
                sov: [64.96],
                sentiment: [0.707],
                citation: [],
                rank: [],
              }}
              isLive
            />
          </LocaleProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    expect(screen.getByText('X: Share of Voice')).toBeInTheDocument()
    expect(screen.getByText(/数据为 partial/)).toBeInTheDocument()
    expect(screen.queryByText('Competitor quadrant is partial')).not.toBeInTheDocument()
  })

  it('keeps demo trend labels on ordinal day fallback instead of mock names', () => {
    const localizedDayLabel = '1\u65e5'

    render(
      <PanoTrendChart
        trendData={[
          {
            day: 1,
            name: localizedDayLabel,
            panoScore: 81,
          },
        ]}
        primaryName="Demo Brand"
        competitors={[]}
        isLive={false}
        t={(key) => key}
      />,
    )

    const chartData = screen.getByTestId('pano-trend-data').textContent || ''
    expect(chartData).toContain('1d')
    expect(chartData).not.toContain(localizedDayLabel)
  })
})
