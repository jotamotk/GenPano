/**
 * E2E for the Post-Login brand-setup flow.
 *
 *   • RequireOnboarded redirects from /brand/overview → /onboarding when
 *     the current user has no Project (`needsOnboarding=true`).
 *   • Searching the brand box invokes /v1/brands/search (debounced).
 *   • Selecting a brand POSTs /v1/projects, then navigates to dashboard.
 *   • Skip flips a sessionStorage flag so the dashboard banner shows
 *     instead of bouncing back to /onboarding.
 *
 * Auth is mocked via localStorage seeding + page.route() — no backend.
 */

import { test, expect, type Page } from '@playwright/test'

import {
  FAKE_BRAND_SEARCH_RESULTS,
  FAKE_PROJECT,
  FAKE_USER,
  FAKE_USER_NEEDS_ONBOARDING,
} from './fixtures'

async function seedTokenOnly(page: Page) {
  // Onboarding flow runs BEFORE a project exists, so we must NOT seed
  // genpano_active_project here — the SPA's ProjectContext bootstraps
  // from /v1/projects/ directly.
  await page.addInitScript(({ token }) => {
    window.localStorage.setItem('genpano_token', token)
  }, { token: 'fake-jwt-token-for-test' })
}

type RouteState = {
  user: typeof FAKE_USER | typeof FAKE_USER_NEEDS_ONBOARDING
  searchResults: typeof FAKE_BRAND_SEARCH_RESULTS
  failCreate: boolean
  searchFails: boolean
  projects: typeof FAKE_PROJECT[]
}

async function installAuthAndApiMocks(
  page: Page,
  state: Partial<RouteState> = {},
) {
  const merged: RouteState = {
    user: state.user ?? FAKE_USER_NEEDS_ONBOARDING,
    searchResults: state.searchResults ?? FAKE_BRAND_SEARCH_RESULTS,
    failCreate: state.failCreate ?? false,
    searchFails: state.searchFails ?? false,
    projects: state.projects ?? [],
  }
  // Mutable holder — needed because /me must return the FRESH user each
  // call (e.g. after createProject succeeds, refreshUser() re-reads /me).
  let currentUser = merged.user
  let currentProjects = merged.projects

  // Playwright route handlers fire in REVERSE registration order — the
  // catch-all goes FIRST so the specific routes registered after it
  // take precedence. Same pattern as chart-pages.spec.ts.
  await page.route('**/api/v1/**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({}),
    })
  })

  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(currentUser),
    })
  })

  await page.route('**/api/v1/projects/', async (route) => {
    if (route.request().method() === 'POST') {
      if (merged.failCreate) {
        await route.fulfill({
          status: 500,
          contentType: 'application/json',
          body: JSON.stringify({
            type: 'about:blank',
            title: 'Internal error',
            status: 500,
            code: 'internal_error',
          }),
        })
        return
      }
      currentProjects = [FAKE_PROJECT]
      currentUser = { ...currentUser, needsOnboarding: false }
      await route.fulfill({
        status: 201,
        contentType: 'application/json',
        body: JSON.stringify(FAKE_PROJECT),
      })
      return
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: currentProjects, total: currentProjects.length }),
    })
  })

  await page.route('**/api/v1/brands/search**', async (route) => {
    if (merged.searchFails) {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ code: 'search_failed' }),
      })
      return
    }
    const url = new URL(route.request().url())
    const q = (url.searchParams.get('q') || '').toLowerCase().trim()
    const items = q
      ? merged.searchResults.filter((b) =>
          b.brandName.toLowerCase().includes(q),
        )
      : []
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items }),
    })
  })
}

test.describe('Post-Login brand-setup flow', () => {
  test.beforeEach(async ({ page }) => {
    await seedTokenOnly(page)
  })

  test('redirects /brand/overview → /onboarding when needsOnboarding=true', async ({ page }) => {
    await installAuthAndApiMocks(page)
    await page.goto('/brand/overview')
    await expect(page).toHaveURL(/\/onboarding$/)
    await expect(page.getByTestId('brand-search-input')).toBeVisible()
  })

  test('shows search results after typing', async ({ page }) => {
    await installAuthAndApiMocks(page)
    await page.goto('/onboarding')
    const input = page.getByTestId('brand-search-input')
    await input.fill('Nike')
    // The first hit appears
    await expect(page.getByTestId('brand-search-hit-1')).toBeVisible()
    await expect(page.getByTestId('brand-search-hit-2')).toBeVisible()
  })

  test('selecting a brand creates project and lands on dashboard', async ({ page }) => {
    await installAuthAndApiMocks(page)
    await page.goto('/onboarding')
    await page.getByTestId('brand-search-input').fill('Nike')
    await page.getByTestId('brand-search-hit-1').click()
    await expect(page).toHaveURL(/\/brand\/overview$/)
    // Banner must NOT show — needsOnboarding flipped to false on /me refresh
    await expect(page.getByTestId('onboarding-banner')).toHaveCount(0)
  })

  test('clicking Skip lands on /brand/overview with banner visible', async ({ page }) => {
    await installAuthAndApiMocks(page)
    await page.goto('/onboarding')
    await page.getByTestId('onboarding-skip').click()
    await expect(page).toHaveURL(/\/brand\/overview$/)
    await expect(page.getByTestId('onboarding-banner')).toBeVisible()
  })

  test('banner CTA returns the user to /onboarding', async ({ page }) => {
    await installAuthAndApiMocks(page)
    await page.goto('/onboarding')
    await page.getByTestId('onboarding-skip').click()
    await expect(page.getByTestId('onboarding-banner-cta')).toBeVisible()
    await page.getByTestId('onboarding-banner-cta').click()
    await expect(page).toHaveURL(/\/onboarding$/)
  })

  test('search with no matches shows empty-state copy', async ({ page }) => {
    await installAuthAndApiMocks(page)
    await page.goto('/onboarding')
    await page.getByTestId('brand-search-input').fill('zzz999')
    await expect(page.getByTestId('brand-search-empty')).toBeVisible()
  })

  test('createProject failure shows toast and stays on /onboarding', async ({ page }) => {
    await installAuthAndApiMocks(page, { failCreate: true })
    page.on('dialog', (dialog) => dialog.accept())
    await page.goto('/onboarding')
    await page.getByTestId('brand-search-input').fill('Nike')
    await page.getByTestId('brand-search-hit-1').click()
    await expect(page).toHaveURL(/\/onboarding$/)
    await expect(page.getByTestId('brand-create-error')).toBeVisible()
  })

  test('already-monitored brand shows ✓ badge', async ({ page }) => {
    await installAuthAndApiMocks(page)
    await page.goto('/onboarding')
    await page.getByTestId('brand-search-input').fill('Adidas')
    await expect(page.getByTestId('brand-search-hit-3')).toBeVisible()
    await expect(
      page.getByTestId('brand-search-hit-3').getByTestId('already-monitoring-badge'),
    ).toBeVisible()
  })

  test('onboarded user is NOT redirected from /brand/overview', async ({ page }) => {
    await installAuthAndApiMocks(page, {
      user: FAKE_USER,
      projects: [FAKE_PROJECT],
    })
    await page.goto('/brand/overview')
    await expect(page).toHaveURL(/\/brand\/overview$/)
    await expect(page.getByTestId('onboarding-banner')).toHaveCount(0)
  })
})
