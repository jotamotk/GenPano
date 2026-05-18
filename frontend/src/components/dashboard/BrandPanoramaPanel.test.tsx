import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import BrandPanoramaPanel from './BrandPanoramaPanel'
import { LocaleProvider } from '../../contexts/LocaleContext'

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
})
