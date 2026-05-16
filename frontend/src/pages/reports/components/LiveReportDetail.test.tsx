import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const reportsHook = vi.hoisted(() => ({
  useReport: vi.fn(),
}))

vi.mock('../../../components/ui', () => ({
  Badge: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  Button: ({
    children,
    onClick,
    disabled,
  }: {
    children: ReactNode
    onClick?: () => void
    disabled?: boolean
  }) => (
    <button onClick={onClick} disabled={disabled}>
      {children}
    </button>
  ),
  Card: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('../../../api/reports', () => ({
  reportsApi: {
    downloadUrl: (p: string, r: string, fmt: string) =>
      `/api/v1/projects/${p}/reports/${r}/download?format=${fmt}`,
    share: vi.fn(),
  },
}))

vi.mock('../../../hooks/useReports', () => ({
  useReport: reportsHook.useReport,
}))

afterEach(() => {
  vi.clearAllMocks()
})

async function renderDetail(props?: {
  projectId?: string
  reportId?: string
}) {
  const { LiveReportDetail } = await import('./LiveReportDetail')
  return render(
    <LiveReportDetail
      projectId={props?.projectId ?? '11111111-1111-4111-8111-111111111111'}
      reportId={props?.reportId ?? 'report-uuid-xyz'}
      onBack={() => {}}
    />,
  )
}

describe('LiveReportDetail (audit #1044 F4-3)', () => {
  it('renders loading state while fetching', async () => {
    reportsHook.useReport.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    })
    await renderDetail()
    expect(screen.getByText(/加载报告内容/)).toBeInTheDocument()
  })

  it('renders error state on fetch failure', async () => {
    reportsHook.useReport.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('500 server error'),
    })
    await renderDetail()
    expect(screen.getByText(/报告加载失败/)).toBeInTheDocument()
    expect(screen.getByText(/500 server error/)).toBeInTheDocument()
  })

  it('renders each backend section with title + summary + metrics + table rows', async () => {
    reportsHook.useReport.mockReturnValue({
      data: {
        id: 'report-uuid-xyz',
        project_id: '11111111-1111-4111-8111-111111111111',
        type: 'json',
        status: 'done',
        created_at: '2026-05-16T00:00:00Z',
        finished_at: '2026-05-16T00:00:01Z',
        output_url: null,
        error: null,
        payload: {
          report_type: 'weekly',
          locale: 'zh-CN',
          period: { from: '2026-05-09', to: '2026-05-15' },
          brand_ids: [42],
          sections: [
            {
              section_type: 'executive_summary',
              title: '执行摘要',
              summary: 'GEO 总分 75, 环比 +3',
              metrics: {
                geo_score: 75,
                mention_rate: 0.42,
                sov: 0.31,
              },
              tables: [],
              variant: 'full',
            },
            {
              section_type: 'competitor_comparison',
              title: '竞品对比',
              summary: '3 brand(s) compared.',
              tables: [
                {
                  name: 'competitor_ranking',
                  rows: [
                    {
                      brand_id: 42,
                      is_primary: true,
                      geo_score: 75,
                      sov: 0.31,
                    },
                    {
                      brand_id: 43,
                      is_primary: false,
                      geo_score: 68,
                      sov: 0.22,
                    },
                  ],
                },
              ],
              variant: 'full',
            },
          ],
        },
      },
      isLoading: false,
      isError: false,
    })
    await renderDetail()

    // Section titles render
    expect(screen.getByText('执行摘要')).toBeInTheDocument()
    expect(screen.getByText('竞品对比')).toBeInTheDocument()

    // Summary strings render
    expect(screen.getByText(/GEO 总分 75/)).toBeInTheDocument()
    expect(screen.getByText(/3 brand\(s\) compared/)).toBeInTheDocument()

    // Metric labels surface — 'geo_score' / 'sov' also appear as table column
    // headers in the competitor section, so use getAllByText.
    expect(screen.getAllByText('geo_score').length).toBeGreaterThan(0)
    expect(screen.getByText('mention_rate')).toBeInTheDocument()
    expect(screen.getAllByText('sov').length).toBeGreaterThan(0)

    // Competitor table column headers
    expect(screen.getByText('brand_id')).toBeInTheDocument()
    expect(screen.getByText('is_primary')).toBeInTheDocument()

    // Header metadata
    expect(screen.getByText('LIVE')).toBeInTheDocument()
    expect(screen.getByText('weekly')).toBeInTheDocument()
  })

  it('renders explicit "no sections" message when payload has empty sections (e.g. lead_diagnostic)', async () => {
    reportsHook.useReport.mockReturnValue({
      data: {
        id: 'lead-uuid',
        project_id: '11111111-1111-4111-8111-111111111111',
        type: 'json',
        status: 'done',
        created_at: '2026-05-16T00:00:00Z',
        finished_at: null,
        output_url: null,
        error: null,
        payload: {
          report_type: 'lead_diagnostic',
          locale: 'zh-CN',
          period: { from: '2026-04-16', to: '2026-05-16' },
          layers: {},
        },
      },
      isLoading: false,
      isError: false,
    })
    await renderDetail()
    expect(screen.getByText(/payload 中无 sections/)).toBeInTheDocument()
  })

  it('shows download buttons that target the live API download endpoint', async () => {
    reportsHook.useReport.mockReturnValue({
      data: {
        id: 'r1',
        project_id: 'p1',
        type: 'json',
        status: 'done',
        created_at: '2026-05-16T00:00:00Z',
        finished_at: '2026-05-16T00:00:01Z',
        output_url: null,
        error: null,
        payload: {
          report_type: 'weekly',
          period: { from: '2026-05-09', to: '2026-05-15' },
          sections: [],
        },
      },
      isLoading: false,
      isError: false,
    })
    await renderDetail({ projectId: 'p1', reportId: 'r1' })
    expect(screen.getByText('Markdown')).toBeInTheDocument()
    expect(screen.getByText('JSON')).toBeInTheDocument()
    expect(screen.getByText('CSV')).toBeInTheDocument()
    expect(screen.getByText('分享')).toBeInTheDocument()
  })
})
