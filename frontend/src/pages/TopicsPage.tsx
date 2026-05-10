import { useMemo, useState } from 'react'

import { Badge, Button, Card } from '../components/ui'
import BrandAnalysisFilterBar from '../components/filters/BrandAnalysisFilterBar'
import { ProfileGroupSampleWarning } from '../components/filters/ProfileGroupFilter'
import ProjectRequiredBanner from '../components/ProjectRequiredBanner'
import QueryActivityCard from '../components/topics/QueryActivityCard'
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
import { toProjectAnalysisParams } from '../lib/projectAnalysisFilters'

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

function pct(value: number | null | undefined, digits = 1) {
  return value == null ? '-' : `${(value * 100).toFixed(digits)}%`
}

function score(value: number | null | undefined) {
  return value == null ? '-' : value.toFixed(2)
}

function SentimentBar({ data }: { data?: Record<string, number> }) {
  const positive = data?.positive || 0
  const neutral = data?.neutral || 0
  const negative = data?.negative || 0
  const total = positive + neutral + negative || 1
  return (
    <div className="flex items-center overflow-hidden rounded-pill h-2.5 w-[150px]">
      <div
        style={{
          width: `${(positive / total) * 100}%`,
          background: 'var(--color-sentiment-positive)',
        }}
      />
      <div
        style={{
          width: `${(neutral / total) * 100}%`,
          background: 'var(--color-sentiment-neutral)',
        }}
      />
      <div
        style={{
          width: `${(negative / total) * 100}%`,
          background: 'var(--color-sentiment-warning)',
        }}
      />
    </div>
  )
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

function TopicsView({
  projectId,
  filters,
  onSelectTopic,
}: {
  projectId: string | null
  filters: any
  onSelectTopic: (topic: any) => void
}) {
  const [search, setSearch] = useState('')
  const analysisParams = toProjectAnalysisParams(filters)
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
  const topicIntentMatrix = useMemo(() => {
    const byIntent = new Map<string, { prompt_count: number; query_count: number }>()
    for (const row of intentRows) {
      const bucket = byIntent.get(row.intent) || { prompt_count: 0, query_count: 0 }
      bucket.prompt_count += row.prompt_count
      bucket.query_count += row.query_count
      byIntent.set(row.intent, bucket)
    }
    return Array.from(byIntent.entries())
  }, [intentRows])

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
            {summary?.topic_count ?? 0}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">Prompts</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">
            {summary?.prompt_count ?? 0}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">Queries</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">
            {summary?.query_count ?? 0}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">Responses</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">
            {summary?.response_count ?? 0}
          </div>
        </Card>
      </div>

      <Card className="p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-themed-primary">Topic x Intent</h3>
          <span className="text-xs text-themed-muted">Filtered data only</span>
        </div>
        {topicIntentMatrix.length ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {topicIntentMatrix.map(([intent, counts]) => (
              <div key={intent} className="rounded-card bg-themed-subtle p-3">
                <div className="text-xs text-themed-muted">
                  {INTENT_LABELS[intent] || intent}
                </div>
                <div className="text-xl font-semibold text-themed-primary tabular-nums mt-1">
                  {counts.query_count}
                </div>
                <div className="text-[11px] text-themed-muted">{counts.prompt_count} prompts</div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState text="No intent data for the current filters." />
        )}
      </Card>

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
              <th className="text-right">Prompts</th>
              <th className="text-right">Queries</th>
              <th className="text-right">Responses</th>
              <th>Engines</th>
              <th>Sentiment</th>
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
                <td className="text-right tabular-nums font-semibold text-themed-primary">
                  {topic.prompt_count}
                </td>
                <td className="text-right tabular-nums text-themed-primary">
                  {topic.query_count}
                </td>
                <td className="text-right tabular-nums text-themed-muted">
                  {topic.response_count}
                </td>
                <td className="text-themed-muted text-xs">
                  {topic.engine_coverage.join(', ') || '-'}
                </td>
                <td>
                  <SentimentBar data={topic.sentiment_distribution} />
                </td>
                <td className="text-themed-muted text-xs">{topic.last_collected || '-'}</td>
              </tr>
            ))}
            {!monitoringQ.isLoading && filtered.length === 0 && (
              <tr>
                <td colSpan={8}>
                  <EmptyState text="No topics match the current filters." />
                </td>
              </tr>
            )}
            {monitoringQ.isLoading && (
              <tr>
                <td colSpan={8}>
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
  onSelectPrompt,
}: {
  projectId: string | null
  topic: any
  filters: any
  onSelectPrompt: (prompt: any) => void
}) {
  const promptsQ = useTopicPrompts(projectId, topic?.topic_id, toProjectAnalysisParams(filters))
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
              <th className="text-right">Mention rate</th>
              <th className="text-right">Avg GEO</th>
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
                  {pct(prompt.mention_rate)}
                </td>
                <td className="text-right tabular-nums text-themed-muted">
                  {score(prompt.avg_geo_score)}
                </td>
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
  onSelectQuery,
}: {
  projectId: string | null
  topic: any
  prompt: any
  filters: any
  onSelectQuery: (query: any) => void
}) {
  const queriesQ = usePromptQueries(projectId, prompt?.prompt_id, toProjectAnalysisParams(filters))
  const queries = queriesQ.data?.items || []
  const successCount = queries.filter((query) =>
    ['done', 'success', 'completed'].includes(String(query.status || '').toLowerCase()),
  ).length
  const successRate = queries.length ? Math.round((successCount / queries.length) * 100) : 0
  const enginesCovered = new Set(queries.map((query) => query.target_llm).filter(Boolean)).size

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
          <span className="text-xs text-themed-muted">
            Engines: {prompt.engine_coverage?.join(', ') || '-'}
          </span>
        </div>
      </Card>

      <div className="grid grid-cols-3 gap-4">
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">Executions</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">
            {queries.length}
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">Success rate</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">
            {successRate}%
          </div>
        </Card>
        <Card className="p-4">
          <div className="text-xs text-themed-muted mb-1">Engines</div>
          <div className="text-2xl font-brand font-bold text-themed-primary tabular-nums">
            {enginesCovered}
          </div>
        </Card>
      </div>

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

function ResponseView({ projectId, query }: { projectId: string | null; query: any }) {
  const detailQ = useQueryResponse(projectId, query?.query_id)
  const detail = detailQ.data
  const response = detail?.response as any
  const analysis = detail?.analysis as any
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
              <span className="text-xs text-themed-muted">GEO {score(analysis?.geo_score)}</span>
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
  const liveProjectId = resolveLiveProjectId(liveProjects, activeProject)
  const analysisParams = toProjectAnalysisParams(filters)

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

      {view === 'topics' && (
        <div className="mb-6">
          <QueryActivityCard
            projectId={liveProjectId}
            brandName={activeProject?.primaryBrandName || activeProject?.name}
            filters={analysisParams}
          />
        </div>
      )}

      {view !== 'topics' && <Breadcrumb items={breadcrumb} onNavigate={onBreadcrumb} />}

      {view === 'topics' && (
        <TopicsView
          projectId={liveProjectId}
          filters={filters}
          onSelectTopic={(topic) => goTo.prompts(topic)}
        />
      )}
      {view === 'prompts' && selectedTopic && (
        <PromptsView
          projectId={liveProjectId}
          topic={selectedTopic}
          filters={filters}
          onSelectPrompt={(prompt) => goTo.queries(prompt)}
        />
      )}
      {view === 'queries' && selectedTopic && selectedPrompt && (
        <QueriesView
          projectId={liveProjectId}
          topic={selectedTopic}
          prompt={selectedPrompt}
          filters={filters}
          onSelectQuery={(query) => goTo.response(query)}
        />
      )}
      {view === 'response' && selectedQuery && (
        <ResponseView projectId={liveProjectId} query={selectedQuery} />
      )}
    </div>
  )
}
