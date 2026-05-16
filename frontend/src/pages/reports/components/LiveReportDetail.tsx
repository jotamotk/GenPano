/**
 * LiveReportDetail — render a backend report payload as a section list.
 *
 * Closes audit #1044 F4-3: the existing ReportDetail.tsx is hard-coded
 * to the mock `ReportData` shape and crashes on real backend payloads.
 * This component is the deterministic counterpart — it reads
 * `ReportDetailOut.payload` (per backend `app/reports/builder.py`) and
 * renders sections faithfully without inventing fields. Mock-only fields
 * (engines / topProduct / newCompetitor / etc.) are not shown.
 *
 * Coverage:
 *   - SECTION_MATRIX-driven payloads (weekly / monthly / on_demand) —
 *     full coverage: title, summary, metrics dict, tables list
 *   - lead_diagnostic payloads — minimum bar; renders layer titles + a
 *     count and links back via the download buttons. Full rich-layer
 *     rendering remains the responsibility of LeadDiagnosticView once
 *     that is migrated to consume backend-supplied linked_diagnostics
 *     (tracked as the F4-4 follow-up).
 *
 * Download / share buttons reuse the same patterns from
 * ReportsLiveBanner.tsx for a single behavior surface.
 */
import { useState } from 'react'
import { Badge, Button, Card } from '../../../components/ui'
import { reportsApi } from '../../../api/reports'
import { useReport } from '../../../hooks/useReports'

interface LiveReportDetailProps {
  projectId: string
  reportId: string
  onBack: () => void
}

interface SectionPayload {
  section_type: string
  title?: string
  summary?: string
  metrics?: Record<string, unknown>
  tables?: Array<{ name?: string; rows?: Array<Record<string, unknown>> }>
  charts?: Array<Record<string, unknown>>
  variant?: string
}

interface ReportPayload {
  report_type?: string
  locale?: string
  reader_perspective?: string
  period?: { from?: string; to?: string }
  brand_ids?: number[]
  sections?: SectionPayload[]
  // lead_diagnostic shape (different schema)
  layers?: Record<string, unknown>
}

export function LiveReportDetail({
  projectId,
  reportId,
  onBack,
}: LiveReportDetailProps) {
  const { data, isLoading, isError, error } = useReport(projectId, reportId)
  const [shareState, setShareState] = useState<
    'idle' | 'pending' | 'copied' | 'error'
  >('idle')

  const handleShare = async () => {
    setShareState('pending')
    try {
      const res = await reportsApi.share(projectId, reportId, 72)
      const fullUrl = `${window.location.origin}${res.url}`
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(fullUrl)
      }
      setShareState('copied')
      window.setTimeout(() => setShareState('idle'), 2500)
    } catch {
      setShareState('error')
    }
  }

  if (isLoading) {
    return (
      <DetailShell onBack={onBack}>
        <Card>
          <div className="text-center py-8 text-themed-muted text-sm">
            加载报告内容…
          </div>
        </Card>
      </DetailShell>
    )
  }

  if (isError || !data) {
    return (
      <DetailShell onBack={onBack}>
        <Card>
          <div className="text-center py-8 text-themed-muted text-sm">
            报告加载失败:{error instanceof Error ? error.message : '未知错误'}
          </div>
        </Card>
      </DetailShell>
    )
  }

  const payload = (data.payload ?? {}) as ReportPayload
  const period = payload.period ?? {}
  const sections = payload.sections ?? []

  return (
    <DetailShell onBack={onBack}>
      <Card className="p-5">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="default">LIVE</Badge>
            <Badge variant="purple" size="sm">
              {payload.report_type ?? data.type ?? 'report'}
            </Badge>
            {payload.locale && (
              <Badge variant="default" size="sm">
                {payload.locale}
              </Badge>
            )}
            <span className="text-sm text-themed-muted">
              {period.from} → {period.to}
            </span>
          </div>
          <div className="flex gap-2 flex-wrap">
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                window.open(
                  reportsApi.downloadUrl(projectId, reportId, 'markdown'),
                  '_blank',
                )
              }
            >
              Markdown
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                window.open(
                  reportsApi.downloadUrl(projectId, reportId, 'json'),
                  '_blank',
                )
              }
            >
              JSON
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() =>
                window.open(
                  reportsApi.downloadUrl(projectId, reportId, 'csv'),
                  '_blank',
                )
              }
            >
              CSV
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleShare}
              disabled={shareState === 'pending'}
            >
              {shareState === 'pending'
                ? '生成中…'
                : shareState === 'copied'
                ? '链接已复制'
                : shareState === 'error'
                ? '失败'
                : '分享'}
            </Button>
          </div>
        </div>
        <div className="mt-3 text-[11px] text-themed-muted">
          Report ID: <span className="font-mono">{data.id}</span> · Status:{' '}
          {data.status}
          {data.finished_at && ` · 完成于 ${data.finished_at}`}
        </div>
      </Card>

      {sections.length === 0 ? (
        <Card>
          <div className="text-center py-8 text-themed-muted text-sm">
            报告 payload 中无 sections — 这通常说明 report_type 走的是 lead_diagnostic
            4 层结构,或后端生成过程中出错。请检查 download → JSON 内容。
          </div>
        </Card>
      ) : (
        sections.map((sec) => (
          <SectionCard key={sec.section_type} section={sec} />
        ))
      )}
    </DetailShell>
  )
}

