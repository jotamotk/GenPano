import { Card } from '../ui'
import TrendChart from '../charts/TrendChart'
import DonutChart from '../charts/DonutChart'
import HorizontalBar from '../charts/HorizontalBar'
import { useQueryAnalytics } from '../../hooks/useQueryAnalytics'
import { ProjectAnalysisParams } from '../../lib/projectAnalysisFilters'
import {
  toEngineBars,
  toKpis,
  toPositionBars,
  toSentimentDonut,
  toTopicBars,
  toTrendSeries,
} from '../../adapters/queryAnalyticsAdapter'

interface QueryActivityCardProps {
  projectId: string | null | undefined
  brandName?: string
  filters?: ProjectAnalysisParams
}

const TREND_LINES = [
  { key: 'mentionRate', label: 'Mention rate', color: 'var(--color-chart-2)' },
  { key: 'sentiment', label: 'Sentiment', color: 'var(--color-chart-6)' },
  { key: 'geoScore', label: 'GEO', color: 'var(--color-chart-3)' },
]

function fmtPct(v: number | null): string {
  return v == null ? '-' : `${(v * 100).toFixed(1)}%`
}

function fmtScore(v: number | null): string {
  return v == null ? '-' : v.toFixed(2)
}

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-card-lg bg-surface border border-b-card p-4 flex-1">
      <div className="text-[11px] text-ink-muted">{label}</div>
      <div className="text-[22px] font-bold text-ink tabular-nums mt-1">{value}</div>
      {hint && <div className="text-[10px] text-ink-faint mt-0.5">{hint}</div>}
    </div>
  )
}

export default function QueryActivityCard({
  projectId,
  brandName,
  filters = {},
}: QueryActivityCardProps) {
  const { data, isLoading, isError, error } = useQueryAnalytics({
    projectId,
    dateFrom: filters.from,
    dateTo: filters.to,
    engine: filters.engine,
    segmentId: filters.segment_id,
    profileId: filters.profile_id,
  })

  if (!projectId) {
    return (
      <Card className="p-6 text-center text-[12px] text-ink-muted">
        Select a live project to view query activity.
      </Card>
    )
  }

  if (isLoading) {
    return (
      <Card className="p-6 text-center text-[12px] text-ink-muted">
        Loading query activity...
      </Card>
    )
  }

  if (isError) {
    return (
      <Card className="p-6 text-center text-[12px] text-danger">
        Failed to load query activity: {(error as Error)?.message || 'unknown error'}
      </Card>
    )
  }

  const kpis = toKpis(data)
  const trend = toTrendSeries(data?.daily_trend)
  const sentimentSlices = toSentimentDonut(data?.sentiment_distribution)
  const topicBars = toTopicBars(data?.by_topic)
  const engineBars = toEngineBars(data?.by_engine)
  const positionBars = toPositionBars(data?.position_distribution)
  const sentimentTotal = sentimentSlices.reduce((acc, s) => acc + s.value, 0)
  const headlineSuffix = brandName ? ` - ${brandName}` : ''

  return (
    <div className="space-y-3">
      <div className="flex items-end justify-between">
        <div>
          <h3 className="text-[14px] font-semibold text-ink">
            Query activity{headlineSuffix}
          </h3>
          <div className="text-[11px] text-ink-muted">
            Project-scoped LLM response analytics ({data?.filters?.date_from} to{' '}
            {data?.filters?.date_to})
          </div>
        </div>
        <div className="text-[11px] text-ink-faint tabular-nums">
          Responses {data?.totals?.responses ?? 0} - Analyzed {data?.totals?.analyzed ?? 0}
        </div>
      </div>

      <div className="flex gap-3">
        <Kpi label="Queries" value={kpis.totalQueries.toLocaleString()} />
        <Kpi
          label="Mention rate"
          value={fmtPct(kpis.mentionRate)}
          hint={`${data?.totals?.mentions_target ?? 0} / ${data?.totals?.responses ?? 0}`}
        />
        <Kpi label="Avg sentiment" value={fmtScore(kpis.avgSentiment)} />
        <Kpi label="Avg GEO" value={fmtScore(kpis.avgGeoScore)} />
      </div>

      <Card className="p-4">
        <div className="text-[12px] font-semibold text-ink mb-2">Daily trend</div>
        {trend.length > 0 ? (
          <TrendChart data={trend} lines={TREND_LINES} height={220} />
        ) : (
          <div className="text-center text-[11px] text-ink-muted py-12">No data</div>
        )}
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Card className="p-4">
          <div className="text-[12px] font-semibold text-ink mb-2">Sentiment</div>
          {sentimentTotal > 0 ? (
            <div className="flex items-center gap-4">
              <DonutChart segments={sentimentSlices} size={160} />
              <div className="flex-1 space-y-1.5 text-[12px]">
                {sentimentSlices.map((s) => (
                  <div key={s.name} className="flex items-center justify-between">
                    <span className="flex items-center gap-2">
                      <span
                        className="inline-block w-2.5 h-2.5 rounded-full"
                        style={{ background: s.color }}
                      />
                      {s.name}
                    </span>
                    <span className="tabular-nums text-ink-muted">
                      {s.value} ({Math.round((s.value / sentimentTotal) * 100)}%)
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="text-center text-[11px] text-ink-muted py-12">No data</div>
          )}
        </Card>

        <Card className="p-4">
          <div className="text-[12px] font-semibold text-ink mb-2">Top topics</div>
          {topicBars.length > 0 ? (
            <HorizontalBar data={topicBars} valueSuffix="%" />
          ) : (
            <div className="text-center text-[11px] text-ink-muted py-12">No data</div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Card className="p-4">
          <div className="text-[12px] font-semibold text-ink mb-2">Engine coverage</div>
          {engineBars.length > 0 ? (
            <HorizontalBar data={engineBars} valueSuffix="%" />
          ) : (
            <div className="text-center text-[11px] text-ink-muted py-12">No data</div>
          )}
        </Card>

        <Card className="p-4">
          <div className="text-[12px] font-semibold text-ink mb-2">Rank distribution</div>
          {positionBars.some((b) => b.value > 0) ? (
            <HorizontalBar
              data={positionBars}
              valueSuffix=""
              defaultColor="var(--color-chart-3)"
            />
          ) : (
            <div className="text-center text-[11px] text-ink-muted py-12">No data</div>
          )}
        </Card>
      </div>
    </div>
  )
}
