import { expect, test, type Page, type Route } from '@playwright/test'

import { buildApiHandlers, FAKE_USER } from './fixtures'

const BESTCOFFER_BRAND_ID = 24
const BESTCOFFER_PROJECT_ID = '6cdf6713-aba0-4517-87b1-0487f1d36df7'

async function json(route: Route, data: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(data),
  })
}

async function seedAuth(page: Page) {
  await page.addInitScript(
    ({ projectId, brandId }) => {
      window.localStorage.setItem('genpano_token', 'fake-jwt-token-for-test')
      window.localStorage.setItem('genpano_lang', 'en-US')
      window.localStorage.setItem(
        'genpano_active_project',
        JSON.stringify({
          id: projectId,
          primaryBrandId: null,
          industryId: null,
          name: 'BestCoffer brand-switch project',
          competitorBrandIds: [],
        }),
      )
      window.localStorage.setItem('genpano_active_brand_id', String(brandId))
    },
    { projectId: BESTCOFFER_PROJECT_ID, brandId: BESTCOFFER_BRAND_ID },
  )
}

async function installApiMocks(page: Page) {
  await page.route(/\/api\/(v1|auth|admin)\//, async (route: Route) => {
    await json(route, { items: [], state: 'empty', total: 0 })
  })

  const handlers = buildApiHandlers()
  for (const [pattern, handler] of Object.entries(handlers)) {
    await page.route(pattern, handler)
  }

  const project = {
    id: BESTCOFFER_PROJECT_ID,
    user_id: FAKE_USER.id,
    name: 'BestCoffer brand-switch project',
    industry_id: null,
    primary_brand_id: null,
    competitor_brand_ids: [],
    preferences: {},
    created_at: '2026-05-12T00:00:00',
    updated_at: '2026-05-12T00:00:00',
    competitors: [],
  }

  await page.route('**/api/auth/me', async route => {
    await json(route, { ...FAKE_USER, needsOnboarding: false })
  })
  await page.route('**/api/v1/projects/', async route => {
    await json(route, { items: [project], total: 1 })
  })
  await page.route(`**/api/v1/projects/${BESTCOFFER_PROJECT_ID}`, async route => {
    await json(route, project)
  })
  await page.route(`**/api/v1/projects/${BESTCOFFER_PROJECT_ID}/overview**`, async route => {
    await json(route, {
      project_id: BESTCOFFER_PROJECT_ID,
      brand_id: BESTCOFFER_BRAND_ID,
      brand_name: 'BestCoffer',
      industry_id: null,
      period: { from: '2026-04-24', to: '2026-05-12' },
      kpi_cards: [],
      geo_score_30d: [],
      sov_30d: [],
      sentiment_30d: [],
      top_prompts: [],
      same_group_shared_domains: [],
      state: 'empty',
      state_reason: 'no_aggregate_rows',
      state_detail: 'Admin collection exists, but App aggregate rows are missing.',
      project_scope: {
        exists: true,
        project_id: BESTCOFFER_PROJECT_ID,
        requested_brand_id: BESTCOFFER_BRAND_ID,
        primary_brand_id: null,
        competitor_brand_ids: [],
        missing_reason: 'project_unbound',
      },
      missing_sources: ['geo_score_daily'],
      missing_reasons: ['analysis_missing', 'no_aggregate_rows'],
      evidence_counts: {
        topic_count: 13,
        prompt_count: 75,
        query_count: 464,
        response_count: 55,
        analysis_row_count: 0,
        brand_mention_row_count: 0,
        citation_row_count: 0,
        geo_score_daily_row_count: 0,
      },
      request_id: 'issue-684-bestcoffer-fixture',
    })
  })
}

test('issue #684 renders BestCoffer brand switch state contract', async ({ page }) => {
  await seedAuth(page)
  await installApiMocks(page)

  await page.goto(`/brand/overview?brandId=${BESTCOFFER_BRAND_ID}`, {
    waitUntil: 'domcontentloaded',
  })
  await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})

  const panel = page.getByTestId('brand-switch-state-contract')
  await expect(panel).toBeVisible()
  await expect(panel).toContainText('brand_id=24')
  await expect(panel).toContainText('project_unbound')
  await expect(panel).toContainText('analysis_missing')
  await expect(panel).toContainText('no_aggregate_rows')
  await expect(page.getByTestId('brand-switch-state-overview')).toContainText('project_unbound')
  await expect(page.getByTestId('brand-switch-state-visibility')).toContainText('no_aggregate_rows')
  await expect(page.getByTestId('brand-switch-state-topics')).toContainText('analysis_missing')
  await expect(page.getByTestId('brand-switch-state-sentiment')).toContainText('analysis_missing')
  await expect(page.getByTestId('brand-switch-state-citations')).toContainText('analysis_missing')
  await expect(page.getByTestId('brand-switch-state-competitors')).toContainText('project_unbound')
  await expect(page.getByTestId('brand-switch-state-pano-trend')).toContainText('no_aggregate_rows')
  await expect(page.getByTestId('brand-switch-evidence')).toContainText('responses 55')
  await expect(page.getByTestId('brand-switch-evidence')).toContainText('geo_score_daily rows 0')

  await page.screenshot({
    path: test.info().outputPath('issue-684-bestcoffer-state-contract.png'),
    fullPage: true,
  })
})
