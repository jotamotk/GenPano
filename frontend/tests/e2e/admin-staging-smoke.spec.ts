import { expect, test, type Page } from '@playwright/test';

import { installAdminErrorGuards } from './admin-fixtures';

const stagingEnabled = process.env.ADMIN_E2E_STAGING === '1';

test.skip(!stagingEnabled, 'Set ADMIN_E2E_STAGING=1 with PLAYWRIGHT_BASE_URL to run the post-CI staging gate.');

const ensureAdminSession = async (page: Page) => {
  await page.goto('/admin/planner-topics', { waitUntil: 'domcontentloaded' });
  const emailInput = page.locator('input[type="email"]').first();
  const passwordInput = page.locator('input[type="password"]').first();
  if (await emailInput.isVisible().catch(() => false)) {
    const email = process.env.ADMIN_E2E_EMAIL || '';
    const password = process.env.ADMIN_E2E_PASSWORD || '';
    test.skip(!email || !password, 'ADMIN_E2E_EMAIL and ADMIN_E2E_PASSWORD are required for staging login.');
    await emailInput.fill(email);
    await passwordInput.fill(password);
    await page.locator('button[type="submit"], form button').first().click();
  }
  await expect(page.getByText('Topic Plan').first()).toBeVisible({ timeout: 30_000 });
};

test('staging Admin core pages have no JS errors or 5xx responses', async ({ page }) => {
  const errors = installAdminErrorGuards(page);
  await ensureAdminSession(page);

  for (const path of [
    '/admin/planner-topics',
    '/admin/planner-prompt-matrix',
    '/admin/planner-query-pool',
    '/admin/planner-llm-extraction',
  ]) {
    await page.goto(path, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('main')).toBeVisible();
  }

  await errors.assertClean();
});

test('optional staging real search-backed Prompt Matrix small sample', async ({ page }) => {
  test.skip(process.env.ADMIN_E2E_REAL_GENERATE !== '1', 'Set ADMIN_E2E_REAL_GENERATE=1 to run real LLM/search generation.');

  const errors = installAdminErrorGuards(page);
  await ensureAdminSession(page);
  await page.goto('/admin/planner-prompt-matrix', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Prompt Matrix').first()).toBeVisible();

  const selectButton = page.getByRole('button', { name: '选择全部匹配' }).first();
  if (await selectButton.isVisible().catch(() => false)) {
    await selectButton.click();
  }
  const generateButton = page.getByRole('button', { name: '生成 Prompt' }).first();
  test.skip(await generateButton.isDisabled().catch(() => true), 'No staging Prompt Matrix topics are available for a small sample run.');
  await generateButton.click({ force: true });

  await expect(page.getByText(/任务|候选|Prompt|失败/).first()).toBeVisible({ timeout: 120_000 });
  await errors.assertClean();
});
