/**
 * BrandDetailLiveBanner — surfaces live primary brand data on the
 * single-brand deep view (/brands/:id) and on the dashboard.
 *
 * Returns null when no live project is active, so mock sessions are
 * unaffected. When live, shows pano / mention rate / SoV / sentiment
 * for the project's primary brand pulled from
 * GET /v1/projects/:id/metrics.
 */
import { Badge, Card, MetricLabel } from '../ui'
import { useProjects } from '../../hooks/useProjects'
import { useBrandMetrics } from '../../hooks/useBrandMetrics'
import { isLiveProjectId } from '../../hooks/useBrandOverview'

function lastValue(points: { value: number }[] | undefined): number | null {
  if (!points || points.length === 0) return null
  return points[points.length - 1].value
}

export default function BrandDetailLiveBanner() {
  const { data: projects } = useProjects()
  const liveProjectId = projects && projects.length > 0 ? projects[0].id : null
  const { data, isLoading, error } = useBrandMetrics(
    isLiveProjectId(liveProjectId) ? liveProjectId : null,
    ['mention_rate', 'sov', 'rank', 'sentiment'],
  )

  if (!isLiveProjectId(liveProjectId)) return null

  const mentionRate = lastValue(
    data?.series.find((s) => s.metric === 'mention_rate')?.points,
  )
  const sov = lastValue(data?.series.find((s) => s.metric === 'sov')?.points)
  const rank = lastValue(data?.series.find((s) => s.metric === 'rank')?.points)
  const sentiment = lastValue(
    data?.series.find((s) => s.metric === 'sentiment')?.points,
  )

  return (
    <Card
      className="p-4"
      style={{ background: 'var(--color-accent-bg-light)' }}
      onClick={undefined}
    >
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <Badge variant="default">LIVE</Badge>
          <span className="text-sm font-medium text-themed-primary">
            {data?.brand_id ? `主品牌 #${data.brand_id}` : '主品牌'} · 实时指标
          </span>
          <span className="text-[11px] text-themed-muted">
            (来自 GET /v1/projects/:id/metrics)
          </span>
          {isLoading && (
            <span className="text-[11px] text-themed-muted">加载中…</span>
          )}
          {error && (
            <span className="text-[11px] text-themed-muted">
              {error instanceof Error ? error.message : 'fetch failed'}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 flex-wrap">
          <KpiCell
            label="提及率"
            helpText="基于品类通用问题计算，排除直接询问品牌的问题（non-brand 口径）。"
            value={mentionRate != null ? `${(mentionRate * 100).toFixed(1)}%` : '—'}
          />
          <KpiCell
            label="SoV"
            helpText="已提到任一品牌的回答中，该品牌占有的声量份额。"
            value={sov != null ? `${(sov * 100).toFixed(1)}%` : '—'}
          />
          <KpiCell
            label="排名"
            helpText="该品牌在当前对比集合中的平均排名，数值越小越靠前。"
            value={rank != null ? `#${rank.toFixed(1)}` : '—'}
          />
          <KpiCell
            label="情感"
            helpText="品牌相关回答的情感加权平均，范围通常为 [-1, 1]。"
            value={sentiment != null ? sentiment.toFixed(2) : '—'}
          />
        </div>
      </div>
    </Card>
  )
}

function KpiCell({
  label,
  value,
  helpText,
}: {
  label: string
  value: string
  helpText?: string
}) {
  return (
    <div className="text-right">
      <p className="text-[10px] uppercase tracking-wider text-themed-muted">
        <MetricLabel helpText={helpText} className="justify-end">
          {label}
        </MetricLabel>
      </p>
      <p className="text-sm font-semibold tabular-nums text-themed-primary">
        {value}
      </p>
    </div>
  )
}
