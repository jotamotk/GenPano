import { expect, test, type Page, type Route } from '@playwright/test'

import {
  buildApiHandlers,
  FAKE_COMPETITOR_METRICS,
  FAKE_METRICS,
  FAKE_OVERVIEW,
  FAKE_PROJECT_ID,
} from './fixtures'

async function json(route: Route, data: unknown) {
  await route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify(data),
  })
}

async function seedAuth(page: Page) {
  await page.addInitScript(
    ({ project }) => {
      window.localStorage.setItem('genpano_token', 'fake-jwt-token-for-test')
      window.localStorage.setItem('genpano_lang', 'en-US')
      window.localStorage.setItem(
        'genpano_active_project',
        JSON.stringify({
          id: project,
          primaryBrandId: 42,
          industryId: 1,
          name: 'Analyzer Status Test Project',
          competitorBrandIds: [99, 100],
        }),
      )
    },
    { project: FAKE_PROJECT_ID },
  )
}

async function installApiMocks(page: Page) {
  await page.route(/\/api\/(v1|auth|admin)\//, async (route: Route) => {
    await json(route, { items: [], state: 'empty', total: 0 })
  })

  const handlers = buildApiHandlers()
  for (const [pattern, handler] of Object.entries(handlers)) {
    await page.route(pattern, handler)
  }

  await page.route(`**/api/v1/projects/${FAKE_PROJECT_ID}/overview**`, async route => {
    await json(route, {
      ...FAKE_OVERVIEW,
      state: 'partial',
      state_reason: 'missing_formula_inputs',
      missing_inputs: ['target_only_sov'],
      missing_reasons: ['target_only_sov'],
      evidence_counts: {
        analyzer_eligible_response_count: 4,
        analyzer_sov_numerator_target_mentions: 4,
        analyzer_sov_denominator_competitive_mentions: 4,
      },
      formula_status: 'partial',
      metric_formula_evidence: {
        coverage: { formula_status: 'ok' },
        sov: { formula_status: 'missing_required_inputs', reason_codes: ['target_only_sov'] },
      },
      kpi_cards: [
        {
          metric_key: 'mention_rate',
          label_zh: 'Mention',
          label_en: 'Mention Rate',
          value: 82.9,
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
          delta_30d_pct: null,
          direction: null,
        },
        {
          metric_key: 'sov',
          label_zh: 'SoV',
          label_en: 'Share of Voice',
          value: 100,
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'missing_required_inputs',
          delta_30d_pct: null,
          direction: null,
        },
      ],
      sov_30d: [{ date: '2026-05-12', value: 1 }],
    })
  })

  await page.route(`**/api/v1/projects/${FAKE_PROJECT_ID}/metrics**`, async route => {
    await json(route, {
      ...FAKE_METRICS,
      state: 'partial',
      state_reason: 'missing_formula_inputs',
      missing_inputs: ['target_only_sov'],
      formula_status: 'partial',
      metric_formula_evidence: {
        coverage: { formula_status: 'ok' },
        sov: { formula_status: 'missing_required_inputs', reason_codes: ['target_only_sov'] },
      },
      series: [
        {
          metric: 'mention_rate',
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'ok',
          points: [{ date: '2026-05-12', value: 82.9 }],
        },
        {
          metric: 'sov',
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'missing_required_inputs',
          missing_inputs: ['target_only_sov'],
          points: [{ date: '2026-05-12', value: 100 }],
        },
      ],
    })
  })

  await page.route(`**/api/v1/projects/${FAKE_PROJECT_ID}/competitors/metrics**`, async route => {
    await json(route, {
      ...FAKE_COMPETITOR_METRICS,
      state: 'partial',
      state_reason: 'missing_formula_inputs',
      formula_status: 'partial',
      metric_formula_evidence: {
        sov: { formula_status: 'missing_required_inputs', reason_codes: ['target_only_sov'] },
      },
      metric_definitions: {
        avg_sov: {
          metric_key: 'avg_sov',
          unit: 'percent',
          value_scale: 'percent',
          formula_status: 'missing_required_inputs',
        },
      },
    })
  })
}

test('issue #609 renders partial analyzer evidence without target-only SoV fallback', async ({ page }) => {
  await seedAuth(page)
  await installApiMocks(page)

  await page.goto('/brand/overview?brandId=42', { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {})

  await expect(page.getByText('Partial analytics')).toBeVisible()
  await expect(page.getByText('target_only_sov')).toBeVisible()
  await expect(page.getByText('82.9%').first()).toBeVisible()
  await expect(page.getByText('100.0%')).toHaveCount(0)

  await page.screenshot({
    path: test.info().outputPath('issue-609-partial-analyzer-overview.png'),
    fullPage: true,
  })
})
