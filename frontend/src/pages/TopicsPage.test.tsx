import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const liveProjectId = '11111111-1111-4111-8111-111111111111'

const topicHooks = vi.hoisted(() => ({
  useTopicMonitoring: vi.fn(),
  useTopicPrompts: vi.fn(),
  usePromptQueries: vi.fn(),
  useQueryResponse: vi.fn(),
}))

const filterHook = vi.hoisted(() => ({
  setRange: vi.fn(),
}))

vi.mock('../components/ui', () => ({
  Badge: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  Button: ({
    children,
    onClick,
    disabled,
    className,
  }: {
    children: ReactNode
    onClick?: () => void
    disabled?: boolean
    className?: string
  }) => (
    <button onClick={onClick} disabled={disabled} className={className}>
      {children}
    </button>
  ),
  Card: ({
    children,
    onClick,
    className,
  }: {
    children: ReactNode
    onClick?: () => void
    className?: string
  }) => (
    <div onClick={onClick} className={className}>
      {children}
    </div>
  ),
  MetricLabel: ({ children }: { children: ReactNode }) => <span>{children}</span>,
}))

vi.mock('../components/filters/BrandAnalysisFilterBar', () => ({
  default: () => null,
}))

vi.mock('../components/filters/ProfileGroupFilter', () => ({
  ProfileGroupSampleWarning: () => null,
}))

vi.mock('../components/ProjectRequiredBanner', () => ({
  default: () => null,
}))

vi.mock('../contexts/ProjectContext', () => ({
  useProject: () => ({ activeProject: { id: liveProjectId } }),
}))

vi.mock('../hooks/useProjects', () => ({
  useProjects: () => ({ data: [{ id: liveProjectId }] }),
}))

vi.mock('../hooks/useBrandAnalysisFilters', () => ({
  useBrandAnalysisFilters: () => ({
    filters: {
      from: '2026-05-04',
      to: '2026-05-11',
      engines: ['chatgpt'],
      profileGroup: 'all',
      dimensions: [],
      intents: [],
    },
    setRange: filterHook.setRange,
  }),
}))

vi.mock('../hooks/useTopicAnalysis', () => topicHooks)

import TopicsPage from './TopicsPage'

function LocationProbe({ onChange }: { onChange: (search: string) => void }) {
  const location = useLocation()
  onChange(location.search)
  return null
}

function renderTopicsPage(initialEntry = '/brand/topics?brandId=12') {
  let search = ''
  const result = render(
    <MemoryRouter initialEntries={[initialEntry]}>
      <TopicsPage />
      <LocationProbe onChange={(next) => {
        search = next
      }}
      />
    </MemoryRouter>,
  )
  return { ...result, getSearch: () => search }
}

function readBlobText(blob: Blob) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result))
    reader.onerror = reject
    reader.readAsText(blob)
  })
}

const urlHydrationTopic = {
  topic_id: 101,
  topic_name: 'Ingredient safety',
  dimension: 'product',
  associated_brand: 'Acme',
  prompt_count: 1,
  query_count: 1,
  response_count: 1,
  sentiment_distribution: { positive: 1, neutral: 0, negative: 0 },
}

const urlHydrationPrompt = {
  prompt_id: 201,
  topic_id: 101,
  prompt_text: 'Which serum is safest?',
  intent: 'commercial',
  language: 'zh',
  query_count: 1,
  response_count: 1,
}

function topicMonitoringState(topics = [urlHydrationTopic]) {
  return {
    data: {
      summary: {
        topic_count: topics.length,
        prompt_count: 1,
        query_count: 1,
        response_count: 1,
      },
      topics,
      intent_matrix: [],
      state: topics.length ? 'ok' : 'empty',
    },
    isLoading: false,
  }
}

function topicPromptsState(items = [urlHydrationPrompt]) {
  return {
    data: {
      items,
      total: items.length,
      state: items.length ? 'ok' : 'empty',
    },
    isLoading: false,
  }
}

