/**
 * BrandSubpageLiveBanner — generic LIVE strip for brand sub-pages
 * (visibility / sentiment / citations / etc.).
 *
 * Renders a 4-card live KPI strip when the user has a real backend
 * project. Each variant pulls a different endpoint and produces 4
 * `{label, value, unit}` cards. When no live project, returns null
 * (no visual regression for mock-only users).
 */

import { useProjects } from '../../hooks/useProjects'
import {
  useBrandMetrics,
  useBrandSentiment,
  useBrandCitations,
} from '../../hooks/useBrandMetrics'
import { isLiveProjectId } from '../../hooks/useBrandOverview'

type Variant = 'visibility' | 'sentiment' | 'citations'

interface Card {
  label: string
  value: string | number
  unit?: string
}

function avg(arr: number[]): number {
  if (!arr.length) return 0
  return arr.reduce((a, b) => a + b, 0) / arr.length
}

function pickProjectId(): string | null {
  // Resolve a single live project to overlay. Mirrors
  // BrandOverviewLiveBanner behaviour.
  return null
}

export default function BrandSubpageLiveBanner({ variant }: { variant: Variant }) {
  const { data: liveProjects } = useProjects()
  const liveProjectId =
    liveProjects && liveProjects.length > 0 ? liveProjects[0].id : null

  // Conditionally fire the right hook for this variant. Each hook is
  // already gated by isLiveProjectId so mock-only users don't 404.
  const metrics = useBrandMetrics(variant === 'visibility' ? liveProjectId : null)
  const sentiment = useBrandSentiment(
    variant === 'sentiment' ? liveProjectId : null,
  )
  const citations = useBrandCitations(
    variant === 'citations' ? liveProjectId : null,
  )

  if (!isLiveProjectId(liveProjectId)) return null

  let title = ''
  let endpointLabel = ''
  let cards: Card[] = []
  let isLoading = false
  let isEmpty = false

  if (variant === 'visibility') {
    isLoading = metrics.isLoading
    if (!metrics.data) return null
    const m = metrics.data
    isEmpty = m.state === 'empty'
    title = `品牌可见度 — ${m.brand_id ? `品牌 ${m.brand_id}` : '主品牌'}`
    endpointLabel = `/v1/projects/${m.project_id.slice(0, 8)}…/metrics`
    const series = (key: string) =>
      m.series.find((s) => s.metric === key)?.points.map((p) => p.value) ?? []
    cards = [
      {
        label: '提及率 30d',
        value: (avg(series('mention_rate')) * 100).toFixed(2),
        unit: '%',
      },
      {
        label: 'SoV 30d',
        value: (avg(series('sov')) * 100).toFixed(2),
        unit: '%',
      },
      {
        label: '平均排名 30d',
        value: avg(series('rank')).toFixed(1),
      },
      {
        label: '情感分 30d',
        value: avg(series('sentiment')).toFixed(2),
      },
    ]
  } else if (variant === 'sentiment') {
    isLoading = sentiment.isLoading
    if (!sentiment.data) return null
    const s = sentiment.data
    isEmpty = s.state === 'empty'
    title = `品牌情感 — ${s.brand_id ? `品牌 ${s.brand_id}` : '主品牌'}`
    endpointLabel = `/v1/projects/${s.project_id.slice(0, 8)}…/sentiment`
    cards = [
      {
        label: '正面占比',
        value: s.distribution.positive_pct.toFixed(1),
        unit: '%',
      },
      {
        label: '负面占比',
        value: s.distribution.negative_pct.toFixed(1),
        unit: '%',
      },
      {
        label: '中性占比',
        value: s.distribution.neutral_pct.toFixed(1),
        unit: '%',
      },
      {
        label: '平均情感分',
        value: s.distribution.avg_sentiment_score.toFixed(2),
      },
    ]
  } else if (variant === 'citations') {
    isLoading = citations.isLoading
    if (!citations.data) return null
    const c = citations.data
    isEmpty = c.state === 'empty'
    title = `品牌引用 — ${c.brand_id ? `品牌 ${c.brand_id}` : '主品牌'}`
    endpointLabel = `/v1/projects/${c.project_id.slice(0, 8)}…/citations`
    const topDomain = c.by_domain_top[0]
    cards = [
      { label: '引用总数', value: c.total },
      { label: '独立域名数', value: c.by_domain_top.length },
      {
        label: 'Top 域名',
        value: topDomain ? topDomain.domain : '—',
      },
      {
        label: 'Top 域名占比',
        value:
          topDomain && c.total > 0
            ? ((topDomain.count / c.total) * 100).toFixed(1)
            : '0',
        unit: topDomain ? '%' : undefined,
      },
    ]
  }

  if (isLoading) return null

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
          <span className="text-sm font-semibold text-themed-primary">{title}</span>
        </div>
        <span className="text-[10px] uppercase font-bold tracking-wider text-themed-muted">
          {endpointLabel}
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {cards.map((card, i) => (
          <div
            key={i}
            className="rounded-card p-3"
            style={{ background: 'var(--color-bg-card, #fff)' }}
          >
            <div className="text-[11px] uppercase tracking-wider text-themed-muted mb-1">
              {card.label}
            </div>
            <div className="flex items-baseline gap-1">
              <span className="text-xl font-bold tabular-nums text-themed-primary">
                {card.value}
              </span>
              {card.unit && (
                <span className="text-xs text-themed-muted">{card.unit}</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {isEmpty && (
        <p className="text-[11px] text-themed-faint mt-3">
          暂无 30 天聚合数据 — 数据采集 pipeline 跑过后会自动填充。
        </p>
      )}
    </div>
  )
}
