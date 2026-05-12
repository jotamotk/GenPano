import { expect, test, type Page, type Route } from '@playwright/test'

import {
  buildApiHandlers,
  FAKE_PROJECT_ID,
} from './fixtures'

async function seedAuth(page: Page) {
  await page.addInitScript(
    ({ token, project }) => {
      window.localStorage.setItem('genpano_token', token)
      window.localStorage.setItem(
        'genpano_active_project',
        JSON.stringify({
          id: project,
          primaryBrandId: 42,
          industryId: 1,
          name: 'Analyzer Contract Test Project',
          competitorBrandIds: [99, 100],
        }),
      )
    },
    { token: 'fake-jwt-token-for-test', project: FAKE_PROJECT_ID },
  )
}

async function installApiMocks(page: Page) {
  await page.route(/\/api\/(v1|auth|admin)\//, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], state: 'empty', total: 0 }),
    })
  })

  const handlers = buildApiHandlers()
  for (const [pattern, handler] of Object.entries(handlers)) {
    await page.route(pattern, handler)
  }
}

test('App analyzer contract route renders the chart matrix', async ({ page }) => {
  await seedAuth(page)
  await installApiMocks(page)

  await page.goto('/brand/analyzer-contract', { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})

  await expect(page).toHaveURL(/\/brand\/analyzer-contract/)
  await expect(page.getByRole('heading', { name: /Analyzer chart data contract/i })).toBeVisible()
  await expect(page.getByText('SoV reset rule')).toBeVisible()
  await expect(page.getByText('Sentiment reset rule')).toBeVisible()
  await expect(page.getByRole('table')).toBeVisible()
  await expect(page.getByText('Competitor quadrant')).toBeVisible()
  await expect(page.getByText('Product BCG quadrant')).toBeVisible()

  await page.screenshot({
    path: test.info().outputPath('app-analyzer-contract-matrix.png'),
    fullPage: true,
  })
})
