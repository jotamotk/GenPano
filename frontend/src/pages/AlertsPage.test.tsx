import { fireEvent, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'

const alertsHooks = vi.hoisted(() => ({
  useAlerts: vi.fn(),
  useUpdateAlertStatus: vi.fn(),
  useMarkAllAlertsRead: vi.fn(),
  useSnoozeAlert: vi.fn(),
}))

vi.mock('../components/ui', () => ({
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

vi.mock('../contexts/LocaleContext', async () => {
  // Use the real i18n dict so refactors that move literals into
  // messages.js still produce the same rendered text (e.g. '稍后再处理').
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

vi.mock('../hooks/useAlerts', () => ({
  useAlerts: alertsHooks.useAlerts,
  useUpdateAlertStatus: alertsHooks.useUpdateAlertStatus,
  useMarkAllAlertsRead: alertsHooks.useMarkAllAlertsRead,
  useSnoozeAlert: alertsHooks.useSnoozeAlert,
}))

afterEach(() => {
  vi.clearAllMocks()
})

function _alert(overrides: Record<string, unknown> = {}) {
  return {
    id: 'alert-1',
    project_id: 'p1',
    brand_id: 42,
    source: 'diagnostic',
    source_ref_id: 'd1',
    severity: 'P1' as const,
    scope: 'user',
    title: 'visibility dropped 30%',
    body: 'GEO score dropped from 80 to 56',
    status: 'unread' as const,
    triggered_at: new Date(Date.now() - 60_000).toISOString(),
    read_at: null,
    resolved_at: null,
    snoozed_until: null,
    assigned_to: null,
    runbook_url: null,
    ...overrides,
  }
}

function _setupHooks(items: ReturnType<typeof _alert>[], snoozeFn = vi.fn()) {
  alertsHooks.useAlerts.mockReturnValue({
    data: { items, total: items.length },
    isLoading: false,
    isError: false,
  })
  alertsHooks.useUpdateAlertStatus.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  })
  alertsHooks.useMarkAllAlertsRead.mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
  })
  alertsHooks.useSnoozeAlert.mockReturnValue({
    mutate: snoozeFn,
    isPending: false,
  })
}

async function renderPage() {
  const { default: AlertsPage } = await import('./AlertsPage')
  return render(<AlertsPage />)
}

describe('AlertsPage snooze UI (PRD §4.8.7 / audit #1044 B3-3)', () => {
  it('renders 稍后再处理 button on unread alerts', async () => {
    _setupHooks([_alert()])
    await renderPage()
    expect(screen.getByText('稍后再处理')).toBeInTheDocument()
  })

  it('does not render snooze button on resolved alerts', async () => {
    _setupHooks([_alert({ status: 'resolved' })])
    await renderPage()
    expect(screen.queryByText('稍后再处理')).not.toBeInTheDocument()
  })

  it('clicking 稍后再处理 reveals preset hour chips', async () => {
    _setupHooks([_alert()])
    await renderPage()
    fireEvent.click(screen.getByText('稍后再处理'))
    expect(screen.getByText('1 小时')).toBeInTheDocument()
    expect(screen.getByText('4 小时')).toBeInTheDocument()
    expect(screen.getByText('1 天')).toBeInTheDocument()
    expect(screen.getByText('7 天')).toBeInTheDocument()
  })

  it('clicking a preset calls snooze.mutate with id + hours', async () => {
    const mutate = vi.fn()
    _setupHooks([_alert()], mutate)
    await renderPage()
    fireEvent.click(screen.getByText('稍后再处理'))
    fireEvent.click(screen.getByText('1 天'))
    expect(mutate).toHaveBeenCalledWith({ id: 'alert-1', hours: 24 })
  })

  it('snoozed alert shows expiry timestamp + 已暂缓 label', async () => {
    const expiry = new Date(Date.now() + 3600_000).toISOString()
    _setupHooks([_alert({ status: 'snoozed', snoozed_until: expiry })])
    await renderPage()
    expect(screen.getByText(/已暂缓/)).toBeInTheDocument()
  })
})

describe('AlertsPage i18n (PR F frontend i18n cleanup)', () => {
  it('renders page title + subtitle from i18n dict (zh-CN)', async () => {
    _setupHooks([_alert()])
    await renderPage()
    expect(screen.getByText('提醒')).toBeInTheDocument()
    expect(
      screen.getByText(/P0 \/ P1 诊断 \+ 监测中断/),
    ).toBeInTheDocument()
  })

  it('uses relative_time keys for "刚刚" / "分钟前"', async () => {
    const just = new Date(Date.now() - 30_000).toISOString()
    _setupHooks([_alert({ triggered_at: just })])
    await renderPage()
    expect(screen.getByText('刚刚')).toBeInTheDocument()
  })
})