function DetailShell({
  onBack,
  children,
}: {
  onBack: () => void
  children: React.ReactNode
}) {
  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={onBack}
        className="text-sm text-themed-accent hover:opacity-80"
      >
        ← 返回报告列表
      </button>
      {children}
    </div>
  )
}

function SectionCard({ section }: { section: SectionPayload }) {
  const metrics = section.metrics ?? {}
  const metricEntries = Object.entries(metrics).filter(
    ([, v]) => v !== null && v !== undefined,
  )
  const tables = section.tables ?? []

  return (
    <Card className="p-5">
      <div className="flex items-baseline justify-between gap-3 flex-wrap mb-2">
        <h3 className="text-heading-3 text-themed-primary">
          {section.title ?? section.section_type}
        </h3>
        <span className="text-[11px] text-themed-muted font-mono">
          {section.section_type}
          {section.variant && ` · ${section.variant}`}
        </span>
      </div>
      {section.summary && (
        <p className="text-sm text-themed-body leading-relaxed">
          {section.summary}
        </p>
      )}

      {metricEntries.length > 0 && (
        <div className="mt-3 grid grid-cols-2 md:grid-cols-3 gap-2">
          {metricEntries.map(([key, value]) => (
            <MetricCell key={key} label={key} value={value} />
          ))}
        </div>
      )}

      {tables.map((table, ti) => {
        const rows = table.rows ?? []
        if (rows.length === 0) return null
        const columns = Object.keys(rows[0])
        return (
          <div key={ti} className="mt-3 overflow-x-auto">
            <p className="text-[11px] text-themed-muted mb-1.5 font-mono">
              {table.name ?? `table_${ti}`}
            </p>
            <table className="text-xs w-full border-collapse">
              <thead>
                <tr className="text-themed-muted">
                  {columns.map((c) => (
                    <th
                      key={c}
                      className="text-left font-medium px-2 py-1 border-b border-themed-card"
                    >
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, ri) => (
                  <tr key={ri}>
                    {columns.map((c) => (
                      <td
                        key={c}
                        className="px-2 py-1 border-b border-themed-card tabular-nums text-themed-body"
                      >
                        {renderCell(row[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      })}
    </Card>
  )
}

function MetricCell({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="bg-themed-subtle rounded-card p-2.5">
      <p className="text-[10px] uppercase tracking-wider text-themed-muted">
        {label}
      </p>
      <p className="text-sm text-themed-primary break-words">
        {renderCell(value)}
      </p>
    </div>
  )
}

function renderCell(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'number') {
    return Number.isInteger(value) ? value.toString() : value.toFixed(2)
  }
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'string') return value
  // Objects / arrays — render compact JSON for visibility
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}
