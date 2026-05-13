import { expect, test, type Page, type Route } from '@playwright/test';

import {
  fulfillJson,
  installAdminDocumentRoute,
  installAdminErrorGuards,
  normalizeAdminApiPath,
} from './admin-fixtures';

const attemptRows = [
  {
    id: 77901,
    response_id: 101,
    target_llm: 'chatgpt',
    status: 'done',
    retry_count: 0,
    query_text: 'Analyzer done row',
    response: 'The answer contains a complete brand comparison.',
    analysis_status: 'done',
    analysis_summary: { geo_score: 0.82, total_brands_mentioned: 4, citations_count: 2 },
    analyzer_run_id: 'run-101',
    analyzed_at: '2026-05-13T09:10:00Z',
  },
  {
    id: 77902,
    response_id: 102,
    target_llm: 'doubao',
    status: 'done',
    retry_count: 1,
    query_text: 'Analyzer partial row',
    response: 'The answer was partially readable.',
    analysis_status: 'partial',
    analyzer_run_id: 'run-102',
  },
  {
    id: 77903,
    response_id: 103,
    target_llm: 'deepseek',
    status: 'done',
    retry_count: 0,
    query_text: 'Analyzer missing row',
    response: 'Fresh response text that has not been analyzed yet.',
    analysis_status: 'missing',
  },
  {
    id: 77904,
    response_id: null,
    target_llm: 'chatgpt',
    status: 'failed',
    retry_count: 2,
    query_text: 'Analyzer failed attempt row',
    response: null,
    retry_reason: 'browser_timeout',
    analysis_status: 'not_eligible',
  },
  {
    id: 77905,
    response_id: 105,
    target_llm: 'chatgpt',
    status: 'done',
    retry_count: 0,
    query_text: 'Analyzer running row',
    response: 'Running analyzer response.',
    analysis_status: 'running',
    analyzer_run_id: 'run-105',
  },
];

const statusByResponseId: Record<number, Record<string, unknown>> = {
  101: {
    success: true,
    query_id: 77901,
    response_id: 101,
    raw_text: attemptRows[0].response,
    analysis_status: 'done',
    analysis_summary: { geo_score: 0.82, total_brands_mentioned: 4, citations_count: 2 },
    analyzer_run_id: 'run-101-live',
    analysis_task: { latest_run_id: 'run-101-live', queue_state: 'complete' },
    metric_readiness_status: 'ok',
  },
  102: {
    success: true,
    query_id: 77902,
    response_id: 102,
    raw_text: attemptRows[1].response,
    analysis_status: 'partial',
    analysis_error: '部分结果需要复核',
    analyzer_run_id: 'run-102-live',
    analysis_task: { latest_run_id: 'run-102-live', queue_state: 'complete' },
    metric_readiness_status: 'warning',
  },
  103: {
    success: true,
    query_id: 77903,
    response_id: 103,
    raw_text: attemptRows[2].response,
    analysis_status: 'failed',
    analysis_error: '上次分析失败，可重新提交',
    analyzer_run_id: 'run-103-live',
    analysis_task: { latest_run_id: 'run-103-live', queue_state: 'failed' },
    metric_readiness_status: 'blocked',
  },
  105: {
    success: true,
    query_id: 77905,
    response_id: 105,
    raw_text: attemptRows[4].response,
    analysis_status: 'running',
    analyzer_run_id: 'run-105-live',
    analysis_task: { latest_run_id: 'run-105-live', queue_state: 'running' },
    metric_readiness_status: 'pending',
  },
};

const FILTER_SCOPE_TOTAL = 42;

const readJson = (route: Route) => {
  try {
    return route.request().postDataJSON() as Record<string, unknown>;
  } catch {
    return {};
  }
};

const analyzerGateBody = {
  success: false,
  error: 'analyzer_run_persistence_required',
  message: '#797 must provide durable run/batch persistence before this endpoint can mutate facts.',
  blocked_by_issue: 797,
};

