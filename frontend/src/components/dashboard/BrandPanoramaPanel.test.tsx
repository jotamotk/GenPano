import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import BrandPanoramaPanel from './BrandPanoramaPanel'
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
})
