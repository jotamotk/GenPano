import { expect, test } from '@playwright/test';

import {
  fulfillJson,
  installAdminDocumentRoute,
  installAdminErrorGuards,
  normalizeAdminApiPath,
} from './admin-fixtures';

const competitiveCandidate = {
  id: 'pm-competitive-varonis-001',
  run_id: 'run-competitive-001',
  topic_id: 135,
  topic_text: '终端数据安全管理工具性价比',
  brand_id: 1,
  brand_name: 'bestCoffer',
  dimension: 'brand',
  intent: 'commercial',
  language: 'zh-CN',
  template_strategy: 'latest',
  template_version: 'v1',
  text: 'bestCoffer 和 Varonis 哪个更适合终端数据安全管理？',
  status: 'pending',
  confidence: 0.92,
  reason: '覆盖用户在终端数据安全管理场景中比较 bestCoffer 与 Varonis 的需求',
  duplicate_of: null,
  prompt_scope: 'competitive',
  competitive_type: 'direct_comparison',
  competitor_name: 'Varonis',
  competitor_brand_id: 2,
  scenario_axis: 'terminal data security',
  quality_gate_status: null,
  quality_gate_reason: null,
  quality_gate_message: null,
  tags: {
    source: 'prompt_matrix',
    routing: 'deferred_to_query_pool',
    prompt_scope: 'competitive',
    competitive_type: 'direct_comparison',
    competitor_name: 'Varonis',
    competitor_brand_id: 2,
    scenario_axis: 'terminal data security',
  },
  review_reason: null,
  approved_prompt_id: null,
  created_at: '2026-05-09T10:00:00',
  reviewed_at: null,
};

test('Prompt Matrix shows a competitive prompt with a named competitor', async ({ page }) => {
  let generated = false;
  await installAdminDocumentRoute(page);
  const errors = installAdminErrorGuards(page);

  await page.route(/.*\/(?:api\/admin|admin\/api)\/.*/, async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = normalizeAdminApiPath(url);
    const method = request.method();

    if (method === 'GET' && path.endsWith('/auth/session')) {
      await fulfillJson(route, {
        authenticated: true,
        admin: {
          id: 'admin-e2e',
          email: 'admin-e2e@example.test',
          role: 'super_admin',
          status: 'active',
        },
      });
      return;
    }

    if (!path.includes('/prompt-matrix/')) {
      await fulfillJson(route, { success: true, rows: [], brands: [], products: [] });
      return;
    }

    if (method === 'GET' && path.endsWith('/config')) {
      await fulfillJson(route, {
        success: true,
        defaults: {
          intentCount: 4,
          languageCount: 2,
          maxPerTopic: 8,
          maxPrompts: 10,
          templateStrategy: 'latest',
          promptStyle: 'natural',
          audienceMode: 'general',
          overflowPolicy: 'auto_batch',
        },
        options: {
          intents: ['informational', 'commercial', 'transactional', 'navigational'],
          languages: ['zh-CN', 'en-US'],
          overflowPolicies: ['auto_batch'],
          templateStrategies: ['latest'],
          promptStyles: ['natural'],
          audienceModes: ['general'],
          maxPromptsHardLimit: 200,
          maxPerTopicLimit: 20,
        },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/topics')) {
      await fulfillJson(route, {
        success: true,
        rows: [
          {
            id: 'T-135',
            raw_id: 135,
            title: '终端数据安全管理工具性价比',
            brand: 'bestCoffer',
            brand_id: 1,
            dimension: 'brand',
            dimension_key: 'brand',
            coverage: 'gap',
            prompt_count: 0,
          },
        ],
        pagination: { page: 1, per_page: 20, total: 1, total_pages: 1 },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/gaps')) {
      await fulfillJson(route, {
        success: true,
        rows: [
          {
            topic_id: 135,
            topic_text: '终端数据安全管理工具性价比',
            brand_name: 'bestCoffer',
            coverage: 'gap',
            prompt_count: 0,
          },
        ],
        summary: { gap_topics: 1, total_topics: 1 },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/prompts')) {
      await fulfillJson(route, {
        success: true,
        rows: [],
        pagination: { page: 1, per_page: 60, total: 0, total_pages: 1 },
        stats: {},
      });
      return;
    }

    if (method === 'POST' && path.endsWith('/generate')) {
      generated = true;
      await fulfillJson(route, {
        success: true,
        run_id: 'run-competitive-001',
        status: 'completed',
        estimated_prompts: 1,
        candidates_generated: 1,
        summary: {
          inserted_count: 1,
          skipped_count: 0,
        },
      });
      return;
    }

    if (method === 'GET' && path.includes('/runs/run-competitive-001')) {
      await fulfillJson(route, {
        success: true,
        run: {
          id: 'run-competitive-001',
          status: 'completed',
          estimated_prompts: 1,
          candidates_generated: 1,
          metrics: { accepted: 1 },
        },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/candidates')) {
      const rows = generated ? [competitiveCandidate] : [];
      await fulfillJson(route, {
        success: true,
        rows,
        pagination: {
          page: 1,
          per_page: 20,
          total: rows.length,
          total_pages: 1,
        },
        summary: {
          status_counts: {
            pending: rows.length,
            approved: 0,
            rejected: 0,
            all: rows.length,
          },
          duplicate_candidates: 0,
          pending_candidates: rows.length,
        },
      });
      return;
    }

    throw new Error(`Unhandled Prompt Matrix API request: ${method} ${path}${url.search}`);
  });

  await page.goto('/admin/planner-prompt-matrix', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Prompt Matrix').first()).toBeVisible();

  await page.getByRole('button', { name: '选择全部匹配' }).first().click();
  await expect(page.getByText(/已选 1/).first()).toBeVisible();

  await page.getByRole('button', { name: '生成 Prompt' }).first().click({ force: true });

  const candidateRow = page.getByRole('row', { name: /pm-competitive-varonis-001/ });
  await expect(candidateRow.getByText(competitiveCandidate.text)).toBeVisible({ timeout: 10_000 });
  await expect(candidateRow.getByText('Competitive', { exact: true })).toBeVisible();
  await expect(candidateRow.getByText('Direct comparison', { exact: true })).toBeVisible();
  await expect(candidateRow.getByText('vs Varonis', { exact: true })).toBeVisible();

  const visibleText = await page.locator('body').innerText();
  expect(visibleText).toContain('bestCoffer');
  expect(visibleText).toContain('Varonis');
  expect(visibleText).not.toMatch(/similar products|同类品牌|其他工具|类似产品/);
  await errors.assertClean();
});
