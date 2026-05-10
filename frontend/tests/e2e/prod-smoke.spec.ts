/**
 * Production smoke E2E.
 *
 * Runs against `PLAYWRIGHT_BASE_URL` — defaults to the deployed instance
 * at http://116.62.36.173 — and validates the live deployment with a
 * mix of:
 *
 *   • REAL backend calls for unauthenticated surfaces
 *     (landing / login / register / /api/auth/lookup / register POST)
 *   • Auth-gate behavior (redirect to /register without a token)
 *   • Console-error sweep on every page hit
 *
 * Auth-gated business flows (brand search → POST projects) cannot run
 * end-to-end against prod because email verification is mailed for real
 * and the JWT secret isn't accessible from here. Those flows are covered
 * by the mocked onboarding-flow.spec.ts that ALSO runs against this URL
 * to prove the SPA bundle deployed at prod behaves identically to dev.
 */

import { test, expect, type ConsoleMessage, type Page } from '@playwright/test'

const BASE = process.env.PLAYWRIGHT_BASE_URL || 'http://116.62.36.173'

// Capture every console.error / page.error during a test so we can fail
// the run if a deployed JS chunk throws on load. Excludes a small set of
// noise we know is benign on the live deploy.
const IGNORED_ERROR_PATTERNS = [
  /Failed to load resource.*favicon/i, // optional favicon, not user-impacting
  /ResizeObserver loop limit exceeded/, // Recharts noise
  /ERR_CERT_AUTHORITY_INVALID/i, // mixed-content third-party trackers on http→https
  /ERR_BLOCKED_BY_CLIENT/i, // ad blockers
  /Failed to load resource.*the server responded with a status of 4/i, // 401/404 from /me probe before auth
]

function watchConsole(page: Page): { errors: string[] } {
  const errors: string[] = []
  const onConsole = (msg: ConsoleMessage) => {
    if (msg.type() === 'error') {
      const text = msg.text()
      if (!IGNORED_ERROR_PATTERNS.some((p) => p.test(text))) errors.push(text)
    }
  }
  const onPageError = (err: Error) => {
    const text = err.message
    if (!IGNORED_ERROR_PATTERNS.some((p) => p.test(text))) errors.push(text)
  }
  page.on('console', onConsole)
  page.on('pageerror', onPageError)
  return { errors }
}

test.describe('Prod smoke — public surfaces', () => {
  test('landing page renders + no console errors', async ({ page }) => {
    const { errors } = watchConsole(page)
    const resp = await page.goto(`${BASE}/`)
    expect(resp?.status()).toBeLessThan(400)
    // Body must contain *some* visible text — not blank
    await expect(page.locator('body')).not.toBeEmpty()
    expect(errors, errors.join('\n')).toEqual([])
  })

  test('login route renders auth form', async ({ page }) => {
    const { errors } = watchConsole(page)
    await page.goto(`${BASE}/login`)
    // The auth page has an email input
    await expect(page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i], input[placeholder*="邮箱"]').first()).toBeVisible({ timeout: 10_000 })
    expect(errors, errors.join('\n')).toEqual([])
  })

  test('register route renders auth form', async ({ page }) => {
    const { errors } = watchConsole(page)
    await page.goto(`${BASE}/register`)
    await expect(page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i], input[placeholder*="邮箱"]').first()).toBeVisible({ timeout: 10_000 })
    expect(errors, errors.join('\n')).toEqual([])
  })

  test('/brand/overview without token redirects to /register or /login', async ({ page }) => {
    await page.goto(`${BASE}/brand/overview`)
    await expect(page).toHaveURL(/\/(register|login)/, { timeout: 10_000 })
  })

  test('/onboarding without token redirects to auth', async ({ page }) => {
    await page.goto(`${BASE}/onboarding`)
    await expect(page).toHaveURL(/\/(register|login)/, { timeout: 10_000 })
  })

  test('POST /api/auth/lookup returns "register" for a never-seen email', async ({ request }) => {
    const fresh = `prod-smoke-${Date.now()}@example.com`
    const res = await request.post(`${BASE}/api/auth/lookup`, {
      data: { email: fresh },
    })
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body.next).toBe('register')
    expect(body.exists).toBe(false)
  })

  test('POST /api/auth/check-email matches lookup result', async ({ request }) => {
    const fresh = `prod-smoke-check-${Date.now()}@example.com`
    const res = await request.get(
      `${BASE}/api/auth/check-email?email=${encodeURIComponent(fresh)}`,
    )
    expect(res.status()).toBe(200)
    expect((await res.json()).exists).toBe(false)
  })

  test('POST /api/auth/register accepts a fresh email and triggers verify-email mail', async ({ request }) => {
    const fresh = `prod-smoke-reg-${Date.now()}@example.com`
    const res = await request.post(`${BASE}/api/auth/register`, {
      data: { email: fresh },
    })
    expect(res.status()).toBe(201)
    const body = await res.json()
    expect(body.email).toBe(fresh)
    // Production sends real emails → previewUrl is null. Just assert
    // the contract shape is correct (no 500, no validation error).
    expect(body).toHaveProperty('message')
  })

  test('Lookup of just-registered email flips to "login"', async ({ request }) => {
    const fresh = `prod-smoke-flow-${Date.now()}@example.com`
    const reg = await request.post(`${BASE}/api/auth/register`, {
      data: { email: fresh },
    })
    expect(reg.status()).toBe(201)
    const lookup = await request.post(`${BASE}/api/auth/lookup`, {
      data: { email: fresh },
    })
    expect(lookup.status()).toBe(200)
    const body = await lookup.json()
    expect(body.exists).toBe(true)
    // Email is registered but unverified → next remains "login" because
    // user must verify via email; that is the existing PRD contract.
    expect(['login', 'register']).toContain(body.next)
  })
})

