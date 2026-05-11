import { expect, test, type Page } from '@playwright/test';

import {
  fulfillJson,
  installAdminDocumentRoute,
  installAdminErrorGuards,
  normalizeAdminApiPath,
} from './admin-fixtures';

const accountRows = [
  {
    id: 101,
    llm_name: 'chatgpt',
    phone_number: 'quota-a@example.test',
    status: 'active',
    cookie_count: 4,
    consecutive_fails: 0,
    query_count_today: 20,
    daily_limit: 20,
    updated_at: '2026-05-12T08:15:00Z',
  },
  {
    id: 102,
    llm_name: 'chatgpt',
    phone_number: 'quota-b@example.test',
    status: 'active',
    cookie_count: 4,
    consecutive_fails: 0,
    query_count_today: 10,
    daily_limit: 10,
    updated_at: '2026-05-12T08:20:00Z',
  },
];

const routeQuotaApis = async (page: Page) => {
  await page.route(/.*\/(?:api|admin\/api)(?:\/.*)?/, async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = normalizeAdminApiPath(url);
    const method = request.method();

    if (method === 'GET' && path.endsWith('/auth/session')) {
      await fulfillJson(route, {
        authenticated: true,
        admin: { id: 'quota-admin', email: 'quota@example.test' },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/admin/brands')) {
      await fulfillJson(route, { brands: [] });
      return;
    }

    if (method === 'GET' && path.endsWith('/topics')) {
      await fulfillJson(route, []);
      return;
    }

    if (method === 'GET' && path.endsWith('/prompts')) {
      await fulfillJson(route, []);
      return;
    }

    if (method === 'GET' && path.endsWith('/queries')) {
      await fulfillJson(route, {
        rows: [
          {
            id: 9001,
            target_llm: 'chatgpt',
            status: 'failed',
            retry_count: 0,
            query_text: 'Quota visibility check',
            account_id: null,
            profile_country: 'CN',
            retry_reason: 'account_daily_limit_exhausted',
            queued_at: '2026-05-12T08:00:00Z',
            started_at: '2026-05-12T08:01:00Z',
            finished_at: '2026-05-12T08:01:12Z',
          },
        ],
        total: 1,
        by_status: { failed: 1 },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/accounts')) {
      await fulfillJson(route, accountRows);
      return;
    }

    if (method === 'GET' && path.endsWith('/accounts/profile_counts')) {
      await fulfillJson(route, {});
      return;
    }

    await fulfillJson(route, {});
  });
};

test('Admin Tracker and Account Pool explain daily quota exhaustion without mutation', async ({ page }) => {
  await installAdminDocumentRoute(page);
  await routeQuotaApis(page);
  const errors = installAdminErrorGuards(page);
  const mutations: string[] = [];

  page.on('request', request => {
    const method = request.method().toUpperCase();
    if (method === 'GET' || method === 'HEAD' || method === 'OPTIONS') return;
    const path = normalizeAdminApiPath(new URL(request.url()));
    if (path.includes('/auth/login')) return;
    if (path.includes('/api')) mutations.push(`${method} ${path}`);
  });

  await page.goto('/admin/tracker-attempts', { waitUntil: 'domcontentloaded' });

  await expect(page.getByText('account_daily_limit_exhausted').first()).toBeVisible();
  await expect(page.getByText('活跃账号 2 个，今日剩余额度 0')).toBeVisible();
  await expect(page.getByText('等待明日重置')).toBeVisible();
  await expect(page.getByText('提高 daily_limit')).toBeVisible();
  await expect(page.getByText('#519 审计退款/修正今日计数')).toBeVisible();

  await page.goto('/admin/planner-resources', { waitUntil: 'domcontentloaded' });

  await expect(page.getByRole('columnheader', { name: '今日配额' })).toBeVisible();
  await expect(page.getByText('20 / 20')).toBeVisible();
  await expect(page.getByText('剩余 0').first()).toBeVisible();
  await expect(page.getByRole('button', { name: '高风险重置' }).first()).toBeVisible();
  await expect(page.getByText('仅在审计确认后使用；正式退款/修正语义见 #519')).toBeVisible();

  expect(mutations, 'visualization pass must not call mutating Admin APIs').toEqual([]);
  await errors.assertClean();
});
