import { expect, test, type Page, type Request } from '@playwright/test';

import { ensureAdminSession } from './admin-auth';
import { installAdminErrorGuards, normalizeAdminApiPath } from './admin-fixtures';

const stagingEnabled = process.env.ADMIN_E2E_STAGING === '1';
const analyzerEnabled = process.env.ADMIN_E2E_ANALYZER_ATTEMPTS === '1';
const mutationConfirmed = process.env.ADMIN_E2E_ANALYZER_MUTATION_CONFIRM === '1';
const singleResponseId = (process.env.ADMIN_E2E_ANALYZER_SINGLE_RESPONSE_ID || '').trim();
const batchResponseIds = (process.env.ADMIN_E2E_ANALYZER_BATCH_RESPONSE_IDS || '').trim();
const pollSeconds = Math.max(
  15,
  Math.min(Number(process.env.ADMIN_E2E_ANALYZER_POLL_SECONDS || '60') || 60, 180),
);

type AttemptAnalyzerSnapshot = {
  queryDbId: number;
  queryId: string;
  responseId: number;
  status: string;
  analysisStatus: string;
  analyzerRunId: string;
  metricReadinessStatus: string;
  responseText: string;
};

type BatchDryRunBody = {
  success?: boolean;
  dry_run?: boolean;
  dry_run_id?: string;
  requested_count?: number | null;
  matched_attempts?: number | null;
  eligible_count?: number | null;
  already_done_count?: number | null;
  skipped_counts?: Record<string, number>;
  skipped_counts_evaluated?: Record<string, number>;
  skipped_no_response_count?: number | null;
  skipped_failed_attempt_without_response_count?: number | null;
  will_enqueue_count?: number | null;
  cap?: number;
  cap_limit?: number;
  cap_exceeded?: boolean;
  counts_complete?: boolean;
  scope_too_large?: boolean;
  error?: string;
  request_id?: string;
};

type JsonRequestOptions = {
  method?: string;
  body?: string;
  headers?: Record<string, string>;
};

const parseCsvIds = (raw: string) => raw
  .split(',')
  .map(value => Number(value.trim()))
  .filter(value => Number.isInteger(value) && value > 0);

const readJsonResponse = async <T>(page: Page, path: string, init?: JsonRequestOptions): Promise<{
  status: number;
  ok: boolean;
  requestId: string;
  body: T;
}> => {
  return await page.evaluate(
    async ({ path: requestPath, init: requestInit }) => {
      const response = await fetch(requestPath, {
        credentials: 'same-origin',
        headers: { 'content-type': 'application/json', ...(requestInit?.headers || {}) },
        ...requestInit,
      });
      const body = await response.json().catch(() => ({}));
      return {
        status: response.status,
        ok: response.ok,
        requestId: response.headers.get('x-request-id') || body.request_id || '',
        body,
      };
    },
    { path, init },
  );
};

