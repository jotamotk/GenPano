import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import type { Page, Route } from '@playwright/test';

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
const adminHtmlPath = path.resolve(here, '../../../backend/static/admin.html');
const alpineCdnPath = require.resolve('alpinejs/dist/cdn.min.js');
let adminHtmlCache: string | null = null;
let alpineCdnCache: string | null = null;

const readAdminHtml = async () => {
  if (adminHtmlCache === null) {
    adminHtmlCache = await readFile(adminHtmlPath, 'utf8');
  }
  return adminHtmlCache;
};

const readAlpineCdn = async () => {
  if (alpineCdnCache === null) {
    alpineCdnCache = await readFile(alpineCdnPath, 'utf8');
  }
  return alpineCdnCache;
};

const fulfillText = async (route: Route, body: string, contentType: string) => {
  await route.fulfill({
    status: 200,
    contentType,
    body,
  });
};

export const fulfillJson = async (route: Route, body: unknown, status = 200) => {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
};

export const normalizeAdminApiPath = (input: URL | string) => {
  const url = typeof input === 'string' ? new URL(input) : input;
  const pathname = url.pathname;
  if (pathname === '/admin/api') return '/api/admin';
  if (pathname.startsWith('/admin/api/')) {
    return `/api/admin${pathname.slice('/admin/api'.length)}`;
  }
  return pathname;
};

const installAdminDependencyRoutes = async (page: Page) => {
  await page.route('https://cdn.tailwindcss.com/**', async route => {
    await fulfillText(route, 'window.tailwind = window.tailwind || {};', 'application/javascript');
  });
  await page.route(/https:\/\/cdn\.jsdelivr\.net\/npm\/alpinejs@[^/]+\/dist\/cdn\.min\.js.*/, async route => {
    await fulfillText(route, await readAlpineCdn(), 'application/javascript');
  });
  await page.route(/https:\/\/cdn\.jsdelivr\.net\/npm\/chart\.js@[^/]+\/dist\/chart\.umd\.min\.js.*/, async route => {
    await fulfillText(
      route,
      'window.Chart = window.Chart || function Chart() {}; window.Chart.register = window.Chart.register || function() {};',
      'application/javascript',
    );
  });
  await page.route(/https:\/\/cdn\.jsdelivr\.net\/npm\/d3@[^/]+\/dist\/d3\.min\.js.*/, async route => {
    await fulfillText(
      route,
      [
        '(function(){',
        '  const noop = new Proxy(function(){ return noop; }, {',
        '    get(){ return noop; },',
        '    apply(){ return noop; },',
        '    construct(){ return noop; }',
        '  });',
        '  window.d3 = window.d3 || noop;',
        '})();',
      ].join('\n'),
      'application/javascript',
    );
  });
  await page.route(/https:\/\/cdn\.jsdelivr\.net\/npm\/lucide@[^/]+\/dist\/umd\/lucide\.min\.js.*/, async route => {
    await fulfillText(route, 'window.lucide = window.lucide || { icons: {}, createIcons() {} };', 'application/javascript');
  });
  await page.route(/https:\/\/fonts\.(?:googleapis|gstatic)\.com\/.*/, async route => {
    await fulfillText(route, '', 'text/css');
  });
};

export const installAdminDocumentRoute = async (page: Page) => {
  await installAdminDependencyRoutes(page);
  await page.route(/.*\/admin(?:\/.*)?$/, async route => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.startsWith('/admin/api')) {
      await route.fallback();
      return;
    }
    if (request.resourceType() !== 'document') {
      await route.fallback();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'text/html; charset=utf-8',
      body: await readAdminHtml(),
    });
  });
};

export const installAdminErrorGuards = (page: Page) => {
  const failures: string[] = [];

  page.on('console', message => {
    if (message.type() === 'error') {
      failures.push(`console error: ${message.text()}`);
    }
  });
  page.on('pageerror', error => {
    failures.push(`page error: ${error.message}`);
  });
  page.on('requestfailed', request => {
    const failure = request.failure();
    if (!failure || failure.errorText.includes('ERR_ABORTED')) return;
    const url = request.url();
    if (url.includes('/admin') || url.includes('/api/admin')) {
      failures.push(`request failed: ${request.method()} ${url} ${failure.errorText}`);
    }
  });
  page.on('response', response => {
    const status = response.status();
    if (status < 500) return;
    const url = response.url();
    if (url.includes('/admin') || url.includes('/api/admin')) {
      failures.push(`network ${status}: ${url}`);
    }
  });

  return {
    assertClean: async () => {
      if (failures.length > 0) {
        throw new Error(`Admin E2E captured browser/runtime failures:\n${failures.join('\n')}`);
      }
    },
  };
};
