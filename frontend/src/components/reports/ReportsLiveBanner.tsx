/**
 * ReportsLiveBanner — surfaces the user's real generated reports
 * (from POST /v1/projects/:id/reports) as a strip above the mock catalog.
 *
 * Design: same LIVE banner pattern used elsewhere — non-invasive, returns
 * null when there's no live project so mock-only sessions are unaffected.
 */
import { Badge, Button, Card } from '../ui'
import { useLocale } from '../../contexts/LocaleContext'
import { useProjects } from '../../hooks/useProjects'
import { isLiveProjectId, useReports } from '../../hooks/useReports'
import { reportsApi } from '../../api/reports'

export default function ReportsLiveBanner() {
  const { formatDate } = useLocale()
  const { data: projects } = useProjects()
  const liveProjectId = projects && projects.length > 0 ? projects[0].id : null

  if (!isLiveProjectId(liveProjectId)) return null

  return <ReportsLiveBannerInner projectId={liveProjectId as string} formatDate={formatDate} />
}

function ReportsLiveBannerInner({
  projectId,
  formatDate,
}: {
  projectId: string
  formatDate: (
    d: string | number | Date,
    opts?: Intl.DateTimeFormatOptions,
  ) => string
}) {
  const { data, isLoading, error } = useReports(projectId, 5)
  const items = data?.items ?? []

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
            最近生成的真实报告
          </span>
          <span className="text-[11px] text-themed-muted">
            (来自 POST /v1/projects/:id/reports · Phase RP)
          </span>
        </div>
        {isLoading && <span className="text-[11px] text-themed-muted">加载中…</span>}
        {error && (
          <span className="text-[11px] text-themed-muted">
            {error instanceof Error ? error.message : 'fetch failed'}
          </span>
        )}
      </div>

      {!isLoading && items.length === 0 && (
        <p className="text-[11px] text-themed-muted">
          还没有真实报告。点击右上角"生成新报告"创建第一份。
        </p>
      )}

      {items.length > 0 && (
        <ul className="space-y-2">
          {items.map((r) => (
            <li
              key={r.id}
              className="flex items-center justify-between gap-3 flex-wrap"
            >
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant="default" size="sm">
                  {r.type}
                </Badge>
                <span className="text-xs text-themed-body">{r.id.slice(0, 8)}</span>
                <span className="text-themed-faint">·</span>
                <span className="text-[11px] text-themed-muted">
                  {formatDate(r.created_at, {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
                <Badge
                  variant={
                    r.status === 'done'
                      ? 'green'
                      : r.status === 'failed'
                      ? 'red'
                      : 'default'
                  }
                  size="sm"
                >
                  {r.status}
                </Badge>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    window.open(
                      reportsApi.downloadUrl(projectId, r.id, 'markdown'),
                      '_blank',
                    )
                  }}
                  style={{}}
                >
                  Markdown
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    window.open(
                      reportsApi.downloadUrl(projectId, r.id, 'json'),
                      '_blank',
                    )
                  }}
                  style={{}}
                >
                  JSON
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    window.open(
                      reportsApi.downloadUrl(projectId, r.id, 'csv'),
                      '_blank',
                    )
                  }}
                  style={{}}
                >
                  CSV
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}