const waitForAttemptsLoaded = async (page: Page) => {
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

const readAnalyzerAttempts = async (page: Page): Promise<AttemptAnalyzerSnapshot[]> => {
  return await page.evaluate(() => {
    const body = document.body as HTMLElement & { _x_dataStack?: any[] };
    const app = body._x_dataStack?.[0];
    const rows = Array.isArray(app?.executionAttempts) ? app.executionAttempts : [];
    return rows
      .map((row: any) => ({
        queryDbId: Number(row.queryDbId || 0),
        queryId: String(row.queryId || ''),
        responseId: Number(row.responseId || 0),
        status: String(row.status || ''),
        analysisStatus: String(row.analyzer?.status || row.analysis_status || ''),
        analyzerRunId: String(row.analyzer?.runId || row.analyzer?.task?.latest_run_id || ''),
        metricReadinessStatus: String(row.analyzer?.metricReadinessStatus || ''),
        responseText: String(row.responseText || ''),
      }))
      .filter((row: AttemptAnalyzerSnapshot) => row.queryDbId > 0);
  });
};

const installAnalyzerMutationGuard = (page: Page) => {
  const mutationRequests: string[] = [];

  page.on('request', (request: Request) => {
    const method = request.method().toUpperCase();
    if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') return;

    const url = new URL(request.url());
    const path = normalizeAdminApiPath(url);
    if (!path.startsWith('/api/admin')) return;
    if (method === 'POST' && path.endsWith('/auth/login')) return;
    if (method === 'POST' && path.endsWith('/analyzer/responses/batch/dry-run')) return;

    const isConfirmedSingle = mutationConfirmed
      && singleResponseId
      && method === 'POST'
      && path === `/api/admin/analyzer/responses/${singleResponseId}/analyze`;
    const isConfirmedBatch = mutationConfirmed
      && batchResponseIds
      && method === 'POST'
      && path === '/api/admin/analyzer/responses/batch';
    if (isConfirmedSingle || isConfirmedBatch) return;

    mutationRequests.push(`${method} ${path}`);
  });

  return {
    assertNoUnexpectedMutation: () => {
      expect(
        mutationRequests,
        'Analyzer production E2E must not call unplanned mutating Admin APIs',
      ).toEqual([]);
    },
  };
};

test.skip(
  !stagingEnabled || !analyzerEnabled,
  'Set ADMIN_E2E_STAGING=1 and ADMIN_E2E_ANALYZER_ATTEMPTS=1 with Admin credentials to run analyzer production E2E.',
);
test.setTimeout(4 * 60_000);

test('production Admin Attempts analyzer status, drawer, dry-run, and optional controlled submit paths', async ({ page }) => {
  test.info().annotations.push({
    type: 'mode',
    description: mutationConfirmed
      ? 'Analyzer production E2E with explicit mutation confirmation.'
      : 'Analyzer production E2E read-only status/drawer plus batch dry-run; submit paths disabled.',
  });

  const errors = installAdminErrorGuards(page);
  const mutationGuard = installAnalyzerMutationGuard(page);
  await ensureAdminSession(page);

  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await expect(page.getByTestId('attempt-analyzer-column-header')).toBeVisible({ timeout: 30_000 });
  await waitForAttemptsLoaded(page);

  const attempts = await readAnalyzerAttempts(page);
  expect(attempts.length, 'Attempts page should load production rows').toBeGreaterThan(0);
  const responseRows = attempts.filter(row => row.responseId > 0 && row.responseText.trim());
  expect(responseRows.length, 'Production Attempts rows should include responses eligible for analyzer status').toBeGreaterThan(0);

  const target = responseRows.find(row => row.responseId === Number(singleResponseId)) || responseRows[0];
  const statusResult = await readJsonResponse<Record<string, any>>(
    page,
    `/admin/api/analyzer/responses/${target.responseId}/status`,
  );
  expect(statusResult.ok, `status endpoint for response ${target.responseId} returned HTTP ${statusResult.status}`).toBeTruthy();
  expect(statusResult.body.success).toBe(true);
  expect(Number(statusResult.body.response_id)).toBe(target.responseId);
  expect(String(statusResult.body.analysis_status || '')).not.toBe('');
  expect(statusResult.body.analysis_task).toBeTruthy();

  await page.getByTestId(`attempt-details-${target.queryDbId}`).click();
  await expect(page.getByTestId('attempt-drawer')).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId('attempt-response-text')).toBeVisible();
  await expect(page.getByTestId('attempt-analyzer-drawer-summary')).toBeVisible();

  const dryRunIds = responseRows.slice(0, 3).map(row => row.responseId);
  expect(dryRunIds.length, 'Need at least one visible response id for analyzer dry-run').toBeGreaterThan(0);
  console.info(
    [
      `[Admin analyzer E2E] pre_dry_run rows=${attempts.length}`,
      `target_query=${target.queryId}`,
      `target_query_db_id=${target.queryDbId}`,
      `target_response_id=${target.responseId}`,
      `status=${statusResult.body.analysis_status}`,
      `metric_readiness=${statusResult.body.metric_readiness_status || 'empty'}`,
      `status_request_id=${statusResult.requestId || 'empty'}`,
      `dry_run_ids=${dryRunIds.join(',')}`,
    ].join('; '),
  );
  const dryRun = await readJsonResponse<BatchDryRunBody>(
    page,
    '/admin/api/analyzer/responses/batch/dry-run',
    {
      method: 'POST',
      body: JSON.stringify({
        scope: { response_ids: dryRunIds },
        mode: 'missing_or_failed_only',
        max_count: 3,
        sample_limit: 3,
        reason: 'issue_786_prod_readonly_dry_run',
      }),
    },
  );
  expect(dryRun.ok, `batch dry-run returned HTTP ${dryRun.status}: ${JSON.stringify(dryRun.body)}`).toBeTruthy();
  expect(dryRun.body.dry_run).toBe(true);
  expect(dryRun.body.requested_count ?? dryRunIds.length).toBeGreaterThan(0);
  expect(Number(dryRun.body.eligible_count ?? dryRun.body.will_enqueue_count ?? 0)).toBeGreaterThanOrEqual(0);
  expect(Number(dryRun.body.already_done_count ?? 0)).toBeGreaterThanOrEqual(0);

  console.info(
    [
      `[Admin analyzer E2E] rows=${attempts.length}`,
      `target_query=${target.queryId}`,
      `target_query_db_id=${target.queryDbId}`,
      `target_response_id=${target.responseId}`,
      `status=${statusResult.body.analysis_status}`,
      `metric_readiness=${statusResult.body.metric_readiness_status || 'empty'}`,
      `status_request_id=${statusResult.requestId || 'empty'}`,
      `dry_run_ids=${dryRunIds.join(',')}`,
      `dry_run_id=${dryRun.body.dry_run_id || 'empty'}`,
      `dry_run_request_id=${dryRun.requestId || dryRun.body.request_id || 'empty'}`,
      `dry_run_eligible=${dryRun.body.eligible_count ?? dryRun.body.will_enqueue_count ?? 'unknown'}`,
      `dry_run_already_done=${dryRun.body.already_done_count ?? 'unknown'}`,
      `dry_run_counts_complete=${dryRun.body.counts_complete !== false}`,
    ].join('; '),
  );

  if (singleResponseId) {
    if (!mutationConfirmed) {
      console.info(
        `[Admin analyzer E2E] single submit skipped: ADMIN_E2E_ANALYZER_SINGLE_RESPONSE_ID=${singleResponseId} but ADMIN_E2E_ANALYZER_MUTATION_CONFIRM!=1.`,
      );
    } else {
      const singleSubmit = await readJsonResponse<Record<string, any>>(
        page,
        `/admin/api/analyzer/responses/${singleResponseId}/analyze`,
        {
          method: 'POST',
          body: JSON.stringify({
            mode: 'missing_or_failed_only',
            reason: 'issue_786_prod_single_submit',
            idempotency_key: `issue-786-single-${singleResponseId}`,
          }),
        },
      );
      expect([200, 202, 409]).toContain(singleSubmit.status);
      expect(Number(singleSubmit.body.response_id)).toBe(Number(singleResponseId));
      console.info(
        `[Admin analyzer E2E] single_submit response_id=${singleResponseId}; http=${singleSubmit.status}; accepted=${singleSubmit.body.accepted}; run_id=${singleSubmit.body.run_id || 'empty'}; task_id=${singleSubmit.body.task_id || 'empty'}; error=${singleSubmit.body.error || 'empty'}; request_id=${singleSubmit.requestId || singleSubmit.body.request_id || 'empty'}.`,
      );
    }
  }

  const confirmedBatchIds = parseCsvIds(batchResponseIds);
  if (confirmedBatchIds.length > 0) {
    if (!mutationConfirmed) {
      console.info(
        `[Admin analyzer E2E] batch submit skipped: ADMIN_E2E_ANALYZER_BATCH_RESPONSE_IDS=${batchResponseIds} but ADMIN_E2E_ANALYZER_MUTATION_CONFIRM!=1.`,
      );
    } else {
      const batchSubmit = await readJsonResponse<Record<string, any>>(
        page,
        '/admin/api/analyzer/responses/batch',
        {
          method: 'POST',
          body: JSON.stringify({
            scope: { response_ids: confirmedBatchIds },
            mode: 'missing_or_failed_only',
            max_count: confirmedBatchIds.length,
            sample_limit: confirmedBatchIds.length,
            confirm: true,
            reason: 'issue_786_prod_batch_submit',
            idempotency_key: `issue-786-batch-${confirmedBatchIds.join('-')}`,
          }),
        },
      );
      expect([200, 202, 409]).toContain(batchSubmit.status);
      console.info(
        `[Admin analyzer E2E] batch_submit response_ids=${confirmedBatchIds.join(',')}; http=${batchSubmit.status}; batch_id=${batchSubmit.body.batch_id || 'empty'}; accepted_count=${batchSubmit.body.accepted_count ?? 'unknown'}; error=${batchSubmit.body.error || 'empty'}; request_id=${batchSubmit.requestId || batchSubmit.body.request_id || 'empty'}.`,
      );

      if (batchSubmit.body.batch_id) {
        const deadline = Date.now() + pollSeconds * 1000;
        let latest: { status: number; ok: boolean; requestId: string; body: Record<string, any> } | null = null;
        while (Date.now() < deadline) {
          latest = await readJsonResponse<Record<string, any>>(
            page,
            `/admin/api/analyzer/batches/${batchSubmit.body.batch_id}`,
          );
          const status = String(latest.body.status || latest.body.batch_status || '').toLowerCase();
          if (['completed', 'done', 'failed', 'partial'].includes(status)) break;
          await page.waitForTimeout(5_000);
        }
        expect(latest?.ok, `batch status failed for batch ${batchSubmit.body.batch_id}`).toBeTruthy();
        console.info(
          `[Admin analyzer E2E] batch_status batch_id=${batchSubmit.body.batch_id}; http=${latest?.status}; status=${latest?.body.status || latest?.body.batch_status || 'empty'}; accepted_count=${latest?.body.accepted_count ?? 'unknown'}; request_id=${latest?.requestId || latest?.body.request_id || 'empty'}.`,
        );
      }
    }
  }

  mutationGuard.assertNoUnexpectedMutation();
  await errors.assertClean();
});