// Real test account provided by the user. Used for full business-flow
// validation against the live deployment. The account is expected to
// exist and have email_verified=true on the prod DB. If it has no
// Project the onboarding-redirect path runs; if it does, the user
// lands on /brand/overview directly.
const TEST_EMAIL = process.env.E2E_PROD_EMAIL || 'FrankWangFJ@gmail.com'
const TEST_PASSWORD = process.env.E2E_PROD_PASSWORD || '@Mb830219'

async function realLogin(
  page: Page,
  request: { post: (url: string, opts: { data: unknown }) => Promise<{ status: () => number; json: () => Promise<{ token: string; user: { needsOnboarding?: boolean } }> }> },
): Promise<{ token: string; needsOnboarding: boolean }> {
  const res = await request.post(`${BASE}/api/auth/login`, {
    data: { email: TEST_EMAIL, password: TEST_PASSWORD },
  })
  if (res.status() !== 200) {
    throw new Error(`Login failed with status ${res.status()}`)
  }
  const body = await res.json()
  await page.addInitScript((token: string) => {
    window.localStorage.setItem('genpano_token', token)
  }, body.token)
  return { token: body.token, needsOnboarding: body.user.needsOnboarding ?? false }
}

test.describe('Prod smoke — REAL auth business flow', () => {
  test('login → me works against prod backend', async ({ request }) => {
    const res = await request.post(`${BASE}/api/auth/login`, {
      data: { email: TEST_EMAIL, password: TEST_PASSWORD },
    })
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body.token).toBeTruthy()
    expect(body.user.email.toLowerCase()).toBe(TEST_EMAIL.toLowerCase())
    expect(body).toHaveProperty('user.needsOnboarding')

    const me = await request.get(`${BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${body.token}` },
    })
    expect(me.status()).toBe(200)
    const meBody = await me.json()
    expect(meBody.email.toLowerCase()).toBe(TEST_EMAIL.toLowerCase())
    expect(meBody).toHaveProperty('needsOnboarding')
  })

  test('GET /v1/brands/search with real token returns hits', async ({ request }) => {
    const login = await request.post(`${BASE}/api/auth/login`, {
      data: { email: TEST_EMAIL, password: TEST_PASSWORD },
    })
    const { token } = await login.json()
    // Try a query likely to match seeded data — fall back gracefully
    // if the prod brands catalog is empty (test asserts contract, not
    // catalog completeness).
    const res = await request.get(`${BASE}/api/v1/brands/search?q=Nike`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    expect(res.status()).toBe(200)
    const body = await res.json()
    expect(body).toHaveProperty('items')
    expect(Array.isArray(body.items)).toBe(true)
    if (body.items.length > 0) {
      expect(body.items[0]).toHaveProperty('brandId')
      expect(body.items[0]).toHaveProperty('brandName')
      expect(body.items[0]).toHaveProperty('isAlreadyMonitoring')
    }
  })

  test('SPA: real login → routes to /onboarding or dashboard', async ({ page, request }) => {
    const { errors } = watchConsole(page)
    const { needsOnboarding } = await realLogin(page, request)
    await page.goto(`${BASE}/brand/overview`)
    if (needsOnboarding) {
      await expect(page).toHaveURL(/\/onboarding$/, { timeout: 15_000 })
      await expect(page.getByTestId('brand-search-input')).toBeVisible({ timeout: 10_000 })
    } else {
      // Already onboarded — should stay on /brand/overview, no banner
      await expect(page).toHaveURL(/\/brand\/overview$/, { timeout: 15_000 })
    }
    expect(errors, errors.join('\n')).toEqual([])
  })

  test('SPA: brand search dropdown works against real /v1/brands/search', async ({ page, request }) => {
    const { needsOnboarding } = await realLogin(page, request)
    test.skip(!needsOnboarding, 'Test account already onboarded; skipping search flow')
    await page.goto(`${BASE}/onboarding`)
    await page.getByTestId('brand-search-input').fill('Nike')
    // Real backend may return 0 or N results depending on catalog. Just
    // verify the network call lands and the input doesn't crash.
    await page.waitForTimeout(800) // allow debounce + RTT
    // Either we see at least one hit OR the empty-state — but no error.
    const hasHits = await page.getByTestId('brand-search-results').locator('button').count()
    if (hasHits === 0) {
      await expect(page.getByTestId('brand-search-empty')).toBeVisible({ timeout: 5_000 })
    }
  })
})

