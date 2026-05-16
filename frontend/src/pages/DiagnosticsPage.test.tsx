import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'

const liveProjectId = '11111111-1111-4111-8111-111111111111'

const diagnosticsHooks = vi.hoisted(() => ({
  useDiagnostics: vi.fn(),
}))

const projectsHook = vi.hoisted(() => ({
  useProjects: vi.fn(),
}))

const projectContext = vi.hoisted(() => ({
  useProject: vi.fn(),
}))

vi.mock('../components/ui', () => ({
  Badge: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  Card: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}))

vi.mock('../components/diagnostics', () => ({
  DiagnosticCard: ({ diag }: { diag: { id: string; title?: string } }) => (
    <div data-testid="diagnostic-card">
      <span data-testid={`card-${diag.id}`}>{diag.title ?? diag.id}</span>
    </div>
  ),
  LeadFormModal: () => null,
}))

vi.mock('../hooks/useDiagnostics', () => ({
  useDiagnostics: diagnosticsHooks.useDiagnostics,
  toMockShape: (d: Record<string, unknown>) => d,
}))

vi.mock('../hooks/useProjects', () => ({
  useProjects: projectsHook.useProjects,
}))

vi.mock('../contexts/ProjectContext', () => ({
  useProject: projectContext.useProject,
}))

vi.mock('../contexts/LocaleContext', async () => {
  // Translate via the real zh-CN dict so assertions like /本项目暂无诊断/
  // continue to match after literals move into messages.js.
  const real = (await vi.importActual('../i18n/messages.js')) as {
    MESSAGES: Record<string, unknown>
    resolveKey: (obj: unknown, key: string) => unknown
    formatMessage: (template: string, params?: Record<string, unknown>) => string
  }
  return {
    useLocale: () => ({
      t: (key: string, params?: Record<string, unknown>) => {
        const v = real.resolveKey(real.MESSAGES['zh-CN'], key)
        return typeof v === 'string' ? real.formatMessage(v, params) : key
      },
    }),
  }
})

afterEach(() => {
  vi.clearAllMocks()
})

async function renderPage() {
  const { default: DiagnosticsPage } = await import('./DiagnosticsPage')
  return render(
    <MemoryRouter>
      <DiagnosticsPage />
    </MemoryRouter>,
  )
}

describe('DiagnosticsPage live vs mock semantics (AC-4.8-23 / audit #1044 F4-2)', () => {
  it('renders explicit empty state when live project has zero diagnostics — NOT mock data', async () => {
    projectContext.useProject.mockReturnValue({
      activeProject: { id: liveProjectId },
    })
    projectsHook.useProjects.mockReturnValue({ data: [{ id: liveProjectId }] })
    diagnosticsHooks.useDiagnostics.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
      isError: false,
    })

    await renderPage()

    expect(
      screen.getByText(/本项目暂无诊断/),
    ).toBeInTheDocument()
    // Mock DIAGNOSTICS contains "雅诗兰黛 SoV" / "兰蔻" titles — must
    // NOT appear when on a live project with empty results.
    expect(screen.queryAllByTestId('diagnostic-card')).toHaveLength(0)
    // No "示例" badge when on real project.
    expect(screen.queryByText('示例')).not.toBeInTheDocument()
  })

  it('renders loading state for live project while data is fetching', async () => {
    projectContext.useProject.mockReturnValue({
      activeProject: { id: liveProjectId },
    })
    projectsHook.useProjects.mockReturnValue({ data: [{ id: liveProjectId }] })
    diagnosticsHooks.useDiagnostics.mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    })

    await renderPage()

    expect(screen.getByText(/加载诊断/)).toBeInTheDocument()
    expect(screen.queryAllByTestId('diagnostic-card')).toHaveLength(0)
  })

  it('renders error state for live project on fetch failure', async () => {
    projectContext.useProject.mockReturnValue({
      activeProject: { id: liveProjectId },
    })
    projectsHook.useProjects.mockReturnValue({ data: [{ id: liveProjectId }] })
    diagnosticsHooks.useDiagnostics.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    })

    await renderPage()

    expect(screen.getByText(/诊断加载失败/)).toBeInTheDocument()
  })

  it('renders live diagnostics when present — never overlays mock', async () => {
    projectContext.useProject.mockReturnValue({
      activeProject: { id: liveProjectId },
    })
    projectsHook.useProjects.mockReturnValue({ data: [{ id: liveProjectId }] })
    diagnosticsHooks.useDiagnostics.mockReturnValue({
      data: {
        items: [
          {
            id: 'live-diag-1',
            severity: 'P0',
            type: 'brand',
            title: 'live diagnostic 1',
            evidence: {},
          },
        ],
        total: 1,
      },
      isLoading: false,
      isError: false,
    })

    await renderPage()

    expect(screen.getByTestId('card-live-diag-1')).toBeInTheDocument()
    // Mock DIAGNOSTICS has IDs unrelated to live-diag-1 — assert none of
    // them rendered alongside.
    expect(screen.queryAllByTestId('diagnostic-card')).toHaveLength(1)
  })

  it('renders mock catalog with 示例 badge when there is no live project', async () => {
    projectContext.useProject.mockReturnValue({ activeProject: null })
    projectsHook.useProjects.mockReturnValue({ data: [] })
    diagnosticsHooks.useDiagnostics.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
    })

    await renderPage()

    expect(screen.getByText('示例')).toBeInTheDocument()
    // Some mock card must render — exact count depends on DIAGNOSTICS;
    // assert at least one to confirm the mock path engaged.
    const cards = screen.queryAllByTestId('diagnostic-card')
    expect(cards.length).toBeGreaterThan(0)
  })

  it('renders severity labels (P0=紧急 etc.) from i18n dict, not hardcoded constants', async () => {
    projectContext.useProject.mockReturnValue({
      activeProject: { id: liveProjectId },
    })
    projectsHook.useProjects.mockReturnValue({ data: [{ id: liveProjectId }] })
    diagnosticsHooks.useDiagnostics.mockReturnValue({
      data: {
        items: [
          { id: 'd-p0', severity: 'P0', type: 'brand', title: 'a', evidence: {} },
          { id: 'd-p1', severity: 'P1', type: 'product', title: 'b', evidence: {} },
        ],
        total: 2,
      },
      isLoading: false,
      isError: false,
    })

    await renderPage()

    // Severity summary bar uses i18n keys diagnostics.severity.P0..P3
    expect(screen.getByText('紧急')).toBeInTheDocument()
    expect(screen.getByText('重要')).toBeInTheDocument()
    expect(screen.getByText('关注')).toBeInTheDocument()
    expect(screen.getByText('信息')).toBeInTheDocument()
  })
})