const routeAttemptsApis = async (page: Page) => {
  const dryRunPayloads: Record<string, unknown>[] = [];
  const submitPayloads: Record<string, unknown>[] = [];
  const statusRequests: string[] = [];
  const actualAnalyzerUrls: string[] = [];

  await page.route(/.*\/(?:api|admin\/api)(?:\/.*)?/, async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = normalizeAdminApiPath(url);
    const method = request.method();

    if (url.pathname.includes('/admin/api/analyzer/')) {
      actualAnalyzerUrls.push(`${method} ${url.pathname}`);
    }

    if (method === 'GET' && path.endsWith('/auth/session')) {
      await fulfillJson(route, {
        authenticated: true,
        admin: { id: 'analyzer-admin', email: 'analyzer@example.test' },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/queries')) {
      await fulfillJson(route, {
        rows: attemptRows,
        total: FILTER_SCOPE_TOTAL,
        by_status: { done: 4, failed: 1 },
      });
      return;
    }

    const statusMatch = path.match(/\/analyzer\/responses\/(\d+)\/status$/);
    if (method === 'GET' && statusMatch) {
      statusRequests.push(statusMatch[1]);
      await fulfillJson(route, statusByResponseId[Number(statusMatch[1])] || {
        success: false,
        error: 'response_not_found',
      }, statusByResponseId[Number(statusMatch[1])] ? 200 : 404);
      return;
    }

    if (method === 'POST' && path.endsWith('/analyzer/responses/batch/dry-run')) {
      const payload = readJson(route);
      dryRunPayloads.push(payload);
      const scope = payload.scope as { response_ids?: number[]; filters?: Record<string, unknown> } | undefined;
      if (scope?.filters) {
        await fulfillJson(route, {
          success: false,
          dry_run: true,
          error: 'dry_run_scope_too_large',
          scope_too_large: true,
          counts_complete: false,
          query_truncated: true,
          query_limit: 5000,
          requested_count: null,
          matched_attempts: null,
          matched_attempts_evaluated: 5000,
          eligible_count: null,
          eligible_count_evaluated: 5000,
          already_done_count: null,
          already_done_count_evaluated: 1200,
          skipped_no_response_count: null,
          skipped_no_response_count_evaluated: 20,
          skipped_failed_attempt_without_response_count: null,
          skipped_failed_attempt_without_response_count_evaluated: 5,
          skipped_invalid_count: null,
          skipped_invalid_count_evaluated: 0,
          skipped_counts_evaluated: { already_done: 1200, already_queued_or_running: 300 },
          will_enqueue_count: 0,
          cap: 25,
          cap_limit: 25,
          cap_exceeded: false,
          cap_truncated: false,
          eligible_response_ids_preview: [],
          requires_confirmation: false,
        });
        return;
      }
      expect(scope?.response_ids).toEqual([101, 102, 105]);
      await fulfillJson(route, {
        success: true,
        dry_run: true,
        dry_run_id: 'dry-run-selected',
        counts_complete: true,
        requested_count: 3,
        matched_attempts: 3,
        eligible_count: 1,
        already_done_count: 1,
        skipped_no_response_count: 0,
        skipped_failed_attempt_without_response_count: 0,
        skipped_invalid_count: 0,
        skipped_counts: { already_done: 1, already_queued_or_running: 1 },
        skipped_reasons: { already_queued_or_running: [{ response_id: 105, query_id: 77905 }] },
        will_enqueue_count: 1,
        cap: 25,
        cap_limit: 25,
        cap_exceeded: false,
        cap_truncated: false,
        eligible_response_ids_preview: [103],
        requires_confirmation: true,
      });
      return;
    }

    if (method === 'POST' && path.match(/\/analyzer\/responses\/\d+\/analyze$/)) {
      await fulfillJson(route, {
        ...analyzerGateBody,
        response_id: Number(path.match(/\/responses\/(\d+)\/analyze$/)?.[1]),
        accepted: false,
      }, 409);
      return;
    }

    if (method === 'POST' && path.endsWith('/analyzer/responses/batch')) {
      submitPayloads.push(readJson(route));
      await fulfillJson(route, {
        ...analyzerGateBody,
        accepted_count: 0,
        skipped_count: 0,
      }, 409);
      return;
    }

    if (
      method === 'GET'
      && (
        path.endsWith('/topics')
        || path.endsWith('/prompts')
        || path.endsWith('/accounts')
        || path.endsWith('/accounts/profile_counts')
        || path.endsWith('/analyzer/brands')
      )
    ) {
      await fulfillJson(route, []);
      return;
    }

    await fulfillJson(route, {});
  });

  return { actualAnalyzerUrls, dryRunPayloads, statusRequests, submitPayloads };
};

test('Admin Attempts uses real analyzer status/dry-run APIs and handles the mutation gate', async ({ page }) => {
  await installAdminDocumentRoute(page);
  const api = await routeAttemptsApis(page);
  const errors = installAdminErrorGuards(page, {
    allowedNetworkErrorUrls: [/\/admin\/api\/analyzer\/responses/],
  });

  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded' });

  await expect(page.getByTestId('attempt-analyzer-column-header')).toBeVisible();
  await expect(page.getByTestId('attempt-analyzer-badge-77901')).toContainText('已分析');
  await expect(page.getByTestId('attempt-analyzer-badge-77903')).toContainText('分析失败');
  await expect.poll(() => new Set(api.statusRequests)).toEqual(new Set(['101', '102', '103', '105']));
  expect(api.actualAnalyzerUrls).toEqual(expect.arrayContaining([
    'GET /admin/api/analyzer/responses/101/status',
    'GET /admin/api/analyzer/responses/103/status',
  ]));

  await page.getByTestId('attempt-details-77903').click();
  await expect(page.getByTestId('attempt-drawer')).toBeVisible();
  await expect(page.getByTestId('attempt-response-text')).toContainText('Fresh response text');
  await expect(page.getByTestId('attempt-analyzer-drawer-summary')).toContainText('上次分析失败');

  await page.getByTestId('attempt-analyzer-drawer-trigger').click();
  await expect(page.getByTestId('attempt-analyzer-gate-message')).toBeVisible();
  await expect(page.getByTestId('attempt-analyzer-gate-message')).toContainText('暂未开放');
  await expect(page.getByTestId('attempt-analyzer-gate-message')).not.toContainText('analyzer_run_persistence_required');
  expect(api.actualAnalyzerUrls).toContain('POST /admin/api/analyzer/responses/103/analyze');

  await page.getByTestId('attempt-select-77901').check();
  await page.getByTestId('attempt-select-77902').check();
  await page.getByTestId('attempt-select-77905').check();
  await page.getByTestId('attempt-analyzer-batch-button').click();
  await expect(page.getByTestId('attempt-analyzer-batch-preview')).toBeVisible();
  await expect(page.getByTestId('attempt-analyzer-batch-requested')).toContainText('3');
  await expect(page.getByTestId('attempt-analyzer-batch-eligible')).toContainText('1');
  await expect(page.getByTestId('attempt-analyzer-batch-skipped-already')).toContainText('1');
  await expect(page.getByTestId('attempt-analyzer-batch-skipped-unavailable')).toContainText('1');
  await expect(page.getByTestId('attempt-analyzer-batch-submit-cap')).toContainText('1 / 25');
  expect(api.dryRunPayloads[0]).toMatchObject({
    mode: 'missing_or_failed_only',
    max_count: 25,
    scope: { response_ids: [101, 102, 105] },
  });

  await page.getByTestId('attempt-analyzer-batch-confirm').click();
  await expect(page.getByTestId('attempt-analyzer-last-run')).toContainText('暂未开放');
  await expect(page.getByTestId('attempt-analyzer-last-run')).not.toContainText('analyzer_run_persistence_required');
  expect(api.submitPayloads).toHaveLength(1);
  expect(api.actualAnalyzerUrls).toContain('POST /admin/api/analyzer/responses/batch');
  await errors.assertClean();
});

test('Admin Attempts shows incomplete dry-run counts for oversized filter scope', async ({ page }) => {
  await installAdminDocumentRoute(page);
  const api = await routeAttemptsApis(page);
  const errors = installAdminErrorGuards(page);

  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded' });
  await page.locator('select[x-model="attemptFilter.status"]').selectOption('done');
  await page.getByTestId('attempt-analyzer-batch-button').click();
  await page.getByTestId('attempt-analyzer-batch-scope-filter').click();

  await expect(page.getByTestId('attempt-analyzer-batch-preview')).toBeVisible();
  await expect(page.getByTestId('attempt-analyzer-batch-incomplete')).toBeVisible();
  await expect(page.getByTestId('attempt-analyzer-batch-eligible')).toContainText('5000');
  await expect(page.getByTestId('attempt-analyzer-batch-submit-cap')).toContainText('0 / 25');
  expect(api.dryRunPayloads.at(-1)).toMatchObject({
    scope: {
      filters: { attempt_status: 'done' },
    },
  });
  await errors.assertClean();
});
