import { expect, test, type Page, type Response } from '@playwright/test';

import { ensureAdminSession } from './admin-auth';
import { installAdminErrorGuards, normalizeAdminApiPath } from './admin-fixtures';

const stagingEnabled = process.env.ADMIN_E2E_STAGING === '1';
const retryQueryIdInput = (process.env.ADMIN_E2E_TRACKER_RETRY_QUERY_ID || '').trim();
const expectedEngineInput = (process.env.ADMIN_E2E_TRACKER_RETRY_EXPECTED_ENGINE || '').trim();
const pollSeconds = Math.max(
  15,
  Math.min(180, Number(process.env.ADMIN_E2E_TRACKER_RETRY_POLL_SECONDS || 90) || 90),
);

const mutationMode = 'controlled live Tracker retry mutation';
const quotaExhaustedReason = 'account_daily_limit_exhausted';

type ApiResult = {
  ok: boolean;
  status: number;
  body: any;
  url: string;
};

type QueryRow = {
  id: number | string;
  status?: string | null;
  target_llm?: string | null;
  retry_count?: number | string | null;
  retry_reason?: string | null;
  error_code?: string | null;
};

test.skip(
  !stagingEnabled || !retryQueryIdInput,
  'Set ADMIN_E2E_STAGING=1 and ADMIN_E2E_TRACKER_RETRY_QUERY_ID to run the opt-in live Tracker retry mutation.',
);
test.setTimeout((pollSeconds + 90) * 1000);

const parseRetryQueryId = () => {
  const queryId = Number(retryQueryIdInput);
  if (!Number.isInteger(queryId) || queryId <= 0) {
    throw new Error(`ADMIN_E2E_TRACKER_RETRY_QUERY_ID must be a positive integer, got "${retryQueryIdInput}".`);
  }
  return queryId;
};

const adminApi = async (page: Page, path: string, options: RequestInit = {}): Promise<ApiResult> => {
  return await page.evaluate(
    async ({ path, options }) => {
      const response = await fetch(`/admin/api${path}`, {
        credentials: 'same-origin',
        ...options,
        headers: {
          'content-type': 'application/json',
          ...(options.headers || {}),
        },
      });
      const text = await response.text();
      let body: any = null;
      try {
        body = text ? JSON.parse(text) : null;
      } catch {
        body = { raw: text };
      }
      return {
        ok: response.ok,
        status: response.status,
        body,
        url: response.url,
      };
    },
    { path, options },
  );
};

const rowsFromQueryBody = (body: any): QueryRow[] => (
  Array.isArray(body) ? body : Array.isArray(body?.rows) ? body.rows : []
);

const readSingleQuery = async (page: Page, queryId: number, count = '1') => {
  const result = await adminApi(page, `/queries?id=${queryId}&count=${count}&limit=1&offset=0`);
  if (!result.ok) {
    throw new Error(`GET ${result.url} failed with HTTP ${result.status}: ${JSON.stringify(result.body).slice(0, 500)}`);
  }
  const rows = rowsFromQueryBody(result.body);
  if (rows.length !== 1) {
    throw new Error(`Preflight for query ${queryId} expected exactly one row, got ${rows.length}. Body=${JSON.stringify(result.body).slice(0, 1000)}`);
  }
  const total = result.body && result.body.total != null ? Number(result.body.total) : rows.length;
  if (count === '1' && total !== 1) {
    throw new Error(`Preflight for query ${queryId} expected total=1, got ${total}. Body=${JSON.stringify(result.body).slice(0, 1000)}`);
  }
  return rows[0];
};

const querySnapshot = (queryId: number, row: QueryRow) => ({
  queryId,
  status: String(row.status || ''),
  retryCount: row.retry_count == null ? null : Number(row.retry_count),
  targetLlm: String(row.target_llm || ''),
  retryReason: String(row.retry_reason || row.error_code || ''),
});

const assertNotQuotaExhausted = (snapshot: ReturnType<typeof querySnapshot>) => {
  if (snapshot.retryReason.toLowerCase().includes(quotaExhaustedReason)) {
    throw new Error(
      `Controlled retry for query ${snapshot.queryId} hit ${quotaExhaustedReason}: ` +
      `status=${snapshot.status}; retry_count=${snapshot.retryCount}; target_llm=${snapshot.targetLlm}; retry_reason=${snapshot.retryReason}`,
    );
  }
};

const isRetryResponse = (queryId: number) => (response: Response) => {
  if (response.request().method() !== 'POST') return false;
  const path = normalizeAdminApiPath(new URL(response.url()));
  return path.endsWith(`/queries/${queryId}/retry`);
};

const loadTrackerFilteredToQuery = async (page: Page, queryId: number) => {
  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await expect(page.locator('main')).toBeVisible({ timeout: 30_000 });
  await page.getByPlaceholder('Query ID').fill(String(queryId));

  const responsePromise = page.waitForResponse(response => {
    if (response.request().method() !== 'GET') return false;
    const url = new URL(response.url());
    const path = normalizeAdminApiPath(url);
    return path.endsWith('/queries') && url.searchParams.get('id') === String(queryId);
  }, { timeout: 60_000 });
  await page.getByRole('button', { name: '搜索' }).click();
  const response = await responsePromise;
  expect(response.ok(), `Filtered Tracker query load must return 2xx/3xx, got HTTP ${response.status()} at ${response.url()}`).toBeTruthy();

  const row = page.locator('tbody tr', { hasText: `Q-${queryId}` }).first();
  await expect(row, `Tracker row Q-${queryId} must be visible before retry`).toBeVisible({ timeout: 30_000 });
  return row;
};