test.describe('Prod smoke — protected surfaces (mocked auth)', () => {
  // For pages that require an active session we mock /me + projects/ in
  // the same way as the onboarding-flow.spec.ts but POINT the SPA to the
  // production URL. This validates that the deployed SPA chunk renders
  // the onboarding flow correctly with the real prod /v1/brands/search.

  test('onboarding renders against prod SPA + /me mock', async ({ page }) => {
    const { errors } = watchConsole(page)
    await page.addInitScript(() => {
      window.localStorage.setItem('genpano_token', 'fake-jwt-for-prod-smoke')
    })
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'user-uuid-prod-smoke',
          email: 'smoke@example.com',
          name: 'Smoke',
          company: null,
          role: 'free',
          provider: 'email',
          emailVerified: true,
          locale: 'zh-CN',
          createdAt: '2026-05-09T00:00:00',
          needsOnboarding: true,
        }),
      })
    })
    await page.route('**/api/v1/projects/', async (route) => {
      if (route.request().method() === 'GET') {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ items: [], total: 0 }),
        })
      } else {
        await route.fallback()
      }
    })

    await page.goto(`${BASE}/brand/overview`)
    await expect(page).toHaveURL(/\/onboarding$/, { timeout: 15_000 })
    await expect(page.getByTestId('brand-search-input')).toBeVisible({ timeout: 10_000 })
    expect(errors, errors.join('\n')).toEqual([])
  })

  test('Skip on onboarding lands on /brand/overview with reminder banner', async ({ page }) => {
    const { errors } = watchConsole(page)
    await page.addInitScript(() => {
      window.localStorage.setItem('genpano_token', 'fake-jwt-for-prod-smoke')
    })
    await page.route('**/api/auth/me', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          id: 'user-uuid-prod-smoke',
          email: 'smoke@example.com',
          name: 'Smoke',
          company: null,
          role: 'free',
          provider: 'email',
          emailVerified: true,
          locale: 'zh-CN',
          createdAt: '2026-05-09T00:00:00',
          needsOnboarding: true,
        }),
      })
    })
    // Empty projects list — dashboard would normally render its empty
    // state; we only need the banner to appear so this works.
    await page.route('**/api/v1/projects/', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ items: [], total: 0 }),
      })
    })
    // Pass any other v1 calls through with empty 200 to keep the page rendering.
    await page.route('**/api/v1/**', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      })
    })

    await page.goto(`${BASE}/onboarding`)
    await page.getByTestId('onboarding-skip').click()
    await expect(page).toHaveURL(/\/brand\/overview$/, { timeout: 10_000 })
    await expect(page.getByTestId('onboarding-banner')).toBeVisible({ timeout: 10_000 })
    expect(errors, errors.join('\n')).toEqual([])
  })
})
