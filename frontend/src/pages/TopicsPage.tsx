import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

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
          {i > 0 && <span className="text-themed-muted">/</span>}
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

function EmptyState({ text }: { text: string }) {
  return <div className="text-center text-[12px] text-themed-muted py-12">{text}</div>
}

function formatEvidenceCount(value: unknown) {
  if (value === null || value === undefined || value === '') return '--'
  const next = Number(value)
  return Number.isFinite(next) ? next : '--'
}

function TopicsView({
  projectId,
  filters,
  brandIdOverride,
  onSelectTopic,
}: {
  projectId: string | null
  filters: any
  brandIdOverride: number | null
  onSelectTopic: (topic: any) => void
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

  return (
    <div className="space-y-6">
      <BrandAnalysisFilterBar sticky={false} />
      <ProfileGroupSampleWarning />

      <Card className="p-3">
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex-1 min-w-[240px] max-w-[420px]">
            <div className="flex items-center gap-2 h-10 px-3 rounded-btn bg-themed-subtle border border-themed-subtle">
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search topics..."
                className="flex-1 bg-transparent text-sm text-themed-primary placeholder:text-themed-faint outline-none"
              />
            </div>
          </div>
          <Button variant="outline" size="sm">
            Export CSV
          </Button>
        </div>
      </Card>

      <div className="grid grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">Topics</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">
            {formatEvidenceCount(summary?.topic_count)}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">Prompts</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">
            {formatEvidenceCount(summary?.prompt_count)}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">Queries</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">
            {formatEvidenceCount(summary?.query_count)}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">Responses</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">
            {formatEvidenceCount(summary?.response_count)}
          </div>
        </Card>
      </div>

      <Card className="p-0 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-themed-card">
          <h3 className="text-sm font-semibold text-themed-primary">Monitoring Topics</h3>
          <span className="text-xs text-themed-muted">{monitoringQ.data?.state || 'empty'}</span>
        </div>
        <table className="t-table w-full">
          <thead>
            <tr>
              <th>Topic</th>
              <th>Dimension</th>
              <th>Associated brand</th>
              <th className="text-right">Prompts</th>
              <th className="text-right">Queries</th>
              <th className="text-right">Responses</th>
              <th>Last collected</th>
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
                  {topic.prompt_count}
                </td>
                <td className="text-right tabular-nums text-themed-primary">
                  {topic.query_count}
                </td>
                <td className="text-right tabular-nums text-themed-muted">
                  {topic.response_count}
                </td>
                <td className="text-themed-muted text-xs">{topic.last_collected || '-'}</td>
              </tr>
            ))}
            {!monitoringQ.isLoading && filtered.length === 0 && (
              <tr>
                <td colSpan={7}>
                  <EmptyState text="No topics match the current filters." />
                </td>
              </tr>
            )}
            {monitoringQ.isLoading && (
              <tr>
                <td colSpan={7}>
                  <EmptyState text="Loading topics..." />
                </td>
              </tr>
            )}
          </tbody>
        </table>
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
  const analysisParams = useMemo(
    () => analysisParamsWithBrand(filters, brandIdOverride),
    [brandIdOverride, filters],
  )
  const promptsQ = useTopicPrompts(projectId, topic?.topic_id, analysisParams)
  const prompts = promptsQ.data?.items || []

  return (
    <div className="space-y-6">
      <Card className="p-5">
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div>
            <h2 className="text-xl font-brand font-bold text-themed-primary mb-2">
              {topic.topic_name}
            </h2>
            <div className="flex items-center gap-3 flex-wrap">
              <Badge variant={DIMENSION_VARIANTS[topic.dimension || ''] || 'blue'} size="sm">
                {topic.dimension || '-'}
              </Badge>
              <span className="text-xs text-themed-muted">Last collected {topic.last_collected || '-'}</span>
            </div>
          </div>
          <div className="flex items-center gap-6">
            <div className="text-right">
              <div className="text-2xl font-brand font-bold text-themed-accent tabular-nums">
                {prompts.length}
              </div>
              <div className="text-xs text-themed-muted">Prompts</div>
            </div>
            <div className="text-right">
              <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">
                {topic.query_count}
              </div>
              <div className="text-xs text-themed-muted">Queries</div>
            </div>
          </div>
        </div>
      </Card>

      <Card className="p-0 overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-themed-card">
          <h3 className="text-sm font-semibold text-themed-primary">Prompts</h3>
          <span className="text-xs text-themed-muted">{promptsQ.data?.state || 'empty'}</span>
        </div>
        <table className="t-table w-full">
          <thead>
            <tr>
              <th>Prompt</th>
              <th>Intent</th>
              <th className="text-right">Queries</th>
              <th className="text-right">Responses</th>
              <th>Last collected</th>
            </tr>
          </thead>
          <tbody>
            {prompts.map((prompt) => (
              <tr
                key={prompt.prompt_id}
                className="cursor-pointer"
                onClick={() => onSelectPrompt(prompt)}
              >
                <td className="font-medium text-themed-primary">{prompt.prompt_text || '-'}</td>
                <td>
                  <Badge variant={INTENT_VARIANTS[prompt.intent || ''] || 'blue'} size="sm">
                    {INTENT_LABELS[prompt.intent || ''] || prompt.intent || '-'}
                  </Badge>
                </td>
                <td className="text-right tabular-nums font-semibold text-themed-accent">
                  {prompt.query_count}
                </td>
                <td className="text-right tabular-nums text-themed-primary">
                  {prompt.response_count}
                </td>
                <td className="text-themed-muted text-xs">{prompt.last_collected || '-'}</td>
              </tr>
            ))}
            {!promptsQ.isLoading && prompts.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <EmptyState text="No prompts for the current filters." />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}

function QueriesView({
  projectId,
  topic,
  prompt,
  filters,
  brandIdOverride,
  onSelectQuery,
}: {
  projectId: string | null
  topic: any
  prompt: any
  filters: any
  brandIdOverride: number | null
  onSelectQuery: (query: any) => void
}) {
  const analysisParams = useMemo(
    () => analysisParamsWithBrand(filters, brandIdOverride),
    [brandIdOverride, filters],
  )
  const queriesQ = usePromptQueries(projectId, prompt?.prompt_id, analysisParams)
  const queries = queriesQ.data?.items || []

  return (
    <div className="space-y-6">
      <Card className="p-5">
        <div className="text-xs text-themed-muted mb-2">Topic: {topic.topic_name}</div>
        <p className="text-base font-medium text-themed-primary mb-3 leading-relaxed">
          {prompt.prompt_text || '-'}
        </p>
        <div className="flex items-center gap-3">
          <Badge variant={INTENT_VARIANTS[prompt.intent || ''] || 'blue'} size="sm">
            {INTENT_LABELS[prompt.intent || ''] || prompt.intent || '-'}
          </Badge>
        </div>
      </Card>

      <Card className="p-0 overflow-hidden">
        <div className="px-5 py-4 border-b border-themed-card">
          <h3 className="text-sm font-semibold text-themed-primary">Query executions</h3>
        </div>
        <table className="t-table w-full">
          <thead>
            <tr>
              <th>Engine</th>
              <th>Profile</th>
              <th>Executed</th>
              <th>Status</th>
              <th className="text-right">Citations</th>
            </tr>
          </thead>
          <tbody>
            {queries.map((query) => {
              const hasResponse = !!query.response_id
              return (
                <tr
                  key={query.query_id}
                  className={hasResponse ? 'cursor-pointer' : 'opacity-60'}
                  onClick={() => hasResponse && onSelectQuery(query)}
                >
                  <td className="font-medium text-themed-primary">{query.target_llm || '-'}</td>
                  <td className="text-themed-muted">{query.profile_id || '-'}</td>
                  <td className="text-themed-muted text-xs tabular-nums">
                    {query.finished_at || query.created_at || '-'}
                  </td>
                  <td className="text-xs font-semibold text-themed-primary">
                    {query.status || '-'}
                  </td>
                  <td className="text-right tabular-nums font-semibold text-themed-primary">
                    {query.citation_count}
                  </td>
                </tr>
              )
            })}
            {!queriesQ.isLoading && queries.length === 0 && (
              <tr>
                <td colSpan={5}>
                  <EmptyState text="No queries for the current filters." />
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </Card>
    </div>
  )
}

function ResponseView({
  projectId,
  query,
  brandIdOverride,
}: {
  projectId: string | null
  query: any
  brandIdOverride: number | null
}) {
  const responseParams = useMemo<ProjectAnalysisParams>(
    () => (brandIdOverride != null ? { brand_id: brandIdOverride } : {}),
    [brandIdOverride],
  )
  const detailQ = useQueryResponse(projectId, query?.query_id, responseParams)
  const detail = detailQ.data
  const response = detail?.response as any
  const mentions = detail?.brand_mentions || []
  const citations = detail?.citations || []

  if (detailQ.isLoading) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm text-themed-muted">Loading response...</p>
      </Card>
    )
  }

  if (!response) {
    return (
      <Card className="p-8 text-center">
        <p className="text-sm text-themed-muted">This query has no response yet.</p>
      </Card>
    )
  }

  return (
    <div className="space-y-6">
      <Card className="p-5">
        <div className="flex items-center gap-4 mb-3 flex-wrap">
          <Badge variant="accent" size="sm">
            {response.target_llm || query.target_llm || '-'}
          </Badge>
          <span className="text-xs text-themed-muted">{query.profile_id || '-'}</span>
          <span className="text-xs text-themed-muted tabular-nums">
            {response.created_at || query.finished_at || '-'}
          </span>
        </div>
        <div className="p-3 rounded-btn bg-themed-subtle">
          <div className="text-xs text-themed-muted">Query</div>
          <p className="text-sm font-medium text-themed-primary mt-1">
            {query.query_text || '-'}
          </p>
        </div>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <Card className="p-5">
            <div className="flex items-center justify-between border-b border-themed-card pb-3 mb-4">
              <h3 className="text-sm font-semibold text-themed-primary">Raw response</h3>
            </div>
            <div className="text-sm leading-relaxed whitespace-pre-wrap text-themed-body">
              {response.raw_text || '-'}
            </div>
          </Card>
        </div>

        <div className="space-y-4">
          <Card className="p-4">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-themed-muted mb-3">
              Brand mentions
            </h4>
            <div className="space-y-3">
              {mentions.map((mention: any) => (
                <div key={mention.mention_id} className="p-2.5 rounded-btn bg-themed-subtle">
                  <div className="text-sm font-medium text-themed-primary">
                    {mention.brand_name}
                  </div>
                  <div className="text-[11px] text-themed-muted mt-1">
                    Rank {mention.position_rank || '-'} - {mention.sentiment || 'neutral'}
                  </div>
                  {mention.context_snippet && (
                    <div className="text-[11px] text-themed-muted mt-1 line-clamp-2">
                      {mention.context_snippet}
                    </div>
                  )}
                </div>
              ))}
              {!mentions.length && <div className="text-xs text-themed-muted">No mentions</div>}
            </div>
          </Card>

          <Card className="p-4">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-themed-muted mb-3">
              Citations
            </h4>
            <div className="space-y-2">
              {citations.map((cite: any) => (
                <a
                  key={cite.citation_id}
                  href={cite.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block text-xs truncate text-themed-accent hover:underline"
                >
                  {cite.domain || cite.url}
                </a>
              ))}
              {!citations.length && <div className="text-xs text-themed-muted">No citations</div>}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}

export default function TopicsPage() {
  const [view, setView] = useState('topics')
  const [selectedTopic, setSelectedTopic] = useState<any>(null)
  const [selectedPrompt, setSelectedPrompt] = useState<any>(null)
  const [selectedQuery, setSelectedQuery] = useState<any>(null)
  const { activeProject } = useProject()
  const { data: liveProjects } = useProjects()
  const { filters } = useBrandAnalysisFilters()
  const [searchParams] = useSearchParams()
  const liveProjectId = resolveLiveProjectId(liveProjects, activeProject)
  const brandIdParam = searchParams.get('brandId')
  const brandIdOverride =
    brandIdParam && /^\d+$/.test(brandIdParam) ? Number(brandIdParam) : null

  const goTo = {
    topics: () => {
      setView('topics')
      setSelectedTopic(null)
      setSelectedPrompt(null)
      setSelectedQuery(null)
    },
    prompts: (topic: any) => {
      setView('prompts')
      setSelectedTopic(topic)
      setSelectedPrompt(null)
      setSelectedQuery(null)
    },
    queries: (prompt: any) => {
      setView('queries')
      setSelectedPrompt(prompt)
      setSelectedQuery(null)
    },
    response: (query: any) => {
      setView('response')
      setSelectedQuery(query)
    },
  }

  const breadcrumb = [{ label: 'Topics', view: 'topics' }]
  if (selectedTopic && view !== 'topics') {
    breadcrumb.push({ label: selectedTopic.topic_name, view: 'prompts' })
  }
  if (selectedPrompt && (view === 'queries' || view === 'response')) {
    const text = selectedPrompt.prompt_text || 'Prompt'
    breadcrumb.push({ label: text.length > 30 ? `${text.slice(0, 30)}...` : text, view: 'queries' })
  }
  if (selectedQuery && view === 'response') {
    breadcrumb.push({
      label: `${selectedQuery.target_llm || 'engine'} - ${selectedQuery.profile_id || 'profile'}`,
      view: 'response',
    })
  }

  const onBreadcrumb = (target: string) => {
    if (target === 'topics') goTo.topics()
    else if (target === 'prompts') {
      setView('prompts')
      setSelectedPrompt(null)
      setSelectedQuery(null)
    } else if (target === 'queries') {
      setView('queries')
      setSelectedQuery(null)
    }
  }

  return (
    <div>
      <ProjectRequiredBanner />

      {view !== 'topics' && <Breadcrumb items={breadcrumb} onNavigate={onBreadcrumb} />}

      {view === 'topics' && (
        <TopicsView
          projectId={liveProjectId}
          filters={filters}
          brandIdOverride={brandIdOverride}
          onSelectTopic={(topic) => goTo.prompts(topic)}
        />
      )}
      {view === 'prompts' && selectedTopic && (
        <PromptsView
          projectId={liveProjectId}
          topic={selectedTopic}
          filters={filters}
          brandIdOverride={brandIdOverride}
          onSelectPrompt={(prompt) => goTo.queries(prompt)}
        />
      )}
      {view === 'queries' && selectedTopic && selectedPrompt && (
        <QueriesView
          projectId={liveProjectId}
          topic={selectedTopic}
          prompt={selectedPrompt}
          filters={filters}
          brandIdOverride={brandIdOverride}
          onSelectQuery={(query) => goTo.response(query)}
        />
      )}
      {view === 'response' && selectedQuery && (
        <ResponseView
          projectId={liveProjectId}
          query={selectedQuery}
          brandIdOverride={brandIdOverride}
        />
      )}
    </div>
  )
}
