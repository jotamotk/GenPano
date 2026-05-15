import { expect, test, type Page, type Response } from '@playwright/test';

import { ensureAdminSession } from './admin-auth';
import {
  fulfillJson,
  installAdminDocumentRoute,
  installAdminErrorGuards,
  normalizeAdminApiPath,
} from './admin-fixtures';

const stagingEnabled = process.env.ADMIN_E2E_STAGING === '1';
const retryQueryIdInput = (process.env.ADMIN_E2E_TRACKER_RETRY_QUERY_ID || '').trim();
const expectedEngineInput = (process.env.ADMIN_E2E_TRACKER_RETRY_EXPECTED_ENGINE || '').trim();
const retryRequiresSuccess = process.env.ADMIN_E2E_TRACKER_RETRY_REQUIRE_SUCCESS === '1';
const pollSeconds = Math.max(
  15,
  Math.min(180, Number(process.env.ADMIN_E2E_TRACKER_RETRY_POLL_SECONDS || 180) || 180),
);

const mutationMode = 'controlled live Tracker retry mutation';
const quotaExhaustedReason = 'account_daily_limit_exhausted';
const retryRequestMarkers = new Set(['qa controlled retry gate', 'manual retry from admin']);

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
  response?: string | null;
  response_id?: number | string | null;
};

type QuerySnapshot = {
  queryId: number;
  status: string;
  retryCount: number | null;
  targetLlm: string;
  retryReason: string;
  responseId: string;
  responseLength: number;
  rawRowJson: string;
};

type PollOptions = {
  requireSuccess?: boolean;
};

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

const querySnapshot = (queryId: number, row: QueryRow): QuerySnapshot => {
  const responseText = typeof row.response === 'string' ? row.response : '';
  const responseId = row.response_id == null ? '' : String(row.response_id);
  const safeRow = {
    ...row,
    response: responseText ? `[redacted len=${responseText.length}]` : row.response,
  };
  return {
    queryId,
    status: String(row.status || ''),
    retryCount: row.retry_count == null ? null : Number(row.retry_count),
    targetLlm: String(row.target_llm || ''),
    retryReason: String(row.retry_reason || row.error_code || ''),
    responseId,
    responseLength: responseText.length,
    rawRowJson: JSON.stringify(safeRow),
  };
};

const assertNoQuotaExhaustionText = (queryId: number, label: string, value: unknown) => {
  const haystack = String(typeof value === 'string' ? value : JSON.stringify(value)).toLowerCase();
  if (haystack.includes(quotaExhaustedReason)) {
    throw new Error(
      `Controlled retry for query ${queryId} hit ${quotaExhaustedReason} in ${label}: ${haystack.slice(0, 1000)}`,
    );
  }
};

const assertNotQuotaExhausted = (snapshot: QuerySnapshot) => {
  assertNoQuotaExhaustionText(snapshot.queryId, 'query snapshot', [
    snapshot.status,
    snapshot.retryReason,
    snapshot.targetLlm,
    snapshot.rawRowJson,
  ].join(' | '));
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
  await page.getByRole('button', { name: '搜索', exact: true }).click();
  const response = await responsePromise;
  expect(response.ok(), `Filtered Tracker query load must return 2xx/3xx, got HTTP ${response.status()} at ${response.url()}`).toBeTruthy();

  const row = page.locator('tbody tr', { hasText: `Q-${queryId}` }).first();
  await expect(row, `Tracker row Q-${queryId} must be visible before retry`).toBeVisible({ timeout: 30_000 });
  return row;
};

