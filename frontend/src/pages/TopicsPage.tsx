import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import {
  BarChart3,
  CalendarRange,
  ChevronRight,
  Download,
  ExternalLink,
  FileText,
  MessageSquare,
  Search,
  SlidersHorizontal,
  X,
} from 'lucide-react'

import { Badge, Button, Card } from '../components/ui'
import BrandAnalysisFilterBar from '../components/filters/BrandAnalysisFilterBar'
import { ProfileGroupSampleWarning } from '../components/filters/ProfileGroupFilter'
import ProjectRequiredBanner from '../components/ProjectRequiredBanner'
import { useProject } from '../contexts/ProjectContext'
import { useBrandAnalysisFilters } from '../hooks/useBrandAnalysisFilters'
import { useProjects } from '../hooks/useProjects'
import {
  usePromptQueries,
  useQueryResponse,
  useTopicMonitoring,
  useTopicPrompts,
} from '../hooks/useTopicAnalysis'
import { resolveLiveProjectId } from '../lib/liveProject'
import {
  ProjectAnalysisParams,
  toProjectAnalysisParams,
} from '../lib/projectAnalysisFilters'

const INTENT_LABELS: Record<string, string> = {
  informational: 'Informational',
  commercial: 'Commercial',
  transactional: 'Transactional',
  navigational: 'Navigational',
}

const INTENT_VARIANTS: Record<string, string> = {
  informational: 'blue',
  commercial: 'green',
  transactional: 'orange',
  navigational: 'purple',
}

const DIMENSION_VARIANTS: Record<string, string> = {
  product: 'purple',
  brand: 'blue',
  category: 'green',
  scenario: 'orange',
}

type LooseRecord = Record<string, any>

function analysisParamsWithBrand(
  filters: any,
  brandIdOverride: number | null,
): ProjectAnalysisParams {
  const params = toProjectAnalysisParams(filters)
  if (brandIdOverride != null) {
    params.brand_id = brandIdOverride
  }
  return params
}

function Breadcrumb({ items, onNavigate }: { items: any[]; onNavigate: (view: string) => void }) {
  return (
    <div className="flex items-center gap-1.5 text-sm mb-5">
      {items.map((item, i) => (
        <span key={`${item.view}-${i}`} className="flex items-center gap-1.5">
          {i > 0 && <ChevronRight size={14} className="text-themed-faint" aria-hidden />}
          {i < items.length - 1 ? (
            <button
              type="button"
              onClick={() => onNavigate(item.view)}
              className="text-themed-muted hover:text-themed-primary transition-colors"
            >
              {item.label}
            </button>
          ) : (
            <span className="font-medium text-themed-primary">{item.label}</span>
          )}
        </span>
      ))}
    </div>
  )
}

