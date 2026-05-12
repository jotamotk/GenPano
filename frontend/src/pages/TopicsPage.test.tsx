import { fireEvent, render, screen, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

describe('TopicsPage live brand override', () => {
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
    render(
      <MemoryRouter initialEntries={['/brand/topics?brandId=12']}>
        <TopicsPage />
      </MemoryRouter>,
    )

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
    render(
      <MemoryRouter initialEntries={['/brand/topics?brandId=12']}>
        <TopicsPage />
      </MemoryRouter>,
    )

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

    render(
      <MemoryRouter initialEntries={['/brand/topics?brandId=12']}>
        <TopicsPage />
      </MemoryRouter>,
    )

    expect(screen.getByText(/Successful responses/i)).toBeInTheDocument()
    expect(screen.getByText(/Analyzed answers/i)).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Visibility/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Sentiment/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: /Citations/i })).toBeInTheDocument()
    expect(screen.getByText('Ingredient safety')).toBeInTheDocument()
    expect(screen.getByText('42.0%')).toBeInTheDocument()
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

    render(
      <MemoryRouter initialEntries={['/brand/topics?brandId=12']}>
        <TopicsPage />
      </MemoryRouter>,
    )

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
})
