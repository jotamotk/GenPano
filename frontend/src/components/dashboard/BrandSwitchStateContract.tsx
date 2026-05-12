import {
  AlertTriangle,
  BarChart3,
  Database,
  LineChart,
  Network,
} from 'lucide-react'

import type {
  BrandSwitchStateContract as BrandSwitchStateContractModel,
  BrandSwitchStateKey,
} from '../../adapters/dashboardAdapter'
import { Badge, Card } from '../ui'

const STATE_STYLE: Record<BrandSwitchStateKey, { variant: string; icon: typeof AlertTriangle }> = {
  no_collected_data: { variant: 'secondary', icon: Database },
  analysis_missing: { variant: 'orange', icon: AlertTriangle },
  project_unbound: { variant: 'red', icon: Network },
  no_aggregate_rows: { variant: 'info', icon: LineChart },
}

export default function BrandSwitchStateContract({
  contract,
}: {
  contract: BrandSwitchStateContractModel | null
}) {
  if (!contract) return null

  return (
    <div data-testid="brand-switch-state-contract">
      <Card
        className="mb-4 p-4"
        style={{
          borderColor: 'var(--color-warning)',
          background: 'var(--color-bg-card)',
        }}
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="orange" size="sm">brand switch</Badge>
              {contract.brandId != null && (
                <span className="text-[11px] font-semibold uppercase tracking-wide text-themed-muted">
                  brand_id={contract.brandId}
                </span>
              )}
            </div>
            <h3 className="mt-2 text-sm font-semibold text-themed-primary">
              {contract.title}
            </h3>
            <p className="mt-1 text-xs text-themed-muted">
              Project {contract.projectId ? contract.projectId.slice(0, 8) : 'pending'} keeps App metrics non-ok until these states clear.
            </p>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {contract.blockers.map((state) => (
              <Badge key={state} variant={STATE_STYLE[state].variant} size="sm">
                {state}
              </Badge>
            ))}
          </div>
        </div>

        {contract.evidence.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5" data-testid="brand-switch-evidence">
            {contract.evidence.map((item) => (
              <span
                key={item}
                className="rounded-pill border border-themed-card px-2 py-0.5 text-[11px] text-themed-muted"
              >
                {item}
              </span>
            ))}
          </div>
        )}

        <div className="mt-4 grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-4">
          {contract.states.map((item) => {
            const Icon = STATE_STYLE[item.state].icon
            return (
              <div
                key={item.surface}
                className="min-h-[112px] rounded-card border border-themed-card bg-themed-subtle p-3"
                data-testid={`brand-switch-state-${item.surface.toLowerCase().replace(/\s+/g, '-')}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <Icon size={15} className="shrink-0 text-themed-muted" aria-hidden />
                    <span className="truncate text-xs font-semibold text-themed-primary">
                      {item.surface}
                    </span>
                  </div>
                  <Badge variant={STATE_STYLE[item.state].variant} size="xs">
                    {item.state}
                  </Badge>
                </div>
                <div className="mt-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-themed-muted">
                  <BarChart3 size={13} aria-hidden />
                  {item.title}
                </div>
                <p className="mt-1 text-[11px] leading-5 text-themed-muted">
                  {item.detail}
                </p>
              </div>
            )
          })}
        </div>
      </Card>
    </div>
  )
}
