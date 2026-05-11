import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.localStorage.setItem('genpano_token', 'issue-482-visualization-token')
  })

  await page.route('**/api/auth/me', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        id: 'issue-482-user',
        email: 'issue-482@example.com',
        name: 'Issue 482',
        needsOnboarding: false,
      }),
    })
  })

  await page.route('**/api/v1/projects/', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify([]),
    })
  })
})

test('renders issue 482 analytics visualization contract', async ({ page }, testInfo) => {
  await page.goto('/brand/overview?viz=analytics-contract')

  const contract = page.getByTestId('analytics-visualization-contract')
  await expect(contract).toBeVisible()
  await expect(contract.getByText('App analytics visualization contract')).toBeVisible()
  await expect(
    contract.locator('p', { hasText: '70 brand-mentioned responses / 432 non-brand category responses' }),
  ).toBeVisible()
  await expect(
    contract.locator('p', { hasText: '70 Estee Lauder mentions / 182 competitive-set brand mentions' }),
  ).toBeVisible()
  await expect(contract.getByText('Partial: identity path blocker')).toBeVisible()
  await expect(
    contract.locator('p', { hasText: 'projects where primary_brand_id=12 or project name matches 雅诗兰黛: 0 rows' }),
  ).toBeVisible()
  await expect(contract.getByText('kpi_cards[].value_scale')).toBeVisible()

  const screenshot = await page.screenshot({ fullPage: true })
  await testInfo.attach('issue-482-analytics-contract', {
    body: screenshot,
    contentType: 'image/png',
  })
})