const triggerRetry = async (page: Page, queryId: number) => {
  const row = await loadTrackerFilteredToQuery(page, queryId);
  const retryButton = row.getByRole('button', { name: /^重试$/ });
  await expect(
    retryButton,
    `Controlled retry requires operator UI evidence: Tracker row Q-${queryId} must expose a visible 重试 button; API fallback is not allowed.`,
  ).toBeVisible({ timeout: 15_000 });
  await expect(
    retryButton,
    `Controlled retry requires operator UI evidence: Tracker row Q-${queryId} retry button must be enabled.`,
  ).toBeEnabled({ timeout: 15_000 });

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

const hasRetryCountIncrease = (before: QuerySnapshot, after: QuerySnapshot) => (
  before.retryCount !== null
  && after.retryCount !== null
  && Number.isFinite(before.retryCount)
  && Number.isFinite(after.retryCount)
  && after.retryCount >= before.retryCount + 1
);

const isRequestMarkerReason = (reason: string) => retryRequestMarkers.has(reason.trim().toLowerCase());

const hasResponseEvidence = (snapshot: QuerySnapshot) => (
  snapshot.responseId.trim().length > 0 || snapshot.responseLength > 0
);

const classifyPassingOutcome = (
  snapshot: QuerySnapshot,
  before: QuerySnapshot,
  options: PollOptions = {},
) => {
  const normalizedStatus = snapshot.status.toLowerCase();
  if (!hasRetryCountIncrease(before, snapshot)) return '';
  if (['done', 'success'].includes(normalizedStatus)) {
    if (options.requireSuccess && !hasResponseEvidence(snapshot)) {
      throw new Error(
        `Controlled retry for query ${snapshot.queryId} reached ${snapshot.status} without response evidence; ` +
        `response_id=${snapshot.responseId || 'empty'}; response_length=${snapshot.responseLength}; ` +
        `raw=${snapshot.rawRowJson.slice(0, 1000)}`,
      );
    }
    return `terminal success status=${snapshot.status}; response_evidence=${hasResponseEvidence(snapshot) ? 'present' : 'not-required'}`;
  }
  if (
    ['failed', 'dlq', 'waiting_manual'].includes(normalizedStatus)
    && snapshot.retryReason
    && !isRequestMarkerReason(snapshot.retryReason)
  ) {
    if (options.requireSuccess) {
      throw new Error(
        `Controlled retry for query ${snapshot.queryId} requires terminal success with response evidence, ` +
        `got status=${snapshot.status}; retry_reason=${snapshot.retryReason}; raw=${snapshot.rawRowJson.slice(0, 1000)}`,
      );
    }
    return `terminal non-quota failure status=${snapshot.status}; retry_reason=${snapshot.retryReason}`;
  }
  return '';
};

const pollForAcceptedOutcome = async (
  page: Page,
  queryId: number,
  before: QuerySnapshot,
  maxPollSeconds = pollSeconds,
  options: PollOptions = {},
) => {
  const deadline = Date.now() + maxPollSeconds * 1000;
  const pollDelayMs = Math.min(5_000, Math.max(250, Math.floor(maxPollSeconds * 500)));
  let lastSnapshot = querySnapshot(queryId, await readSingleQuery(page, queryId, '0'));
  let outcome = '';

  while (Date.now() < deadline) {
    lastSnapshot = querySnapshot(queryId, await readSingleQuery(page, queryId, '0'));
    assertNotQuotaExhausted(lastSnapshot);

    outcome = classifyPassingOutcome(lastSnapshot, before, options);
    if (outcome) {
      return { outcome, snapshot: lastSnapshot };
    }

    await page.waitForTimeout(pollDelayMs);
  }

  assertNotQuotaExhausted(lastSnapshot);
  throw new Error(
    `Controlled retry for query ${queryId} did not reach an accepted terminal outcome within ${maxPollSeconds}s: ` +
    `status=${lastSnapshot.status || 'empty'}; retry_count=${lastSnapshot.retryCount}; ` +
    `expected_retry_count_min=${before.retryCount === null ? 'unknown' : before.retryCount + 1}; target_llm=${lastSnapshot.targetLlm}; ` +
    `retry_reason=${lastSnapshot.retryReason || 'empty'}; ` +
    `response_evidence=${hasResponseEvidence(lastSnapshot) ? 'present' : 'missing'}; raw=${lastSnapshot.rawRowJson.slice(0, 1000)}`,
  );
};

test(`${mutationMode} dispatches one explicit query and rejects quota exhaustion`, async ({ page }) => {
  test.skip(
    !stagingEnabled || !retryQueryIdInput,
    'Set ADMIN_E2E_STAGING=1 and ADMIN_E2E_TRACKER_RETRY_QUERY_ID to run the opt-in live Tracker retry mutation.',
  );

  const queryId = parseRetryQueryId();
  test.info().annotations.push({
    type: 'mode',
    description: `${mutationMode}; mutates exactly one query id=${queryId}; no batch retry, no cleanup, no manual dispatch.`,
  });
  console.info(`[Admin Tracker controlled retry] MUTATION ENABLED: targeting exactly one query id=${queryId}; poll_seconds=${pollSeconds}; require_success=${retryRequiresSuccess ? '1' : '0'}; no batch retry, cleanup, or manual dispatch will run.`);

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
  assertNoQuotaExhaustionText(queryId, 'retry POST body', retryResult.body);
  expect(retryResult.status, `Retry POST must return HTTP 200 at ${retryResult.url}; body=${JSON.stringify(retryResult.body)}`).toBe(200);
  expect(retryResult.body?.success, `Retry POST must return success=true; body=${JSON.stringify(retryResult.body)}`).toBe(true);
  expect(retryResult.body?.dispatched, `Retry POST must dispatch to worker; dispatched=false is not accepted for query ${queryId}. Body=${JSON.stringify(retryResult.body)}`).toBe(true);
  console.info(`[Admin Tracker controlled retry] Retry POST accepted via ${path}; dispatched=true for query ${queryId}.`);

  const { outcome, snapshot } = await pollForAcceptedOutcome(
    page,
    queryId,
    before,
    pollSeconds,
    { requireSuccess: retryRequiresSuccess },
  );
  await loadTrackerFilteredToQuery(page, queryId);
  await expect(page.locator('tbody tr', { hasText: `Q-${queryId}` }).first()).toBeVisible({ timeout: 30_000 });

  console.info(
    `[Admin Tracker controlled retry] Final outcome for query ${queryId}: ${outcome}; ` +
    `status=${snapshot.status}; retry_count=${snapshot.retryCount}; target_llm=${snapshot.targetLlm}; ` +
    `retry_reason=${snapshot.retryReason || 'empty'}; response_evidence=${hasResponseEvidence(snapshot) ? 'present' : 'missing'}.`,
  );

  await errors.assertClean();
});

const fakeQueryId = 184576;
const fakeQueryRow = (overrides: Record<string, unknown> = {}) => ({
  id: fakeQueryId,
  target_llm: 'deepseek',
  status: 'failed',
  retry_count: 2,
  retry_reason: 'browser_timeout',
  query_text: 'controlled retry fake row',
  account_label: 'ACC-FAKE',
  ...overrides,
});

const installControlledRetryRoutes = async (
  page: Page,
  rows: QueryRow[],
  options: { includeRetryButton?: boolean } = {},
) => {
  let queryReads = 0;
  await installAdminDocumentRoute(page);
  if (options.includeRetryButton === false) {
    await page.addInitScript(() => {
      const style = document.createElement('style');
      style.textContent = 'tbody tr button { display: none !important; }';
      document.addEventListener('DOMContentLoaded', () => document.head.appendChild(style), { once: true });
    });
  }
  await page.route(/.*\/(?:api\/admin|admin\/api)(?:\/.*)?/, async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = normalizeAdminApiPath(url);
    const method = request.method();

    if (method === 'GET' && path.endsWith('/auth/session')) {
      await fulfillJson(route, {
        authenticated: true,
        admin: { id: 'admin-controlled-retry-e2e', email: 'tracker@example.test' },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/analyzer/brands')) {
      await fulfillJson(route, []);
      return;
    }

    if (method === 'GET' && path.endsWith('/queries')) {
      const row = rows[Math.min(queryReads, rows.length - 1)];
      queryReads += 1;
      await fulfillJson(route, {
        rows: [row],
        total: 1,
        by_status: { [String(row.status || '')]: 1 },
      });
      return;
    }

    if (method === 'POST' && path.endsWith(`/queries/${fakeQueryId}/retry`)) {
      await fulfillJson(route, { success: true, dispatched: true });
      return;
    }

    await fulfillJson(route, {});
  });
};

test('controlled retry fails instead of using API fallback when the UI retry button is unavailable', async ({ page }) => {
  await installControlledRetryRoutes(page, [fakeQueryRow()], { includeRetryButton: false });
  await expect(triggerRetry(page, fakeQueryId)).rejects.toThrow(/operator UI evidence|API fallback/i);
});

test('controlled retry polling fails pending timeout instead of accepting it', async ({ page }) => {
  await installControlledRetryRoutes(page, [
    fakeQueryRow({ retry_count: 2 }),
    fakeQueryRow({ status: 'pending', retry_count: 3, retry_reason: 'qa controlled retry gate' }),
  ]);
  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded' });
  await expect(pollForAcceptedOutcome(page, fakeQueryId, querySnapshot(fakeQueryId, fakeQueryRow({ retry_count: 2 })), 1)).rejects.toThrow(/pending/i);
});

test('controlled retry polling fails running timeout instead of accepting it', async ({ page }) => {
  await installControlledRetryRoutes(page, [
    fakeQueryRow({ retry_count: 2 }),
    fakeQueryRow({ status: 'running', retry_count: 3, retry_reason: 'qa controlled retry gate' }),
  ]);
  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded' });
  await expect(pollForAcceptedOutcome(page, fakeQueryId, querySnapshot(fakeQueryId, fakeQueryRow({ retry_count: 2 })), 1)).rejects.toThrow(/running/i);
});

test('controlled retry polling fails quota exhaustion when sentinel appears in raw row fields', async ({ page }) => {
  await installControlledRetryRoutes(page, [
    fakeQueryRow({ retry_count: 2 }),
    fakeQueryRow({
      status: 'failed:account_daily_limit_exhausted',
      retry_count: 3,
      retry_reason: 'browser_timeout',
    }),
  ]);
  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded' });
  await expect(pollForAcceptedOutcome(page, fakeQueryId, querySnapshot(fakeQueryId, fakeQueryRow({ retry_count: 2 })), 1)).rejects.toThrow(quotaExhaustedReason);
});

test('controlled retry polling requires retry_count to increase before accepting terminal failure', async ({ page }) => {
  await installControlledRetryRoutes(page, [
    fakeQueryRow({ retry_count: 2 }),
    fakeQueryRow({ status: 'failed', retry_count: 2, retry_reason: 'browser_timeout' }),
  ]);
  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded' });
  await expect(pollForAcceptedOutcome(page, fakeQueryId, querySnapshot(fakeQueryId, fakeQueryRow({ retry_count: 2 })), 1)).rejects.toThrow(/expected_retry_count_min=3/);
});

test('controlled retry success-required mode rejects terminal failure', async ({ page }) => {
  await installControlledRetryRoutes(page, [
    fakeQueryRow({ retry_count: 2 }),
    fakeQueryRow({ status: 'failed', retry_count: 3, retry_reason: 'doubao_not_logged_in' }),
  ]);
  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded' });
  await expect(
    pollForAcceptedOutcome(
      page,
      fakeQueryId,
      querySnapshot(fakeQueryId, fakeQueryRow({ retry_count: 2 })),
      1,
      { requireSuccess: true },
    ),
  ).rejects.toThrow(/requires terminal success/i);
});

test('controlled retry success-required mode requires response evidence for done rows', async ({ page }) => {
  await installControlledRetryRoutes(page, [
    fakeQueryRow({ retry_count: 2 }),
    fakeQueryRow({ status: 'done', retry_count: 3, retry_reason: null, response: '' }),
  ]);
  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded' });
  await expect(
    pollForAcceptedOutcome(
      page,
      fakeQueryId,
      querySnapshot(fakeQueryId, fakeQueryRow({ retry_count: 2 })),
      1,
      { requireSuccess: true },
    ),
  ).rejects.toThrow(/response evidence/i);
});
