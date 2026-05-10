/**
 * BrandsListLiveBanner — surfaces real backend brand metrics on the
 * BrandsPage list table.
 *
 * When a live project is active, renders a strip above the mock table
 * with the project's primary brand + each pinned competitor (from
 * GET /v1/projects/:id/competitors/metrics), each row showing the
 * authoritative GEO score / SoV / sentiment / co-mention count for
 * the current 30-day window. Returns null otherwise.
 */
import { Badge, Card, MetricLabel } from '../ui'
import { useProjects } from '../../hooks/useProjects'
import { useCompetitorMetrics } from '../../hooks/useBrandMetrics'
import { isLiveProjectId } from '../../hooks/useBrandOverview'

export default function BrandsListLiveBanner() {
  const { data: projects } = useProjects()
  const liveProjectId = projects && projects.length > 0 ? projects[0].id : null
  const { data, isLoading, error } = useCompetitorMetrics(
    isLiveProjectId(liveProjectId) ? liveProjectId : null,
  )

  if (!isLiveProjectId(liveProjectId)) return null

  const primary = data?.primary ?? null
  const competitors = data?.competitors ?? []
  const hasRows = primary != null || competitors.length > 0

  return (
    <Card
      className="p-4"
      style={{ background: 'var(--color-accent-bg-light)' }}
      onClick={undefined}
    >
      <div className="flex items-center justify-between gap-3 flex-wrap mb-3">
        <div className="flex items-center gap-2">
          <Badge variant="default">LIVE</Badge>
          <span className="text-sm font-medium text-themed-primary">
            真实品牌矩阵
          </span>
          <span className="text-[11px] text-themed-muted">
            (来自 GET /v1/projects/:id/competitors/metrics · 30 天窗口)
          </span>
        </div>
        {isLoading && (
          <span className="text-[11px] text-themed-muted">加载中…</span>
        )}
        {error && (
          <span className="text-[11px] text-themed-muted">
            {error instanceof Error ? error.message : 'fetch failed'}
          </span>
        )}
      </div>

      {!isLoading && !hasRows && (
        <p className="text-[11px] text-themed-muted">
          还没有真实品牌数据 — 完成 onboarding + 等首批采集即可。
        </p>
      )}

      {hasRows && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-wider text-themed-muted">
                <th className="py-1.5 pr-3">品牌</th>
                <th className="py-1.5 pr-3 text-right">
                  <MetricLabel
                    helpText="品牌在当前 30 天窗口内的综合 AI 可见度得分。"
                    className="justify-end"
                  >
                    GEO 分
                  </MetricLabel>
                </th>
                <th className="py-1.5 pr-3 text-right">
                  <MetricLabel
                    helpText="基于品类通用问题计算，排除直接询问品牌的问题（non-brand 口径）。"
                    className="justify-end"
                  >
                    提及率
                  </MetricLabel>
                </th>
                <th className="py-1.5 pr-3 text-right">
                  <MetricLabel
                    helpText="已提到任一品牌的回答中，该品牌占有的声量份额。"
                    className="justify-end"
                  >
                    SoV
                  </MetricLabel>
                </th>
                <th className="py-1.5 pr-3 text-right">
                  <MetricLabel
                    helpText="品牌相关回答的情感加权平均，范围通常为 [-1, 1]。"
                    className="justify-end"
                  >
                    情感
                  </MetricLabel>
                </th>
                <th className="py-1.5 pr-3 text-right">
                  <MetricLabel
                    helpText="主品牌与该竞品在同一回答中共同出现的次数。"
                    className="justify-end"
                  >
                    共现次数
                  </MetricLabel>
                </th>
                <th className="py-1.5 pr-3 text-right">
                  <MetricLabel
                    helpText="当前 30 天窗口相对上一周期的变化百分比。"
                    className="justify-end"
                  >
                    30d Δ%
                  </MetricLabel>
                </th>
              </tr>
            </thead>
            <tbody>
              {primary && (
                <Row
                  brandId={primary.brand_id}
                  brandName={primary.brand_name}
                  isPrimary
                  geo={primary.avg_geo_score}
                  mention={primary.avg_mention_rate}
                  sov={primary.avg_sov}
                  sentiment={primary.avg_sentiment}
                  coMention={primary.co_mention_count}
                  delta={primary.delta_30d_pct}
                />
              )}
              {competitors.map((c) => (
                <Row
                  key={c.brand_id}
                  brandId={c.brand_id}
                  brandName={c.brand_name}
                  geo={c.avg_geo_score}
                  mention={c.avg_mention_rate}
                  sov={c.avg_sov}
                  sentiment={c.avg_sentiment}
                  coMention={c.co_mention_count}
                  delta={c.delta_30d_pct}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

interface RowProps {
  brandId: number
  brandName: string | null
  isPrimary?: boolean
  geo: number | null
  mention: number | null
  sov: number | null
  sentiment: number | null
  coMention: number
  delta: number | null
}

function Row({
  brandId,
  brandName,
  isPrimary,
  geo,
  mention,
  sov,
  sentiment,
  coMention,
  delta,
}: RowProps) {
  const deltaText = delta != null ? `${delta >= 0 ? '+' : ''}${delta.toFixed(1)}%` : '—'
  const deltaTone =
    delta == null
      ? 'text-themed-muted'
      : delta > 0
      ? 'text-themed-success'
      : delta < 0
      ? 'text-themed-danger'
      : 'text-themed-muted'
  return (
    <tr className="border-t border-themed-subtle">
      <td className="py-2 pr-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-themed-primary">
            {brandName ?? `Brand #${brandId}`}
          </span>
          <span className="text-[11px] text-themed-muted">#{brandId}</span>
          {isPrimary && (
            <Badge variant="accent" size="sm">
              主品牌
            </Badge>
          )}
        </div>
      </td>
      <td className="py-2 pr-3 text-right tabular-nums text-themed-primary">
        {geo != null ? geo.toFixed(1) : '—'}
      </td>
      <td className="py-2 pr-3 text-right tabular-nums text-themed-secondary">
        {mention != null ? `${(mention * 100).toFixed(1)}%` : '—'}
      </td>
      <td className="py-2 pr-3 text-right tabular-nums text-themed-secondary">
        {sov != null ? `${(sov * 100).toFixed(1)}%` : '—'}
      </td>
      <td className="py-2 pr-3 text-right tabular-nums text-themed-secondary">
        {sentiment != null ? sentiment.toFixed(2) : '—'}
      </td>
      <td className="py-2 pr-3 text-right tabular-nums text-themed-secondary">
        {coMention}
      </td>
      <td className={`py-2 pr-3 text-right tabular-nums ${deltaTone}`}>
        {deltaText}
      </td>
    </tr>
  )
}
