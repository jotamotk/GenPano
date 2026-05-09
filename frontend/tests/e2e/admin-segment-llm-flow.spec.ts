import { expect, test, type Route } from '@playwright/test';

const brand = {
  id: 'brand-bestcoffer-security',
  name: 'bestCoffer',
  industry: '数据安全',
  target_market: 'global',
  description: 'Enterprise data security platform.',
};

const products = [
  {
    id: 'prod-vault',
    name: 'bestCoffer Vault',
    sku: 'BC-VLT',
    category: 'Data vault',
    description: 'Encrypted data vault for regulated teams.',
    status: 'active',
  },
  {
    id: 'prod-dlp',
    name: 'bestCoffer DLP',
    sku: 'BC-DLP',
    category: 'Data loss prevention',
    description: 'Policy and leakage monitoring for enterprise data.',
    status: 'active',
  },
];

const persistedSegment = {
  id: 'SEG-PERSISTED-001',
  code: 'SEG-PERSISTED-001',
  brand_id: brand.id,
  brand_name: brand.name,
  name: 'Persisted Product Security Segment',
  industry: brand.industry,
  status: 'active',
  weight: 0.2,
  age_range: '28-45',
  income: 'Enterprise budget owner',
  regions: 'Global',
  sampling_rate: '15%',
  note: 'Security buyers for selected bestCoffer products.',
  profile_count: 0,
  active_profile_count: 0,
};

