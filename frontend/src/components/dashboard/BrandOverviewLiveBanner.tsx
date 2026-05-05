/**
 * BrandOverviewLiveBanner — live KPI strip rendered above
 * BrandPanoramaPanel when the active project is real (UUID-shaped id).
 *
 * Rationale: rewriting the 910-line BrandPanoramaPanel to take real
 * backend props is a large refactor (Phase 2.1 follow-up). This
 * banner is a non-invasive way to surface real values right now —
 * `/v1/projects/:id/overview` populates 4 KPI cards above the existing
 * mock viz, so the user sees the backend is actually wired without
 * waiting for the bigger refactor.
 *
 * When the project is mock-shaped (`proj-001`) the hook short-circuits
 * and the banner renders nothing, leaving DashboardPage unchanged.
 */

import { useProjects } from '../../hooks/useProjects'
import { useBrandOverview, isLiveProjectId } from '../../hooks/useBrandOverview'

const DIRECTION_ICON: Record<string, string> = {
  up: '↑',
  down: '↓',
  flat: '→',
}
const DIRECTION_COLOR: Record<string, string> = {
  up: '#16a34a',
  down: '#dc2626',
  flat: '#64748b',
}

export default function BrandOverviewLiveBanner() {
  // Resolve a live project ID via /v1/projects/. If the user has any
  // real project in the backend, use the first one. Otherwise the
  // banner renders nothing and the page falls back to mock viz only.
  const { data: liveProjects } = useProjects()
  const liveProjectId = liveProjects && liveProjects.length > 0 ? liveProjects[0].id : null

  const { data: overview, isLoading } = useBrandOverview(liveProjectId)

  if (!isLiveProjectId(liveProjectId) || isLoading || !overview) {
    return null
  }

  return (
    <div
      className="rounded-card border p-4 mb-4"
      style={{
        background:
          'linear-gradient(135deg, rgba(99, 91, 255, 0.06), rgba(139, 92, 246, 0.04))',
        borderColor: 'var(--color-accent, #635bff)',
      }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span
            className="px-2 py-0.5 rounded-pill text-[10px] font-bold tabular-nums"
            style={{ background: 'var(--color-accent, #635bff)', color: 'white' }}
          >
            LIVE
          </span>
          <span className="text-sm font-semibold text-themed-primary">
            {overview.brand_name || `品牌 ${overview.brand_id ?? '—'}`}
          </span>
          <span className="text-[11px] text-themed-faint">
            {overview.period.from} → {overview.period.to}
          </span>
        </div>
        <span className="text-[10px] uppercase font-bold tracking-wider text-themed-muted">
          来自 /v1/projects/{overview.project_id.slice(0, 8)}…/overview
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {overview.kpi_cards.map((card, i) => {
          const dirIcon = card.direction ? DIRECTION_ICON[card.direction] : null
          const dirColor = card.direction
            ? DIRECTION_COLOR[card.direction]
            : 'var(--color-text-muted, #64748b)'
          return (
            <div
              key={i}
              className="rounded-card p-3"
              style={{ background: 'var(--color-bg-card, #fff)' }}
            >
              <div className="text-[11px] uppercase tracking-wider text-themed-muted mb-1">
                {card.label_zh}
              </div>
              <div className="flex items-baseline gap-1">
                <span className="text-xl font-bold tabular-nums text-themed-primary">
                  {typeof card.value === 'number'
                    ? card.value.toLocaleString(undefined, { maximumFractionDigits: 2 })
                    : card.value}
                </span>
                {card.unit && (
                  <span className="text-xs text-themed-muted">{card.unit}</span>
                )}
              </div>
              {card.delta_30d_pct !== null && card.delta_30d_pct !== undefined && (
                <div className="text-[11px] mt-1 tabular-nums" style={{ color: dirColor }}>
                  {dirIcon} {card.delta_30d_pct > 0 ? '+' : ''}
                  {card.delta_30d_pct.toFixed(1)}% vs 上 30d
                </div>
              )}
            </div>
          )
        })}
      </div>

      {overview.state === 'empty' && (
        <p className="text-[11px] text-themed-faint mt-3">
          暂无 30 天聚合数据 — 数据采集 pipeline 跑过后会自动填充。
        </p>
      )}
    </div>
  )
}