describe('TopicsPage live brand override', () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  beforeEach(() => {
    topicHooks.useTopicMonitoring.mockReset()
    topicHooks.useTopicPrompts.mockReset()
    topicHooks.usePromptQueries.mockReset()
    topicHooks.useQueryResponse.mockReset()
    filterHook.setRange.mockReset()
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: {
        summary: {
          topic_count: 0,
          prompt_count: 0,
          query_count: 0,
          response_count: 0,
        },
        topics: [],
        intent_matrix: [],
        state: 'empty',
      },
      isLoading: false,
    })
    topicHooks.useTopicPrompts.mockReturnValue({
      data: { items: [], total: 0, state: 'empty' },
      isLoading: false,
    })
    topicHooks.usePromptQueries.mockReturnValue({
      data: { items: [], total: 0, state: 'empty' },
      isLoading: false,
    })
    topicHooks.useQueryResponse.mockReturnValue({
      data: null,
      isLoading: false,
    })
  })

  it('passes URL brandId to the topic monitoring API filters', () => {
    renderTopicsPage()

    expect(topicHooks.useTopicMonitoring).toHaveBeenCalledWith(
      liveProjectId,
      expect.objectContaining({
        brand_id: 12,
        from: '2026-05-04',
        to: '2026-05-11',
        engine: 'chatgpt',
      }),
    )
  })

  it('shows an honest 7-day empty state with a 30-day switch affordance', () => {
    renderTopicsPage()

    expect(
      screen.getByText(/No successful responses in the current 7-day view/i),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Switch to 30 days/i }))

    expect(filterHook.setRange).toHaveBeenCalledWith('30d')
  })

  it('renders the successful-only topics workspace with visibility sentiment and citation metrics', () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: {
        summary: {
          topic_count: 1,
          prompt_count: 2,
          query_count: 4,
          response_count: 3,
          analyzed_count: 3,
          target_mention_count: 2,
          citation_count: 5,
          last_collected: '2026-05-11',
        },
        topics: [
          {
            topic_id: 101,
            topic_name: 'Ingredient safety',
            dimension: 'product',
            associated_brand: 'Acme',
            prompt_count: 2,
            query_count: 4,
            response_count: 3,
            mention_rate: 0.67,
            sov: 0.42,
            avg_rank: 2.3,
            avg_geo_score: 0.74,
            sentiment_distribution: { positive: 2, neutral: 1, negative: 0 },
            citation_rate: 0.88,
            last_collected: '2026-05-11',
          },
        ],
        intent_matrix: [],
        state: 'ok',
      },
      isLoading: false,
    })

    renderTopicsPage()

    expect(screen.getByText(/Successful responses/i)).toBeInTheDocument()
    expect(screen.getByText(/Analyzed answers/i)).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Visibility/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Sentiment/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Citations/i })).toBeInTheDocument()
    expect(screen.getByText('Ingredient safety')).toBeInTheDocument()
    expect(screen.getAllByText('42.0%').length).toBeGreaterThan(0)
  })

  it('shows analyzer trust states instead of fake zero topic metrics when coverage is partial', () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: {
        summary: {
          topic_count: 1,
          prompt_count: 75,
          query_count: 464,
          response_count: 56,
          analyzed_count: 34,
          target_mention_count: 30,
          citation_count: 183,
          last_collected: '2026-05-13',
        },
        analyzer_coverage: {
          eligible_response_count: 56,
          analyzed_response_count: 34,
          missing_response_count: 22,
          analyzer_version: 'v3',
        },
        formula_status: 'partial',
        metric_formula_evidence: {
          visibility: {
            formula_status: 'partial',
            numerator: 0,
            denominator: 56,
            reason_codes: ['missing_analyzer_rows', 'insufficient_coverage'],
          },
          sentiment: {
            formula_status: 'partial',
            reason_codes: ['missing_sentiment_quote'],
          },
          citation: {
            formula_status: 'partial',
            numerator: 0,
            denominator: 183,
            reason_codes: ['unresolved_citation_attribution'],
          },
          pano_geo: {
            formula_status: 'missing',
            reason_codes: ['missing_analyzer_rows'],
            missing_inputs: ['geo_score_daily'],
          },
        },
        missing_inputs: ['missing_analyzer_rows'],
        topics: [
          {
            topic_id: 101,
            topic_name: 'Ingredient safety',
            dimension: 'product',
            associated_brand: 'Acme',
            prompt_count: 75,
            query_count: 464,
            response_count: 56,
            visibility_rate: 0,
            mention_rate: 0,
            sov: 0,
            sentiment_distribution: { positive: 0, neutral: 0, negative: 0 },
            citation_rate: 0,
            citation_count: 183,
            last_collected: '2026-05-13',
            formula_status: 'partial',
            metric_formula_evidence: {
              visibility: {
                formula_status: 'partial',
                numerator: 0,
                denominator: 56,
                reason_codes: ['missing_analyzer_rows', 'insufficient_coverage'],
              },
              sentiment: {
                formula_status: 'partial',
                reason_codes: ['missing_sentiment_quote'],
              },
              citation: {
                formula_status: 'partial',
                numerator: 0,
                denominator: 183,
                reason_codes: ['unresolved_citation_attribution'],
              },
            },
          },
        ],
        intent_matrix: [],
        state: 'ok',
      },
      isLoading: false,
    })

    renderTopicsPage()

    expect(screen.getAllByText('Coverage incomplete').length).toBeGreaterThan(0)
    expect(screen.getAllByText('34 of 56 analyzed').length).toBeGreaterThan(0)
    expect(screen.getAllByText('22 missing').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Analyzer v3').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Analysis coverage missing').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Citation attribution unresolved').length).toBeGreaterThan(0)
    expect(screen.getAllByText('Sentiment quote missing').length).toBeGreaterThan(0)

    const row = screen.getByText('Ingredient safety').closest('tr') as HTMLElement
    expect(within(row).getAllByText('Needs review').length).toBeGreaterThan(0)
    expect(within(row).queryByText('0.0%')).not.toBeInTheDocument()
  })

  it('uses backend visibility_rate ahead of legacy mention or sov fields', () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: {
        summary: {
          topic_count: 1,
          prompt_count: 1,
          query_count: 1,
          response_count: 1,
        },
        topics: [
          {
            topic_id: 101,
            topic_name: 'Ingredient safety',
            dimension: 'product',
            associated_brand: 'Acme',
            prompt_count: 1,
            query_count: 1,
            response_count: 1,
            visibility_rate: 0.83,
            mention_rate: 0.12,
            sov: 0.24,
            sentiment_distribution: { positive: 1, neutral: 0, negative: 0 },
          },
        ],
        intent_matrix: [],
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.useTopicPrompts.mockReturnValue({
      data: {
        items: [
          {
            prompt_id: 201,
            topic_id: 101,
            prompt_text: 'Which serum is safest?',
            intent: 'informational',
            language: 'en',
            query_count: 1,
            response_count: 1,
            visibility_rate: 0.71,
            mention_rate: 0.13,
            sentiment_distribution: { positive: 1, neutral: 0, negative: 0 },
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })

    renderTopicsPage()

    expect(screen.getAllByText('83.0%').length).toBeGreaterThan(0)
    expect(screen.queryByText('24.0%')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('Ingredient safety'))

    expect(screen.getByText('71.0%')).toBeInTheDocument()
    expect(screen.queryByText('13.0%')).not.toBeInTheDocument()
  })

  it('exports backend visibility_rate instead of legacy visibility fields', async () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: {
        summary: {
          topic_count: 1,
          prompt_count: 1,
          query_count: 1,
          response_count: 1,
        },
        topics: [
          {
            topic_id: 101,
            topic_name: 'Ingredient safety',
            dimension: 'product',
            associated_brand: 'Acme',
            prompt_count: 1,
            query_count: 1,
            response_count: 1,
            visibility_rate: 0.83,
            mention_rate: 0.12,
            sov: 0.24,
            sentiment_distribution: { positive: 1, neutral: 0, negative: 0 },
          },
        ],
        intent_matrix: [],
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.useTopicPrompts.mockReturnValue({
      data: {
        items: [
          {
            prompt_id: 201,
            topic_id: 101,
            prompt_text: 'Which serum is safest?',
            intent: 'informational',
            language: 'en',
            query_count: 1,
            response_count: 1,
            visibility_rate: 0.71,
            mention_rate: 0.13,
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })
    const createObjectURL = vi.fn(() => 'blob:topics-export')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: createObjectURL,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectURL,
    })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    renderTopicsPage()

    fireEvent.click(screen.getByRole('button', { name: /Export topics/i }))

    const blob = createObjectURL.mock.calls[0][0] as Blob
    const csv = await readBlobText(blob)
    const dataRow = csv.split('\n').find((line) => line.includes('Ingredient safety')) || ''
    expect(dataRow).toContain('0.83')
    expect(dataRow).not.toContain('0.24')
    expect(dataRow).not.toContain('0.12')

    fireEvent.click(screen.getByText('Ingredient safety'))
    fireEvent.click(screen.getByRole('button', { name: /Export prompts/i }))

    const promptBlob = createObjectURL.mock.calls[1][0] as Blob
    const promptCsv = await readBlobText(promptBlob)
    const promptRow = promptCsv.split('\n').find((line) => line.includes('Which serum is safest?')) || ''
    expect(promptRow).toContain('0.71')
    expect(promptRow).not.toContain('0.13')
  })

  it('does not borrow summary citations for topic rows without per-topic citation counts', () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: {
        summary: {
          topic_count: 1,
          prompt_count: 2,
          query_count: 4,
          response_count: 3,
          analyzed_count: 3,
          target_mention_count: 2,
          citation_count: 987,
          last_collected: '2026-05-11',
        },
        topics: [
          {
            topic_id: 101,
            topic_name: 'Ingredient safety',
            dimension: 'product',
            associated_brand: 'Acme',
            prompt_count: 2,
            query_count: 4,
            response_count: 3,
            mention_rate: 0.67,
            sov: 0.42,
            sentiment_distribution: { positive: 2, neutral: 1, negative: 0 },
            citation_rate: 0.88,
            last_collected: '2026-05-11',
          },
        ],
        intent_matrix: [],
        state: 'ok',
      },
      isLoading: false,
    })

    renderTopicsPage()

    const row = screen.getByText('Ingredient safety').closest('tr') as HTMLElement
    expect(within(row).queryByText('987')).not.toBeInTheDocument()
    expect(within(row).getByText('--')).toBeInTheDocument()
  })

  it('uses product availability copy instead of raw API states', () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: {
        summary: {
          topic_count: 1,
          prompt_count: 0,
          query_count: 0,
          response_count: 0,
        },
        topics: [
          {
            topic_id: 101,
            topic_name: 'Ingredient safety',
            dimension: 'product',
            associated_brand: 'Acme',
            prompt_count: 0,
            query_count: 0,
            response_count: 0,
            sentiment_distribution: { positive: 0, neutral: 0, negative: 0 },
          },
        ],
        intent_matrix: [],
        state: 'partial',
      },
      isLoading: false,
    })

    renderTopicsPage()

    expect(screen.getByText('Limited data')).toBeInTheDocument()
    expect(screen.queryByText(/^partial$/i)).not.toBeInTheDocument()
  })

  it('drills from topics to prompts to query groups and opens the response attempts modal', () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: {
        summary: {
          topic_count: 1,
          prompt_count: 1,
          query_count: 2,
          response_count: 2,
          analyzed_count: 2,
          target_mention_count: 1,
          citation_count: 2,
          last_collected: '2026-05-11',
        },
        topics: [
          {
            topic_id: 101,
            topic_name: 'Ingredient safety',
            dimension: 'product',
            associated_brand: 'Acme',
            prompt_count: 1,
            query_count: 2,
            response_count: 2,
            mention_rate: 0.5,
            sov: 0.5,
            avg_rank: 1,
            avg_geo_score: 0.9,
            sentiment_distribution: { positive: 1, neutral: 1, negative: 0 },
            citation_rate: 0.5,
            last_collected: '2026-05-11',
          },
        ],
        intent_matrix: [],
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.useTopicPrompts.mockReturnValue({
      data: {
        items: [
          {
            prompt_id: 201,
            topic_id: 101,
            prompt_text: 'Which serum is safest for sensitive skin?',
            intent: 'informational',
            language: 'en',
            query_count: 2,
            response_count: 2,
            success_rate: 1,
            engine_coverage: ['chatgpt', 'doubao'],
            mention_rate: 0.5,
            avg_rank: 1,
            avg_geo_score: 0.9,
            citation_rate: 0.5,
            last_collected: '2026-05-11',
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.usePromptQueries.mockReturnValue({
      data: {
        items: [
          {
            query_id: 301,
            prompt_id: 201,
            query_text: 'What is the safest vitamin C serum for sensitive skin?',
            target_llm: 'chatgpt',
            status: 'success',
            profile_id: 'Sensitive skin buyer',
            created_at: '2026-05-10T09:00:00Z',
            executed_at: '2026-05-10T09:00:00Z',
            finished_at: '2026-05-10T09:01:00Z',
            latency_ms: 1200,
            response_id: 401,
            target_mentioned: true,
            citation_count: 2,
            geo_score: 0.9,
            sentiment_score: 0.72,
            query_group_key: 'safest-vitamin-c-sensitive-skin',
            attempt_count: 1,
            daily_latest: [
              {
                query_id: 301,
                prompt_id: 201,
                query_text: 'What is the safest vitamin C serum for sensitive skin?',
                target_llm: 'chatgpt',
                profile_id: 'profile-sensitive',
                profile_name: 'Sensitive skin buyer',
                created_at: '2026-05-10T09:00:00Z',
                executed_at: '2026-05-10T09:00:00Z',
                finished_at: '2026-05-10T09:01:00Z',
                response_id: 401,
                target_mentioned: true,
                citation_count: 2,
                geo_score: 0.9,
                sentiment_score: 0.72,
                date: '2026-05-10',
              },
            ],
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.useQueryResponse.mockReturnValue({
      data: {
        response: {
          response_id: 401,
          target_llm: 'chatgpt',
          created_at: '2026-05-10T09:01:00Z',
          raw_text: 'Use a fragrance-free serum and patch test first.',
        },
        analysis: {
          products: ['Vitamin C serum'],
          features: ['fragrance-free', 'patch test'],
          attributes: ['gentle'],
          relations: ['Acme serum -> sensitive skin'],
          sentiment_drivers: ['gentle positioning'],
        },
        brand_mentions: [
          {
            mention_id: 501,
            brand_name: 'Acme',
            sentiment: 'positive',
            position_rank: 1,
            context_snippet: 'Acme is described as gentle.',
          },
        ],
        citations: [
          {
            citation_id: 601,
            url: 'https://example.com/safety',
            domain: 'example.com',
          },
        ],
        state: 'ok',
      },
      isLoading: false,
    })

    renderTopicsPage()

    fireEvent.click(screen.getByText('Ingredient safety'))

    expect(screen.getByText(/Topic summary/i)).toBeInTheDocument()
    expect(screen.getByText(/2 queries/i)).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: /^Responses$/i })).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('Which serum is safest for sensitive skin?'))

    expect(screen.getByText(/Daily latest successful responses/i)).toBeInTheDocument()
    expect(screen.getByText(/Sensitive skin buyer/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Open response attempts/i }))

    const modal = screen.getByRole('dialog', { name: /Response attempts/i })
    expect(within(modal).getByText(/Attempt 1/i)).toBeInTheDocument()
    expect(within(modal).getByText(/Exact query/i)).toBeInTheDocument()
    expect(within(modal).getByText(/Use a fragrance-free serum and patch test first/i)).toBeInTheDocument()
    expect(within(modal).getByText(/Analyzer facts/i)).toBeInTheDocument()
    expect(within(modal).getByText(/Citations/i)).toBeInTheDocument()
    expect(within(modal).getByText(/Brands/i)).toBeInTheDocument()
    expect(within(modal).getByText(/Products and features/i)).toBeInTheDocument()
    expect(within(modal).getByText(/Response relations/i)).toBeInTheDocument()
    expect(within(modal).getByText(/Sentiment drivers/i)).toBeInTheDocument()
  })

  it('renders current response analyzer facts when future enrichment lists are absent', () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: {
        summary: {
          topic_count: 1,
          prompt_count: 1,
          query_count: 1,
          response_count: 1,
          analyzed_count: 1,
          target_mention_count: 1,
          citation_count: 0,
          last_collected: '2026-05-11',
        },
        topics: [
          {
            topic_id: 101,
            topic_name: 'Ingredient safety',
            dimension: 'product',
            associated_brand: 'Acme',
            prompt_count: 1,
            query_count: 1,
            response_count: 1,
            mention_rate: 1,
            sov: 1,
            sentiment_distribution: { positive: 1, neutral: 0, negative: 0 },
            citation_rate: 0,
            last_collected: '2026-05-11',
          },
        ],
        intent_matrix: [],
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.useTopicPrompts.mockReturnValue({
      data: {
        items: [
          {
            prompt_id: 201,
            topic_id: 101,
            prompt_text: 'Which serum is safest for sensitive skin?',
            intent: 'informational',
            language: 'en',
            query_count: 1,
            response_count: 1,
            success_rate: 1,
            engine_coverage: ['chatgpt'],
            mention_rate: 1,
            avg_rank: 2,
            avg_geo_score: 0.82,
            citation_rate: 0,
            last_collected: '2026-05-11',
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.usePromptQueries.mockReturnValue({
      data: {
        items: [
          {
            query_id: 301,
            prompt_id: 201,
            query_text: 'What is the safest vitamin C serum for sensitive skin?',
            target_llm: 'chatgpt',
            status: 'success',
            profile_id: 'Sensitive skin buyer',
            created_at: '2026-05-10T09:00:00Z',
            executed_at: '2026-05-10T09:00:00Z',
            finished_at: '2026-05-10T09:01:00Z',
            response_id: 401,
            target_mentioned: true,
            citation_count: 0,
            geo_score: 0.82,
            sentiment_score: 0.74,
            query_group_key: 'safest-vitamin-c-sensitive-skin',
            attempt_count: 1,
            daily_latest: [
              {
                query_id: 301,
                prompt_id: 201,
                query_text: 'What is the safest vitamin C serum for sensitive skin?',
                target_llm: 'chatgpt',
                profile_id: 'profile-sensitive',
                profile_name: 'Sensitive skin buyer',
                created_at: '2026-05-10T09:00:00Z',
                executed_at: '2026-05-10T09:00:00Z',
                finished_at: '2026-05-10T09:01:00Z',
                response_id: 401,
                target_mentioned: true,
                citation_count: 0,
                geo_score: 0.82,
                sentiment_score: 0.74,
                date: '2026-05-10',
              },
            ],
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.useQueryResponse.mockReturnValue({
      data: {
        response: {
          response_id: 401,
          target_llm: 'chatgpt',
          created_at: '2026-05-10T09:01:00Z',
          raw_text: 'Acme is mentioned positively for sensitive skin routines.',
        },
        analysis: {
          target_brand_mentioned: true,
          target_brand_rank: 2,
          target_brand_sentiment: 'positive',
          visibility_score: 0.68,
          sentiment_score: 0.74,
          sov_score: 0.5,
          citation_score: 0,
          geo_score: 0.82,
          analyzed_at: '2026-05-10T09:02:00Z',
        },
        brand_mentions: [],
        citations: [],
        state: 'ok',
      },
      isLoading: false,
    })

    renderTopicsPage()

    fireEvent.click(screen.getByText('Ingredient safety'))
    fireEvent.click(screen.getByText('Which serum is safest for sensitive skin?'))
    fireEvent.click(screen.getByRole('button', { name: /Open response attempts/i }))

    const modal = screen.getByRole('dialog', { name: /Response attempts/i })
    expect(within(modal).getByText(/Analyzer summary/i)).toBeInTheDocument()
    expect(within(modal).getByText('Target brand')).toBeInTheDocument()
    expect(within(modal).getByText('Mentioned')).toBeInTheDocument()
    expect(within(modal).getByText('Target rank')).toBeInTheDocument()
    expect(within(modal).getByText('#2')).toBeInTheDocument()
    expect(within(modal).getByText('Visibility score')).toBeInTheDocument()
    expect(within(modal).getByText('68.0')).toBeInTheDocument()
    expect(
      within(modal).getByText(/Product, relation, and driver details are not available for this response yet/i),
    ).toBeInTheDocument()
    expect(
      within(modal).queryByText(/No products, features, or attributes for this response/i),
    ).not.toBeInTheDocument()
  })

  it('sends prompt intent to the backend filters and preserves prompt filters in the URL', () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: {
        summary: {
          topic_count: 1,
          prompt_count: 2,
          query_count: 2,
          response_count: 2,
        },
        topics: [
          {
            topic_id: 101,
            topic_name: 'Ingredient safety',
            dimension: 'product',
            associated_brand: 'Acme',
            prompt_count: 2,
            query_count: 2,
            response_count: 2,
            sentiment_distribution: { positive: 1, neutral: 1, negative: 0 },
          },
        ],
        intent_matrix: [],
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.useTopicPrompts.mockReturnValue({
      data: {
        items: [
          {
            prompt_id: 201,
            topic_id: 101,
            prompt_text: 'Which serum is safest?',
            intent: 'informational',
            language: 'en',
            query_count: 1,
            response_count: 1,
            sentiment_distribution: { positive: 1, neutral: 0, negative: 0 },
          },
          {
            prompt_id: 202,
            topic_id: 101,
            prompt_text: 'Where can I buy the serum?',
            intent: 'commercial',
            language: 'zh',
            query_count: 1,
            response_count: 1,
            sentiment_distribution: { positive: 0, neutral: 1, negative: 0 },
          },
        ],
        total: 2,
        state: 'ok',
      },
      isLoading: false,
    })

    const { getSearch } = renderTopicsPage()

    fireEvent.click(screen.getByText('Ingredient safety'))
    fireEvent.click(screen.getByRole('button', { name: /Commercial/i }))
    fireEvent.click(screen.getByRole('button', { name: 'ZH' }))

    const promptCalls = topicHooks.useTopicPrompts.mock.calls
    const lastPromptCall = promptCalls[promptCalls.length - 1]
    expect(lastPromptCall[1]).toBe(101)
    expect(lastPromptCall[2]).toEqual(
      expect.objectContaining({
        brand_id: 12,
        intent: 'commercial',
      }),
    )
    expect(getSearch()).toContain('promptIntent=commercial')
    expect(getSearch()).toContain('promptLanguage=zh')
    expect(screen.queryByText('Which serum is safest?')).not.toBeInTheDocument()
    expect(screen.getByText('Where can I buy the serum?')).toBeInTheDocument()
  })

  it('renders backend logical query groups with daily_latest rows and explicit profile labels', () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: {
        summary: {
          topic_count: 1,
          prompt_count: 1,
          query_count: 1,
          response_count: 2,
        },
        topics: [
          {
            topic_id: 101,
            topic_name: 'Ingredient safety',
            dimension: 'product',
            associated_brand: 'Acme',
            prompt_count: 1,
            query_count: 1,
            response_count: 2,
            sentiment_distribution: { positive: 1, neutral: 1, negative: 0 },
          },
        ],
        intent_matrix: [],
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.useTopicPrompts.mockReturnValue({
      data: {
        items: [
          {
            prompt_id: 201,
            topic_id: 101,
            prompt_text: 'Which serum is safest?',
            intent: 'informational',
            language: 'en',
            query_count: 1,
            response_count: 2,
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.usePromptQueries.mockReturnValue({
      data: {
        items: [
          {
            query_id: 900,
            prompt_id: 201,
            query_group_key: 'serum-safety',
            query_text: 'Vitamin C serum safety group',
            attempt_count: 3,
            daily_latest: [
              {
                date: '2026-05-10',
                query_id: 301,
                response_id: 401,
                query_text: 'What is the safest vitamin C serum for sensitive skin?',
                target_llm: 'chatgpt',
                profile_id: 'profile-1',
                profile_name: 'Sensitive skin buyer',
                finished_at: '2026-05-10T10:02:00Z',
                response_created_at: '2026-05-10T10:02:30Z',
                response_preview: 'Latest answer recommends a gentle vitamin C serum with dermatologist-backed citations.',
                target_mentioned: true,
                citation_count: 2,
              },
              {
                date: '2026-05-09',
                query_id: 302,
                response_id: 402,
                query_text: 'Which vitamin C serum is safest during pregnancy?',
                target_llm: 'doubao',
                profile_id: null,
                profile_name: 'Unknown profile',
                finished_at: '2026-05-09T10:02:00Z',
                response_created_at: '2026-05-09T10:02:30Z',
                response_preview: 'Earlier answer did not include citations and did not mention the target brand.',
                target_mentioned: false,
                citation_count: 0,
              },
            ],
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })

    renderTopicsPage()

    fireEvent.click(screen.getByText('Ingredient safety'))
    fireEvent.click(screen.getByText('Which serum is safest?'))

    expect(screen.getByText('Vitamin C serum safety group')).toBeInTheDocument()
    expect(
      screen.getByText('What is the safest vitamin C serum for sensitive skin?'),
    ).toBeInTheDocument()
    expect(
      screen.getByText('Which vitamin C serum is safest during pregnancy?'),
    ).toBeInTheDocument()
    expect(screen.getByText('Unique Queries')).toBeInTheDocument()
    expect(screen.getByText('Daily Successful Responses')).toBeInTheDocument()
    expect(screen.getByText('Profiles Covered')).toBeInTheDocument()
    expect(screen.getByText('Citation Coverage')).toBeInTheDocument()
    expect(screen.getByText('Includes Unknown profile')).toBeInTheDocument()
    expect(screen.getByText(/Latest answer recommends a gentle vitamin C serum/i)).toBeInTheDocument()
    expect(screen.getByText(/Earlier answer did not include citations/i)).toBeInTheDocument()
    expect(screen.getByText('2 days')).toBeInTheDocument()
    expect(screen.getByText('Sensitive skin buyer')).toBeInTheDocument()
    expect(screen.getByText('Unknown profile')).toBeInTheDocument()
    expect(screen.getAllByText('2').length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText('All profiles')).not.toBeInTheDocument()
  })

  it('does not reconstruct query groups from legacy raw execution rows without daily_latest', () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: {
        summary: {
          topic_count: 1,
          prompt_count: 1,
          query_count: 1,
          response_count: 1,
        },
        topics: [
          {
            topic_id: 101,
            topic_name: 'Ingredient safety',
            dimension: 'product',
            associated_brand: 'Acme',
            prompt_count: 1,
            query_count: 1,
            response_count: 1,
            sentiment_distribution: { positive: 1, neutral: 0, negative: 0 },
          },
        ],
        intent_matrix: [],
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.useTopicPrompts.mockReturnValue({
      data: {
        items: [
          {
            prompt_id: 201,
            topic_id: 101,
            prompt_text: 'Which serum is safest?',
            intent: 'informational',
            language: 'en',
            query_count: 1,
            response_count: 1,
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.usePromptQueries.mockReturnValue({
      data: {
        items: [
          {
            query_id: 301,
            prompt_id: 201,
            query_text: 'Legacy raw successful execution',
            target_llm: 'chatgpt',
            status: 'success',
            profile_name: 'Leaked profile',
            response_id: 401,
            citation_count: 9,
            finished_at: '2026-05-10T10:02:00Z',
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })

    renderTopicsPage()

    fireEvent.click(screen.getByText('Ingredient safety'))
    fireEvent.click(screen.getByText('Which serum is safest?'))

    expect(screen.getByText(/Query groups are unavailable/i)).toBeInTheDocument()
    expect(screen.queryByText('Legacy raw successful execution')).not.toBeInTheDocument()
    expect(screen.queryByText('Leaked profile')).not.toBeInTheDocument()
    expect(screen.queryByText('9')).not.toBeInTheDocument()
  })

  it('hydrates topic and prompt drilldown from URL params on refresh', () => {
    topicHooks.useTopicMonitoring.mockReturnValue(topicMonitoringState())
    topicHooks.useTopicPrompts.mockReturnValue(topicPromptsState())
    topicHooks.usePromptQueries.mockReturnValue({
      data: {
        items: [
          {
            query_id: 900,
            prompt_id: 201,
            query_group_key: 'serum-safety',
            query_text: 'What is the safest vitamin C serum?',
            attempt_count: 1,
            daily_latest: [
              {
                date: '2026-05-10',
                query_id: 301,
                response_id: 401,
                query_text: 'What is the safest vitamin C serum?',
                target_llm: 'chatgpt',
                profile_id: null,
                profile_name: 'Unknown profile',
                finished_at: '2026-05-10T10:02:00Z',
                target_mentioned: true,
                citation_count: 2,
              },
            ],
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })

    renderTopicsPage('/brand/topics?brandId=12&topicId=101&promptId=201')

    expect(topicHooks.usePromptQueries).toHaveBeenCalledWith(
      liveProjectId,
      201,
      expect.objectContaining({ brand_id: 12 }),
    )
    expect(screen.getByText(/Daily latest successful responses/i)).toBeInTheDocument()
    expect(screen.getByText('Topic: Ingredient safety')).toBeInTheDocument()
    expect(screen.getAllByText('Which serum is safest?').length).toBeGreaterThan(0)
    expect(screen.getByText('Commercial')).toBeInTheDocument()
    expect(screen.getByText('ZH')).toBeInTheDocument()
    expect(screen.queryByText(/Topic 101/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Prompt 201/)).not.toBeInTheDocument()
    expect(screen.queryByText('UNKNOWN')).not.toBeInTheDocument()
    expect(screen.getAllByText('What is the safest vitamin C serum?').length).toBeGreaterThan(0)
    expect(screen.getByText('Unknown profile')).toBeInTheDocument()
  })

  it('exports query previews with the successful daily rows', async () => {
    topicHooks.useTopicMonitoring.mockReturnValue(topicMonitoringState())
    topicHooks.useTopicPrompts.mockReturnValue(topicPromptsState())
    topicHooks.usePromptQueries.mockReturnValue({
      data: {
        items: [
          {
            query_id: 900,
            prompt_id: 201,
            query_group_key: 'serum-safety',
            query_text: 'Vitamin C serum safety group',
            attempt_count: 1,
            daily_latest: [
              {
                date: '2026-05-10',
                query_id: 301,
                response_id: 401,
                query_text: 'What is the safest vitamin C serum for sensitive skin?',
                target_llm: 'chatgpt',
                profile_id: null,
                profile_name: null,
                finished_at: '2026-05-10T10:02:00Z',
                response_created_at: '2026-05-10T10:02:30Z',
                response_preview: 'Preview exported for operators, with comma support.',
                target_mentioned: true,
                citation_count: 2,
              },
            ],
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })
    const createObjectURL = vi.fn(() => 'blob:topics-query-export')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: createObjectURL,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectURL,
    })
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    renderTopicsPage('/brand/topics?brandId=12&topicId=101&promptId=201')

    fireEvent.click(screen.getByRole('button', { name: /Export queries/i }))

    expect(clickSpy).toHaveBeenCalled()
    const blob = createObjectURL.mock.calls[0][0] as Blob
    const csv = await readBlobText(blob)
    expect(csv).toContain('response_preview')
    expect(csv).toContain('What is the safest vitamin C serum for sensitive skin?')
    expect(csv).not.toContain('Vitamin C serum safety group')
    expect(csv).toContain('"Preview exported for operators, with comma support."')
    expect(csv).toContain('response_created_at')
    expect(csv).toContain('Unknown profile')
  })

  it('shows a metadata loading state while URL topic and prompt labels are restoring', () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: null,
      isLoading: true,
      isError: false,
    })
    topicHooks.useTopicPrompts.mockReturnValue({
      data: null,
      isLoading: true,
      isError: false,
    })

    renderTopicsPage('/brand/topics?brandId=12&topicId=101&promptId=201')

    expect(screen.getByText(/Loading drilldown metadata/i)).toBeInTheDocument()
    expect(screen.getByText(/Restoring topic and prompt labels/i)).toBeInTheDocument()
    expect(screen.queryByText(/Daily latest successful responses/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Topic 101/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Prompt 201/)).not.toBeInTheDocument()
    expect(screen.queryByText('UNKNOWN')).not.toBeInTheDocument()
  })

  it('shows an explicit unavailable state when topic metadata API fails', () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
    })
    topicHooks.useTopicPrompts.mockReturnValue(topicPromptsState())

    renderTopicsPage('/brand/topics?brandId=12&topicId=101&promptId=201')

    expect(screen.getByText(/Drilldown metadata unavailable/i)).toBeInTheDocument()
    expect(screen.getByText(/Topic metadata could not be loaded/i)).toBeInTheDocument()
    expect(screen.queryByText(/Topic 101/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Prompt 201/)).not.toBeInTheDocument()
    expect(screen.queryByText('UNKNOWN')).not.toBeInTheDocument()
  })

  it('shows an explicit unavailable state when prompt metadata API fails', () => {
    topicHooks.useTopicMonitoring.mockReturnValue(topicMonitoringState())
    topicHooks.useTopicPrompts.mockReturnValue({
      data: null,
      isLoading: false,
      isError: true,
    })

    renderTopicsPage('/brand/topics?brandId=12&topicId=101&promptId=201')

    expect(screen.getByText(/Drilldown metadata unavailable/i)).toBeInTheDocument()
    expect(screen.getByText(/Prompt metadata could not be loaded/i)).toBeInTheDocument()
    expect(screen.queryByText(/Topic 101/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Prompt 201/)).not.toBeInTheDocument()
    expect(screen.queryByText('UNKNOWN')).not.toBeInTheDocument()
  })

  it('shows unavailable state when topic metadata does not include the requested URL topic', () => {
    topicHooks.useTopicMonitoring.mockReturnValue(topicMonitoringState([]))
    topicHooks.useTopicPrompts.mockReturnValue(topicPromptsState())

    renderTopicsPage('/brand/topics?brandId=12&topicId=101&promptId=201')

    expect(screen.getByText(/Drilldown metadata unavailable/i)).toBeInTheDocument()
    expect(screen.getByText(/Topic metadata could not be loaded/i)).toBeInTheDocument()
    expect(screen.queryByText(/Topic 101/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Prompt 201/)).not.toBeInTheDocument()
    expect(screen.queryByText('UNKNOWN')).not.toBeInTheDocument()
  })

  it('shows unavailable state when prompt metadata does not include the requested URL prompt', () => {
    topicHooks.useTopicMonitoring.mockReturnValue(topicMonitoringState())
    topicHooks.useTopicPrompts.mockReturnValue(topicPromptsState([]))

    renderTopicsPage('/brand/topics?brandId=12&topicId=101&promptId=201')

    expect(screen.getByText(/Drilldown metadata unavailable/i)).toBeInTheDocument()
    expect(screen.getByText(/Prompt metadata could not be loaded/i)).toBeInTheDocument()
    expect(screen.queryByText(/Topic 101/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Prompt 201/)).not.toBeInTheDocument()
    expect(screen.queryByText('UNKNOWN')).not.toBeInTheDocument()
  })

  it('opens response attempts from backend payload, switches attempts, and renders analyzer_facts', () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: {
        summary: {
          topic_count: 1,
          prompt_count: 1,
          query_count: 1,
          response_count: 2,
        },
        topics: [
          {
            topic_id: 101,
            topic_name: 'Ingredient safety',
            dimension: 'product',
            associated_brand: 'Acme',
            prompt_count: 1,
            query_count: 1,
            response_count: 2,
            sentiment_distribution: { positive: 1, neutral: 1, negative: 0 },
          },
        ],
        intent_matrix: [],
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.useTopicPrompts.mockReturnValue({
      data: {
        items: [
          {
            prompt_id: 201,
            topic_id: 101,
            prompt_text: 'Which serum is safest?',
            intent: 'informational',
            language: 'en',
            query_count: 1,
            response_count: 2,
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.usePromptQueries.mockReturnValue({
      data: {
        items: [
          {
            query_id: 900,
            prompt_id: 201,
            query_group_key: 'serum-safety',
            query_text: 'What is the safest vitamin C serum?',
            attempt_count: 2,
            daily_latest: [
              {
                date: '2026-05-10',
                query_id: 301,
                response_id: 401,
                query_text: 'What is the safest vitamin C serum?',
                target_llm: 'chatgpt',
                profile_id: 'profile-1',
                profile_name: 'Sensitive skin buyer',
                finished_at: '2026-05-10T10:02:00Z',
                target_mentioned: true,
                citation_count: 2,
              },
            ],
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.useQueryResponse.mockReturnValue({
      data: {
        query: {
          query_id: 301,
          query_text: 'What is the safest vitamin C serum?',
          profile_name: 'Sensitive skin buyer',
        },
        response: {
          response_id: 401,
          query_id: 301,
          raw_text: 'First answer cites two sources.',
          target_llm: 'chatgpt',
          created_at: '2026-05-10T10:02:00Z',
        },
        analysis: {
          target_brand_mentioned: true,
          visibility_score: 0.9,
        },
        analyzer_facts: {
          citations: [
            { citation_id: 1, response_id: 401, url: 'https://official.example/a', domain: 'official.example' },
            { citation_id: 2, response_id: 401, url: 'https://review.example/b', domain: 'review.example' },
          ],
          brands_mentioned: [
            { mention_id: 1, response_id: 401, brand_name: 'Acme', position_rank: 1, sentiment: 'positive' },
          ],
          products_features_attributes: [
            { feature_id: 1, product_name: 'Vitamin C serum', feature_name: 'fragrance-free' },
          ],
          relations: [
            { source: 'response_analysis', type: 'supports', a_name: 'Acme', b_name: 'Sensitive skin', response_id: 401 },
          ],
          sentiment_drivers: [
            { driver_id: 1, response_id: 401, driver_text: 'Dermatologist backed', polarity: 'positive' },
          ],
        },
        attempts: [
          {
            query_id: 301,
            response_id: 401,
            query_text: 'What is the safest vitamin C serum?',
            target_llm: 'chatgpt',
            profile_name: 'Sensitive skin buyer',
            finished_at: '2026-05-10T10:02:00Z',
            response: {
              response_id: 401,
              query_id: 301,
              raw_text: 'First answer cites two sources.',
              target_llm: 'chatgpt',
              created_at: '2026-05-10T10:02:00Z',
            },
            analysis: { target_brand_mentioned: true, visibility_score: 0.9 },
            analyzer_facts: {
              citations: [
                { citation_id: 1, response_id: 401, url: 'https://official.example/a', domain: 'official.example' },
                { citation_id: 2, response_id: 401, url: 'https://review.example/b', domain: 'review.example' },
              ],
              brands_mentioned: [
                { mention_id: 1, response_id: 401, brand_name: 'Acme', position_rank: 1, sentiment: 'positive' },
              ],
              products_features_attributes: [
                { feature_id: 1, product_name: 'Vitamin C serum', feature_name: 'fragrance-free' },
              ],
              relations: [
                { source: 'response_analysis', type: 'supports', a_name: 'Acme', b_name: 'Sensitive skin', response_id: 401 },
              ],
              sentiment_drivers: [
                { driver_id: 1, response_id: 401, driver_text: 'Dermatologist backed', polarity: 'positive' },
              ],
            },
          },
          {
            query_id: 303,
            response_id: 403,
            query_text: 'What is the safest vitamin C serum?',
            target_llm: 'chatgpt',
            profile_name: 'Sensitive skin buyer',
            finished_at: '2026-05-10T08:02:00Z',
            response: {
              response_id: 403,
              query_id: 303,
              raw_text: 'Earlier answer cites one source.',
              target_llm: 'chatgpt',
              created_at: '2026-05-10T08:02:00Z',
            },
            analysis: { target_brand_mentioned: false, visibility_score: 0.1 },
            analyzer_facts: {
              citations: [
                { citation_id: 3, response_id: 403, url: 'https://earlier.example/c', domain: 'earlier.example' },
              ],
              brands_mentioned: [],
              products_features_attributes: [],
              relations: [],
              sentiment_drivers: [],
            },
          },
        ],
        state: 'ok',
      },
      isLoading: false,
    })

    renderTopicsPage()

    fireEvent.click(screen.getByText('Ingredient safety'))
    fireEvent.click(screen.getByText('Which serum is safest?'))
    fireEvent.click(screen.getByRole('button', { name: /Open response attempts/i }))

    const modal = screen.getByRole('dialog', { name: /Response attempts/i })
    expect(within(modal).getByText('Attempt 2')).toBeInTheDocument()
    expect(within(modal).getByText(/Citations \(2\)/i)).toBeInTheDocument()
    expect(within(modal).getByText('official.example')).toBeInTheDocument()
    expect(within(modal).getByText('Vitamin C serum / fragrance-free')).toBeInTheDocument()
    expect(within(modal).getByText('Acme supports Sensitive skin')).toBeInTheDocument()
    expect(within(modal).getByText('Dermatologist backed')).toBeInTheDocument()

    fireEvent.click(within(modal).getByText('Attempt 2'))

    expect(within(modal).getByText(/Earlier answer cites one source/i)).toBeInTheDocument()
    expect(within(modal).getByText(/Citations \(1\)/i)).toBeInTheDocument()
    expect(within(modal).getByText('earlier.example')).toBeInTheDocument()
  })

  it('uses response contract state for analyzer facts without falling back to empty facts as ok', () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: {
        summary: {
          topic_count: 1,
          prompt_count: 1,
          query_count: 1,
          response_count: 1,
        },
        topics: [
          {
            topic_id: 101,
            topic_name: 'Ingredient safety',
            dimension: 'product',
            associated_brand: 'BestCoffer',
            prompt_count: 1,
            query_count: 1,
            response_count: 1,
            sentiment_distribution: { positive: 0, neutral: 0, negative: 0 },
          },
        ],
        intent_matrix: [],
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.useTopicPrompts.mockReturnValue({
      data: {
        items: [
          {
            prompt_id: 201,
            topic_id: 101,
            prompt_text: 'Which coffee maker has trustworthy citations?',
            intent: 'informational',
            language: 'en',
            query_count: 1,
            response_count: 1,
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.usePromptQueries.mockReturnValue({
      data: {
        items: [
          {
            query_id: 900,
            prompt_id: 201,
            query_text: 'Which coffee maker has trustworthy citations?',
            attempt_count: 1,
            daily_latest: [
              {
                date: '2026-05-13',
                query_id: 301,
                response_id: 401,
                query_text: 'Which coffee maker has trustworthy citations?',
                target_llm: 'chatgpt',
                profile_name: 'Coffee buyer',
                finished_at: '2026-05-13T10:02:00Z',
                citation_count: 0,
              },
            ],
          },
        ],
        total: 1,
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.useQueryResponse.mockReturnValue({
      data: {
        query: {
          query_id: 301,
          query_text: 'Which coffee maker has trustworthy citations?',
          profile_name: 'Coffee buyer',
        },
        response: {
          response_id: 401,
          query_id: 301,
          raw_text: 'BestCoffer is discussed but attribution is incomplete.',
          target_llm: 'chatgpt',
          created_at: '2026-05-13T10:02:00Z',
        },
        analysis: null,
        analyzer_facts: {
          citations: [],
          brands_mentioned: [],
          products_features_attributes: [],
          relations: [],
          sentiment_drivers: [],
        },
        attempts: [],
        state: 'partial',
        formula_status: 'partial',
        selected_filters: {
          project: '95d43022-a5c8-5944-b6d6-34b29faa18b5',
          brand_id: 24,
          from: '2026-05-06',
          to: '2026-05-13',
        },
        analyzer_coverage: {
          eligible_response_count: 56,
          analyzed_response_count: 34,
          missing_response_count: 22,
          analyzer_version: 'v3',
        },
        metric_formula_evidence: {
          analyzer_facts: {
            formula_status: 'partial',
            reason_codes: ['missing_analyzer_rows', 'unresolved_citation_attribution'],
            missing_inputs: ['missing_sentiment_driver_quote'],
            numerator: 34,
            denominator: 56,
          },
        },
        missing_reasons: ['unresolved_citation_attribution'],
      },
      isLoading: false,
    })

    renderTopicsPage('/brand/topics?brandId=24')

    fireEvent.click(screen.getByText('Ingredient safety'))
    fireEvent.click(screen.getByText('Which coffee maker has trustworthy citations?'))
    fireEvent.click(screen.getByRole('button', { name: /Open response attempts/i }))

    expect(topicHooks.useQueryResponse).toHaveBeenCalledWith(
      liveProjectId,
      301,
      expect.objectContaining({ brand_id: 24 }),
    )

    const modal = screen.getByRole('dialog', { name: /Response attempts/i })
    expect(within(modal).getByText('Needs review')).toBeInTheDocument()
    expect(within(modal).getByText('34 of 56 analyzed')).toBeInTheDocument()
    expect(within(modal).getByText('22 missing')).toBeInTheDocument()
    expect(within(modal).getByText('Citation attribution unresolved')).toBeInTheDocument()
    expect(within(modal).getByText('Sentiment quote missing')).toBeInTheDocument()
    expect(within(modal).getByText(/Brand #24/)).toBeInTheDocument()
    expect(within(modal).queryByText(/missing_analyzer_rows/)).not.toBeInTheDocument()
  })

  it('exports the active prompt layer with current filters and visible successful rows', async () => {
    topicHooks.useTopicMonitoring.mockReturnValue({
      data: {
        summary: {
          topic_count: 1,
          prompt_count: 2,
          query_count: 2,
          response_count: 2,
        },
        topics: [
          {
            topic_id: 101,
            topic_name: 'Ingredient safety',
            dimension: 'product',
            associated_brand: 'Acme',
            prompt_count: 2,
            query_count: 2,
            response_count: 2,
            sentiment_distribution: { positive: 1, neutral: 1, negative: 0 },
          },
        ],
        intent_matrix: [],
        state: 'ok',
      },
      isLoading: false,
    })
    topicHooks.useTopicPrompts.mockReturnValue({
      data: {
        items: [
          {
            prompt_id: 201,
            topic_id: 101,
            prompt_text: 'Which serum is safest?',
            intent: 'informational',
            language: 'en',
            query_count: 1,
            response_count: 1,
            citation_count: 0,
          },
          {
            prompt_id: 202,
            topic_id: 101,
            prompt_text: 'Where can I buy the serum?',
            intent: 'commercial',
            language: 'zh',
            query_count: 1,
            response_count: 1,
            citation_count: 2,
          },
        ],
        total: 2,
        state: 'ok',
      },
      isLoading: false,
    })
    const createObjectURL = vi.fn(() => 'blob:topics-export')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: createObjectURL,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectURL,
    })
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    renderTopicsPage()

    fireEvent.click(screen.getByText('Ingredient safety'))
    fireEvent.click(screen.getByRole('button', { name: /Commercial/i }))
    fireEvent.click(screen.getByRole('button', { name: /Export prompts/i }))

    expect(clickSpy).toHaveBeenCalled()
    const blob = createObjectURL.mock.calls[0][0] as Blob
    const csv = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result))
      reader.onerror = reject
      reader.readAsText(blob)
    })
    expect(csv).toContain('layer,prompts')
    expect(csv).toContain('intent,commercial')
    expect(csv).toContain('language,all')
    expect(csv).toContain('Where can I buy the serum?')
    expect(csv).not.toContain('Which serum is safest?')
  })
})