test('Admin LLM Segment import keeps the persisted Segment id for the Profile flow', async ({ page }) => {
  let imported = false;
  const segmentGenerateBodies: unknown[] = [];
  const profileGenerateBodies: unknown[] = [];
  const badSegmentUrls: string[] = [];

  const fulfillJson = async (route: Route, body: unknown, status = 200) => {
    await route.fulfill({
      status,
      contentType: 'application/json',
      body: JSON.stringify(body),
    });
  };

  await page.route('**/api/admin/auth/session', async route => {
    await fulfillJson(route, {
      authenticated: true,
      admin: { id: 'admin-e2e', email: 'admin-e2e@example.test', name: 'Admin E2E' },
    });
  });

  await page.route('**/admin/api/**', async route => {
    const request = route.request();
    const url = new URL(request.url());
    const method = request.method();

    if (url.pathname.includes('SEG-DRAFT-001')) {
      badSegmentUrls.push(`${method} ${url.pathname}${url.search}`);
      await fulfillJson(route, {
        detail: {
          title: 'Resource not found',
          status: 404,
          code: 'not_found',
          detail: 'segment_not_found',
        },
      }, 404);
      return;
    }

    if (method === 'GET' && url.pathname.endsWith('/admin/brands')) {
      await fulfillJson(route, { brands: [brand] });
      return;
    }

    if (method === 'GET' && url.pathname.endsWith('/admin/products')) {
      expect(url.searchParams.get('brand_id')).toBe(brand.id);
      await fulfillJson(route, { products });
      return;
    }

    if (method === 'GET' && url.pathname.endsWith('/segments')) {
      await fulfillJson(route, {
        rows: imported ? [persistedSegment] : [],
        summary: { segment_count: imported ? 1 : 0, active_segment_count: imported ? 1 : 0, profile_count: 0 },
        pagination: { page: 1, per_page: 50, total: imported ? 1 : 0, total_pages: 1 },
      });
      return;
    }

    if (method === 'POST' && url.pathname.endsWith('/segments/generate')) {
      const body = request.postDataJSON();
      segmentGenerateBodies.push(body);
      expect(body.brand_id).toBe(brand.id);
      expect(body.product_ids).toEqual(['prod-vault', 'prod-dlp']);
      expect(body.products.map((product: { product_id: string }) => product.product_id)).toEqual(['prod-vault', 'prod-dlp']);
      await fulfillJson(route, {
        drafts: [{
          id: 'SEG-DRAFT-001',
          code: 'SEG-DRAFT-001',
          brand_id: brand.id,
          brand_name: brand.name,
          name: 'Draft Product Security Segment',
          industry: brand.industry,
          status: 'active',
          weight: 0.2,
          age_range: '28-45',
          income: 'Enterprise budget owner',
          regions: 'Global',
          sampling_rate: '15%',
          note: 'Draft that should not be reused after import.',
        }],
      });
      return;
    }

    if (method === 'POST' && url.pathname.endsWith('/segments/import')) {
      const body = request.postDataJSON();
      expect(body.rows[0].id).toBe('SEG-DRAFT-001');
      imported = true;
      await fulfillJson(route, { success: true, added: 1, updated: 0, skipped: 0, rows: [persistedSegment] });
      return;
    }

    if (method === 'GET' && url.pathname.endsWith('/segments/SEG-PERSISTED-001')) {
      await fulfillJson(route, { segment: persistedSegment });
      return;
    }

    if (method === 'GET' && url.pathname.endsWith('/segments/SEG-PERSISTED-001/profiles')) {
      await fulfillJson(route, {
        segment: persistedSegment,
        rows: [],
        pagination: { page: 1, per_page: 100, total: 0, total_pages: 1 },
      });
      return;
    }

    if (method === 'POST' && url.pathname.endsWith('/segments/SEG-PERSISTED-001/profiles/generate')) {
      const body = request.postDataJSON();
      profileGenerateBodies.push(body);
      expect(body.brand_id).toBe(brand.id);
      expect(body.product_ids).toEqual(['prod-vault']);
      expect(body).not.toHaveProperty('goal');
      expect(body).not.toHaveProperty('constraints');
      await fulfillJson(route, {
        drafts: [{
          id: 'P-001',
          code: 'P-001',
          brand_id: brand.id,
          brand_name: brand.name,
          name: 'Compliance Profile',
          demographic: 'Security lead at a regulated mid-market company',
          need: 'Needs encrypted storage and leakage monitoring for selected products.',
          weight: 1,
          status: 'active',
          persona_json: {},
        }],
      });
      return;
    }

    if (method === 'POST' && url.pathname.endsWith('/segments/SEG-PERSISTED-001/profiles/import')) {
      const body = request.postDataJSON();
      expect(body.rows[0].id).toBe('P-001');
      await fulfillJson(route, { success: true, added: 1, updated: 0, skipped: 0, rows: body.rows });
      return;
    }

    throw new Error(`Unhandled admin API request: ${method} ${url.pathname}${url.search}`);
  });

  await page.goto('/admin/planner-profiles');
  await expect(page.locator('a[href="/admin/planner-profiles"]')).toHaveClass(/nav-item-active/);

  await page.locator('button[title*="LLM"][title*="Segment"]').click();
  const segmentModal = page.locator('div[x-show="segmentLlmModalOpen"]');
  await expect(segmentModal).toBeVisible();

  await segmentModal.locator('select[x-model="segmentLlmForm.brandId"]').selectOption(brand.id);
  await expect(segmentModal.locator('select[x-model="segmentLlmForm.productIds"] option[value="prod-vault"]')).toBeVisible();
  await segmentModal.locator('select[x-model="segmentLlmForm.productIds"]').selectOption(['prod-vault', 'prod-dlp']);
  await segmentModal.locator('button[\\@click="generateBrandSegments()"]').click();
  await expect(segmentModal.getByText('Draft Product Security Segment')).toBeVisible();

  await segmentModal.locator('button[\\@click="applySegmentLlmDrafts()"]').click();
  await expect(segmentModal.getByText('Segment 已加入列表')).toBeVisible();
  await expect(page.getByText('SEG-PERSISTED-001').first()).toBeVisible();
  expect(badSegmentUrls).toEqual([]);

  await segmentModal.locator('button[\\@click="closeSegmentLlmPanel()"]').click();
  await page.getByText('Persisted Product Security Segment').first().click();
  await expect(page.locator('button[\\@click="openLlmPanel()"]')).toBeVisible();

  await page.locator('button[\\@click="openLlmPanel()"]').click();
  const profilePanel = page.locator('section[x-show="llmPanelOpen"]');
  await expect(profilePanel).toBeVisible();
  await expect(profilePanel.locator('textarea[x-model="llmForm.goal"]')).toHaveCount(0);
  await expect(profilePanel.locator('textarea[x-model="llmForm.notes"]')).toHaveCount(0);
  await expect(profilePanel.locator('select[x-model="llmForm.productIds"] option[value="prod-vault"]')).toBeVisible();
  await profilePanel.locator('select[x-model="llmForm.productIds"]').selectOption(['prod-vault']);
  await profilePanel.locator('button[\\@click="generateSegmentLlm()"]').click();
  await expect(profilePanel.getByText('Compliance Profile')).toBeVisible();

  await profilePanel.locator('button[\\@click="applyProfileLlmDrafts()"]').click();
  await expect(profilePanel.getByText('Profile 已加入列表')).toBeVisible();

  expect(segmentGenerateBodies).toHaveLength(1);
  expect(profileGenerateBodies).toHaveLength(1);
  expect(badSegmentUrls).toEqual([]);
});