function EmptyState({
  title,
  text,
  action,
}: {
  title?: string
  text: string
  action?: ReactNode
}) {
  return (
    <div className="text-center py-12 px-4">
      {title && <div className="text-sm font-semibold text-themed-primary mb-1">{title}</div>}
      <div className="text-[12px] text-themed-muted">{text}</div>
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

function MetadataState({ title, text }: { title: string; text: string }) {
  return (
    <Card className="p-0">
      <EmptyState title={title} text={text} />
    </Card>
  )
}

function StateBadge({ state }: { state?: string }) {
  const normalized = String(state || '').toLowerCase()
  if (!normalized || normalized === 'ok') return null
  const display =
    normalized === 'partial'
      ? { label: 'Limited data', variant: 'orange' }
      : normalized === 'empty'
        ? { label: 'No data yet', variant: 'secondary' }
        : { label: 'Data unavailable', variant: 'secondary' }
  return (
    <Badge variant={display.variant} size="sm">
      {display.label}
    </Badge>
  )
}

function MetricCard({
  label,
  value,
  detail,
  tone = 'primary',
}: {
  label: string
  value: ReactNode
  detail?: ReactNode
  tone?: 'primary' | 'accent' | 'success' | 'warning'
}) {
  const valueClass =
    tone === 'accent'
      ? 'text-themed-accent'
      : tone === 'success'
        ? 'text-themed-success'
        : tone === 'warning'
          ? 'text-themed-warning'
          : 'text-themed-primary'

  return (
    <Card className="p-4 min-h-[108px]">
      <div className="text-xs text-themed-muted mb-1">{label}</div>
      <div className={`text-2xl font-brand font-bold tabular-nums ${valueClass}`}>{value}</div>
      {detail && <div className="text-[11px] text-themed-muted mt-2">{detail}</div>}
    </Card>
  )
}

function asNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null
  const next = Number(value)
  return Number.isFinite(next) ? next : null
}

function formatEvidenceCount(value: unknown) {
  const next = asNumber(value)
  return next == null ? '--' : next.toLocaleString()
}

function formatPercent(value: unknown, digits = 1) {
  const next = asNumber(value)
  if (next == null) return '--'
  const normalized = Math.abs(next) <= 1 ? next * 100 : next
  return `${normalized.toFixed(digits)}%`
}

function formatScore(value: unknown) {
  const next = asNumber(value)
  if (next == null) return '--'
  return Math.abs(next) <= 1 ? (next * 100).toFixed(1) : next.toFixed(1)
}

function formatDateTime(value: unknown) {
  if (!value) return '-'
  const date = new Date(String(value))
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function dayKey(value: unknown) {
  if (!value) return 'No date'
  const text = String(value)
  const date = new Date(text)
  if (Number.isNaN(date.getTime())) return text.slice(0, 10) || 'No date'
  return date.toISOString().slice(0, 10)
}

function latestTimestamp(query: LooseRecord) {
  return query.finished_at || query.executed_at || query.created_at || ''
}

function averageMetric(rows: LooseRecord[], keys: string[]) {
  const values = rows
    .map((row) => keys.map((key) => asNumber(row[key])).find((value) => value != null))
    .filter((value): value is number => value != null)
  if (!values.length) return null
  return values.reduce((sum, value) => sum + value, 0) / values.length
}

function sentimentTotals(rows: LooseRecord[]) {
  return rows.reduce(
    (acc, row) => {
      const sentiment = row.sentiment_distribution || {}
      acc.positive += asNumber(sentiment.positive) || 0
      acc.neutral += asNumber(sentiment.neutral) || 0
      acc.negative += asNumber(sentiment.negative) || 0
      return acc
    },
    { positive: 0, neutral: 0, negative: 0 },
  )
}

function SentimentMix({ value }: { value?: LooseRecord }) {
  const sentiment = value || { positive: 0, neutral: 0, negative: 0 }
  return (
    <div className="flex flex-wrap gap-1.5">
      <span className="text-[11px] px-2 py-1 rounded-pill bg-themed-subtle text-themed-success">
        Positive {formatEvidenceCount(sentiment.positive)}
      </span>
      <span className="text-[11px] px-2 py-1 rounded-pill bg-themed-subtle text-themed-muted">
        Neutral {formatEvidenceCount(sentiment.neutral)}
      </span>
      <span className="text-[11px] px-2 py-1 rounded-pill bg-themed-subtle text-themed-danger">
        Negative {formatEvidenceCount(sentiment.negative)}
      </span>
    </div>
  )
}

function miniMetric(label: string, value: ReactNode) {
  return (
    <div className="min-w-[86px]">
      <div className="text-[11px] text-themed-muted">{label}</div>
      <div className="text-sm font-semibold text-themed-primary tabular-nums mt-0.5">{value}</div>
    </div>
  )
}

function uniqueValues(rows: LooseRecord[], key: string) {
  return Array.from(
    new Set(
      rows
        .map((row) => row[key])
        .filter((value) => value !== null && value !== undefined && value !== '')
        .map((value) => String(value)),
    ),
  )
}

function withCurrentOption(options: string[], current: string) {
  if (!current || current === 'all' || options.includes(current)) return options
  return [current, ...options]
}

function profileLabel(row: LooseRecord | null | undefined) {
  const name = row?.profile_name == null ? '' : String(row.profile_name).trim()
  const id = row?.profile_id == null ? '' : String(row.profile_id).trim()
  return name || id || 'Unknown profile'
}

function visibilityValue(row: LooseRecord | null | undefined) {
  return row?.visibility_rate ?? row?.sov ?? row?.mention_rate
}

function parseIdParam(value: string | null) {
  if (!value || !/^\d+$/.test(value)) return null
  return Number(value)
}

function urlTopic(topicId: number | null) {
  return {
    topic_id: topicId,
    topic_name: topicId == null ? 'Topic' : `Topic ${topicId}`,
    dimension: null,
    associated_brand: null,
    __urlPlaceholder: true,
  }
}

function urlPrompt(promptId: number, topicId: number | null) {
  return {
    prompt_id: promptId,
    topic_id: topicId,
    prompt_text: `Prompt ${promptId}`,
    intent: null,
    language: null,
    __urlPlaceholder: true,
  }
}

function isUrlPlaceholder(value: LooseRecord | null | undefined) {
  return Boolean(value?.__urlPlaceholder)
}

function csvCell(value: unknown) {
  const text = value == null ? '' : String(value)
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}

function csvLine(values: unknown[]) {
  return values.map(csvCell).join(',')
}

function downloadCsv(
  filename: string,
  metadata: Record<string, unknown>,
  rows: Array<Record<string, unknown>>,
) {
  const headers = Array.from(new Set(rows.flatMap((row) => Object.keys(row))))
  const lines = [
    ...Object.entries(metadata).map(([key, value]) => csvLine([key, value])),
    '',
    csvLine(headers),
    ...rows.map((row) => csvLine(headers.map((header) => row[header]))),
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function exportMetadata(
  layer: string,
  filters: any,
  brandIdOverride: number | null,
  extra: Record<string, unknown> = {},
) {
  const params = analysisParamsWithBrand(filters, brandIdOverride)
  return {
    layer,
    success_only: true,
    from: params.from || '',
    to: params.to || '',
    engine: params.engine || '',
    segment_id: params.segment_id || '',
    profile_id: params.profile_id || '',
    brand_id: params.brand_id ?? '',
    ...extra,
  }
}

function topicExportRows(rows: LooseRecord[]) {
  return rows.map((topic) => ({
    topic_id: topic.topic_id,
    topic_name: topic.topic_name,
    dimension: topic.dimension || '',
    associated_brand: topic.associated_brand || '',
    prompt_count: topic.prompt_count ?? 0,
    query_count: topic.query_count ?? 0,
    response_count: topic.response_count ?? 0,
    visibility_rate: topic.visibility_rate ?? topic.sov ?? topic.mention_rate ?? '',
    citation_count: topic.citation_count ?? 0,
    citation_rate: topic.citation_rate ?? '',
    positive: topic.sentiment_distribution?.positive ?? 0,
    neutral: topic.sentiment_distribution?.neutral ?? 0,
    negative: topic.sentiment_distribution?.negative ?? 0,
    last_collected: topic.last_collected || '',
  }))
}

function promptExportRows(rows: LooseRecord[]) {
  return rows.map((prompt) => ({
    prompt_id: prompt.prompt_id,
    topic_id: prompt.topic_id,
    prompt_text: prompt.prompt_text || '',
    intent: prompt.intent || '',
    language: prompt.language || '',
    query_count: prompt.query_count ?? 0,
    response_count: prompt.response_count ?? 0,
    visibility_rate: prompt.visibility_rate ?? prompt.mention_rate ?? '',
    citation_count: prompt.citation_count ?? 0,
    citation_rate: prompt.citation_rate ?? '',
    success_rate: prompt.success_rate ?? '',
    last_collected: prompt.last_collected || '',
  }))
}

function queryExportRows(groups: ReturnType<typeof groupSuccessfulQueries>) {
  return groups.flatMap((group) =>
    group.dailyRows.map(({ date, attempt }) => ({
      query_group_key: group.key,
      query_text: attempt.query_text || group.queryText,
      date,
      query_id: attempt.query_id,
      response_id: attempt.response_id,
      response_created_at: attempt.response_created_at || '',
      response_preview: attempt.response_preview || '',
      target_llm: attempt.target_llm || '',
      profile: profileLabel(attempt),
      target_mentioned: Boolean(attempt.target_mentioned),
      citation_count: attempt.citation_count ?? 0,
      geo_score: attempt.geo_score ?? '',
      sentiment_score: attempt.sentiment_score ?? '',
      finished_at: attempt.finished_at || '',
    })),
  )
}

function ListFilter({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: string
  options: string[]
  onChange: (next: string) => void
}) {
  return (
    <div className="inline-flex items-center gap-1.5">
      <span className="text-xs text-themed-muted shrink-0">{label}</span>
      <div className="inline-flex flex-wrap gap-1.5">
        {['all', ...options].map((option) => {
          const active = value === option
          const text = option === 'all' ? 'All' : INTENT_LABELS[option] || option.toUpperCase()
          return (
            <button
              key={option}
              type="button"
              onClick={() => onChange(option)}
              className="px-2.5 py-1 rounded-pill text-[11px] font-medium transition-colors"
              style={{
                background: active ? 'var(--color-accent-bg-light)' : 'var(--color-bg-card)',
                color: active ? 'var(--color-accent)' : 'var(--color-text-muted)',
                border: `1px solid ${
                  active ? 'var(--color-accent-alpha-27)' : 'var(--color-border-subtle)'
                }`,
              }}
            >
              {text}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function isSevenDayWindow(filters: any) {
  if (!filters?.from || !filters?.to) return true
  const from = new Date(filters.from).getTime()
  const to = new Date(filters.to).getTime()
  if (Number.isNaN(from) || Number.isNaN(to)) return false
  const days = Math.round((to - from) / 86_400_000)
  return days <= 7
}

function TopicsView({
  projectId,
  filters,
  brandIdOverride,
  onSelectTopic,
  onSwitchTo30Days,
}: {
  projectId: string | null
  filters: any
  brandIdOverride: number | null
  onSelectTopic: (topic: any) => void
  onSwitchTo30Days: () => void
}) {
  const [search, setSearch] = useState('')
  const analysisParams = useMemo(
    () => analysisParamsWithBrand(filters, brandIdOverride),
    [brandIdOverride, filters],
  )
  const monitoringQ = useTopicMonitoring(projectId, analysisParams)
  const rows = monitoringQ.data?.topics || []
  const intentRows = monitoringQ.data?.intent_matrix || []

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    return rows.filter((topic) => {
      if (term && !topic.topic_name.toLowerCase().includes(term)) return false
      if (filters.intents?.length) {
        const topicIntents = intentRows
          .filter((row) => row.topic_id === topic.topic_id)
          .map((row) => row.intent)
        if (!filters.intents.some((intent: string) => topicIntents.includes(intent))) {
          return false
        }
      }
      if (filters.dimensions?.length) {
        const dim = topic.dimension || ''
        if (!filters.dimensions.includes(dim)) return false
      }
      return true
    })
  }, [filters.dimensions, filters.intents, intentRows, rows, search])

  const summary = monitoringQ.data?.summary
  const avgVisibility = averageMetric(rows, ['visibility_rate', 'sov', 'mention_rate'])
  const avgCitationCoverage = averageMetric(rows, ['citation_rate'])
  const sentiment = sentimentTotals(rows)
  const isEmpty = !monitoringQ.isLoading && rows.length === 0
  const sevenDayEmpty = isEmpty && isSevenDayWindow(filters)

  return (
    <div className="space-y-5">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-xl font-brand font-bold text-themed-primary">Topics</h2>
          <p className="text-sm text-themed-muted mt-1">
            Topics, prompts, queries, and successful response evidence.
          </p>
        </div>
        <div className="inline-flex items-center gap-2 text-xs text-themed-muted">
          <CalendarRange size={15} aria-hidden />
          {filters.from} to {filters.to}
        </div>
      </header>

      <BrandAnalysisFilterBar sticky={false} />
      <ProfileGroupSampleWarning />

      <Card className="p-3">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex-1 min-w-[240px] max-w-[420px]">
            <div className="flex items-center gap-2 h-10 px-3 rounded-btn bg-themed-subtle border border-themed-subtle">
              <Search size={16} className="text-themed-muted" aria-hidden />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search topics..."
                className="flex-1 bg-transparent text-sm text-themed-primary placeholder:text-themed-faint outline-none"
              />
            </div>
          </div>
          <button
            type="button"
            className="inline-flex items-center gap-2 t-btn-secondary py-1.5 px-3 text-xs font-medium"
            aria-label="Export topics"
            onClick={() =>
              downloadCsv(
                'topics-successful.csv',
                exportMetadata('topics', filters, brandIdOverride),
                topicExportRows(filtered),
              )
            }
          >
            <Download size={14} aria-hidden />
            Export
          </button>
        </div>
      </Card>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-6 gap-3">
        <MetricCard label="Visible Topics" value={formatEvidenceCount(summary?.topic_count)} />
        <MetricCard
          label="Successful responses"
          value={formatEvidenceCount(summary?.response_count)}
          detail="Only successful answers are included."
          tone="success"
        />
        <MetricCard label="Avg Visibility" value={formatPercent(avgVisibility)} tone="accent" />
        <MetricCard
          label="Sentiment Mix"
          value={`${formatEvidenceCount(sentiment.positive)} / ${formatEvidenceCount(
            sentiment.neutral,
          )} / ${formatEvidenceCount(sentiment.negative)}`}
          detail="Positive / neutral / negative"
        />
        <MetricCard
          label="Citation Coverage"
          value={formatPercent(avgCitationCoverage)}
          detail={`${formatEvidenceCount(summary?.citation_count)} citations`}
        />
        <MetricCard
          label="Analyzed answers"
          value={formatEvidenceCount(summary?.analyzed_count)}
          detail={`Last success ${summary?.last_collected || '-'}`}
        />
      </div>

      <Card className="p-0 overflow-hidden">
        <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-themed-card">
          <div>
            <h3 className="text-sm font-semibold text-themed-primary">Topic evidence</h3>
            <div className="text-xs text-themed-muted mt-1">
              Visibility, sentiment, and citations are shown from eligible answers.
            </div>
          </div>
          <StateBadge state={monitoringQ.data?.state} />
        </div>
        <div className="overflow-x-auto">
          <table className="t-table w-full min-w-[980px]">
            <thead>
              <tr>
                <th>Topic</th>
                <th>Dimension</th>
                <th>Associated brand</th>
                <th className="text-right">Visibility</th>
                <th>Sentiment</th>
                <th className="text-right">Citation Coverage</th>
                <th className="text-right">Citations</th>
                <th className="text-right">Prompts</th>
                <th className="text-right">Queries</th>
                <th>Last success</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((topic) => (
                <tr
                  key={topic.topic_id}
                  className="cursor-pointer"
                  onClick={() => onSelectTopic(topic)}
                >
                  <td className="font-medium text-themed-primary">{topic.topic_name}</td>
                  <td>
                    <Badge variant={DIMENSION_VARIANTS[topic.dimension || ''] || 'blue'} size="sm">
                      {topic.dimension || '-'}
                    </Badge>
                  </td>
                  <td className="text-themed-muted">{topic.associated_brand || '-'}</td>
                  <td className="text-right tabular-nums font-semibold text-themed-primary">
                    {formatPercent(visibilityValue(topic))}
                  </td>
                  <td>
                    <SentimentMix value={topic.sentiment_distribution} />
                  </td>
                  <td className="text-right tabular-nums text-themed-primary">
                    {formatPercent(topic.citation_rate)}
                  </td>
                  <td className="text-right tabular-nums text-themed-muted">
                    {formatEvidenceCount((topic as LooseRecord).citation_count)}
                  </td>
                  <td className="text-right tabular-nums font-semibold text-themed-primary">
                    {formatEvidenceCount(topic.prompt_count)}
                  </td>
                  <td className="text-right tabular-nums text-themed-primary">
                    {formatEvidenceCount(topic.query_count)}
                  </td>
                  <td className="text-themed-muted text-xs">{topic.last_collected || '-'}</td>
                </tr>
              ))}
              {!monitoringQ.isLoading && filtered.length === 0 && (
                <tr>
                  <td colSpan={10}>
                    {sevenDayEmpty ? (
                      <EmptyState
                        title="No successful responses in the current 7-day view"
                        text="This view only shows successful answers. Expand the range to see older evidence."
                        action={
                          <Button variant="outline" size="sm" onClick={onSwitchTo30Days}>
                            Switch to 30 days
                          </Button>
                        }
                      />
                    ) : (
                      <EmptyState text="No topics match the current filters." />
                    )}
                  </td>
                </tr>
              )}
              {monitoringQ.isLoading && (
                <tr>
                  <td colSpan={10}>
                    <EmptyState text="Loading topics..." />
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}

function PromptsView({
  projectId,
  topic,
  filters,
  brandIdOverride,
  onSelectPrompt,
}: {
  projectId: string | null
  topic: any
  filters: any
  brandIdOverride: number | null
  onSelectPrompt: (prompt: any) => void
}) {
  const [searchParams, setSearchParams] = useSearchParams()
  const promptIntentParam = searchParams.get('promptIntent') || 'all'
  const promptLanguageParam = searchParams.get('promptLanguage') || 'all'
  const [intent, setIntent] = useState(promptIntentParam)
  const [language, setLanguage] = useState(promptLanguageParam)
  useEffect(() => {
    setIntent(promptIntentParam)
  }, [promptIntentParam])
  useEffect(() => {
    setLanguage(promptLanguageParam)
  }, [promptLanguageParam])

  const setPromptFilter = (key: 'promptIntent' | 'promptLanguage', next: string) => {
    if (key === 'promptIntent') setIntent(next)
    else setLanguage(next)
    const params = new URLSearchParams(searchParams)
    if (!next || next === 'all') params.delete(key)
    else params.set(key, next)
    setSearchParams(params, { replace: true })
  }

  const analysisParams = useMemo(() => {
    const params = analysisParamsWithBrand(filters, brandIdOverride)
    if (intent !== 'all') params.intent = intent
    return params
  }, [brandIdOverride, filters, intent])
  const promptsQ = useTopicPrompts(projectId, topic?.topic_id, analysisParams)
  const prompts = promptsQ.data?.items || []
  const promptIntents = withCurrentOption(uniqueValues(prompts, 'intent'), intent)
  const languages = withCurrentOption(uniqueValues(prompts, 'language'), language)
  const filteredPrompts = useMemo(
    () =>
      prompts.filter((prompt) => {
        if (intent !== 'all' && prompt.intent !== intent) return false
        if (language !== 'all' && prompt.language !== language) return false
        return true
      }),
    [intent, language, prompts],
  )
  const topicVisibility = visibilityValue(topic)

  return (
    <div className="space-y-5">
      <Card className="p-5">
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div className="max-w-3xl">
            <div className="text-xs font-semibold uppercase tracking-wide text-themed-muted mb-2">
              Topic summary
            </div>
            <h2 className="text-xl font-brand font-bold text-themed-primary mb-2">
              {topic.topic_name}
            </h2>
            <div className="flex items-center gap-3 flex-wrap">
              <Badge variant={DIMENSION_VARIANTS[topic.dimension || ''] || 'blue'} size="sm">
                {topic.dimension || '-'}
              </Badge>
              {topic.associated_brand && <Badge size="sm">{topic.associated_brand}</Badge>}
              <span className="text-xs text-themed-muted">
                Last success {topic.last_collected || '-'}
              </span>
            </div>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
            {miniMetric('Prompts', formatEvidenceCount(promptsQ.data?.total ?? prompts.length))}
            {miniMetric('Queries', formatEvidenceCount(topic.query_count))}
            {miniMetric('Visibility', formatPercent(topicVisibility))}
            {miniMetric('Citation coverage', formatPercent(topic.citation_rate))}
          </div>
        </div>
      </Card>

      <Card className="p-3">
        <div className="flex items-center gap-4 flex-wrap">
          <SlidersHorizontal size={15} className="text-themed-muted" aria-hidden />
          <ListFilter
            label="Intent"
            value={intent}
            options={promptIntents}
            onChange={(next) => setPromptFilter('promptIntent', next)}
          />
          <ListFilter
            label="Language"
            value={language}
            options={languages}
            onChange={(next) => setPromptFilter('promptLanguage', next)}
          />
          <button
            type="button"
            className="inline-flex items-center gap-2 t-btn-secondary py-1.5 px-3 text-xs font-medium"
            aria-label="Export prompts"
            onClick={() =>
              downloadCsv(
                'topics-prompts-successful.csv',
                exportMetadata('prompts', filters, brandIdOverride, { intent, language }),
                promptExportRows(filteredPrompts),
              )
            }
          >
            <Download size={14} aria-hidden />
            Export prompts
          </button>
        </div>
      </Card>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {filteredPrompts.map((prompt) => (
          <Card
            key={prompt.prompt_id}
            hover
            onClick={() => onSelectPrompt(prompt)}
            className="p-4"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <Badge variant={INTENT_VARIANTS[prompt.intent || ''] || 'blue'} size="sm">
                    {INTENT_LABELS[prompt.intent || ''] || prompt.intent || '-'}
                  </Badge>
                  <Badge size="sm">{(prompt.language || 'unknown').toUpperCase()}</Badge>
                  {(prompt.engine_coverage || []).slice(0, 3).map((engine: string) => (
                    <span
                      key={engine}
                      className="text-[11px] px-2 py-0.5 rounded-pill bg-themed-subtle text-themed-muted"
                    >
                      {engine}
                    </span>
                  ))}
                </div>
                <p className="text-sm font-semibold leading-relaxed text-themed-primary">
                  {prompt.prompt_text || '-'}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <div className="text-sm font-semibold text-themed-accent tabular-nums">
                  {formatEvidenceCount(prompt.query_count)} queries
                </div>
                <div className="text-[11px] text-themed-muted mt-1">
                  Last success {prompt.last_collected || '-'}
                </div>
              </div>
            </div>
            <div className="mt-4 pt-4 border-t border-themed-card grid grid-cols-2 md:grid-cols-4 gap-3">
              {miniMetric('Success rate', formatPercent(prompt.success_rate))}
              {miniMetric('Visibility', formatPercent(visibilityValue(prompt)))}
              {miniMetric('Avg rank', formatScore(prompt.avg_rank))}
              {miniMetric('Citation coverage', formatPercent(prompt.citation_rate))}
            </div>
          </Card>
        ))}
        {!promptsQ.isLoading && filteredPrompts.length === 0 && (
          <Card className="xl:col-span-2">
            <EmptyState text="No prompts for the current filters." />
          </Card>
        )}
        {promptsQ.isLoading && (
          <Card className="xl:col-span-2">
            <EmptyState text="Loading prompts..." />
          </Card>
        )}
      </div>
    </div>
  )
}

function groupSuccessfulQueries(queries: LooseRecord[]) {
  return queries
    .filter((query) => Array.isArray(query.daily_latest))
    .map((query) => {
      const dailyRows = query.daily_latest
        .filter((attempt: LooseRecord) => attempt?.response_id != null)
        .map((attempt: LooseRecord) => ({
          date: attempt.date || dayKey(latestTimestamp(attempt)),
          attempt,
        }))
      return {
        key: query.query_group_key || query.query_text || `Query ${query.query_id}`,
        queryText: query.query_text || dailyRows[0]?.attempt?.query_text || `Query ${query.query_id}`,
        attempts: dailyRows.map(({ attempt }) => attempt),
        attemptCount: asNumber(query.attempt_count) ?? dailyRows.length,
        dailyRows,
      }
    })
    .filter((group) => group.dailyRows.length > 0)
}

function queryMetricSummary(groups: ReturnType<typeof groupSuccessfulQueries>) {
  const dailyRows = groups.flatMap((group) => group.dailyRows.map(({ attempt }) => attempt))
  const profiles = new Set(dailyRows.map((attempt) => profileLabel(attempt)))
  const citedRows = dailyRows.filter((attempt) => (asNumber(attempt.citation_count) || 0) > 0)
  return {
    uniqueQueries: groups.length,
    dailyResponses: dailyRows.length,
    profilesCovered: profiles.size,
    includesUnknownProfile: profiles.has('Unknown profile'),
    citationCoverage: dailyRows.length ? citedRows.length / dailyRows.length : 0,
  }
}

function responsePreview(attempt: LooseRecord) {
  const preview = attempt.response_preview == null ? '' : String(attempt.response_preview).trim()
  return preview || 'No preview available.'
}

function QueriesView({
  projectId,
  topic,
  prompt,
  filters,
  brandIdOverride,
  onOpenAttempts,
}: {
  projectId: string | null
  topic: any
  prompt: any
  filters: any
  brandIdOverride: number | null
  onOpenAttempts: (query: any, attempts: any[]) => void
}) {
  const analysisParams = useMemo(
    () => analysisParamsWithBrand(filters, brandIdOverride),
    [brandIdOverride, filters],
  )
  const queriesQ = usePromptQueries(projectId, prompt?.prompt_id, analysisParams)
  const queries = queriesQ.data?.items || []
  const missingDailyLatest = queries.some((query) => !Array.isArray(query.daily_latest))
  const groups = useMemo(() => groupSuccessfulQueries(queries), [queries])
  const successfulAttempts = groups.reduce((count, group) => count + group.attemptCount, 0)
  const queryMetrics = useMemo(() => queryMetricSummary(groups), [groups])

  return (
    <div className="space-y-5">
      <Card className="p-5">
        <div className="text-xs text-themed-muted mb-2">Topic: {topic.topic_name}</div>
        <p className="text-base font-medium text-themed-primary mb-3 leading-relaxed">
          {prompt.prompt_text || '-'}
        </p>
        <div className="flex items-center gap-3 flex-wrap">
          <Badge variant={INTENT_VARIANTS[prompt.intent || ''] || 'blue'} size="sm">
            {INTENT_LABELS[prompt.intent || ''] || prompt.intent || '-'}
          </Badge>
          <Badge size="sm">{(prompt.language || 'unknown').toUpperCase()}</Badge>
          <span className="text-xs text-themed-muted">
            {formatEvidenceCount(successfulAttempts)} successful attempts
          </span>
        </div>
      </Card>

      <div className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        <Card className="p-4 min-h-[88px]">
          <div className="text-[11px] text-themed-muted">Unique Queries</div>
          <div className="text-xl font-brand font-bold text-themed-primary tabular-nums mt-1">
            {formatEvidenceCount(queryMetrics.uniqueQueries)}
          </div>
        </Card>
        <Card className="p-4 min-h-[88px]">
          <div className="text-[11px] text-themed-muted">Daily Successful Responses</div>
          <div className="text-xl font-brand font-bold text-themed-primary tabular-nums mt-1">
            {formatEvidenceCount(queryMetrics.dailyResponses)}
          </div>
        </Card>
        <Card className="p-4 min-h-[88px]">
          <div className="text-[11px] text-themed-muted">Profiles Covered</div>
          <div className="text-xl font-brand font-bold text-themed-primary tabular-nums mt-1">
            {formatEvidenceCount(queryMetrics.profilesCovered)}
          </div>
          {queryMetrics.includesUnknownProfile && (
            <div className="text-[11px] text-themed-muted mt-1">Includes Unknown profile</div>
          )}
        </Card>
        <Card className="p-4 min-h-[88px]">
          <div className="text-[11px] text-themed-muted">Citation Coverage</div>
          <div className="text-xl font-brand font-bold text-themed-primary tabular-nums mt-1">
            {formatPercent(queryMetrics.citationCoverage)}
          </div>
        </Card>
      </div>

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-sm font-semibold text-themed-primary">
            Daily latest successful responses
          </h3>
          <p className="text-xs text-themed-muted mt-1">
            Query groups show the latest successful answer for each day.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StateBadge state={queriesQ.data?.state} />
          <button
            type="button"
            className="inline-flex items-center gap-2 t-btn-secondary py-1.5 px-3 text-xs font-medium"
            aria-label="Export queries"
            onClick={() =>
              downloadCsv(
                'topics-queries-successful.csv',
                exportMetadata('queries', filters, brandIdOverride, {
                  prompt_id: prompt?.prompt_id ?? '',
                }),
                queryExportRows(groups),
              )
            }
          >
            <Download size={14} aria-hidden />
            Export queries
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {groups.map((group) => (
          <Card key={group.key} className="p-0 overflow-hidden">
            <div className="px-4 py-3 border-b border-themed-card flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="inline-flex items-center gap-2 text-xs text-themed-muted mb-1">
                  <MessageSquare size={14} aria-hidden />
                  Logical query group
                </div>
                <div className="text-sm font-semibold text-themed-primary leading-relaxed">
                  {group.queryText}
                </div>
              </div>
              <Badge size="sm">{group.dailyRows.length} days</Badge>
            </div>
            <div className="divide-y divide-[var(--color-border-subtle)]">
              {group.dailyRows.map(({ date, attempt }) => {
                const exactQuery = attempt.query_text || group.queryText
                return (
                  <div
                    key={`${group.key}-${date}-${attempt.query_id}`}
                    className="grid grid-cols-1 lg:grid-cols-[110px_minmax(150px,0.85fr)_minmax(220px,1.35fr)_105px_105px_150px] gap-3 px-4 py-3 items-center"
                  >
                    <div className="text-xs font-semibold text-themed-primary tabular-nums">
                      {date}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <Badge variant="accent" size="sm">
                          {attempt.target_llm || '-'}
                        </Badge>
                        <span className="text-sm text-themed-primary">
                          {profileLabel(attempt)}
                        </span>
                      </div>
                      <div className="text-[11px] text-themed-muted mt-1">
                        Finished {formatDateTime(latestTimestamp(attempt))}
                      </div>
                    </div>
                    <div className="min-w-0">
                      <div className="text-[11px] text-themed-muted">Exact query</div>
                      <div className="text-xs leading-relaxed mt-1 line-clamp-1 break-words text-themed-primary">
                        {exactQuery}
                      </div>
                      <div className="text-[11px] text-themed-muted mt-2">Latest response</div>
                      <div
                        className={`text-xs leading-relaxed mt-1 line-clamp-2 break-words ${
                          attempt.response_preview ? 'text-themed-primary' : 'text-themed-muted'
                        }`}
                      >
                        {responsePreview(attempt)}
                      </div>
                    </div>
                    <div>
                      <div className="text-[11px] text-themed-muted">Visibility</div>
                      <div className="text-sm font-semibold text-themed-primary tabular-nums">
                        {attempt.target_mentioned ? 'Mentioned' : 'Not mentioned'}
                      </div>
                    </div>
                    <div>
                      <div className="text-[11px] text-themed-muted">Citations</div>
                      <div className="text-sm font-semibold text-themed-primary tabular-nums">
                        {formatEvidenceCount(attempt.citation_count)}
                      </div>
                    </div>
                    <div className="lg:text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onOpenAttempts(attempt, group.attempts)}
                      >
                        Open response attempts
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          </Card>
        ))}
        {!queriesQ.isLoading && groups.length === 0 && (
          <Card>
            {missingDailyLatest ? (
              <EmptyState
                title="Query groups are unavailable"
                text="The backend response is missing daily latest successful rows for this prompt."
              />
            ) : (
              <EmptyState text="No successful query responses for the current filters." />
            )}
          </Card>
        )}
        {queriesQ.isLoading && (
          <Card>
            <EmptyState text="Loading query groups..." />
          </Card>
        )}
      </div>
    </div>
  )
}

function toDisplayList(value: unknown): string[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item === 'object') {
          const row = item as LooseRecord
          return row.name || row.label || row.value || row.text || JSON.stringify(row)
        }
        return item == null ? '' : String(item)
      })
      .filter(Boolean)
  }
  if (typeof value === 'string') return value ? [value] : []
  return []
}

function analysisList(analysis: LooseRecord | null | undefined, keys: string[]) {
  if (!analysis) return []
  for (const key of keys) {
    const list = toDisplayList(analysis[key])
    if (list.length) return list
  }
  return []
}

function analyzerFacts(value: LooseRecord | null | undefined) {
  return {
    citations: Array.isArray(value?.citations) ? value.citations : [],
    brands_mentioned: Array.isArray(value?.brands_mentioned) ? value.brands_mentioned : [],
    products_features_attributes: Array.isArray(value?.products_features_attributes)
      ? value.products_features_attributes
      : [],
    relations: Array.isArray(value?.relations) ? value.relations : [],
    sentiment_drivers: Array.isArray(value?.sentiment_drivers) ? value.sentiment_drivers : [],
  }
}

function productFactLabels(items: LooseRecord[]) {
  return items
    .map((item) => {
      const parts = [item.product_name, item.feature_name]
        .filter((value) => value !== null && value !== undefined && value !== '')
        .map(String)
      if (parts.length) return parts.join(' / ')
      return item.context_snippet || item.brand_name || item.scenario || JSON.stringify(item)
    })
    .filter(Boolean)
}

function relationLabels(items: LooseRecord[]) {
  return items
    .map((item) => {
      const a = item.a_name || item.a_id
      const b = item.b_name || item.b_id
      const type = item.type || item.entity_kind
      if (a && type && b) return `${a} ${type} ${b}`
      return item.evidence || JSON.stringify(item)
    })
    .filter(Boolean)
    .map(String)
}

function driverLabels(items: LooseRecord[]) {
  return items
    .map((item) => item.driver_text || item.source_quote || item.category || JSON.stringify(item))
    .filter(Boolean)
    .map(String)
}

function titleCase(value: unknown) {
  const text = value == null ? '' : String(value)
  if (!text) return ''
  return text
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function analysisSummaryFacts(analysis: LooseRecord | null | undefined) {
  if (!analysis) return []
  const facts: Array<{ label: string; value: string }> = []
  const targetMentioned = analysis.target_brand_mentioned
  if (typeof targetMentioned === 'boolean') {
    facts.push({ label: 'Target brand', value: targetMentioned ? 'Mentioned' : 'Not mentioned' })
  }
  const rank = asNumber(analysis.target_brand_rank)
  if (rank != null) facts.push({ label: 'Target rank', value: `#${formatEvidenceCount(rank)}` })
  if (analysis.target_brand_sentiment) {
    facts.push({ label: 'Target sentiment', value: titleCase(analysis.target_brand_sentiment) })
  }
  const scoreFields = [
    ['Visibility score', analysis.visibility_score],
    ['Sentiment score', analysis.sentiment_score],
    ['Share of voice', analysis.sov_score],
    ['Citation score', analysis.citation_score],
    ['GEO score', analysis.geo_score],
  ] as const
  scoreFields.forEach(([label, value]) => {
    if (asNumber(value) != null) facts.push({ label, value: formatScore(value) })
  })
  if (analysis.analyzed_at) facts.push({ label: 'Analyzed', value: formatDateTime(analysis.analyzed_at) })
  return facts
}

function AnalysisSummaryGrid({ facts }: { facts: Array<{ label: string; value: string }> }) {
  if (!facts.length) {
    return <div className="text-xs text-themed-muted">No analyzer summary is available for this response.</div>
  }
  return (
    <div className="grid grid-cols-2 gap-2">
      {facts.map((fact) => (
        <div key={fact.label} className="p-2.5 rounded-btn bg-themed-subtle">
          <div className="text-[11px] text-themed-muted">{fact.label}</div>
          <div className="text-sm font-semibold text-themed-primary mt-0.5">{fact.value}</div>
        </div>
      ))}
    </div>
  )
}

function FactList({ items, emptyText }: { items: string[]; emptyText: string }) {
  if (!items.length) return <div className="text-xs text-themed-muted">{emptyText}</div>
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.slice(0, 12).map((item) => (
        <span
          key={item}
          className="text-[11px] px-2 py-1 rounded-pill bg-themed-subtle text-themed-primary"
        >
          {item}
        </span>
      ))}
    </div>
  )
}

function FactSection({
  title,
  children,
}: {
  title: string
  children: ReactNode
}) {
  return (
    <section className="space-y-2">
      <h4 className="text-xs font-semibold uppercase tracking-wide text-themed-muted">{title}</h4>
      {children}
    </section>
  )
}

function ResponseAttemptsModal({
  projectId,
  brandIdOverride,
  query,
  attempts,
  onClose,
}: {
  projectId: string | null
  brandIdOverride: number | null
  query: any
  attempts: any[]
  onClose: () => void
}) {
  const responseParams = useMemo<ProjectAnalysisParams>(
    () => (brandIdOverride != null ? { brand_id: brandIdOverride } : {}),
    [brandIdOverride],
  )
  const initialAttempts = attempts.length ? attempts : [query]
  const initialQueryId = query?.query_id || initialAttempts[0]?.query_id
  const detailQ = useQueryResponse(projectId, initialQueryId, responseParams)
  const detail = detailQ.data
  const detailedAttempts = Array.isArray((detail as LooseRecord | null | undefined)?.attempts)
    ? ((detail as LooseRecord).attempts as LooseRecord[])
    : []
  const orderedAttempts = detailedAttempts.length ? detailedAttempts : initialAttempts
  const [activeId, setActiveId] = useState(orderedAttempts[0]?.query_id)
  useEffect(() => {
    setActiveId(orderedAttempts[0]?.query_id)
  }, [orderedAttempts[0]?.query_id])

  const activeAttempt =
    orderedAttempts.find((attempt) => attempt.query_id === activeId) || orderedAttempts[0]
  const response = (activeAttempt?.response || detail?.response) as LooseRecord | null | undefined
  const analysis = (activeAttempt?.analysis || detail?.analysis) as LooseRecord | null | undefined
  const factsSource = (activeAttempt?.analyzer_facts || detail?.analyzer_facts) as
    | LooseRecord
    | null
    | undefined
  const scopedFacts = analyzerFacts(factsSource)
  const hasScopedFacts = Boolean(factsSource)
  const mentions = hasScopedFacts ? scopedFacts.brands_mentioned : detail?.brand_mentions || []
  const citations = hasScopedFacts
    ? scopedFacts.citations
    : (activeAttempt?.citations || detail?.citations || [])
  const productFacts = hasScopedFacts
    ? productFactLabels(scopedFacts.products_features_attributes)
    : [
        ...analysisList(analysis, ['products', 'product_mentions', 'product_names']),
        ...analysisList(analysis, ['features', 'product_features', 'feature_mentions']),
        ...analysisList(analysis, ['attributes', 'attribute_mentions']),
      ]
  const relations = hasScopedFacts
    ? relationLabels(scopedFacts.relations)
    : analysisList(analysis, ['relations', 'response_relations'])
  const drivers = hasScopedFacts
    ? driverLabels(scopedFacts.sentiment_drivers)
    : analysisList(analysis, ['sentiment_drivers', 'drivers'])
  const summaryFacts = analysisSummaryFacts(analysis)
  const hasFutureAnalyzerFacts = productFacts.length > 0 || relations.length > 0 || drivers.length > 0

  return (
    <div
      className="fixed inset-0 z-50 bg-black/35 flex items-center justify-center p-4"
      role="presentation"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Response attempts"
        className="w-full max-w-[1180px] max-h-[88vh] overflow-hidden rounded-card bg-themed-card shadow-elevated border border-themed-card"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-themed-card">
          <div>
            <h3 className="text-sm font-semibold text-themed-primary">Response attempts</h3>
            <div className="text-xs text-themed-muted mt-1">
              Successful answers and scoped facts for the selected query group.
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close response attempts"
            className="w-8 h-8 inline-flex items-center justify-center rounded-btn text-themed-muted hover:text-themed-primary hover:bg-themed-subtle transition-colors"
          >
            <X size={16} aria-hidden />
          </button>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[220px_minmax(0,1fr)_320px] max-h-[calc(88vh-73px)] overflow-hidden">
          <aside className="border-b lg:border-b-0 lg:border-r border-themed-card p-3 overflow-y-auto">
            <div className="text-xs font-semibold text-themed-muted mb-3">Attempts</div>
            <div className="space-y-2">
              {orderedAttempts.map((attempt, index) => {
                const active = attempt.query_id === activeAttempt?.query_id
                return (
                  <button
                    key={attempt.query_id || index}
                    type="button"
                    onClick={() => setActiveId(attempt.query_id)}
                    className="w-full text-left p-3 rounded-btn border transition-colors"
                    style={{
                      background: active ? 'var(--color-accent-bg-light)' : 'var(--color-bg-card)',
                      borderColor: active
                        ? 'var(--color-accent-alpha-27)'
                        : 'var(--color-border-subtle)',
                    }}
                  >
                    <div className="text-sm font-semibold text-themed-primary">
                      Attempt {index + 1}
                    </div>
                    <div className="text-[11px] text-themed-muted mt-1">
                      {attempt.target_llm || '-'} / {formatDateTime(latestTimestamp(attempt))}
                    </div>
                  </button>
                )
              })}
            </div>
          </aside>

          <main className="p-5 overflow-y-auto">
            <div className="space-y-4">
              <section className="p-4 rounded-card bg-themed-subtle border border-themed-subtle">
                <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-themed-muted mb-2">
                  <FileText size={14} aria-hidden />
                  Exact query
                </div>
                <p className="text-sm font-medium text-themed-primary leading-relaxed">
                  {activeAttempt?.query_text || query?.query_text || '-'}
                </p>
                <div className="flex items-center gap-2 flex-wrap mt-3 text-xs text-themed-muted">
                  <Badge variant="accent" size="sm">
                    {activeAttempt?.target_llm || '-'}
                  </Badge>
                  <span>{profileLabel(activeAttempt || detail?.query || query)}</span>
                  <span>{formatDateTime(response?.created_at || latestTimestamp(activeAttempt))}</span>
                </div>
              </section>

              <section>
                <div className="flex items-center justify-between gap-3 mb-3">
                  <h4 className="text-sm font-semibold text-themed-primary">Full LLM answer</h4>
                  <StateBadge state={detail?.state} />
                </div>
                <div className="min-h-[260px] whitespace-pre-wrap text-sm leading-relaxed text-themed-body p-4 rounded-card border border-themed-card bg-themed-card">
                  {detailQ.isLoading
                    ? 'Loading response...'
                    : response?.raw_text || 'No answer text is available for this attempt.'}
                </div>
              </section>
            </div>
          </main>

          <aside className="border-t lg:border-t-0 lg:border-l border-themed-card p-5 overflow-y-auto space-y-5">
            <div className="flex items-center gap-2">
              <BarChart3 size={16} className="text-themed-accent" aria-hidden />
              <h4 className="text-sm font-semibold text-themed-primary">Analyzer facts</h4>
            </div>

            <FactSection title="Analyzer summary">
              <AnalysisSummaryGrid facts={summaryFacts} />
            </FactSection>

            <FactSection title={`Citations (${citations.length})`}>
              <div className="space-y-2">
                {citations.slice(0, 6).map((cite: LooseRecord, index: number) => (
                  <a
                    key={cite.citation_id || cite.url || index}
                    href={cite.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-2 text-xs text-themed-accent hover:underline min-w-0"
                  >
                    <ExternalLink size={12} className="shrink-0" aria-hidden />
                    <span className="truncate">{cite.domain || cite.url || 'Citation'}</span>
                  </a>
                ))}
                {!citations.length && (
                  <div className="text-xs text-themed-muted">No citations for this response.</div>
                )}
              </div>
            </FactSection>

            <FactSection title="Brands">
              <div className="space-y-2">
                {mentions.slice(0, 6).map((mention: LooseRecord, index: number) => (
                  <div
                    key={mention.mention_id || `${mention.brand_name}-${index}`}
                    className="p-2.5 rounded-btn bg-themed-subtle"
                  >
                    <div className="text-sm font-medium text-themed-primary">
                      {mention.brand_name || 'Brand'}
                    </div>
                    <div className="text-[11px] text-themed-muted mt-1">
                      Rank {mention.position_rank || '-'} / {mention.sentiment || 'neutral'}
                    </div>
                    {mention.context_snippet && (
                      <div className="text-[11px] text-themed-muted mt-1 line-clamp-2">
                        {mention.context_snippet}
                      </div>
                    )}
                  </div>
                ))}
                {!mentions.length && (
                  <div className="text-xs text-themed-muted">No brand mentions for this response.</div>
                )}
              </div>
            </FactSection>

            {productFacts.length > 0 && (
              <FactSection title="Products and features">
                <FactList
                  items={productFacts}
                  emptyText="No products, features, or attributes for this response."
                />
              </FactSection>
            )}

            {relations.length > 0 && (
              <FactSection title="Response relations">
                <FactList items={relations} emptyText="No response-scoped relations for this response." />
              </FactSection>
            )}

            {drivers.length > 0 && (
              <FactSection title="Sentiment drivers">
                <FactList items={drivers} emptyText="No sentiment drivers for this response." />
              </FactSection>
            )}

            {analysis && !hasFutureAnalyzerFacts && (
              <FactSection title="Additional analyzer fields">
                <div className="text-xs text-themed-muted">
                  Product, relation, and driver details are not available for this response yet.
                </div>
              </FactSection>
            )}
          </aside>
        </div>
      </div>
    </div>
  )
}

export default function TopicsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const topicIdFromUrl = parseIdParam(searchParams.get('topicId'))
  const promptIdFromUrl = parseIdParam(searchParams.get('promptId'))
  const [view, setView] = useState(() =>
    promptIdFromUrl != null ? 'queries' : topicIdFromUrl != null ? 'prompts' : 'topics',
  )
  const [selectedTopic, setSelectedTopic] = useState<any>(() =>
    topicIdFromUrl != null || promptIdFromUrl != null ? urlTopic(topicIdFromUrl) : null,
  )
  const [selectedPrompt, setSelectedPrompt] = useState<any>(() =>
    promptIdFromUrl != null ? urlPrompt(promptIdFromUrl, topicIdFromUrl) : null,
  )
  const [responseModal, setResponseModal] = useState<{ query: any; attempts: any[] } | null>(null)
  const { activeProject } = useProject()
  const { data: liveProjects } = useProjects()
  const { filters, setRange } = useBrandAnalysisFilters()
  const liveProjectId = resolveLiveProjectId(liveProjects, activeProject)
  const brandIdParam = searchParams.get('brandId')
  const brandIdOverride =
    brandIdParam && /^\d+$/.test(brandIdParam) ? Number(brandIdParam) : null
  const baseAnalysisParams = useMemo(
    () => analysisParamsWithBrand(filters, brandIdOverride),
    [brandIdOverride, filters],
  )
  const needsUrlMetadata = topicIdFromUrl != null || promptIdFromUrl != null
  const metadataProjectId = needsUrlMetadata ? liveProjectId : null
  const topicMetadataQ = useTopicMonitoring(metadataProjectId, baseAnalysisParams)
  const promptMetadataQ = useTopicPrompts(
    metadataProjectId,
    topicIdFromUrl,
    baseAnalysisParams,
  )
  const hydratedTopic = useMemo(
    () =>
      topicIdFromUrl == null
        ? null
        : (topicMetadataQ.data?.topics || []).find(
            (topic: LooseRecord) => topic.topic_id === topicIdFromUrl,
          ) || null,
    [topicIdFromUrl, topicMetadataQ.data?.topics],
  )
  const hydratedPrompt = useMemo(
    () =>
      promptIdFromUrl == null
        ? null
        : (promptMetadataQ.data?.items || []).find(
            (prompt: LooseRecord) => prompt.prompt_id === promptIdFromUrl,
          ) || null,
    [promptIdFromUrl, promptMetadataQ.data?.items],
  )

  useEffect(() => {
    if (topicIdFromUrl == null && promptIdFromUrl == null) {
      setView('topics')
      setSelectedTopic(null)
      setSelectedPrompt(null)
      setResponseModal(null)
      return
    }

    setSelectedTopic((current: any) =>
      current?.topic_id === topicIdFromUrl ? current : urlTopic(topicIdFromUrl),
    )

    if (promptIdFromUrl != null) {
      setView('queries')
      setSelectedPrompt((current: any) =>
        current?.prompt_id === promptIdFromUrl
          ? current
          : urlPrompt(promptIdFromUrl, topicIdFromUrl),
      )
    } else {
      setView('prompts')
      setSelectedPrompt(null)
    }
    setResponseModal(null)
  }, [promptIdFromUrl, topicIdFromUrl])

  useEffect(() => {
    if (!hydratedTopic) return
    setSelectedTopic((current: any) =>
      current?.topic_id === hydratedTopic.topic_id && !isUrlPlaceholder(current)
        ? current
        : hydratedTopic,
    )
  }, [hydratedTopic])

  useEffect(() => {
    if (!hydratedPrompt) return
    setSelectedPrompt((current: any) =>
      current?.prompt_id === hydratedPrompt.prompt_id && !isUrlPlaceholder(current)
        ? current
        : hydratedPrompt,
    )
  }, [hydratedPrompt])

  const updateDrilldownParams = (updates: Record<string, string | number | null>) => {
    const params = new URLSearchParams(searchParams)
    Object.entries(updates).forEach(([key, value]) => {
      if (value === null || value === '') params.delete(key)
      else params.set(key, String(value))
    })
    setSearchParams(params)
  }

  const goTo = {
    topics: () => {
      setView('topics')
      setSelectedTopic(null)
      setSelectedPrompt(null)
      setResponseModal(null)
      updateDrilldownParams({
        topicId: null,
        promptId: null,
        promptIntent: null,
        promptLanguage: null,
      })
    },
    prompts: (topic: any) => {
      setView('prompts')
      setSelectedTopic(topic)
      setSelectedPrompt(null)
      setResponseModal(null)
      updateDrilldownParams({
        topicId: topic?.topic_id ?? null,
        promptId: null,
      })
    },
    queries: (prompt: any) => {
      setView('queries')
      setSelectedPrompt(prompt)
      setResponseModal(null)
      updateDrilldownParams({
        topicId: selectedTopic?.topic_id ?? null,
        promptId: prompt?.prompt_id ?? null,
      })
    },
  }

  const breadcrumb = [{ label: 'Topics', view: 'topics' }]
  if (selectedTopic && view !== 'topics') {
    breadcrumb.push({ label: selectedTopic.topic_name, view: 'prompts' })
  }
  if (selectedPrompt && view === 'queries') {
    const text = selectedPrompt.prompt_text || 'Prompt'
    breadcrumb.push({ label: text.length > 30 ? `${text.slice(0, 30)}...` : text, view: 'queries' })
  }

  const onBreadcrumb = (target: string) => {
    if (target === 'topics') goTo.topics()
    else if (target === 'prompts') {
      setView('prompts')
      setSelectedPrompt(null)
      setResponseModal(null)
      updateDrilldownParams({ promptId: null })
    } else if (target === 'queries') {
      setView('queries')
      setResponseModal(null)
    }
  }

  const topicPlaceholderPending =
    topicIdFromUrl != null &&
    selectedTopic?.topic_id === topicIdFromUrl &&
    isUrlPlaceholder(selectedTopic)
  const promptPlaceholderPending =
    promptIdFromUrl != null &&
    selectedPrompt?.prompt_id === promptIdFromUrl &&
    isUrlPlaceholder(selectedPrompt)
  const promptUrlMissingTopic = promptIdFromUrl != null && topicIdFromUrl == null
  const topicMetadataLoading =
    topicPlaceholderPending &&
    (topicMetadataQ.isLoading || (!topicMetadataQ.data && !topicMetadataQ.isError))
  const promptMetadataLoading =
    !promptUrlMissingTopic &&
    promptPlaceholderPending &&
    (promptMetadataQ.isLoading || (!promptMetadataQ.data && !promptMetadataQ.isError))
  const topicMetadataFailed =
    topicPlaceholderPending &&
    (topicMetadataQ.isError ||
      (!topicMetadataQ.isLoading && Boolean(topicMetadataQ.data) && !hydratedTopic))
  const promptMetadataFailed =
    !promptUrlMissingTopic &&
    promptPlaceholderPending &&
    (promptMetadataQ.isError ||
      (!promptMetadataQ.isLoading && Boolean(promptMetadataQ.data) && !hydratedPrompt))
  const metadataLoading = topicMetadataLoading || promptMetadataLoading
  const metadataError = promptUrlMissingTopic
    ? 'Prompt metadata could not be loaded because this URL is missing a topicId.'
    : topicMetadataFailed
      ? 'Topic metadata could not be loaded for this URL. Go back to Topics and select the topic again.'
      : promptMetadataFailed
        ? 'Prompt metadata could not be loaded for this URL. Go back to the topic and select the prompt again.'
        : ''

  return (
    <div>
      <ProjectRequiredBanner />

      {metadataLoading && (
        <MetadataState
          title="Loading drilldown metadata"
          text="Restoring topic and prompt labels from the latest analysis data."
        />
      )}
      {!metadataLoading && metadataError && (
        <MetadataState title="Drilldown metadata unavailable" text={metadataError} />
      )}

      {!metadataLoading && !metadataError && view !== 'topics' && (
        <Breadcrumb items={breadcrumb} onNavigate={onBreadcrumb} />
      )}

      {!metadataLoading && !metadataError && view === 'topics' && (
        <TopicsView
          projectId={liveProjectId}
          filters={filters}
          brandIdOverride={brandIdOverride}
          onSelectTopic={(topic) => goTo.prompts(topic)}
          onSwitchTo30Days={() => setRange('30d')}
        />
      )}
      {!metadataLoading && !metadataError && view === 'prompts' && selectedTopic && (
        <PromptsView
          projectId={liveProjectId}
          topic={selectedTopic}
          filters={filters}
          brandIdOverride={brandIdOverride}
          onSelectPrompt={(prompt) => goTo.queries(prompt)}
        />
      )}
      {!metadataLoading &&
        !metadataError &&
        view === 'queries' &&
        selectedTopic &&
        selectedPrompt && (
          <QueriesView
            projectId={liveProjectId}
            topic={selectedTopic}
            prompt={selectedPrompt}
            filters={filters}
            brandIdOverride={brandIdOverride}
            onOpenAttempts={(query, attempts) => setResponseModal({ query, attempts })}
          />
        )}

      {responseModal && (
        <ResponseAttemptsModal
          projectId={liveProjectId}
          brandIdOverride={brandIdOverride}
          query={responseModal.query}
          attempts={responseModal.attempts}
          onClose={() => setResponseModal(null)}
        />
      )}
    </div>
  )
}
