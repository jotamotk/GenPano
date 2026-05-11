import { expect, test, type Page } from '@playwright/test';

import {
  fulfillJson,
  installAdminDocumentRoute,
  installAdminErrorGuards,
  normalizeAdminApiPath,
} from './admin-fixtures';

const routeSchedulerApis = async (page: Page) => {
  await page.route(/.*\/(?:api\/admin|admin\/api)(?:\/.*)?/, async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = normalizeAdminApiPath(url);
    const method = request.method();

    if (method === 'GET' && path.endsWith('/auth/session')) {
      await fulfillJson(route, {
        authenticated: true,
        admin: { id: 'admin-scheduler-e2e', email: 'scheduler@example.test' },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/admin/brands')) {
      await fulfillJson(route, { brands: [] });
      return;
    }

    if (method === 'GET' && path.endsWith('/segments')) {
      await fulfillJson(route, {
        rows: [],
        pagination: { page: 1, per_page: 50, total: 0, total_pages: 1 },
        summary: {},
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/scheduler/config')) {
      await fulfillJson(route, {
        mode: 'auto',
        daily_time: '09:00',
        timezone: 'Asia/Shanghai',
        retry_max: 3,
        paused_engines: [],
        engine_caps: {},
        capacity: [],
        capacity_total: 0,
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/scheduler/today')) {
      await fulfillJson(route, {
        engines: [],
        total: { target: 0, done: 0, running: 0, pending: 0, failed: 0 },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/scheduler/runs')) {
      await fulfillJson(route, { rows: [], total: 0, page: 1, per_page: 20 });
      return;
    }

    if (method === 'GET' && path.endsWith('/scheduler/schedules')) {
      await fulfillJson(route, []);
      return;
    }

    if (method === 'GET' && path.endsWith('/scheduler/upcoming')) {
      await fulfillJson(route, {
        days: 2,
        by_date: {
          '2026-05-10': [
            {
              id: 42,
              query_text: 'Compare Lancôme and Estée Lauder serums',
              target_llm: 'ChatGPT',
              profile_id: null,
              cadence_days: 2,
              fires_at: '2026-05-10T08:30:00',
            },
          ],
        },
      });
      return;
    }

    await fulfillJson(route, {});
  });
};

test('Admin scheduler renders upcoming by_date payload without the failure toast', async ({ page }) => {
  await installAdminDocumentRoute(page);
  await routeSchedulerApis(page);
  const errors = installAdminErrorGuards(page);

  await page.goto('/admin/planner-scheduler', { waitUntil: 'domcontentloaded' });

  await expect(page.getByText('2026-05-10')).toBeVisible();
  await expect(page.getByText('Compare Lancôme and Estée Lauder serums')).toBeVisible();
  await expect(page.getByText(/加载未来计划失败/)).toHaveCount(0);

  await errors.assertClean();
});
