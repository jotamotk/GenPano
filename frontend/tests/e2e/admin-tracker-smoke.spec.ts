import { expect, test, type Page, type Response } from '@playwright/test';

import { ensureAdminSession } from './admin-auth';
import { installAdminErrorGuards, normalizeAdminApiPath } from './admin-fixtures';

const stagingEnabled = process.env.ADMIN_E2E_STAGING === '1';
const readOnlyMode = 'read-only Tracker smoke';

test.skip(
  !stagingEnabled,
  'Set ADMIN_E2E_STAGING=1 with PLAYWRIGHT_BASE_URL and Admin credentials to run the read-only Tracker smoke.',
);
test.setTimeout(3 * 60_000);

type TrackerAttemptSnapshot = {
  queryId: string;
  engine: string;
  status: string;
  errorCode: string | null;
  retryReason: string | null;
  accountId: string;
  proxyRegion: string;
  queuedAt: string | null;
  startedAtRaw: string | null;
  finishedAtRaw: string | null;
};

type TrackerStateSnapshot = {
  page: string;
  attemptsLoading: boolean;
  attemptsError: string;
  attemptsLastLoaded: string;
  attemptsTotal: number;
  executionAttemptsLength: number;
  attemptsSummary: {
    total: number;
    success: number;
    failed: number;
    running: number;
    queued: number;
    unqueued: number;
  };
  firstAttempt: TrackerAttemptSnapshot | null;
};

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const normalizeUrlPath = (url: string) => {
  const parsed = new URL(url);
  return {
    parsed,
    path: normalizeAdminApiPath(parsed),
  };
};

const isAdminApiPath = (path: string) => (
  path.startsWith('/api/admin') || path.startsWith('/api/')
);

const isTrackerQueryListResponse = (response: Response) => {
  if (response.request().method() !== 'GET') return false;
  const { parsed, path } = normalizeUrlPath(response.url());
  return path.endsWith('/queries') && parsed.searchParams.get('count') === '1';
};

const installReadOnlyMutationGuard = (page: Page) => {
  const mutationRequests: string[] = [];

  page.on('request', request => {
    const method = request.method().toUpperCase();
    if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') return;

    const { parsed, path } = normalizeUrlPath(request.url());
    if (!isAdminApiPath(path)) return;
    if (method === 'POST' && path.endsWith('/auth/login')) return;

    mutationRequests.push(`${method} ${path}${parsed.search}`);
  });

  return {
    assertReadOnly: () => {
      expect(mutationRequests, `${readOnlyMode} must not call mutating Admin APIs`).toEqual([]);
    },
  };
};

const readTrackerState = async (page: Page): Promise<TrackerStateSnapshot> => {
  return await page.evaluate(() => {
    const body = document.body as HTMLElement & { _x_dataStack?: any[] };
    const app = body._x_dataStack?.[0];
    const rows = Array.isArray(app?.executionAttempts) ? app.executionAttempts : [];
    const summary = app?.attemptsSummary || {};
    const first = rows[0] || null;

    return {
      page: String(app?.page || ''),
      attemptsLoading: Boolean(app?.attemptsLoading),
      attemptsError: String(app?.attemptsError || ''),
      attemptsLastLoaded: app?.attemptsLastLoaded ? String(app.attemptsLastLoaded) : '',
      attemptsTotal: Number(app?.attemptsTotal || 0),
      executionAttemptsLength: rows.length,
      attemptsSummary: {
        total: Number(summary.total || 0),
        success: Number(summary.success || 0),
        failed: Number(summary.failed || 0),
        running: Number(summary.running || 0),
        queued: Number(summary.queued || 0),
        unqueued: Number(summary.unqueued || 0),
      },
      firstAttempt: first
        ? {
            queryId: String(first.queryId || ''),
            engine: String(first.engine || ''),
            status: String(first.status || ''),
            errorCode: first.errorCode ? String(first.errorCode) : null,
            retryReason: first.retryReason ? String(first.retryReason) : null,
            accountId: String(first.accountId || ''),
            proxyRegion: String(first.proxyRegion || ''),
            queuedAt: first.queuedAt ? String(first.queuedAt) : null,
            startedAtRaw: first.startedAtRaw ? String(first.startedAtRaw) : null,
            finishedAtRaw: first.finishedAtRaw ? String(first.finishedAtRaw) : null,
          }
        : null,
    };
  });
};

