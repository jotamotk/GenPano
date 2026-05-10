import { expect, type Page } from '@playwright/test';

type LoginResult = {
  ok: boolean;
  status: number;
  text: string;
};

const readRequiredEnv = (name: string): string => {
  const value = (process.env[name] || '').trim();
  if (!value) {
    throw new Error(`${name} is required for Admin staging E2E login.`);
  }
  return value;
};

const isAuthenticated = async (page: Page): Promise<boolean> => {
  return await page.evaluate(async () => {
    const response = await fetch('/api/admin/auth/session', {
      credentials: 'same-origin',
    });
    if (!response.ok) return false;
    const body = await response.json().catch(() => null);
    return !!(body && (body.authenticated === true || body.admin));
  });
};

const apiLogin = async (page: Page, email: string, password: string): Promise<LoginResult> => {
  return await page.evaluate(
    async ({ email, password }) => {
      const response = await fetch('/api/admin/auth/login', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      return {
        ok: response.ok,
        status: response.status,
        text: await response.text(),
      };
    },
    { email, password },
  );
};

export const ensureAdminSession = async (page: Page) => {
  await page.goto('/admin/planner-topics', { waitUntil: 'domcontentloaded' });
  if (!(await isAuthenticated(page))) {
    const result = await apiLogin(
      page,
      readRequiredEnv('ADMIN_E2E_EMAIL'),
      readRequiredEnv('ADMIN_E2E_PASSWORD'),
    );
    if (!result.ok) {
      throw new Error(
        `Admin API login failed with HTTP ${result.status}: ${result.text.slice(0, 500)}`,
      );
    }
    await page.goto('/admin/planner-topics', { waitUntil: 'domcontentloaded' });
  }
  await expect(page.locator('main')).toBeVisible({ timeout: 30_000 });
};
