/**
 * BrandOverviewLiveView — full-page live brand overview that REPLACES
 * the mock BrandPanoramaPanel when the user has a real backend project.
 *
 * Phase 5 §"mock 退役" — pages should no longer show mock data when a
 * live project is active. This component renders the entire dashboard
 * body using GET /v1/projects/:id/overview, with explicit empty /
 * loading / error states.
 */
import { useNavigate } from 'react-router-dom'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  AreaChart,
  Area,
} from 'recharts'

import { Badge, Button, Card } from '../ui'
import { useLocale } from '../../contexts/LocaleContext'
import { useBrandOverview, isLiveProjectId } from '../../hooks/useBrandOverview'
import type { TrendPoint, KpiCard as KpiCardT } from '../../api/brandOverview'

const DIRECTION_ICON: Record<string, string> = { up: '↑', down: '↓', flat: '→' }
const DIRECTION_COLOR: Record<string, string> = {
  up: '#16a34a',
  down: '#dc2626',
  flat: '#64748b',
}

interface Props {
  projectId: string
}

export default function BrandOverviewLiveView({ projectId }: Props) {
  const navigate = useNavigate()
  const { t, locale, formatDate } = useLocale()
  const { data, isLoading, error, refetch } = useBrandOverview(projectId)

  if (!isLiveProjectId(projectId)) return null

  if (isLoading) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-sm text-themed-muted">加载真实数据…</div>
      </Card>
    )
  }

  if (error) {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-sm text-themed-muted mb-3">
          加载失败: {error instanceof Error ? error.message : 'unknown'}
        </div>
        <Button variant="secondary" size="sm" onClick={() => refetch()}>
          重试
        </Button>
      </Card>
    )
  }

  if (!data || data.state === 'empty') {
    return (
      <Card className="p-12 text-center" onClick={undefined} style={{}}>
        <div className="text-3xl mb-3">📡</div>
        <h3 className="text-base font-semibold text-themed-primary mb-2">
          首批数据采集中
        </h3>
        <p className="text-sm text-themed-muted mb-4 max-w-md mx-auto">
          后端已经接收到该 Project, 但还没有 LLM 响应入库. 通常首批查询
          在 24h 内完成, 之后该页将填充真实 GEO 指标 / SoV / 情感 / 引用 / 诊断.
        </p>
        <div className="flex justify-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => navigate('/project-settings')}>
            管理 Project
          </Button>
          <Button variant="primary" size="sm" onClick={() => refetch()}>
            刷新
          </Button>
        </div>
      </Card>
    )
  }

  const period = data.period
  const periodLabel = `${formatDate(period.from)} – ${formatDate(period.to)}`
  const brandLabel = data.brand_name ?? `Brand #${data.brand_id ?? '?'}`

  return (
    <div className="space-y-6">
      {/* Header strip */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-baseline gap-3 flex-wrap">
          <Badge variant="default">LIVE</Badge>
          <h1 className="text-heading-2 text-themed-primary font-bold">
            {brandLabel}
          </h1>
          <span className="text-sm text-themed-muted">{periodLabel}</span>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => navigate('/project-settings')}
          >
            管理 Project
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => navigate('/brand/diagnostics')}
          >
            查看诊断
          </Button>
        </div>
      </div>

      {/* KPI cards */}
      {data.kpi_cards && data.kpi_cards.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {data.kpi_cards.map((kpi, idx) => (
            <KpiCard key={idx} kpi={kpi} locale={locale} />
          ))}
        </div>
      )}

      {/* Trend charts */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <TrendCard
          title="GEO 综合分 (30d)"
          points={data.geo_score_30d}
          color="var(--color-accent, #635bff)"
          formatDate={formatDate}
        />
        <TrendCard
          title="SoV (30d)"
          points={data.sov_30d}
          color="#16a34a"
          formatDate={formatDate}
          unit="%"
          asArea
        />
        <TrendCard
          title="平均情感 (30d)"
          points={data.sentiment_30d}
          color="#f59e0b"
          formatDate={formatDate}
        />
      </div>

      {/* Top prompts table */}
      {data.top_prompts && data.top_prompts.length > 0 && (
        <Card className="p-0 overflow-hidden" onClick={undefined} style={{}}>
          <div className="px-5 py-3 border-b border-themed-subtle">
            <h3 className="text-sm font-semibold text-themed-primary">
              Top 提及 Prompt (30d)
            </h3>
            <p className="text-xs text-themed-muted">
              来自 brand_mentions GROUP BY prompt
            </p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-themed-muted">
                  <th className="py-2 pl-5">Prompt</th>
                  <th className="py-2 px-3 text-right">提及次数</th>
                  <th className="py-2 px-3 text-right">平均位置</th>
                  <th className="py-2 px-3 text-right">情感</th>
                </tr>
              </thead>
              <tbody>
                {data.top_prompts.map((row) => (
                  <tr
                    key={row.prompt_id ?? row.prompt_text}
                    className="border-t border-themed-subtle"
                  >
                    <td className="py-2 pl-5 pr-3 text-themed-primary truncate max-w-md">
                      {row.prompt_text}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                      {row.mention_count}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                      {row.avg_position_rank != null
                        ? `#${row.avg_position_rank.toFixed(1)}`
                        : '—'}
                    </td>
                    <td className="py-2 px-3 text-right tabular-nums text-themed-secondary">
                      {row.avg_sentiment_score != null
                        ? row.avg_sentiment_score.toFixed(2)
                        : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Same-group shared domains */}
      {data.same_group_shared_domains && data.same_group_shared_domains.length > 0 && (
        <Card className="p-5" onClick={undefined} style={{}}>
          <h3 className="text-sm font-semibold text-themed-primary mb-1">
            同集团共享域名
          </h3>
          <p className="text-xs text-themed-muted mb-3">
            来自 brand_group_shared_domains (Phase A.6)
          </p>
          <ul className="space-y-2">
            {data.same_group_shared_domains.map((row) => (
              <li
                key={row.domain}
                className="flex items-center justify-between text-sm border-b border-themed-subtle pb-2"
              >
                <span className="text-themed-primary">{row.domain}</span>
                <span className="text-themed-muted text-xs">
                  跨 {row.brand_count} 品牌 · {row.total_mentions} 提及
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {data.state === 'partial' && (
        <p className="text-[11px] text-themed-muted">
          ⚠️ 数据状态: partial — 后端聚合还未跑齐, 部分图表可能滞后.
        </p>
      )}
    </div>
  )
}

function KpiCard({ kpi, locale }: { kpi: KpiCardT; locale: string }) {
  const label = locale === 'zh-CN' ? kpi.label_zh : kpi.label_en
  const direction = kpi.direction ?? 'flat'
  return (
    <Card className="p-4" onClick={undefined} style={{}}>
      <p className="text-[11px] text-themed-muted uppercase tracking-wider">
        {label}
      </p>
      <p className="mt-1 text-2xl font-bold tabular-nums text-themed-primary">
        {kpi.value.toLocaleString(undefined, { maximumFractionDigits: 1 })}
        {kpi.unit ? <span className="text-sm font-normal ml-0.5">{kpi.unit}</span> : null}
      </p>
      {kpi.delta_30d_pct != null && (
        <p
          className="mt-1 text-xs tabular-nums"
          style={{ color: DIRECTION_COLOR[direction] }}
        >
          {DIRECTION_ICON[direction]} {kpi.delta_30d_pct.toFixed(1)}% (30d)
        </p>
      )}
    </Card>
  )
}

function TrendCard({
  title,
  points,
  color,
  formatDate,
  unit,
  asArea,
}: {
  title: string
  points: TrendPoint[]
  color: string
  formatDate: (d: string | number | Date, opts?: Intl.DateTimeFormatOptions) => string
  unit?: string
  asArea?: boolean
}) {
  if (!points || points.length === 0) {
    return (
      <Card className="p-4" onClick={undefined} style={{}}>
        <h4 className="text-sm font-semibold text-themed-primary mb-2">{title}</h4>
        <p className="text-xs text-themed-muted">数据采集中…</p>
      </Card>
    )
  }
  const data = points.map((p) => ({
    date: p.date,
    value: p.value,
  }))
  return (
    <Card className="p-4" onClick={undefined} style={{}}>
      <h4 className="text-sm font-semibold text-themed-primary mb-2">{title}</h4>
      <ResponsiveContainer width="100%" height={150}>
        {asArea ? (
          <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10 }}
              tickFormatter={(d) =>
                formatDate(d, { month: 'short', day: 'numeric' })
              }
            />
            <YAxis tick={{ fontSize: 10 }} unit={unit} />
            <Tooltip
              labelFormatter={(d) =>
                formatDate(d, { year: 'numeric', month: 'short', day: 'numeric' })
              }
            />
            <Area
              type="monotone"
              dataKey="value"
              stroke={color}
              fill={color}
              fillOpacity={0.15}
            />
          </AreaChart>
        ) : (
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="var(--color-chart-line-grid)" strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10 }}
              tickFormatter={(d) =>
                formatDate(d, { month: 'short', day: 'numeric' })
              }
            />
            <YAxis tick={{ fontSize: 10 }} unit={unit} />
            <Tooltip
              labelFormatter={(d) =>
                formatDate(d, { year: 'numeric', month: 'short', day: 'numeric' })
              }
            />
            <Line type="monotone" dataKey="value" stroke={color} strokeWidth={2} dot={false} />
          </LineChart>
        )}
      </ResponsiveContainer>
    </Card>
  )
}