const waitForTrackerInitialization = async (page: Page) => {
  await page.waitForFunction(() => {
    const body = document.body as HTMLElement & { _x_dataStack?: any[] };
    const app = body._x_dataStack?.[0];
    if (!app || app.page !== 'tracker-attempts') return false;
    if (app.attemptsError) return true;
    return app.attemptsLoading === false
      && Boolean(app.attemptsLastLoaded)
      && Array.isArray(app.executionAttempts);
  }, undefined, { timeout: 60_000 });
};

const statusPatterns: Record<string, RegExp> = {
  success: /成功/,
  failed: /失败/,
  running: /运行中/,
  pending: /待执行/,
  retrying: /重试中/,
  waiting_manual: /待人工/,
  dlq: /DLQ/,
};

test(`${readOnlyMode} loads /admin/tracker-attempts without JS errors, 5xx, or mutation`, async ({ page }) => {
  test.info().annotations.push({
    type: 'mode',
    description: `${readOnlyMode}; mutation disabled; no retry, batch retry, cleanup, or manual dispatch actions are clicked.`,
  });
  console.info(
    `[Admin Tracker smoke] ${readOnlyMode}: mutation disabled; no retry, batch retry, cleanup, or manual dispatch actions will be invoked.`,
  );

  const errors = installAdminErrorGuards(page);
  const readOnlyGuard = installReadOnlyMutationGuard(page);
  await ensureAdminSession(page);

  const queryListResponsePromise = page.waitForResponse(
    isTrackerQueryListResponse,
    { timeout: 60_000 },
  );

  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded', timeout: 60_000 });
  const queryListResponse = await queryListResponsePromise;

  expect(
    queryListResponse.ok(),
    `Tracker query list must return 2xx/3xx, got HTTP ${queryListResponse.status()} at ${queryListResponse.url()}`,
  ).toBeTruthy();

  await expect(page.locator('main')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole('button', { name: 'Attempt 列表' })).toBeVisible();
  await expect(page.locator('main table thead')).toContainText('Query ID');
  await waitForTrackerInitialization(page);

  const state = await readTrackerState(page);
  expect(state.page).toBe('tracker-attempts');
  expect(state.attemptsLoading).toBe(false);
  expect(state.attemptsError, 'Tracker attempts list must initialize without an error banner').toBe('');
  expect(state.attemptsLastLoaded, 'Tracker attempts list must record a completed load timestamp').not.toBe('');
  expect(state.attemptsTotal, 'Tracker smoke must read latest query rows from production').toBeGreaterThan(0);
  expect(state.executionAttemptsLength, 'Tracker table must render at least one latest query row').toBeGreaterThan(0);
  expect(state.attemptsSummary.total, 'Tracker summary total should match the loaded API total').toBe(state.attemptsTotal);
  expect(Number.isFinite(state.attemptsSummary.queued)).toBeTruthy();
  expect(Number.isFinite(state.attemptsSummary.unqueued)).toBeTruthy();
  expect(state.firstAttempt, 'Tracker latest query row must be present').not.toBeNull();

  const firstAttempt = state.firstAttempt!;
  expect(firstAttempt.queryId, 'Latest row must expose a Query ID').toMatch(/^Q-\d+$/);
  expect(firstAttempt.status, 'Latest row must expose an operator-visible status').not.toBe('');
  expect(firstAttempt.engine, 'Latest row must expose an engine label').not.toBe('');
  expect(firstAttempt.accountId, 'Latest row must expose an account/proxy field, even if empty').not.toBe('');

  const row = page.locator('tbody tr', { hasText: firstAttempt.queryId }).first();
  await expect(row, `Latest query ${firstAttempt.queryId} should be visible in the Tracker table`).toBeVisible();
  await expect(row).toContainText(firstAttempt.engine);
  await expect(row).toContainText(firstAttempt.accountId);
  await expect(row).toContainText(
    statusPatterns[firstAttempt.status] || new RegExp(escapeRegExp(firstAttempt.status)),
  );
  if (firstAttempt.errorCode) {
    await expect(row).toContainText(firstAttempt.errorCode);
  }

  await expect(page.locator('main')).toContainText(/总 Query:/);
  await expect(page.locator('main')).toContainText(/未派发:/);

  console.info(
    `[Admin Tracker smoke] ${readOnlyMode} loaded ${state.executionAttemptsLength}/${state.attemptsTotal} rows; latest=${firstAttempt.queryId}; status=${firstAttempt.status}; accountField=${firstAttempt.accountId === '—' ? 'empty' : 'present'}; retryReason=${firstAttempt.errorCode ? 'present' : 'empty'}.`,
  );

  readOnlyGuard.assertReadOnly();
  await errors.assertClean();
});
