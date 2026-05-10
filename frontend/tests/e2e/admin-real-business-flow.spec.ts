import { expect, test, type Page } from '@playwright/test';

import { installAdminErrorGuards } from './admin-fixtures';

const stagingEnabled = process.env.ADMIN_E2E_STAGING === '1';
const realBusinessFlowEnabled = process.env.ADMIN_E2E_REAL_BUSINESS_FLOW === '1';

test.skip(
  !stagingEnabled || !realBusinessFlowEnabled,
  'Set ADMIN_E2E_STAGING=1 and ADMIN_E2E_REAL_BUSINESS_FLOW=1 to run the real business flow gate.',
);

type ApiResult = {
  ok: boolean;
  status: number;
  url: string;
  body: any;
  text: string;
};

type ApiOptions = {
  method?: string;
  body?: any;
};

const runId = process.env.E2E_RUN_ID || `local-${Date.now()}`;

const requireEnv = (name: string): string => {
  const value = (process.env[name] || '').trim();
  if (!value) {
    throw new Error(`${name} is required for the real Admin business-flow E2E gate.`);
  }
  return value;
};

const ensureAdminSession = async (page: Page) => {
  await page.goto('/admin/planner-topics', { waitUntil: 'domcontentloaded' });
  const emailInput = page.locator('input[type="email"]').first();
  const passwordInput = page.locator('input[type="password"]').first();
  if (await emailInput.isVisible().catch(() => false)) {
    await emailInput.fill(requireEnv('ADMIN_E2E_EMAIL'));
    await passwordInput.fill(requireEnv('ADMIN_E2E_PASSWORD'));
    await page.locator('button[type="submit"], form button').first().click();
  }
  await expect(page.locator('main')).toBeVisible({ timeout: 30_000 });
};

const adminApi = async (page: Page, path: string, options: ApiOptions = {}): Promise<ApiResult> => {
  return await page.evaluate(
    async ({ path, options }) => {
      const response = await fetch(`/api/admin${path}`, {
        method: options.method || 'GET',
        credentials: 'same-origin',
        headers: { 'content-type': 'application/json' },
        body: options.body === undefined ? undefined : JSON.stringify(options.body),
      });
      const text = await response.text();
      let body: any = null;
      try {
        body = text ? JSON.parse(text) : null;
      } catch {
        body = null;
      }
      return {
        ok: response.ok,
        status: response.status,
        url: response.url,
        body,
        text,
      };
    },
    { path, options },
  );
};

const expectApiOk = (result: ApiResult, label: string): any => {
  if (!result.ok) {
    const detail = result.body ? JSON.stringify(result.body) : result.text;
    throw new Error(`${label} failed with HTTP ${result.status} at ${result.url}: ${detail}`);
  }
  return result.body;
};

const pollRun = async (
  page: Page,
  pathPrefix: string,
  id: string,
  label: string,
  timeoutMs = 10 * 60_000,
) => {
  const startedAt = Date.now();
  let lastRun: any = null;
  while (Date.now() - startedAt < timeoutMs) {
    const body = expectApiOk(await adminApi(page, `${pathPrefix}/${id}`), `${label} run read`);
    lastRun = body.run;
    const status = String(lastRun?.status || '');
    if (['completed', 'failed', 'cancelled'].includes(status)) {
      if (status !== 'completed') {
        throw new Error(`${label} run did not complete: ${JSON.stringify(lastRun)}`);
      }
      return lastRun;
    }
    await page.waitForTimeout(5_000);
  }
  throw new Error(`${label} run timed out. Last run state: ${JSON.stringify(lastRun)}`);
};

const createSegmentAndProfile = async (page: Page, brand: any) => {
  const suffix = runId.replace(/[^a-zA-Z0-9]/g, '').slice(-8).toUpperCase() || 'LOCAL';
  const segmentId = `SEG-${suffix}`;
  const profileId = `P-${suffix}`;
  const brandId = String(brand.id);
  const brandName = String(brand.name || brand.brand_name || `Brand ${brandId}`);

  const segmentBody = expectApiOk(
    await adminApi(page, '/segments', {
      method: 'POST',
      body: {
        id: segmentId,
        code: segmentId,
        name: `E2E ${runId}`,
        brand_id: brandId,
        brand_name: brandName,
        industry: brand.industry_id || brand.industry || '',
        status: 'active',
        weight: 1,
        reason: `e2e ${runId}`,
      },
    }),
    'create E2E segment',
  );
  const segment = segmentBody.segment;

  const profileBody = expectApiOk(
    await adminApi(page, `/segments/${segment.id}/profiles`, {
      method: 'POST',
      body: {
        id: profileId,
        code: profileId,
        name: `E2E profile ${runId}`,
        demographic: 'Business software evaluator for a small real-flow smoke test.',
        need: 'Needs concise, relevant buying and comparison queries.',
        status: 'active',
        weight: 1,
        reason: `e2e ${runId}`,
      },
    }),
    'create E2E profile',
  );

  return { segment, profile: profileBody.profile };
};

