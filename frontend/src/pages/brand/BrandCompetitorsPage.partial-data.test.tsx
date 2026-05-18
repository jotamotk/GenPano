import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { LocaleProvider } from '../../contexts/LocaleContext'
import BrandCompetitorsPage from './BrandCompetitorsPage'

// Issue #1185 follow-up: when state=partial but state_reason indicates
// the data itself is just "partial" (not metric-trust failure) AND
// competitors[] is non-empty, the page should render the threat cards
// + downstream charts, surfacing the partiality as a small badge —
// not suppress the whole panel.
//
// Real-surface evidence — bestCoffer recent window
// (https://github.com/jotamotk/trash_test/actions/runs/26035019036):
//   state: "partial"
//   state_reason: "partial_competitor_data"
//   competitors: 11 same-industry rows (IBM Security, Intralinks, ...)
// Pre-fix, threatCards.length was forced to 0 and the banner hid the
// data even though it was scoped and valid.

vi.mock('recharts', async () => {
  const React = await import('react')
  const Passthrough = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>
  const Empty = () => <div />
  return {
    ResponsiveContainer: Passthrough,
    RadarChart: Passthrough,
    PolarGrid: Empty,
    PolarAngleAxis: Empty,
    PolarRadiusAxis: Empty,
    Radar: Empty,
    Legend: Empty,
  }
})

vi.mock('../../components/filters/BrandAnalysisFilterBar', () => ({
  default: () => <div data-testid="filter-bar" />,
}))

vi.mock('../../components/charts/BrandTopicHeatmap', () => ({
  default: () => <div data-testid="topic-heatmap" />,
}))

vi.mock('../../contexts/ProjectContext', () => ({
  useProject: () => ({
    activeProject: {
      id: '7380c0e0-8798-4a5f-998f-42010a7d9caa',
      primaryBrandId: 24,
      primaryBrandName: 'bestCoffer',
      name: 'BestCoffer App Analytics',
      competitorBrandIds: [2],
      industryId: null,
    },
  }),
}))

vi.mock('../../hooks/useBrandAnalysisFilters', () => ({
  useBrandAnalysisFilters: () => ({ filters: {} }),
}))

vi.mock('../../hooks/useProjects', () => ({
  useProjects: () => ({
    data: [{ id: '7380c0e0-8798-4a5f-998f-42010a7d9caa', primaryBrandId: 24 }],
  }),
}))

vi.mock('../../lib/liveProject', () => ({
  resolveLiveProjectId: () => '7380c0e0-8798-4a5f-998f-42010a7d9caa',
}))

vi.mock('../../hooks/useBrandOverview', () => ({
  isLiveProjectId: () => true,
}))

