import { render } from '@testing-library/react'
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

vi.mock('../components/ui', () => ({
  Badge: ({ children }: { children: ReactNode }) => <span>{children}</span>,
  Button: ({ children }: { children: ReactNode }) => <button>{children}</button>,
  Card: ({ children }: { children: ReactNode }) => <div>{children}</div>,
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
})
