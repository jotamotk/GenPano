import { expect, test, type Page, type Route } from '@playwright/test';

import {
  fulfillJson,
  installAdminDocumentRoute,
  installAdminErrorGuards,
  normalizeAdminApiPath,
} from './admin-fixtures';

const runId = process.env.E2E_RUN_ID || `local-${Date.now()}`;
const brandId = 91001;
const brandName = `E2E Gate Brand ${runId}`;
const contextVersion = `bcx-${runId}`;

type GateState = {
  topicCandidates: Array<Record<string, unknown>>;
  promptCandidates: Array<Record<string, unknown>>;
  queryCandidates: Array<Record<string, unknown>>;
  extraction: {
    entities: Array<Record<string, unknown>>;
    attributes: Array<Record<string, unknown>>;
    claims: Array<Record<string, unknown>>;
  };
  promptRunStatus: 'idle' | 'completed' | 'failed';
  topicGenerateMode: 'normal' | 'failed';
  promptGenerateMode: 'normal' | 'run_failed';
  queryAssembleMode: 'normal' | 'run_failed';
  extractionBackfillMode: 'normal' | 'failed';
  deletedPromptCandidateIds: string[];
};

const makeState = (): GateState => ({
  topicCandidates: [
    {
      id: `topic-candidate-${runId}`,
      title: `${brandName} secure diligence workflow`,
      brand: brandName,
      brand_id: brandId,
      dimension: 'scenario',
      coverage_gap: 'scenario + competitor context',
      confidence: 0.92,
      status: 'pending',
      reason: 'Search-backed context references product, buyer segment, and competitor axes.',
      brand_context_version: contextVersion,
      topic_axis: 'scenario',
      context_refs_json: { products: ['Gate Vault'], competitors: ['DealRoom'], scenarios: ['M&A diligence'] },
    },
  ],
  promptCandidates: [
    {
      id: `prompt-candidate-${runId}`,
      topic_id: 135,
      topic_text: `${brandName} secure diligence workflow`,
      brand_id: brandId,
      brand_name: brandName,
      dimension: 'scenario',
      intent: 'commercial',
      language: 'zh-CN',
      template_strategy: 'latest',
      template_version: 'v1',
      text: `${brandName} Gate Vault 和 DealRoom 在 M&A 尽调权限审计方面哪个更适合？`,
      status: 'pending',
      confidence: 0.94,
      reason: 'Uses exact competitor and comparison axis from the context slot.',
      duplicate_of: null,
      prompt_scope: 'competitive',
      competitive_type: 'direct_comparison',
      product_name: 'Gate Vault',
      competitor_name: 'DealRoom',
      competitor_brand_id: 91002,
      scenario_axis: 'M&A diligence',
      comparison_axis: 'permission audit',
      brand_context_version: contextVersion,
      quality_gate_status: null,
      quality_gate_reason: null,
      quality_gate_message: null,
      approved_prompt_id: null,
      tags: {
        prompt_scope: 'competitive',
        competitive_type: 'direct_comparison',
        product_name: 'Gate Vault',
        competitor_name: 'DealRoom',
        competitor_brand_id: 91002,
        scenario_axis: 'M&A diligence',
        comparison_axis: 'permission audit',
        brand_context_version: contextVersion,
      },
    },
  ],
  queryCandidates: [
    {
      id: `query-candidate-${runId}`,
      prompt_id: 77001,
      prompt_text: `${brandName} Gate Vault 和 DealRoom 在 M&A 尽调权限审计方面哪个更适合？`,
      topic_text: `${brandName} secure diligence workflow`,
      rendered_query: `CFO 在 M&A 尽调时比较 ${brandName} Gate Vault 和 DealRoom 权限审计能力`,
      segment_id: 'Enterprise Deal Team',
      profile_id: 'CFO + legal operations',
      candidate_status: 'candidate',
      metadata: {
        prompt_scope: 'competitive',
        product_name: 'Gate Vault',
        competitor_name: 'DealRoom',
        competitive_type: 'direct_comparison',
        comparison_axis: 'permission audit',
        brand_context_version: contextVersion,
      },
    },
  ],
  extraction: {
    entities: [
      {
        id: `entity-candidate-${runId}`,
        brand_id: brandId,
        brand_context_version: contextVersion,
        entity_type: 'competitor',
        name: 'DealRoom',
        normalized_name: 'dealroom',
        candidate_key: `entity:competitor:dealroom:${brandId}`,
        source: 'llm_search',
        confidence: 0.87,
        attributes: { overlap_category: 'Virtual data room' },
        evidence: { snippet: 'DealRoom is a virtual data room competitor.' },
        source_notes: [{ title: 'Search result', url: 'https://example.test/dealroom' }],
        status: 'pending',
      },
    ],
    attributes: [
      {
        id: `attribute-candidate-${runId}`,
        brand_id: brandId,
        brand_context_version: contextVersion,
        entity_kind: 'product',
        entity_name: 'Gate Vault',
        attribute_key: 'key_features',
        attribute_value: 'permission audit',
        normalized_value: 'permission audit',
        candidate_key: `attr:product:gate-vault:key_features:permission-audit:${runId}`,
        source: 'llm_search',
        confidence: 0.84,
        evidence: { snippet: 'Gate Vault supports permission audit.' },
        source_notes: [{ title: 'Product page', url: 'https://example.test/gate-vault' }],
        status: 'pending',
      },
    ],
    claims: [
      {
        id: `claim-candidate-${runId}`,
        brand_id: brandId,
        brand_context_version: contextVersion,
        entity_kind: 'brand',
        entity_id: String(brandId),
        entity_name: brandName,
        claim_type: 'pros',
        text: 'Strong audit trail for regulated deal teams.',
        normalized_text: 'strong audit trail for regulated deal teams',
        scenario: 'M&A diligence',
        candidate_key: `claim:brand:${brandId}:pros:audit-trail:${runId}`,
        source: 'llm_search',
        confidence: 0.81,
        evidence: { snippet: 'Strong audit trail.' },
        source_notes: [{ title: 'Search result', url: 'https://example.test/audit' }],
        status: 'pending',
      },
    ],
  },
  promptRunStatus: 'idle',
  topicGenerateMode: 'normal',
  promptGenerateMode: 'normal',
  queryAssembleMode: 'normal',
  extractionBackfillMode: 'normal',
  deletedPromptCandidateIds: [],
});