const postRetryByApi = async (page: Page, queryId: number) => {
  console.info(`[Admin Tracker controlled retry] UI retry button unavailable; falling back to same-origin POST /admin/api/queries/${queryId}/retry.`);
  return await adminApi(page, `/queries/${queryId}/retry`, {
    method: 'POST',
    body: JSON.stringify({ reason: 'qa controlled retry gate' }),
  });
};

const triggerRetry = async (page: Page, queryId: number) => {
  const row = await loadTrackerFilteredToQuery(page, queryId);
  const retryButton = row.getByRole('button', { name: '重试' });
  const uiButtonVisible = await retryButton.isVisible({ timeout: 15_000 }).catch(() => false);

  if (!uiButtonVisible) {
    return {
      result: await postRetryByApi(page, queryId),
      path: 'api-fallback',
    };
  }

  console.info(`[Admin Tracker controlled retry] Clicking Tracker UI row retry button for query ${queryId}.`);
  const retryResponsePromise = page.waitForResponse(isRetryResponse(queryId), { timeout: 60_000 });
  await retryButton.click();
  const response = await retryResponsePromise;
  const body = await response.json().catch(() => null);
  return {
    result: {
      ok: response.ok(),
      status: response.status(),
      body,
      url: response.url(),
    },
    path: 'ui',
  };
};

const classifyPassingOutcome = (snapshot: ReturnType<typeof querySnapshot>, timedOut: boolean) => {
  const normalizedStatus = snapshot.status.toLowerCase();
  if (['done', 'success'].includes(normalizedStatus)) {
    return `terminal success status=${snapshot.status}`;
  }
  if (normalizedStatus === 'failed' && snapshot.retryReason) {
    return `terminal non-quota failure status=${snapshot.status}; retry_reason=${snapshot.retryReason}`;
  }
  if (timedOut && ['pending', 'running', 'retrying', 'queued', ''].includes(normalizedStatus)) {
    return `still ${snapshot.status || 'unknown'} after ${pollSeconds}s with no quota exhaustion`;
  }
  return '';
};

const pollForAcceptedOutcome = async (page: Page, queryId: number) => {
  const deadline = Date.now() + pollSeconds * 1000;
  let lastSnapshot = querySnapshot(queryId, await readSingleQuery(page, queryId, '0'));
  let outcome = '';

  while (Date.now() < deadline) {
    lastSnapshot = querySnapshot(queryId, await readSingleQuery(page, queryId, '0'));
    assertNotQuotaExhausted(lastSnapshot);

    outcome = classifyPassingOutcome(lastSnapshot, false);
    if (outcome) {
      return { outcome, snapshot: lastSnapshot };
    }

    await page.waitForTimeout(5_000);
  }

  assertNotQuotaExhausted(lastSnapshot);
  outcome = classifyPassingOutcome(lastSnapshot, true);
  if (!outcome) {
    throw new Error(
      `Controlled retry for query ${queryId} ended in unsupported state: ` +
      `status=${lastSnapshot.status}; retry_count=${lastSnapshot.retryCount}; target_llm=${lastSnapshot.targetLlm}; retry_reason=${lastSnapshot.retryReason}`,
    );
  }
  return { outcome, snapshot: lastSnapshot };
};

test(`${mutationMode} dispatches one explicit query and rejects quota exhaustion`, async ({ page }) => {
  const queryId = parseRetryQueryId();
  test.info().annotations.push({
    type: 'mode',
    description: `${mutationMode}; mutates exactly one query id=${queryId}; no batch retry.`,
  });
  console.info(`[Admin Tracker controlled retry] MUTATION ENABLED: targeting exactly one query id=${queryId}; no batch retry will run.`);

  const errors = installAdminErrorGuards(page);
  await ensureAdminSession(page);

  const before = querySnapshot(queryId, await readSingleQuery(page, queryId, '1'));
  console.info(
    `[Admin Tracker controlled retry] Preflight query=${queryId}; status=${before.status}; retry_count=${before.retryCount}; target_llm=${before.targetLlm}; retry_reason=${before.retryReason || 'empty'}.`,
  );
  assertNotQuotaExhausted(before);

  if (expectedEngineInput) {
    expect(
      before.targetLlm.toLowerCase(),
      `Controlled retry query ${queryId} target_llm should match ADMIN_E2E_TRACKER_RETRY_EXPECTED_ENGINE.`,
    ).toBe(expectedEngineInput.toLowerCase());
  }

  const { result: retryResult, path } = await triggerRetry(page, queryId);
  expect(retryResult.status, `Retry POST must return HTTP 200 at ${retryResult.url}; body=${JSON.stringify(retryResult.body)}`).toBe(200);
  expect(retryResult.body?.success, `Retry POST must return success=true; body=${JSON.stringify(retryResult.body)}`).toBe(true);
  expect(retryResult.body?.dispatched, `Retry POST must dispatch to worker; dispatched=false is not accepted for query ${queryId}. Body=${JSON.stringify(retryResult.body)}`).toBe(true);
  console.info(`[Admin Tracker controlled retry] Retry POST accepted via ${path}; dispatched=true for query ${queryId}.`);

  const { outcome, snapshot } = await pollForAcceptedOutcome(page, queryId);
  await loadTrackerFilteredToQuery(page, queryId);
  await expect(page.locator('tbody tr', { hasText: `Q-${queryId}` }).first()).toBeVisible({ timeout: 30_000 });

  console.info(
    `[Admin Tracker controlled retry] Final outcome for query ${queryId}: ${outcome}; ` +
    `status=${snapshot.status}; retry_count=${snapshot.retryCount}; target_llm=${snapshot.targetLlm}; retry_reason=${snapshot.retryReason || 'empty'}.`,
  );

  await errors.assertClean();
});
