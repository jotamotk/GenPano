import { expect, test, type Page } from '@playwright/test';

import {
  fulfillJson,
  installAdminDocumentRoute,
  installAdminErrorGuards,
  normalizeAdminApiPath,
} from './admin-fixtures';

type RetryScenario = 'dispatched' | 'dispatch-failed' | 'api-error';

const queryId = 185003;

const makeQueryRow = (overrides: Record<string, unknown> = {}) => ({
  id: queryId,
  target_llm: 'doubao',
  status: 'failed',
  query_text: '请用豆包回答某品牌口碑趋势',
  brand_id: 12,
  profile_id: 'profile-1',
  account_id: 7,
  created_at: '2026-05-11T10:50:00Z',
  executed_at: '2026-05-11T10:56:00Z',
  retry_count: 0,
  queued_at: '2026-05-11T10:55:00Z',
  started_at: '2026-05-11T10:55:10Z',
  finished_at: '2026-05-11T10:56:20Z',
  latency_ms: 70000,
  retry_reason: 'doubao previous_error',
  prompt_id: 501,
  prompt_text: '豆包品牌趋势 Prompt',
  topic_id: 301,
  topic_text: '品牌趋势',
  response: '',
  citations: null,
  profile_name: 'Segment A',
  profile_country: 'CN',
  account_label: 'ACC-007',
  ...overrides,
});

const installTrackerRoutes = async (page: Page, scenario: RetryScenario) => {
  let accepted = false;
  let readsAfterRetry = 0;

  const currentRow = () => {
    if (!accepted) return makeQueryRow();
    if (scenario === 'dispatch-failed') {
      return makeQueryRow({
        status: 'pending',
        retry_count: 1,
        queued_at: '2026-05-11T10:57:39Z',
        started_at: null,
        finished_at: null,
        latency_ms: null,
        retry_reason: 'manual retry from admin',
      });
    }
    readsAfterRetry += 1;
    if (readsAfterRetry <= 2) {
      return makeQueryRow({
        status: 'pending',
        retry_count: 1,
        queued_at: '2026-05-11T10:57:39Z',
        started_at: null,
        finished_at: null,
        latency_ms: null,
        retry_reason: 'manual retry from admin',
      });
    }
    return makeQueryRow({
      status: 'failed',
      retry_count: 1,
      queued_at: '2026-05-11T10:57:39Z',
      started_at: '2026-05-11T10:57:45Z',
      finished_at: '2026-05-11T10:58:11Z',
      latency_ms: 26000,
      retry_reason: 'doubao no_response',
    });
  };

  await page.route(/.*\/(?:api\/admin|admin\/api)(?:\/.*)?/, async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = normalizeAdminApiPath(url);
    const method = request.method();

    if (method === 'GET' && path.endsWith('/auth/session')) {
      await fulfillJson(route, {
        authenticated: true,
        admin: { id: 'admin-tracker-e2e', email: 'tracker@example.test' },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/analyzer/brands')) {
      await fulfillJson(route, []);
      return;
    }

    if (method === 'GET' && path.endsWith('/queries')) {
      const row = currentRow();
      await fulfillJson(route, {
        rows: [row],
        total: 1,
        by_status: { [String(row.status)]: 1 },
      });
      return;
    }

    if (method === 'POST' && path.endsWith(`/queries/${queryId}/retry`)) {
      if (scenario === 'api-error') {
        await fulfillJson(route, { success: false, error: 'retry rejected by backend' }, 400);
        return;
      }
      accepted = true;
      readsAfterRetry = 0;
      await fulfillJson(route, { success: true, dispatched: scenario === 'dispatched' });
      return;
    }

    await fulfillJson(route, {});
  });
};

test('Admin Tracker retry treats HTTP 200 as accepted, refreshes detail, and shows the later failed reason', async ({ page }) => {
  await installAdminDocumentRoute(page);
  await installTrackerRoutes(page, 'dispatched');
  const errors = installAdminErrorGuards(page);

  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded' });
  const row = page.locator('tbody tr', { hasText: `Q-${queryId}` });
  await expect(row).toContainText('doubao previous_error');

  await row.getByRole('button', { name: '详情' }).click();
  await page.getByRole('button', { name: '重试此 Query' }).click();

  await expect(page.getByText(`已提交重试，已重新派发 · query #${queryId}`)).toBeVisible();
  await expect(page.getByText(/已入队 retry/)).toHaveCount(0);
  await expect(row).toContainText('待执行');
  await expect(page.getByText('retry_reason').locator('..')).toContainText('manual retry from admin');

  await expect(row).toContainText('doubao no_response', { timeout: 8_000 });
  await expect(page.getByText('retry_reason').locator('..')).toContainText('doubao no_response');
  await errors.assertClean();
});

test('Admin Tracker retry warns when the retry reset is accepted but dispatch fails', async ({ page }) => {
  await installAdminDocumentRoute(page);
  await installTrackerRoutes(page, 'dispatch-failed');
  const errors = installAdminErrorGuards(page);

  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded' });
  const row = page.locator('tbody tr', { hasText: `Q-${queryId}` });
  await row.getByRole('button', { name: '重试' }).click();

  await expect(page.getByText(`已重置但未派发 · query #${queryId}`)).toBeVisible();
  await expect(page.getByText(/已入队 retry/)).toHaveCount(0);
  await expect(row).toContainText('待执行');
  await errors.assertClean();
});

test('Admin Tracker retry keeps the failed row unchanged when the API rejects retry', async ({ page }) => {
  await installAdminDocumentRoute(page);
  await installTrackerRoutes(page, 'api-error');
  const errors = installAdminErrorGuards(page, {
    allowedNetworkErrorUrls: [/\/queries\/185003\/retry/],
  });

  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded' });
  const row = page.locator('tbody tr', { hasText: `Q-${queryId}` });
  await row.getByRole('button', { name: '重试' }).click();

  await expect(page.getByText('重试失败: retry rejected by backend')).toBeVisible();
  await expect(row).toContainText('失败');
  await expect(row).toContainText('doubao previous_error');
  await errors.assertClean();
});