const routeAdminApi = async (page: Page, state: GateState) => {
  await page.route(/.*\/(?:api\/admin|admin\/api)\/.*/, async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = normalizeAdminApiPath(url);
    const method = request.method();

    if (method === 'GET' && path.endsWith('/auth/session')) {
      await fulfillJson(route, {
        authenticated: true,
        admin: { id: `admin-${runId}`, email: `admin-${runId}@example.test`, role: 'super_admin' },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/topic-plan/config')) {
      await fulfillJson(route, {
        success: true,
        brands: [{ id: brandId, name: brandName, industry_id: 'vdr', topic_count: 0, selected: true }],
        industries: [{ id: 'vdr', name: 'vdr' }],
        categories: [{ id: 'deal-workflow', name: 'deal workflow' }],
        defaults: { industryId: 'vdr', categoryId: '', maxPerBrand: 40, maxTopics: 180, gapPriority: 'p12', overflowPolicy: 'review' },
        summary: { pending_candidates: state.topicCandidates.length, low_confidence: 0, llm_configured: true },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/topic-plan/coverage')) {
      await fulfillJson(route, {
        success: true,
        rows: [{ brand_id: brandId, brand: brandName, category: 'deal workflow', missing_topics: 1, coverage_pct: 33 }],
        summary: { total_brands: 1, gap_brands: 1 },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/topic-plan/candidates')) {
      const status = url.searchParams.get('status') || 'pending';
      const rows = state.topicCandidates.filter(row => status === 'all' || row.status === status);
      await fulfillJson(route, {
        success: true,
        rows,
        summary: { pending: rows.filter(row => row.status === 'pending').length, approved: 0, rejected: 0 },
      });
      return;
    }

    if (method === 'POST' && path.endsWith('/topic-plan/candidates/bulk-review')) {
      const body = request.postDataJSON();
      const ids = new Set<string>(body.candidate_ids || body.ids || []);
      state.topicCandidates = state.topicCandidates.map(row => (
        ids.has(String(row.id)) ? { ...row, status: body.status, reviewed_at: '2026-05-10T10:00:00' } : row
      ));
      await fulfillJson(route, { success: true, summary: { updated_count: ids.size } });
      return;
    }

    if (method === 'POST' && path.endsWith('/topic-plan/generate')) {
      if (state.topicGenerateMode === 'failed') {
        await fulfillJson(route, {
          success: false,
          code: 'llm_failed',
          message: 'LLM call failed',
          detail: 'search-backed topic generation timed out',
          request_id: `req-topic-failed-${runId}`,
        }, 502);
        return;
      }
      await fulfillJson(route, {
        success: true,
        run_id: `topic-run-${runId}`,
        status: 'completed',
        summary: { estimated: 1, generated: state.topicCandidates.length },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/topic-plan/topics')) {
      await fulfillJson(route, {
        success: true,
        rows: [
          {
            id: 'T-135',
            raw_id: 135,
            title: `${brandName} secure diligence workflow`,
            brand: brandName,
            brand_id: brandId,
            dimension: 'scenario',
            coverage: 'gap',
            prompt_count: state.promptCandidates.length,
            brand_context_version: contextVersion,
            topic_axis: 'scenario',
          },
        ],
        pagination: { page: 1, per_page: 20, total: 1, total_pages: 1 },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/prompt-matrix/config')) {
      await fulfillJson(route, {
        success: true,
        brands: [{ id: brandId, name: brandName, industry_id: 'vdr', aliases: [] }],
        industries: [{ id: 'vdr', name: 'vdr' }],
        defaults: { intentCount: 4, languageCount: 2, maxPerTopic: 8, maxPrompts: 10, templateStrategy: 'latest', promptStyle: 'natural', audienceMode: 'general', overflowPolicy: 'auto_batch' },
        options: { intents: ['commercial'], languages: ['zh-CN'], maxPromptsHardLimit: 200, maxPerTopicLimit: 20 },
        summary: { pending_candidates: state.promptCandidates.length, duplicate_candidates: 0, llm_configured: true },
        stats: {},
        qualityGates: [],
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/prompt-matrix/topics')) {
      await fulfillJson(route, {
        success: true,
        rows: [{ raw_id: 135, id: 'T-135', title: `${brandName} secure diligence workflow`, brand_id: brandId, brand: brandName, prompt_count: 0, brand_context_version: contextVersion }],
        pagination: { page: 1, per_page: 20, total: 1, total_pages: 1 },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/prompt-matrix/gaps')) {
      await fulfillJson(route, {
        success: true,
        rows: [{ topic_id: 135, topic_text: `${brandName} secure diligence workflow`, brand_name: brandName, prompt_count: 0, coverage: 'gap' }],
        summary: { gap_topics: 1, total_topics: 1 },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/prompt-matrix/prompts')) {
      await fulfillJson(route, {
        success: true,
        rows: [
          {
            raw_id: 77001,
            id: 77001,
            text: state.promptCandidates[0].text,
            title: state.promptCandidates[0].text,
            topic_id: 135,
            topic_text: state.promptCandidates[0].topic_text,
            intent: 'commercial',
            language: 'zh-CN',
            prompt_scope: 'competitive',
            metadata: state.promptCandidates[0].tags,
          },
        ],
        pagination: { page: 1, per_page: 60, total: 1, total_pages: 1 },
        stats: {},
      });
      return;
    }

    if (method === 'POST' && path.endsWith('/prompt-matrix/generate')) {
      if (state.promptGenerateMode === 'run_failed') {
        state.promptRunStatus = 'failed';
        await fulfillJson(route, {
          success: true,
          run_id: `prompt-run-${runId}`,
          status: 'running',
          estimated_prompts: 1,
          candidates_generated: 0,
          summary: { accepted: 0, duplicate: 0, retry: 1, coverage: { competitive: 0 } },
        });
        return;
      }
      state.promptRunStatus = 'completed';
      await fulfillJson(route, {
        success: true,
        run_id: `prompt-run-${runId}`,
        status: 'completed',
        estimated_prompts: 1,
        candidates_generated: state.promptCandidates.length,
        summary: { accepted: state.promptCandidates.length, duplicate: 0, retry: 0, coverage: { competitive: 1 } },
      });
      return;
    }

    if (method === 'GET' && path.includes('/prompt-matrix/runs/')) {
      await fulfillJson(route, {
        success: true,
        run: {
          id: `prompt-run-${runId}`,
          status: state.promptRunStatus === 'failed' ? 'failed' : 'completed',
          llm_error: state.promptRunStatus === 'failed' ? 'Prompt LLM call failed after retry' : '',
          request_id: state.promptRunStatus === 'failed' ? `req-prompt-failed-${runId}` : '',
          estimated_prompts: 1,
          candidates_generated: state.promptRunStatus === 'failed' ? 0 : state.promptCandidates.length,
          metrics: { accepted: state.promptCandidates.length, duplicate: 0, retry: 0, coverage: { competitive: 1 } },
        },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/prompt-matrix/candidates')) {
      const status = url.searchParams.get('status') || 'pending';
      const scope = url.searchParams.get('scope') || 'all';
      const visibleRows = state.promptCandidates.filter(row => !state.deletedPromptCandidateIds.includes(String(row.id)));
      const rows = visibleRows
        .filter(row => status === 'all' || row.status === status)
        .filter(row => scope === 'all' || row.prompt_scope === scope);
      await fulfillJson(route, {
        success: true,
        rows,
        pagination: { page: 1, per_page: 20, total: rows.length, total_pages: 1 },
        summary: {
          status_counts: {
            pending: visibleRows.filter(row => row.status === 'pending').length,
            approved: visibleRows.filter(row => row.status === 'approved').length,
            rejected: visibleRows.filter(row => row.status === 'rejected').length,
            all: visibleRows.length,
          },
          duplicate_candidates: 0,
          pending_candidates: visibleRows.filter(row => row.status === 'pending').length,
        },
      });
      return;
    }

    if (method === 'POST' && path.endsWith('/prompt-matrix/candidates/bulk-review')) {
      const body = request.postDataJSON();
      const ids = new Set<string>(body.candidate_ids || body.ids || []);
      state.promptCandidates = state.promptCandidates.map(row => (
        ids.has(String(row.id)) ? { ...row, status: body.status, approved_prompt_id: body.status === 'approved' ? 77001 : null } : row
      ));
      await fulfillJson(route, { success: true, summary: { updated_count: ids.size } });
      return;
    }

    if (method === 'POST' && path.endsWith('/prompt-matrix/candidates/bulk-delete')) {
      const body = request.postDataJSON();
      const ids = (body.candidate_ids || body.ids || []).map(String);
      state.deletedPromptCandidateIds.push(...ids);
      await fulfillJson(route, { success: true, deleted: ids });
      return;
    }

    if (method === 'DELETE' && /\/prompt-matrix\/candidates\/[^/]+$/.test(path)) {
      const id = path.split('/').pop() || '';
      state.deletedPromptCandidateIds.push(id);
      await fulfillJson(route, { success: true, deleted: [id] });
      return;
    }

    if (method === 'POST' && path.endsWith('/admin/query-pool/assemble')) {
      if (state.queryAssembleMode === 'run_failed') {
        await fulfillJson(route, {
          success: true,
          run: {
            id: `query-run-${runId}`,
            status: 'failed',
            llm_error: 'Query scope guard failed',
            request_id: `req-query-failed-${runId}`,
            candidates_estimated: 1,
            candidates_assembled: 0,
            preflight_summary: {
              raw_candidates_estimated: 1,
              candidate_ready: 0,
              render_pass_rate: 0,
              segment_coverage: 1,
              profile_coverage: 1,
              scheduler_intake: 'blocked',
            },
          },
        });
        return;
      }
      await fulfillJson(route, {
        success: true,
        run: {
          id: `query-run-${runId}`,
          status: 'completed',
          candidates_estimated: state.queryCandidates.length,
          candidates_assembled: state.queryCandidates.length,
          preflight_summary: {
            raw_candidates_estimated: state.queryCandidates.length,
            candidate_ready: state.queryCandidates.length,
            render_pass_rate: 1,
            segment_coverage: 1,
            profile_coverage: 1,
            scheduler_intake: 'ready',
          },
        },
      });
      return;
    }

    if (method === 'GET' && path.endsWith('/admin/query-pool/candidates')) {
      await fulfillJson(route, {
        success: true,
        rows: state.queryCandidates,
        page_info: { has_next: false, has_prev: false, next_cursor: null, prev_cursor: null },
        summary: { total: state.queryCandidates.length },
      });
      return;
    }

    if (method === 'GET' && path.includes('/llm-extraction/candidates')) {
      const rows = state.extraction.entities;
      await fulfillJson(route, { success: true, items: rows, pagination: { page: 1, per_page: 50, total: rows.length, total_pages: 1 } });
      return;
    }

    if (method === 'GET' && path.includes('/llm-extraction/attributes')) {
      const rows = state.extraction.attributes;
      await fulfillJson(route, { success: true, items: rows, pagination: { page: 1, per_page: 50, total: rows.length, total_pages: 1 } });
      return;
    }

    if (method === 'GET' && path.includes('/llm-extraction/claims')) {
      const rows = state.extraction.claims;
      await fulfillJson(route, { success: true, items: rows, pagination: { page: 1, per_page: 50, total: rows.length, total_pages: 1 } });
      return;
    }

    if (method === 'POST' && path.endsWith('/llm-extraction/backfill')) {
      if (state.extractionBackfillMode === 'failed') {
        await fulfillJson(route, {
          success: false,
          code: 'search_context_failed',
          message: 'Extraction backfill failed',
          detail: 'search-backed extraction timed out',
          request_id: `req-extraction-failed-${runId}`,
        }, 502);
        return;
      }
      await fulfillJson(route, { success: true, summary: { entities_created: 1, attributes_created: 1, claims_created: 1 } });
      return;
    }

    if (method === 'POST' && /\/llm-extraction\/(candidates|attributes|claims)\/[^/]+\/(approve|reject)$/.test(path)) {
      const [, collection, id, action] = path.match(/\/llm-extraction\/(candidates|attributes|claims)\/([^/]+)\/(approve|reject)$/) || [];
      const key = collection === 'candidates' ? 'entities' : collection;
      const rows = state.extraction[key as keyof GateState['extraction']];
      const row = rows.find(item => item.id === id);
      if (row) row.status = action === 'approve' ? 'approved' : 'rejected';
      await fulfillJson(route, { success: true, item: row });
      return;
    }

    throw new Error(`Unhandled Admin API request: ${method} ${path}${url.search}`);
  });
};

test('Admin release gate covers Topic, Prompt Matrix, Query Pool, and Extraction without client errors', async ({ page }) => {
  const state = makeState();
  await installAdminDocumentRoute(page);
  await routeAdminApi(page, state);
  const errors = installAdminErrorGuards(page);
  page.on('dialog', dialog => dialog.accept());

  await page.goto('/admin/planner-topics', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Topic Plan').first()).toBeVisible();
  await expect(page.getByText(/Context bcx-/).first()).toBeVisible();
  await page
    .getByRole('row')
    .filter({ hasText: 'Search-backed context references product' })
    .locator('input[type="checkbox"]')
    .check();
  await page.getByRole('button', { name: '批量通过' }).click();
  await expect(page.getByText('已批量通过 1 个候选 Topic')).toBeVisible();

  await page.goto('/admin/planner-prompt-matrix', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Prompt Matrix').first()).toBeVisible();
  await page.locator("button[\\@click=\"setPromptMatrixTopics(true, 'filtered')\"]").first().click();
  await page.locator('button[\\@click="startPromptMatrixGenerate()"]').first().click({ force: true });
  const promptRow = page.getByRole('row', { name: new RegExp(`prompt-candidate-${runId}`) });
  await expect(promptRow.getByText('vs DealRoom', { exact: true })).toBeVisible({ timeout: 10_000 });
  await expect(promptRow.getByText('Axis permission audit', { exact: true })).toBeVisible();
  await promptRow.locator('input[type="checkbox"]').check();
  await page.getByRole('button', { name: '批量通过' }).click();
  await page.getByRole('button', { name: /已通过/ }).first().click();
  const approvedPromptRow = page.getByRole('row', { name: new RegExp(`prompt-candidate-${runId}`) });
  await expect(approvedPromptRow.getByText('Prompt #77001')).toBeVisible();
  await approvedPromptRow.locator('input[type="checkbox"]').check();
  await page.getByRole('button', { name: /删除 1 条/ }).click();
  const deleteModal = page.getByRole('heading', { name: '批量删除 Prompt 候选' }).locator('..').locator('..');
  await deleteModal.locator('input[type="checkbox"]').check();
  await deleteModal.locator('input[placeholder*="操作理由"]').fill('admin e2e cleanup');
  await deleteModal.getByRole('button', { name: '确认执行' }).click();
  await expect(page.getByText('已删除 1 条 Prompt 候选')).toBeVisible();

  await page.goto('/admin/planner-query-pool', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText(state.queryCandidates[0].rendered_query as string)).toBeVisible();
  await expect(page.getByText('DealRoom').first()).toBeVisible();
  await expect(page.getByText(/bcx-/).first()).toBeVisible();

  await page.goto('/admin/planner-llm-extraction', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('LLM Extraction').first()).toBeVisible();
  await page.getByRole('button', { name: '刷新' }).click();
  await expect(page.getByText('DealRoom').first()).toBeVisible();
  await page.getByRole('button', { name: 'Backfill' }).click();
  await expect(page.getByText(/Backfill 完成：1 entities/)).toBeVisible();
  await page.getByRole('button', { name: '通过' }).first().click();
  await expect(page.getByText('已通过 LLM Extraction 候选')).toBeVisible();
  await page.getByRole('button', { name: 'Attribute' }).click();
  await expect(page.getByText('permission audit').first()).toBeVisible();
  await page.getByRole('button', { name: '拒绝' }).first().click();
  await expect(page.getByText('已拒绝 LLM Extraction 候选')).toBeVisible();
  await page.getByRole('button', { name: 'Claim' }).click();
  await expect(page.getByText('Strong audit trail for regulated deal teams.')).toBeVisible();

  await errors.assertClean();
});

const clearStickyErrorPanel = async (page: Page) => {
  await page.evaluate(() => {
    const data = (window as unknown as { Alpine?: { $data?: (node: Element) => Record<string, unknown> } }).Alpine?.$data?.(document.body);
    if (data) {
      data.errorPanel = null;
      data.errorQueue = [];
      data.errorPanelCopied = false;
      data.errorPanelExpanded = false;
    }
  });
};

test('Admin release gate surfaces Topic, Prompt, Query, and Extraction failures without crashing', async ({ page }) => {
  const state = makeState();
  state.topicGenerateMode = 'failed';
  state.promptGenerateMode = 'run_failed';
  state.queryAssembleMode = 'run_failed';
  state.extractionBackfillMode = 'failed';
  await installAdminDocumentRoute(page);
  await routeAdminApi(page, state);
  const errors = installAdminErrorGuards(page, {
    allowedNetworkErrorUrls: [
      /\/api\/admin\/topic-plan\/generate$/,
      /\/admin\/api\/llm-extraction\/backfill$/,
    ],
  });

  await page.goto('/admin/planner-topics', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Topic Plan').first()).toBeVisible();
  await page.locator('button[\\@click="startTopicPlanGenerate()"]').click();

  await expect(page.getByText('LLM call failed').first()).toBeVisible();
  await expect(page.getByText(`req-topic-failed-${runId}`).first()).toBeVisible();
  await clearStickyErrorPanel(page);

  await page.goto('/admin/planner-prompt-matrix', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Prompt Matrix').first()).toBeVisible();
  await page.locator("button[\\@click=\"setPromptMatrixTopics(true, 'filtered')\"]").first().click();
  await page.locator('button[\\@click="startPromptMatrixGenerate()"]').first().click({ force: true });
  await expect(page.getByText('Prompt LLM call failed after retry').first()).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(`req-prompt-failed-${runId}`).first()).toBeVisible();
  await clearStickyErrorPanel(page);

  await page.goto('/admin/planner-query-pool', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('Query Pool').first()).toBeVisible();
  await page.locator("button[\\@click=\"setQueryPoolPrompts(true, 'filtered')\"]").first().click();
  await page.locator('button[\\@click="startQueryPoolAssemble()"]').first().click();
  await expect(page.getByText('Query scope guard failed').first()).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(`req-query-failed-${runId}`).first()).toBeVisible();
  await clearStickyErrorPanel(page);

  await page.goto('/admin/planner-llm-extraction', { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('LLM Extraction').first()).toBeVisible();
  await page.getByRole('button', { name: 'Backfill' }).click();
  await expect(page.getByText('Extraction backfill failed').first()).toBeVisible();
  await expect(page.getByText(`req-extraction-failed-${runId}`).first()).toBeVisible();
  await errors.assertClean();
});