// Fixture matches the bestCoffer AFTER readback from run 26035019036:
// 11 same-industry competitors with IBM Security at top by co_mention.
vi.mock('../../hooks/useBrandMetrics', () => ({
  useCompetitorMetrics: () => ({
    data: {
      project_id: '7380c0e0-8798-4a5f-998f-42010a7d9caa',
      primary_brand_id: 24,
      period: { from: '2026-05-11', to: '2026-05-18' },
      state: 'partial',
      state_reason: 'partial_competitor_data',
      state_detail: 'Some analyzer evidence is partial.',
      missing_inputs: ['partial_analyzer_data', 'brand_unresolved'],
      primary: {
        brand_id: 24,
        brand_key: 'id:24',
        brand_name: 'bestCoffer',
        avg_geo_score: null,
        avg_mention_rate: 0.6036,
        avg_sov: 0.6496,
        avg_sentiment: 0.707,
        co_mention_count: 0,
        delta_30d_pct: null,
      },
      competitors: [
        {
          brand_id: null,
          brand_key: 'name:ibm security',
          brand_name: 'IBM Security',
          avg_geo_score: null,
          avg_mention_rate: 0.1435,
          avg_sov: 0.1594,
          avg_sentiment: 0.22,
          co_mention_count: 33,
          delta_30d_pct: null,
        },
        {
          brand_id: 25,
          brand_key: 'id:25',
          brand_name: 'IBM Security',
          avg_geo_score: null,
          avg_mention_rate: 0.0087,
          avg_sov: 0.0128,
          avg_sentiment: 0.4,
          co_mention_count: 2,
          delta_30d_pct: null,
        },
        {
          brand_id: null,
          brand_key: 'name:intralinks',
          brand_name: 'Intralinks',
          avg_geo_score: null,
          avg_mention_rate: 0.0348,
          avg_sov: 0.0085,
          avg_sentiment: -0.175,
          co_mention_count: 7,
          delta_30d_pct: null,
        },
        {
          brand_id: null,
          brand_key: 'name:datasite',
          brand_name: 'Datasite',
          avg_geo_score: null,
          avg_mention_rate: 0.0261,
          avg_sov: 0.0055,
          avg_sentiment: -0.05,
          co_mention_count: 4,
          delta_30d_pct: null,
        },
      ],
      project_scope: {
        exists: true,
        project_id: '7380c0e0-8798-4a5f-998f-42010a7d9caa',
        primary_brand_id: 24,
        requested_brand_id: 24,
        competitor_brand_ids: [2],
      },
      evidence_counts: {
        competitor_brand_count: 1,
        eligible_response_count: 0,
        competitive_mention_count: 472,
      },
      metric_definitions: {
        avg_geo_score: {
          metric_key: 'avg_geo_score',
          unit: 'score',
          value_scale: 'score_0_100',
          formula_status: 'ok',
        },
        avg_mention_rate: {
          metric_key: 'avg_mention_rate',
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
        },
        avg_sov: {
          metric_key: 'avg_sov',
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
        },
        avg_sentiment: {
          metric_key: 'avg_sentiment',
          unit: 'score',
          value_scale: 'raw_-1_1',
          formula_status: 'ok',
        },
      },
    },
  }),
  useCompetitorTrends: () => ({
    data: { series: [], state: 'partial' },
  }),
}))

vi.mock('../../hooks/useCharts', () => ({
  useAuthorityRadar: () => ({ data: null }),
  useGroupSharedDomains: () => ({ data: null }),
  useTopicHeatmap: () => ({ data: null }),
}))

describe('BrandCompetitorsPage partial_competitor_data fall-through', () => {
  it('renders threat cards (with partial badge) when competitors[] is non-empty and state_reason is partial_competitor_data', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={['/brand/competitors?brandId=24']}>
          <LocaleProvider initialLocale="en-US">
            <BrandCompetitorsPage />
          </LocaleProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    // Top 3 威胁竞品 cards must be rendered, not the generic banner.
    // threatCards is sliced to 3 by SoV; IBM Security (0.1594) + IBM Security
    // brand_id=25 (0.0128) + Intralinks (0.0085) are the top three in the
    // fixture, so they must appear; Datasite is rank 4 and is intentionally
    // out of the top-3 slice for this test.
    expect(screen.getAllByText('IBM Security').length).toBeGreaterThan(0)
    expect(screen.getByText('Intralinks')).toBeInTheDocument()
    // Partial indicator badge surfaces the state without hiding data.
    expect(screen.getByText(/数据为 partial/)).toBeInTheDocument()
    // The full-suppression banner must NOT appear.
    expect(screen.queryByText('Competitor comparison is partial')).not.toBeInTheDocument()
    // Issue #1185 follow-up — chart titles must use the live primary
    // brand name (bestCoffer), not the mock cosmetics fallback that
    // leaked through when `BRANDS.find(...)` returned undefined for the
    // bestCoffer brand_id and silently selected BRANDS[1] (雅诗兰黛).
    // Authority Radar / Topic 胜负图 / PANO 趋势 titles all share the
    // same "{primary.name} vs {focus.name}" pattern.
    expect(screen.queryByText(/雅诗兰黛/)).not.toBeInTheDocument()
    expect(
      screen.getAllByText((_, element) => /bestCoffer.*vs.*IBM Security/.test(element?.textContent ?? '')).length,
    ).toBeGreaterThan(0)
  })
})
