// @vitest-environment node

import { describe, expect, it } from 'vitest';

import playwrightConfig from '../../playwright.config.ts';
import viteConfig from '../../vite.config.js';
import viteTsConfig from '../../vite.config.ts';

describe('Admin Vite dev server config', () => {
  it.each([
    ['vite.config.js', viteConfig],
    ['vite.config.ts', viteTsConfig],
  ])('serves local Admin from %s on the documented 5173 port', (_label, config) => {
    const server = config.server || {};
    const adminApiProxy = server.proxy?.['/admin/api'];

    expect(server.port).toBe(5173);
    expect(server.strictPort).toBe(true);
    expect(adminApiProxy).toBeTruthy();
    expect(adminApiProxy.target).toBe('http://localhost:4000');
    expect(adminApiProxy.rewrite('/admin/api/llm-extraction/candidates')).toBe(
      '/api/llm-extraction/candidates',
    );
  });

  it('uses the same documented local dev port for Playwright webServer checks', () => {
    expect(playwrightConfig.use?.baseURL).toBe('http://localhost:5173');
    expect(playwrightConfig.webServer?.url).toBe('http://localhost:5173');
  });
});
