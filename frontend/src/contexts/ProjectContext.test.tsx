/**
 * ProjectContext URL-aware override test — Epic #1175.
 *
 * Asserts the context-level fix that resolves the dual-identity bug:
 * when the URL carries `?brandId=<int>` and a live project owns that
 * brand, `useProject().activeProject` MUST return that project even
 * when the user-click-driven `activeProjectId` points elsewhere.
 *
 * This is the canonical test for the bug class — the per-page
 * patches (#1204, #1229) became unnecessary once the context itself
 * became URL-aware (AGENTS.md Hard Rule 4 — same fixture pattern as
 * production tests `11111111-...` for BestCoffer, `22222222-...` for
 * Estée).
 */
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

import { LocaleProvider } from './LocaleContext'
import { ProjectProvider, useProject } from './ProjectContext'

const bestCofferProjectId = '11111111-1111-4111-8111-111111111111'
const esteeProjectId = '22222222-2222-4222-8222-222222222222'

// AuthContext consumer in ProjectProvider only needs { token } to gate
// the live useProjects() fetch. We mock useAuth to surface a token so
// the live-mode branch runs.
vi.mock('./AuthContext', () => ({
  useAuth: () => ({ token: 'test-token' }),
}))

// useProjects returns the same two-project fixture as
// DashboardPage.project-context.test.tsx and
// BrandSentimentPage.project-context.test.tsx so that the assertion
// pattern matches across the suite.
//
// CRITICAL: the fixture object MUST be hoisted and stable across calls.
// The real react-query useProjects() returns reference-stable data; if
// the mock returns a fresh object/array each call, ProjectProvider's
// "sync mockProjects from liveProjects" useEffect fires forever and
// the test hangs.
const liveProjectsFixture = vi.hoisted(() => ({
  data: [
    {
      id: '11111111-1111-4111-8111-111111111111',
      name: 'BestCoffer App Analytics',
      primary_brand_id: 24,
      industry_id: 3,
      competitors: [],
    },
    {
      id: '22222222-2222-4222-8222-222222222222',
      name: 'Estée Lauder App Analytics',
      primary_brand_id: 12,
      industry_id: 7,
      competitors: [],
    },
  ],
}))

vi.mock('../hooks/useProjects', async () => {
  const actual =
    await vi.importActual<typeof import('../hooks/useProjects')>(
      '../hooks/useProjects',
    )
  return {
    ...actual,
    useProjects: () => liveProjectsFixture,
  }
})

function ActiveProjectProbe({
  capture,
}: {
  capture: (value: ReturnType<typeof useProject>['activeProject']) => void
}) {
  const { activeProject } = useProject()
  capture(activeProject)
  return null
}

function renderProvider(initialEntry: string) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  let captured: ReturnType<typeof useProject>['activeProject'] = null
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <LocaleProvider initialLocale="en-US">
          <ProjectProvider>
            <ActiveProjectProbe capture={(v) => { captured = v }} />
          </ProjectProvider>
        </LocaleProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return captured
}

describe('ProjectContext URL-aware activeProject override (Epic #1175)', () => {
  it('overrides activeProject to the Estée project when URL carries brandId=12', () => {
    const activeProject = renderProvider(
      '/brand/sentiment?brandId=12&range=30d&profileGroup=all',
    )

    // The URL says brandId=12 → Estée owns brand 12 → activeProject must
    // be the Estée project, NOT the default (which would be BestCoffer
    // because it's the first row in the fixture).
    expect(activeProject).not.toBeNull()
    expect(activeProject?.id).toBe(esteeProjectId)
    expect(activeProject?.id).not.toBe(bestCofferProjectId)
    expect(activeProject?.name).toContain('Estée Lauder')
  })

  it('falls back to the default activeProject when URL has no brandId', () => {
    const activeProject = renderProvider('/brand/sentiment')

    // No URL override → use the user-click-driven state, which defaults
    // to the first live project (BestCoffer in this fixture).
    expect(activeProject).not.toBeNull()
    expect(activeProject?.id).toBe(bestCofferProjectId)
  })

  it('falls back to the default activeProject when URL brandId is not owned by any live project', () => {
    const activeProject = renderProvider('/brand/sentiment?brandId=999')

    // brandId=999 is not owned by any live project → fall through to
    // the user-click default (BestCoffer).
    expect(activeProject).not.toBeNull()
    expect(activeProject?.id).toBe(bestCofferProjectId)
  })
})
