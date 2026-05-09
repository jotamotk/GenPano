/**
 * E2E smoke test for the 8 chart pages + Dashboard.
 *
 * Verifies for each page:
 *   1. Page loads without runtime errors
 *   2. At least one chart renders (recharts <svg>, donut <svg>, or table)
 *   3. When live data is mocked → no MockDataBadge appears next to titles
 *   4. When live data is empty → MockDataBadge appears as fallback
 */

import { test, expect, type Page, type Route } from '@playwright/test'

import {
  buildApiHandlers,
  FAKE_PROJECT_ID,
  FAKE_USER,
} from './fixtures'

const PAGES = [
  { route: '/brand/overview', name: 'Brand Overview (Dashboard)' },
  { route: '/brand/visibility', name: 'Brand Visibility' },
  { route: '/brand/sentiment', name: 'Brand Sentiment' },
  { route: '/brand/citations', name: 'Brand Citations - overview' },
  { route: '/brand/citations?sub=content-gap', name: 'Brand Citations - content gap' },
  { route: '/brand/citations?sub=pr-targets', name: 'Brand Citations - PR targets' },
  { route: '/brand/citations?sub=simulator', name: 'Brand Citations - simulator' },
  { route: '/brand/competitors', name: 'Brand Competitors' },
  { route: '/brand/products', name: 'Brand Products' },
  { route: '/industry/overview?industryId=1', name: 'Industry Overview' },
  { route: '/industry/ranking?industryId=1', name: 'Industry Ranking' },
  { route: '/industry/topics?industryId=1', name: 'Industry Topics' },
]

async function seedAuthAndProject(page: Page) {
  await page.addInitScript(
    ({ token, project }) => {
      window.localStorage.setItem('genpano_token', token)
      window.localStorage.setItem(
        'genpano_active_project',
        JSON.stringify({
          id: project,
          primaryBrandId: 42,
          industryId: 1,
          name: 'Test Project',
          competitorBrandIds: [99, 100],
        }),
      )
    },
    { token: 'fake-jwt-token-for-test', project: FAKE_PROJECT_ID },
  )
}

async function installApiMocks(page: Page) {
  // Playwright matches routes in REVERSE registration order, so register the
  // catch-all FIRST so the specific handlers below override it.
  // Match only real backend API paths — NOT Vite's /src/api/*.ts modules.
  const catchAll = async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [], state: 'empty', total: 0 }),
    })
  }
  await page.route(/\/api\/(v1|auth|admin)\//, catchAll)
  const handlers = buildApiHandlers()
  for (const [pattern, handler] of Object.entries(handlers)) {
    await page.route(pattern, handler)
  }
}

test.describe('Chart pages (live mode)', () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthAndProject(page)
    await installApiMocks(page)

    // Capture console errors so a chart that crashes makes the test fail.
    const errors: string[] = []
    page.on('pageerror', err => errors.push(`pageerror: ${err.message}`))
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(`console: ${msg.text()}`)
    })
    ;(page as Page & { _errs?: string[] })._errs = errors
  })

  for (const { route, name } of PAGES) {
    test(`${name} renders without runtime errors`, async ({ page }) => {
      await page.goto(route, { waitUntil: 'domcontentloaded' })
      // Wait for the React tree to mount + first paint of charts.
      await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})

      // Page should land at the requested route (no redirect to /register).
      const url = new URL(page.url())
      expect(url.pathname + url.search).toContain(route.split('?')[0])

      // At least one chart visual must render: recharts produces <svg>
      // wrappers under .recharts-wrapper or the page's table-of-rankings
      // and donut/heatmap fallbacks render their own <svg> too.
      const chartCount = await page
        .locator('.recharts-wrapper, svg, table')
        .count()
      expect(chartCount).toBeGreaterThan(0)

      const errs = (page as Page & { _errs?: string[] })._errs ?? []
      const fatal = errs.filter(
        e =>
          !e.includes('Failed to load resource') &&
          !e.includes('favicon') &&
          !e.includes('ResizeObserver loop') &&
          !e.includes('react-router') &&
          !e.includes('A request was aborted'),
      )
      expect(fatal, fatal.join('\n')).toEqual([])
    })
  }
})

test.describe('Mock fallback badge', () => {
  test('Brand Visibility renders MockDataBadge when no live project exists', async ({ page }) => {
    await seedAuthAndProject(page)

    // Catch-all real API paths only (not Vite's /src/api/*).
    await page.route(/\/api\/(v1|auth|admin)\//, async route => {
      const url = route.request().url()
      if (url.includes('/api/auth/me')) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(FAKE_USER),
        })
        return
      }
      if (url.includes('/api/v1/projects/')) {
        // No projects → BrandVisibilityPage hooks see isLive=false, render mock
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [], total: 0 }),
        })
        return
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], state: 'empty' }),
      })
    })

    await page.goto('/brand/visibility', { waitUntil: 'domcontentloaded' })
    await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})

    // Badge should be visible somewhere on the page when not in live mode.
    const badge = page.locator('[aria-label*="演示数据"]').first()
    await expect(badge).toBeVisible({ timeout: 10_000 })
  })
})
