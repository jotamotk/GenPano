import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import DashboardPage from './DashboardPage'
import { LocaleProvider } from '../contexts/LocaleContext'

const bestCofferProjectId = '11111111-1111-4111-8111-111111111111'
const esteeProjectId = '22222222-2222-4222-8222-222222222222'

const useBrandOverviewMock = vi.fn()
const useBrandMetricsMock = vi.fn()
const useCompetitorMetricsMock = vi.fn()
const useCompetitorTrendsMock = vi.fn()

vi.mock('../contexts/ProjectContext', () => ({
  useProject: () => ({
    projects: [
      {
        id: bestCofferProjectId,
        name: 'BestCoffer App Analytics',
        primaryBrandId: '24',
        competitorBrandIds: [],
        industryId: '3',
      },
    ],
    activeProject: {
      id: bestCofferProjectId,
      name: 'BestCoffer App Analytics',
      primaryBrandId: '24',
      competitorBrandIds: [],
      industryId: '3',
    },
  }),
}))

vi.mock('../hooks/useProjects', () => ({
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

vi.mock('../hooks/useBrandOverview', async () => {
  const actual = await vi.importActual<typeof import('../hooks/useBrandOverview')>(
    '../hooks/useBrandOverview',
  )
  return {
    ...actual,
    useBrandOverview: (...args: unknown[]) => useBrandOverviewMock(...args),
  }
})

vi.mock('../hooks/useBrandMetrics', () => ({
  useBrandMetrics: (...args: unknown[]) => useBrandMetricsMock(...args),
  useCompetitorMetrics: (...args: unknown[]) => useCompetitorMetricsMock(...args),
  useCompetitorTrends: (...args: unknown[]) => useCompetitorTrendsMock(...args),
}))

vi.mock('../hooks/useDiagnostics', () => ({
  useDiagnostics: () => ({
    data: { items: [] },
    error: null,
  }),
}))

vi.mock('../hooks/useIndustries', () => ({
  useIndustries: () => ({
    data: [{ industry_id: 7, name: 'Beauty', nameZh: 'Beauty', nameEn: 'Beauty' }],
    isLoading: false,
    error: null,
  }),
  useIndustryAvgGeo: () => ({
    data: null,
    error: null,
  }),
}))

vi.mock('../components/dashboard/BrandPanoramaPanel', () => ({
  default: ({ primary }: { primary: { name?: string; nameZh?: string; nameEn?: string } }) => (
    <section>
      <h1>{primary.nameZh || primary.name || primary.nameEn}</h1>
      <p>{primary.nameEn}</p>
    </section>
  ),
}))

describe('DashboardPage project and brand route context', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useBrandOverviewMock.mockReturnValue({
      data: {
        project_id: esteeProjectId,
        brand_id: 12,
        brand_name: '雅诗兰黛',
        industry_id: 7,
        kpi_cards: [],
      },
      isLoading: false,
      error: null,
    })
    useBrandMetricsMock.mockReturnValue({ data: null, isLoading: false, error: null })
    useCompetitorMetricsMock.mockReturnValue({ data: null, isLoading: false, error: null })
    useCompetitorTrendsMock.mockReturnValue({ data: null, isLoading: false, error: null })
  })

  it('uses the live project that owns the URL brand instead of a stale active project', () => {
    render(
      <MemoryRouter initialEntries={['/brand/overview?brandId=12&range=30d&profileGroup=all']}>
        <LocaleProvider initialLocale="en-US">
          <DashboardPage />
        </LocaleProvider>
      </MemoryRouter>,
    )

    expect(useBrandOverviewMock).toHaveBeenCalledWith(esteeProjectId, 12)
    expect(useBrandMetricsMock).toHaveBeenCalledWith(
      esteeProjectId,
      ['mention_rate', 'sov', 'sentiment', 'rank', 'citation'],
      12,
      expect.objectContaining({ from: expect.any(String), to: expect.any(String) }),
    )
    expect(useCompetitorMetricsMock).toHaveBeenCalledWith(
      esteeProjectId,
      12,
      expect.objectContaining({ from: expect.any(String), to: expect.any(String) }),
    )
    expect(useCompetitorTrendsMock).toHaveBeenCalledWith(
      esteeProjectId,
      'geo_score',
      12,
      expect.objectContaining({ from: expect.any(String), to: expect.any(String) }),
    )
    expect(screen.getByRole('heading', { name: '雅诗兰黛' })).toBeInTheDocument()
    expect(screen.queryByText('BestCoffer App Analytics')).not.toBeInTheDocument()
  })
})
