import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const projectsHooks = vi.hoisted(() => ({
  useProjects: vi.fn(),
}))

const reportsHooks = vi.hoisted(() => ({
  useReports: vi.fn(),
  isLiveProjectId: vi.fn(),
}))

vi.mock('../../hooks/useProjects', () => ({
  useProjects: projectsHooks.useProjects,
}))

vi.mock('../../hooks/useReports', () => ({
  useReports: reportsHooks.useReports,
  isLiveProjectId: reportsHooks.isLiveProjectId,
}))

vi.mock('../../api/reports', () => ({
  reportsApi: {
    list: vi.fn(),
    share: vi.fn(),
    downloadUrl: () => '/dl',
  },
}))

vi.mock('../../components/ui', () => ({
  Badge: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  Button: ({
    children,
    onClick,
  }: {
    children: ReactNode
    onClick?: () => void
  }) => <button onClick={onClick}>{children}</button>,
  Card: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  Tabs: ({ tabs }: { tabs: { id: string; label: string }[] }) => (
    <div data-testid="mock-tabs">
      {tabs.map((tab) => (
        <span key={tab.id}>{tab.label}</span>
      ))}
    </div>
  ),
}))

vi.mock('../../contexts/LocaleContext', () => ({
  useLocale: () => ({
    t: (key: string) => key,
    locale: 'zh-CN',
    formatDate: () => '2026-04-14',
    formatBrand: (b: { nameZh: string }) => b.nameZh,
    formatNumber: (n: number) => String(n),
    formatDateRange: () => '2026-04-07 — 2026-04-13',
  }),
}))

vi.mock('./components/GenerateModal', () => ({
  GenerateModal: () => null,
}))

vi.mock('./components/LiveReportDetail', () => ({
  LiveReportDetail: () => null,
}))

vi.mock('./components/ReportDetail', () => ({
  ReportDetail: () => null,
}))

vi.mock('../../components/reports/ReportsLiveBanner', () => ({
  default: () => <div data-testid="live-banner" />,
}))

afterEach(() => {
  vi.clearAllMocks()
})

async function renderPage() {
  const { default: ReportsPage } = await import('./ReportsPage')
  return render(<ReportsPage />)
}

describe('ReportsPage mock catalog gating', () => {
  // Captured from user screenshot 2026-05-18: report tab shows brand
  // "雅诗兰黛" and Pano score "82" from hardcoded REPORTS[0] even when
  // the LIVE banner already says "no real reports yet".
  const SCREENSHOT_BRAND = '雅诗兰黛'
  const SCREENSHOT_PANO = '82'

  it('hides mock catalog when a live project (UUID id) is present', async () => {
    projectsHooks.useProjects.mockReturnValue({
      data: [{ id: 'b3a1c2d4-1111-2222-3333-444455556666' }],
    })
    reportsHooks.isLiveProjectId.mockImplementation(
      (id: unknown) =>
        typeof id === 'string' &&
        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
          id,
        ),
    )
    reportsHooks.useReports.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
      error: null,
    })

    await renderPage()

    expect(screen.queryByText(SCREENSHOT_BRAND)).not.toBeInTheDocument()
    expect(screen.queryByText(SCREENSHOT_PANO)).not.toBeInTheDocument()
    expect(screen.queryByTestId('mock-tabs')).not.toBeInTheDocument()
    expect(screen.getByTestId('live-banner')).toBeInTheDocument()
  })

  it('shows mock catalog when no live project is present (demo mode)', async () => {
    projectsHooks.useProjects.mockReturnValue({ data: [] })
    reportsHooks.isLiveProjectId.mockReturnValue(false)
    reportsHooks.useReports.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
    })

    await renderPage()

    expect(screen.getAllByText(SCREENSHOT_BRAND).length).toBeGreaterThan(0)
    expect(screen.getByText(SCREENSHOT_PANO)).toBeInTheDocument()
    expect(screen.getByTestId('mock-tabs')).toBeInTheDocument()
  })
})
