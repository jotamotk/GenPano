import { expect, test } from '@playwright/test';

import { ensureAdminSession } from './admin-auth';
import { installAdminErrorGuards } from './admin-fixtures';

const stagingEnabled = process.env.ADMIN_E2E_STAGING === '1';

test.skip(
  !stagingEnabled,
  'Set ADMIN_E2E_STAGING=1 with PLAYWRIGHT_BASE_URL to run the post-CI staging gate.',
);

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