test('real Topic -> Prompt Matrix -> Query Pool -> Extraction flow succeeds', async ({ page }) => {
  const brandId = Number(requireEnv('ADMIN_E2E_BRAND_ID'));
  const errors = installAdminErrorGuards(page);
  await ensureAdminSession(page);

  let segmentId: string | undefined;
  try {
    const config = expectApiOk(await adminApi(page, '/topic-plan/config'), 'topic config');
    const brand = (config.brands || []).find((item: any) => Number(item.id) === brandId);
    if (!brand) {
      throw new Error(`ADMIN_E2E_BRAND_ID=${brandId} was not found in Topic Plan config.`);
    }

    const { segment } = await createSegmentAndProfile(page, brand);
    segmentId = segment.id;

    const topicGenerate = expectApiOk(
      await adminApi(page, '/topic-plan/generate', {
        method: 'POST',
        body: {
          brand_ids: [brandId],
          max_per_brand: 2,
          max_topics: 2,
          gap_priority: 'p12',
          overflow_policy: 'review',
        },
      }),
      'topic generation start',
    );
    const topicRun = await pollRun(
      page,
      '/topic-plan/runs',
      topicGenerate.run_id,
      'Topic Plan',
    );
    expect(Number(topicRun.candidates_generated || 0)).toBeGreaterThan(0);

    const topicCandidates = expectApiOk(
      await adminApi(
        page,
        `/topic-plan/candidates?status=pending&run_id=${encodeURIComponent(topicGenerate.run_id)}&limit=20`,
      ),
      'topic candidates',
    ).rows;
    expect(topicCandidates.length).toBeGreaterThan(0);
    const topicCandidate = topicCandidates[0];
    expect(topicCandidate.brand_context_version).toBeTruthy();

    const approvedTopic = expectApiOk(
      await adminApi(page, `/topic-plan/candidates/${topicCandidate.id}/review`, {
        method: 'POST',
        body: { status: 'approved', reason: `e2e ${runId}` },
      }),
      'approve topic candidate',
    ).candidate;
    expect(approvedTopic.approved_topic_id).toBeTruthy();

    const promptGenerate = expectApiOk(
      await adminApi(page, '/prompt-matrix/generate', {
        method: 'POST',
        body: {
          topic_ids: [approvedTopic.approved_topic_id],
          intent_count: 4,
          language_count: 2,
          max_per_topic: 8,
          max_prompts: 8,
          template_strategy: 'latest',
          prompt_style: 'natural',
          audience_mode: 'general',
          overflow_policy: 'review',
        },
      }),
      'prompt generation start',
    );
    const promptRun = await pollRun(
      page,
      '/prompt-matrix/runs',
      promptGenerate.run_id,
      'Prompt Matrix',
    );
    expect(Number(promptRun.candidates_generated || 0)).toBeGreaterThan(0);

    const promptCandidateRows = expectApiOk(
      await adminApi(
        page,
        `/prompt-matrix/candidates?status=pending&brand_id=${brandId}&per_page=100`,
      ),
      'prompt candidates',
    ).rows.filter((row: any) => row.run_id === promptGenerate.run_id);
    expect(promptCandidateRows.length).toBeGreaterThan(0);

    const promptCandidate = promptCandidateRows[0];
    expect(promptCandidate.prompt_scope).toBeTruthy();
    expect(promptCandidate.intent).toBeTruthy();
    expect(promptCandidate.language).toBeTruthy();

    const approvedPrompt = expectApiOk(
      await adminApi(page, `/prompt-matrix/candidates/${promptCandidate.id}/review`, {
        method: 'POST',
        body: { status: 'approved', reason: `e2e ${runId}` },
      }),
      'approve prompt candidate',
    ).candidate;
    expect(approvedPrompt.approved_prompt_id).toBeTruthy();

    const queryStart = expectApiOk(
      await adminApi(page, '/query-pool/assemble', {
        method: 'POST',
        body: {
          prompt_ids: [String(approvedPrompt.approved_prompt_id)],
          segment_ids: [segment.id],
          profiles_per_prompt: 1,
          profile_strategy: 'full',
          desired_engine_policy: 'inherit',
          max_candidates: 1,
          overflow_policy: 'split',
        },
      }),
      'query assemble start',
    );
    const queryRunId = queryStart.run?.id;
    expect(queryRunId).toBeTruthy();
    const queryRun = await pollRun(page, '/query-pool/runs', queryRunId, 'Query Pool');
    expect(Number(queryRun.candidates_assembled || 0)).toBeGreaterThan(0);

    const queryCandidates = expectApiOk(
      await adminApi(page, `/query-pool/candidates?run_id=${encodeURIComponent(queryRunId)}&limit=20`),
      'query candidates',
    ).rows;
    expect(queryCandidates.length).toBeGreaterThan(0);
    expect(queryCandidates[0].rendered_query).toBeTruthy();
    expect(queryCandidates[0].brand_context_version).toBeTruthy();

    const extraction = expectApiOk(
      await adminApi(page, '/llm-extraction/backfill', {
        method: 'POST',
        body: {
          brand_id: brandId,
          brand_context_version: topicCandidate.brand_context_version,
          limit: 5,
          reason: `e2e ${runId}`,
        },
      }),
      'llm extraction backfill',
    ).summary;
    expect(Number(extraction.snapshots_scanned || 0)).toBeGreaterThan(0);

    await errors.assertClean();
  } finally {
    if (segmentId) {
      await adminApi(page, `/segments/${segmentId}`, {
        method: 'DELETE',
        body: { reason: `e2e cleanup ${runId}` },
      }).catch(() => undefined);
    }
  }
});
