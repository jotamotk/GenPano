import { expect, test, type Page } from '@playwright/test';

import {
  fulfillJson,
  installAdminDocumentRoute,
  installAdminErrorGuards,
  normalizeAdminApiPath,
} from './admin-fixtures';

const attemptRows = [
  {
    id: 77901,
    target_llm: 'chatgpt',
    status: 'done',
    retry_count: 0,
    query_text: 'Analyzer done row',
    response: 'The answer contains a complete brand comparison.',
    analysis_status: 'done',
    analysis_summary: '已完成分析 · 4 条依据',
    analysis_evidence_count: 4,
    analysis_run_id: 'ana-run-100',
    analyzed_at: '2026-05-13T09:10:00Z',
  },
  {
    id: 77902,
    target_llm: 'doubao',
    status: 'done',
    retry_count: 1,
    query_text: 'Analyzer partial row',
    response: 'The answer was partially readable.',
    analysis_status: 'partial',
    analysis_summary: '部分完成 · 仍可重新分析',
    analysis_evidence_count: 1,
    analysis_run_id: 'ana-run-101',
  },
  {
    id: 77903,
    target_llm: 'deepseek',
    status: 'done',
    retry_count: 0,
    query_text: 'Analyzer missing row',
    response: 'Fresh response text that has not been analyzed yet.',
    analysis_status: 'missing',
  },
  {
    id: 77904,
    target_llm: 'chatgpt',
    status: 'failed',
    retry_count: 2,
    query_text: 'Analyzer failed attempt row',
    response: null,
    retry_reason: 'browser_timeout',
    analysis_status: 'skipped',
  },
  {
    id: 77905,
    target_llm: 'chatgpt',
    status: 'done',
    retry_count: 0,
    query_text: 'Analyzer running row',
    response: 'Running analyzer response.',
    analysis_status: 'running',
    analysis_run_id: 'ana-run-102',
  },
];

const FILTER_SCOPE_TOTAL = 42;

const routeAttemptsApis = async (page: Page) => {
  await page.route(/.*\/(?:api|admin\/api)(?:\/.*)?/, async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = normalizeAdminApiPath(url);
    const method = request.method();

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
};

test('Admin Attempts shows analyzer status, drawer action, and batch preview without backend mutation', async ({ page }) => {
  await installAdminDocumentRoute(page);
  await routeAttemptsApis(page);
  const errors = installAdminErrorGuards(page);
  const mutations: string[] = [];

  page.on('request', request => {
    const method = request.method().toUpperCase();
    if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') return;
    const path = normalizeAdminApiPath(new URL(request.url()));
    if (path.endsWith('/auth/login')) return;
    if (path.includes('/api')) mutations.push(`${method} ${path}`);
  });

  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded' });

  await expect(page.getByTestId('attempt-analyzer-column-header')).toBeVisible();
  await expect(page.getByTestId('attempt-analyzer-badge-77901')).toContainText('已分析');
  await expect(page.getByTestId('attempt-analyzer-badge-77902')).toContainText('部分完成');
  await expect(page.getByTestId('attempt-analyzer-badge-77903')).toContainText('未分析');
  await expect(page.getByTestId('attempt-analyzer-badge-77904')).toContainText('不可分析');
  await expect(page.getByTestId('attempt-analyzer-badge-77905')).toContainText('分析中');
  await expect(page.getByTestId('attempt-analyzer-action-77904')).toBeDisabled();

  await page.getByTestId('attempt-details-77903').click();
  await expect(page.getByTestId('attempt-drawer')).toBeVisible();
  await expect(page.getByTestId('attempt-response-text')).toContainText('Fresh response text');
  await expect(page.getByTestId('attempt-analyzer-drawer-summary')).toContainText('未分析');
  await page.getByTestId('attempt-analyzer-drawer-trigger').click();
  await expect(page.getByTestId('attempt-analyzer-drawer-summary')).toContainText('等待分析');

  await page.getByTestId('attempt-select-77901').check();
  await page.getByTestId('attempt-select-77902').check();
  await page.getByTestId('attempt-select-77904').check();
  await page.getByTestId('attempt-select-77905').check();
  await page.getByTestId('attempt-analyzer-batch-button').click();
  await expect(page.getByTestId('attempt-analyzer-batch-preview')).toBeVisible();
  await expect(page.getByTestId('attempt-analyzer-batch-scope-selected')).toBeVisible();
  await expect(page.getByTestId('attempt-analyzer-batch-scope-filter')).toBeVisible();
  await expect(page.getByTestId('attempt-analyzer-batch-scope-note')).toContainText('已选');
  await expect(page.getByTestId('attempt-analyzer-batch-requested')).toContainText('4');
  await expect(page.getByTestId('attempt-analyzer-batch-eligible')).toContainText('1');
  await expect(page.getByTestId('attempt-analyzer-batch-skipped-already')).toContainText('1');
  await expect(page.getByTestId('attempt-analyzer-batch-skipped-failed')).toContainText('1');
  await expect(page.getByTestId('attempt-analyzer-batch-skipped-unavailable')).toContainText('1');
  await expect(page.getByTestId('attempt-analyzer-batch-reasons')).toContainText('处理中');
  await expect(page.getByTestId('attempt-analyzer-batch-submit-cap')).toContainText('1 / 25');

  await page.getByTestId('attempt-analyzer-batch-scope-filter').click();
  await expect(page.getByTestId('attempt-analyzer-batch-scope-note')).toContainText('当前筛选');
  await expect(page.getByTestId('attempt-analyzer-batch-requested')).toContainText(String(FILTER_SCOPE_TOTAL));
  await expect(page.getByTestId('attempt-analyzer-batch-visible')).toContainText(String(attemptRows.length));
  await expect(page.getByTestId('attempt-analyzer-batch-submit-cap')).toContainText('25 / 25');

  await page.getByTestId('attempt-analyzer-batch-scope-selected').click();
  await expect(page.getByTestId('attempt-analyzer-batch-submit-cap')).toContainText('1 / 25');

  await page.getByTestId('attempt-analyzer-batch-confirm').click();
  await expect(page.getByTestId('attempt-analyzer-last-run')).toContainText('提交 1 条');
  expect(mutations, 'visualization prototype must not call mutating Admin APIs').toEqual([]);
  await errors.assertClean();
});
